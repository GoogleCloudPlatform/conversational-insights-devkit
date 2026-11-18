# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Read-only CCAI Insights conversation and analysis tools."""

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from cxidk.core import context
from cxidk.core import errors
from cxidk.core import serialize
from cxidk.ai.tools import models
from cxidk.ai.tools import registry
from cxidk.ai.tools import validation
from cxidk.wrapper import insights
from cxidk.wrapper import sensitive_data_protection

TranscriptMode = validation.TranscriptMode

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_PHONE_RE = re.compile(
    r"(?<!\w)(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]\d{3}[-.\s]\d{4}(?!\w)"
)


def resolve_target_context(
    cx: Optional[context.CxContext],
    project_id: Optional[str],
    location: Optional[str],
) -> context.CxContext:
    """Resolves a `CxContext` from an injected context or environment defaults.

    Args:
        cx: Optional pre-configured `CxContext`.
        project_id: Optional GCP project ID override.
        location: Optional GCP location override.

    Returns:
        Validated `CxContext` targeting the resolved project and location.
    """
    return context.CxContext.resolve(
        cx, project_id=project_id, location=location
    )


def mask_common_pii(text: str) -> str:
    """Applies defense-in-depth regex masking for common PII patterns.

    Args:
        text: Unredacted transcript or summary text.

    Returns:
        Text with email addresses, SSNs, card numbers, and phone numbers masked.
    """
    masked = _EMAIL_RE.sub("[EMAIL_ADDRESS]", text)
    masked = _SSN_RE.sub("[US_SOCIAL_SECURITY_NUMBER]", masked)
    masked = _CARD_RE.sub("[CREDIT_CARD_NUMBER]", masked)
    return _PHONE_RE.sub("[PHONE_NUMBER]", masked)


def _redact_texts_with_dlp(
    texts: List[str],
    target: context.CxContext,
    deidentify_template: Optional[str],
    inspect_template: Optional[str],
) -> List[str]:
    """Redacts text strings via Cloud DLP when a template is configured, plus regex masking."""
    eff_deidentify = deidentify_template or os.environ.get(
        "CXIDK_DLP_DEIDENTIFY_TEMPLATE"
    )
    eff_inspect = inspect_template or os.environ.get(
        "CXIDK_DLP_INSPECT_TEMPLATE"
    )
    output = list(texts)
    if eff_deidentify and texts:
        dlp_client = sensitive_data_protection.DLP(
            project_id=target.project_id,
            location=target.location,
            auth=target.auth,
            config=target.config,
        )
        table_payload = {
            "transcript_header": [
                {"name": f"t_{idx}"} for idx in range(len(texts))
            ],
            "transcript": [{"string_value": val} for val in texts],
        }
        dlp_resp = dlp_client.redact(
            data=table_payload,
            inspect_template=eff_inspect,
            deidentify_template=eff_deidentify,
        )
        rows = getattr(dlp_resp.item.table, "rows", [])
        if rows:
            output = [str(cell.string_value) for cell in rows[0].values]
    return [mask_common_pii(item) for item in output]


def _extract_segments(transcript_obj: Dict[str, Any]) -> Tuple[str, List[Any]]:
    """Returns `(segments_key, segments_list)` supporting snake_case and camelCase."""
    if "transcript_segments" in transcript_obj:
        return "transcript_segments", list(
            transcript_obj.get("transcript_segments") or []
        )
    return "transcriptSegments", list(
        transcript_obj.get("transcriptSegments") or []
    )


def _apply_transcript_mode(
    conv_data: Dict[str, Any],
    *,
    mode: TranscriptMode,
    max_turns: int,
    target: context.CxContext,
    dlp_deidentify_template: Optional[str],
    dlp_inspect_template: Optional[str],
) -> Tuple[Dict[str, Any], bool]:
    """Applies turn truncation and transcript redaction/omission policies."""
    transcript_obj = conv_data.get("transcript")
    if not isinstance(transcript_obj, dict):
        return conv_data, False

    seg_key, segments = _extract_segments(transcript_obj)
    truncated = len(segments) > max_turns
    if truncated:
        segments = segments[:max_turns]

    if mode == "omit":
        conv_data["transcript"] = {
            "omitted": True,
            "segment_count": len(segments),
        }
        return conv_data, truncated

    if mode == "redacted":
        raw_texts = [
            str(seg.get("text", "")) if isinstance(seg, dict) else ""
            for seg in segments
        ]
        summary_refs: List[Dict[str, Any]] = [
            obj
            for sum_key in ("latest_summary", "latestSummary")
            if isinstance((obj := conv_data.get(sum_key)), dict)
            and obj.get("text")
        ]
        combined_inputs = raw_texts + [str(obj["text"]) for obj in summary_refs]
        redacted_all = _redact_texts_with_dlp(
            combined_inputs,
            target=target,
            deidentify_template=dlp_deidentify_template,
            inspect_template=dlp_inspect_template,
        )
        for seg, clean_text in zip(segments, redacted_all[: len(raw_texts)]):
            if isinstance(seg, dict):
                seg["text"] = clean_text
        for summary_obj, clean_summary in zip(
            summary_refs, redacted_all[len(raw_texts) :]
        ):
            summary_obj["text"] = clean_summary

    transcript_obj[seg_key] = segments
    conv_data["transcript"] = transcript_obj
    return conv_data, truncated


