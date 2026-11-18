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

"""Guarded CCAI Insights conversation ingestion and bulk analysis tools."""

from typing import Any, Dict, List, Literal, Optional

from cxidk.core import context
from cxidk.core import errors
from cxidk.core import serialize
from cxidk.ai.tools import models
from cxidk.ai.tools import registry
from cxidk.ai.tools import validation
from cxidk.wrapper import insights

_ALLOWED_BULK_ANNOTATORS = {
    insights.Annotators.INSIGHTS.value,
    insights.Annotators.SUMMARIZATION.value,
    insights.Annotators.TOPIC_MODEL.value,
}


def _resolve_medium(medium: str) -> insights.Mediums:
    """Resolves `'PHONE_CALL'` or `'CHAT'` to `insights.Mediums`."""
    normalized = medium.strip().upper()
    if normalized == "PHONE_CALL":
        return insights.Mediums.PHONE_CALL
    if normalized == "CHAT":
        return insights.Mediums.CHAT
    raise errors.InvalidArgumentError(
        f"Unsupported medium: {medium!r}",
        hint="Choose 'PHONE_CALL' or 'CHAT'.",
    )


def _validate_annotators(annotators: List[str]) -> List[str]:
    """Validates requested bulk analysis annotator names."""
    if not annotators:
        raise errors.InvalidArgumentError(
            "annotators must contain at least one annotator name.",
            hint=f"Supported annotators: {sorted(_ALLOWED_BULK_ANNOTATORS)}.",
        )
    cleaned: List[str] = []
    for raw in annotators:
        norm = raw.strip().upper()
        if norm not in _ALLOWED_BULK_ANNOTATORS:
            raise errors.InvalidArgumentError(
                f"Unsupported bulk annotator: {raw!r}",
                hint=f"Choose from: {sorted(_ALLOWED_BULK_ANNOTATORS)}.",
            )
        cleaned.append(norm)
    return cleaned


@registry.cx_tool(
    name="insights_ingest_conversation",
    title="Ingest Single Conversation into CCAI Insights",
    description=(
        "Uploads a single conversation from Google Cloud Storage (`transcript_uri` "
        "or `audio_uri`) into CCAI Insights and returns the resulting long-running "
        "operation handle. Pass `dry_run=True` to validate inputs without writing."
    ),
    safety=registry.Safety.WRITE,
    idempotent=False,
    open_world=True,
    toolset="writes",
    confirm=True,
    output_model=models.IngestionOutput,
    summary_fn=lambda args: (
        f"Ingest conversation into {args.get('project_id') or 'default-project'}/"
        f"{args.get('location') or 'default-location'} from "
        f"{args.get('transcript_uri') or args.get('audio_uri')!r}."
    ),
)
def insights_ingest_conversation(
    transcript_uri: Optional[str] = None,
    audio_uri: Optional[str] = None,
    conversation_id: Optional[str] = None,
    language_code: str = "en-US",
    medium: Literal["PHONE_CALL", "CHAT"] = "PHONE_CALL",
    labels: Optional[Dict[str, str]] = None,
    dlp_inspect_template: Optional[str] = None,
    dlp_deidentify_template: Optional[str] = None,
    dry_run: bool = False,
    project_id: Optional[str] = None,
    location: Optional[str] = None,
    *,
    cx: Optional[context.CxContext] = None,
) -> models.IngestionOutput:
    """Validates and ingests a single conversation from GCS into CCAI Insights.

    Args:
        transcript_uri: Optional `gs://` URI to an Insights JSON transcript.
        audio_uri: Optional `gs://` URI to an audio recording.
        conversation_id: Optional caller-assigned bare conversation ID.
        language_code: BCP-47 language tag (for example `'en-US'`).
        medium: Channel medium (`'PHONE_CALL'` or `'CHAT'`).
        labels: Optional key/value metadata labels attached to the conversation.
        dlp_inspect_template: Optional Cloud DLP inspect template resource name.
        dlp_deidentify_template: Optional Cloud DLP de-identify template name.
        dry_run: When True, validates arguments and returns a preview without writing.
        project_id: Optional destination GCP project ID override.
        location: Optional destination GCP location override.
        cx: Optional execution `CxContext`.

    Returns:
        `IngestionOutput` with `operation_name` (when executed) and `preview`.

    Raises:
        errors.InvalidArgumentError: If URIs, `conversation_id`, or `medium` is invalid.
        errors.CxidkError: If the Insights upload API call fails.
    """
    if bool(transcript_uri) == bool(audio_uri):
        raise errors.InvalidArgumentError(
            "Specify exactly one of `transcript_uri` or `audio_uri`.",
            hint="Pass `transcript_uri='gs://...'` for JSON transcripts or `audio_uri='gs://...'`.",
        )
    if transcript_uri:
        validation.validate_gcs_uri(transcript_uri, "transcript_uri")
    if audio_uri:
        validation.validate_gcs_uri(audio_uri, "audio_uri")
    clean_conv_id = (
        validation.validate_resource_id(conversation_id, "conversation_id")
        if conversation_id
        else None
    )
    medium_enum = _resolve_medium(medium)
    target = context.CxContext.resolve(cx, project_id, location)

    preview: Dict[str, Any] = {
        "source_uri": (transcript_uri or audio_uri or "").strip(),
        "conversation_id": clean_conv_id or "<server-generated>",
        "language_code": language_code,
        "medium": medium,
        "dlp_enabled": bool(dlp_inspect_template or dlp_deidentify_template),
    }
    if dry_run:
        return models.IngestionOutput(
            dry_run=True,
            project_id=target.project_id,
            location=target.location,
            preview=preview,
        )

    with errors.translate_google_api_error():
        ingestor = insights.Ingestion(
            parent=target.parent,
            audio_path=audio_uri.strip() if audio_uri else None,
            transcript_path=transcript_uri.strip() if transcript_uri else None,
            dlp_redact_template=dlp_inspect_template,
            dlp_deidentify_template=dlp_deidentify_template,
            auth=target.auth,
            config=target.config,
        )
        operation = ingestor.single(
            language_code=language_code,
            medium=medium_enum,
            conversation_id=clean_conv_id,
            labels=dict(labels) if labels else None,
        )
        op_dict = serialize.to_jsonable(operation)

    return models.IngestionOutput(
        dry_run=False,
        project_id=target.project_id,
        location=target.location,
        operation_name=str(op_dict.get("name", "")),
        preview=preview,
    )