@registry.cx_tool(
    name="insights_list_conversations",
    title="List CCAI Insights Conversations",
    description=(
        "Lists a single page of CCAI Insights conversations using metadata-only "
        "BASIC view by default to conserve context window tokens and minimize PII "
        "exposure. Use `filter` with Insights filter expressions (for example "
        "`medium=\"CHAT\"` or `latest_analysis:*`) and pass `page_token` to paginate."
    ),
    safety=registry.Safety.READ,
    idempotent=True,
    open_world=True,
    toolset="core",
    confirm=False,
    output_model=models.ConversationListOutput,
)
def insights_list_conversations(
    filter: str = "",  # pylint: disable=redefined-builtin
    page_size: int = 25,
    page_token: str = "",
    order_by: str = "",
    project_id: Optional[str] = None,
    location: Optional[str] = None,
    *,
    cx: Optional[context.CxContext] = None,
) -> models.ConversationListOutput:
    """Lists conversations in BASIC view with explicit pagination.

    Args:
        filter: Optional CCAI Insights filter expression.
        page_size: Number of conversations per page (`1..100`).
        page_token: Optional pagination cursor from a previous call.
        order_by: Optional sort order expression.
        project_id: Optional target GCP project ID override.
        location: Optional target GCP location override.
        cx: Optional execution `CxContext`.

    Returns:
        `ConversationListOutput` with serialized metadata items and `next_page_token`.

    Raises:
        errors.InvalidArgumentError: If `page_size` or filter arguments are invalid.
        errors.CxidkError: If the Insights API request fails.
    """
    validation.validate_page_size(page_size)
    clean_filter = validation.validate_filter(filter)
    clean_token = validation.validate_page_token(page_token)
    clean_order = validation.validate_filter(order_by, max_length=256)
    target = context.CxContext.resolve(cx, project_id, location)

    with errors.translate_google_api_error():
        client = insights.Conversations(
            project_id=target.project_id,
            location=target.location,
            auth=target.auth,
            config=target.config,
        )
        items, next_token = client.list(
            filter_str=clean_filter or None,
            page_size=page_size,
            page_token=clean_token or None,
            order_by=clean_order or None,
            view="BASIC",
        )

    serialized = [serialize.to_jsonable(item) for item in items]
    return models.ConversationListOutput(
        project_id=target.project_id,
        location=target.location,
        conversations=serialized,
        count=len(serialized),
        next_page_token=next_token,
    )


@registry.cx_tool(
    name="insights_get_conversation",
    title="Get CCAI Insights Conversation",
    description=(
        "Fetches a single CCAI Insights conversation by bare `conversation_id`, "
        "including analysis summary, quality metadata, and turn-by-turn transcript "
        "subject to `transcript_mode` ('full', 'redacted', or 'omit') and `max_turns`."
    ),
    safety=registry.Safety.READ,
    idempotent=True,
    open_world=True,
    toolset="core",
    confirm=False,
    output_model=models.ConversationDetailOutput,
)
def insights_get_conversation(
    conversation_id: str,
    transcript_mode: Optional[TranscriptMode] = None,
    max_turns: int = 200,
    dlp_deidentify_template: Optional[str] = None,
    dlp_inspect_template: Optional[str] = None,
    project_id: Optional[str] = None,
    location: Optional[str] = None,
    *,
    cx: Optional[context.CxContext] = None,
    default_transcript_mode: TranscriptMode = "full",
) -> models.ConversationDetailOutput:
    """Fetches a single conversation with transcript privacy and size controls.

    Args:
        conversation_id: Bare CCAI Insights conversation ID.
        transcript_mode: Transcript handling mode (`'full'`, `'redacted'`, or `'omit'`).
        max_turns: Maximum utterance turns returned (`1..2000`).
        dlp_deidentify_template: Optional Cloud DLP de-identify template name.
        dlp_inspect_template: Optional Cloud DLP inspect template name.
        project_id: Optional target GCP project ID override.
        location: Optional target GCP location override.
        cx: Optional execution `CxContext`.
        default_transcript_mode: Server-level default when `transcript_mode` is None.

    Returns:
        `ConversationDetailOutput` containing the serialized conversation payload.

    Raises:
        errors.InvalidArgumentError: If `conversation_id`, `max_turns`, or
            `transcript_mode` is invalid.
        errors.CxidkError: If the Insights or Cloud DLP API call fails.
    """
    clean_id = validation.validate_resource_id(conversation_id, "conversation_id")
    if max_turns < 1 or max_turns > 2000:
        raise errors.InvalidArgumentError(
            "max_turns must be between 1 and 2000.",
            hint="Use max_turns=200 for standard conversations.",
        )
    effective_mode = validation.validate_transcript_mode(
        transcript_mode or default_transcript_mode
    )
    target = context.CxContext.resolve(cx, project_id, location)
    view_name = "BASIC" if effective_mode == "omit" else "FULL"

    with errors.translate_google_api_error():
        client = insights.Conversations(
            project_id=target.project_id,
            location=target.location,
            auth=target.auth,
            config=target.config,
        )
        convo = client.get(conversation_id=clean_id, view=view_name)
        conv_dict = serialize.to_jsonable(convo)
        conv_dict, truncated = _apply_transcript_mode(
            conv_dict,
            mode=effective_mode,
            max_turns=max_turns,
            target=target,
            dlp_deidentify_template=dlp_deidentify_template,
            dlp_inspect_template=dlp_inspect_template,
        )

    return models.ConversationDetailOutput(
        project_id=target.project_id,
        location=target.location,
        transcript_mode=effective_mode,
        truncated_turns=truncated,
        conversation=conv_dict,
    )


@registry.cx_tool(
    name="insights_list_analyses",
    title="List Conversation Analyses",
    description=(
        "Lists completed CCAI Insights analyses for a single `conversation_id`, "
        "including QA scorecard answers, detected issues, entities, sentiment, "
        "and summarization annotations."
    ),
    safety=registry.Safety.READ,
    idempotent=True,
    open_world=True,
    toolset="core",
    confirm=False,
    output_model=models.AnalysisListOutput,
)
def insights_list_analyses(
    conversation_id: str,
    page_size: int = 25,
    page_token: str = "",
    filter: str = "",  # pylint: disable=redefined-builtin
    project_id: Optional[str] = None,
    location: Optional[str] = None,
    *,
    cx: Optional[context.CxContext] = None,
) -> models.AnalysisListOutput:
    """Lists analyses belonging to a conversation.

    Args:
        conversation_id: Bare CCAI Insights conversation ID.
        page_size: Maximum analyses per page (`1..100`).
        page_token: Optional pagination cursor from a previous call.
        filter: Optional CCAI Insights analysis filter expression.
        project_id: Optional target GCP project ID override.
        location: Optional target GCP location override.
        cx: Optional execution `CxContext`.

    Returns:
        `AnalysisListOutput` containing serialized `Analysis` items.

    Raises:
        errors.InvalidArgumentError: If `conversation_id` or `page_size` is invalid.
        errors.CxidkError: If the Insights API call fails.
    """
    clean_id = validation.validate_resource_id(conversation_id, "conversation_id")
    validation.validate_page_size(page_size)
    clean_token = validation.validate_page_token(page_token)
    clean_filter = validation.validate_filter(filter)
    target = context.CxContext.resolve(cx, project_id, location)

    with errors.translate_google_api_error():
        client = insights.Analyses(
            project_id=target.project_id,
            location=target.location,
            auth=target.auth,
            config=target.config,
        )
        items, next_token = client.list(
            conversation_id=clean_id,
            page_size=page_size,
            page_token=clean_token or None,
            filter_str=clean_filter or None,
        )

    serialized = [serialize.to_jsonable(item) for item in items]
    return models.AnalysisListOutput(
        conversation_id=clean_id,
        analyses=serialized,
        count=len(serialized),
        next_page_token=next_token,
    )