@registry.cx_tool(
    name="insights_bulk_analyze",
    title="Bulk Analyze CCAI Insights Conversations",
    description=(
        "Launches a billable bulk analysis job across conversations matching "
        "`analysis_filter` (required non-empty filter). Always run with "
        "`dry_run=True` or call `insights_calculate_stats` first to verify "
        "matching conversation volume and estimated billing impact."
    ),
    safety=registry.Safety.WRITE,
    idempotent=False,
    open_world=True,
    toolset="writes",
    confirm=True,
    output_model=models.IngestionOutput,
    summary_fn=lambda args: (
        f"Bulk analyze {args.get('analysis_percentage', 100.0)}% of conversations "
        f"matching {args.get('analysis_filter')!r} with annotators "
        f"{args.get('annotators')}."
    ),
)
def insights_bulk_analyze(
    analysis_filter: str,
    annotators: List[str],
    analysis_percentage: float = 100.0,
    dry_run: bool = False,
    project_id: Optional[str] = None,
    location: Optional[str] = None,
    *,
    cx: Optional[context.CxContext] = None,
) -> models.IngestionOutput:
    """Runs or dry-runs a bulk conversation analysis job.

    Args:
        analysis_filter: Non-empty CCAI Insights filter bounding target conversations.
        annotators: Annotator selectors (`'INSIGHTS'`, `'SUMMARIZATION'`, `'TOPIC_MODEL'`).
        analysis_percentage: Percentage of matching conversations to analyze (`(0, 100]`).
        dry_run: When True, estimates matched conversation count without launching LRO.
        project_id: Optional target GCP project ID override.
        location: Optional target GCP location override.
        cx: Optional execution `CxContext`.

    Returns:
        `IngestionOutput` containing dry-run volume estimates or the LRO `operation_name`.

    Raises:
        errors.InvalidArgumentError: If `analysis_filter`, `annotators`, or
            `analysis_percentage` is invalid.
        errors.CxidkError: If the Insights API call fails.
    """
    clean_filter = validation.validate_filter(analysis_filter)
    if not clean_filter:
        raise errors.InvalidArgumentError(
            "analysis_filter must be non-empty for bulk analysis.",
            hint=(
                "Provide an Insights filter (for example `create_time > \"2025-01-01T00:00:00Z\"`) "
                "to bound the billable scope."
            ),
        )
    if analysis_percentage <= 0.0 or analysis_percentage > 100.0:
        raise errors.InvalidArgumentError(
            "analysis_percentage must be in (0.0, 100.0].",
            hint="Pass a percentage such as 10.0 or 100.0.",
        )
    clean_annotators = _validate_annotators(annotators)
    target = context.CxContext.resolve(cx, project_id, location)

    preview: Dict[str, Any] = {
        "analysis_filter": clean_filter,
        "annotators": clean_annotators,
        "analysis_percentage": analysis_percentage,
    }
    with errors.translate_google_api_error():
        if dry_run:
            stats_client = insights.Stats(
                project_id=target.project_id,
                location=target.location,
                auth=target.auth,
                config=target.config,
            )
            stats_data = serialize.to_jsonable(
                stats_client.calculate(filter_str=clean_filter)
            )
            matched = int(
                stats_data.get("conversation_count")
                or stats_data.get("conversationCount")
                or 0
            )
            preview["matched_conversations"] = matched
            preview["estimated_analyzed_conversations"] = int(
                round(matched * (analysis_percentage / 100.0))
            )
            return models.IngestionOutput(
                dry_run=True,
                project_id=target.project_id,
                location=target.location,
                preview=preview,
            )

        analyzer = insights.Analysis(
            parent=target.parent,
            auth=target.auth,
            config=target.config,
        )
        op = analyzer.bulk(
            annotators=clean_annotators,
            analysis_percentage=analysis_percentage,
            analysis_filter=clean_filter,
        )
        op_dict = serialize.to_jsonable(op)

    return models.IngestionOutput(
        dry_run=False,
        project_id=target.project_id,
        location=target.location,
        operation_name=str(op_dict.get("name", "")),
        preview=preview,
    )
