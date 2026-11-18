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

"""Transcript conversion, schema validation, and speaker role recognition tools."""

import json
import os
from typing import Any, Dict, List, Literal, Optional

import jsonschema

from cxidk.core import context
from cxidk.core import errors
from cxidk.ai.tools import models
from cxidk.ai.tools import registry
from cxidk.workflow import format as workflow_format
from cxidk.workflow import role_recognizer

_SCHEMA_FILES: Dict[str, str] = {
    "aws": "aws_schema.json",
    "genesys_cloud": "genesys_cloud_schema.json",
    "insights": "conversation.json",
}


def read_schema_text(schema_format: str) -> str:
    """Reads the raw UTF-8 JSON Schema text for a supported transcript format.

    Args:
        schema_format: Schema identifier (`'aws'`, `'genesys_cloud'`, or `'insights'`).

    Returns:
        UTF-8 JSON Schema document text.

    Raises:
        errors.InvalidArgumentError: If `schema_format` is unknown.
    """
    filename = _SCHEMA_FILES.get(schema_format)
    if not filename:
        raise errors.InvalidArgumentError(
            f"Unsupported schema_format: {schema_format!r}",
            hint=f"Choose from: {sorted(_SCHEMA_FILES)}.",
        )
    schema_path = os.path.join(
        os.path.dirname(workflow_format.__file__),
        "utils",
        "schemas",
        filename,
    )
    with open(schema_path, "r", encoding="utf-8") as handle:
        return handle.read()


def _load_schema(schema_format: str) -> Dict[str, Any]:
    """Parses one of the bundled transcript JSON schemas."""
    data: Dict[str, Any] = json.loads(read_schema_text(schema_format))
    return data


def _count_entries(schema_format: str, transcript: Dict[str, Any]) -> int:
    """Counts utterances in a vendor or Insights transcript dictionary."""
    if schema_format == "aws":
        items = transcript.get("Transcript")
        return len(items) if isinstance(items, list) else 0
    if schema_format == "genesys_cloud":
        transcripts = transcript.get("transcripts")
        if isinstance(transcripts, list) and transcripts:
            first = transcripts[0]
            if isinstance(first, dict) and isinstance(first.get("phrases"), list):
                return len(first["phrases"])
        return 0
    entries = transcript.get("entries")
    return len(entries) if isinstance(entries, list) else 0


@registry.cx_tool(
    name="transcript_convert",
    title="Convert Vendor Transcript to CCAI Insights Format",
    description=(
        "Deterministically converts an AWS Transcribe (`aws`) or Genesys Cloud "
        "(`genesys_cloud`) transcript JSON object into CCAI Insights "
        "`JsonConversationInput` (`{'entries': [...]}`). Runs locally with no "
        "external network calls."
    ),
    safety=registry.Safety.READ,
    idempotent=True,
    open_world=False,
    toolset="transcripts",
    confirm=False,
    output_model=models.TranscriptConvertOutput,
)
def transcript_convert(
    source_format: Literal["aws", "genesys_cloud"],
    transcript: Dict[str, Any],
    transcript_datetime: Optional[str] = None,
) -> models.TranscriptConvertOutput:
    """Converts a vendor transcript dictionary to Insights `JsonConversationInput`.

    Args:
        source_format: Vendor schema (`'aws'` or `'genesys_cloud'`).
        transcript: Raw vendor transcript dictionary.
        transcript_datetime: Optional base timestamp (`%Y/%m/%d %H:%M:%S`) for AWS.

    Returns:
        `TranscriptConvertOutput` with converted `entries` and `entry_count`.

    Raises:
        errors.InvalidArgumentError: If `source_format`, schema validation, or
            `transcript_datetime` is invalid.
    """
    converter = workflow_format.Insights()
    try:
        if source_format == "aws":
            converted = converter.from_aws(
                transcript=transcript,
                transcript_datetime_string=transcript_datetime,
            )
        elif source_format == "genesys_cloud":
            converted = converter.from_genesys_cloud(transcript=transcript)
        else:
            raise errors.InvalidArgumentError(
                f"Unsupported source_format: {source_format!r}",
                hint="Supported vendor formats: 'aws' and 'genesys_cloud'.",
            )
    except jsonschema.ValidationError as exc:
        raise errors.InvalidArgumentError(
            f"Input transcript failed {source_format} schema validation: {exc.message}",
            hint="Call `transcript_validate` to inspect all schema violations.",
        ) from exc
    except ValueError as exc:
        raise errors.InvalidArgumentError(
            f"Invalid transcript timestamp or payload: {exc}",
            hint="For `aws`, `transcript_datetime` must match `%Y/%m/%d %H:%M:%S`.",
        ) from exc

    entries = converted.get("entries", [])
    return models.TranscriptConvertOutput(
        source_format=source_format,
        entry_count=len(entries),
        transcript=converted,
    )


@registry.cx_tool(
    name="transcript_validate",
    title="Validate Transcript JSON Schema",
    description=(
        "Validates a transcript JSON object against the bundled `aws`, "
        "`genesys_cloud`, or `insights` (`JsonConversationInput`) JSON Schema "
        "and returns all detected validation errors."
    ),
    safety=registry.Safety.READ,
    idempotent=True,
    open_world=False,
    toolset="transcripts",
    confirm=False,
    output_model=models.TranscriptValidateOutput,
)
def transcript_validate(
    schema_format: Literal["aws", "genesys_cloud", "insights"],
    transcript: Dict[str, Any],
) -> models.TranscriptValidateOutput:
    """Validates a transcript dictionary against a target JSON schema.

    Args:
        schema_format: Target schema (`'aws'`, `'genesys_cloud'`, or `'insights'`).
        transcript: Transcript JSON dictionary to validate.

    Returns:
        `TranscriptValidateOutput` with `valid`, `entry_count`, and `errors`.
    """
    schema = _load_schema(schema_format)
    validator = jsonschema.Draft7Validator(schema)
    validation_errors: List[str] = []
    for err in sorted(validator.iter_errors(transcript), key=lambda e: list(e.path)):
        path = ".".join(str(part) for part in err.path) or "<root>"
        validation_errors.append(f"{path}: {err.message}")

    return models.TranscriptValidateOutput(
        schema_format=schema_format,
        valid=not validation_errors,
        entry_count=_count_entries(schema_format, transcript),
        errors=validation_errors,
    )


@registry.cx_tool(
    name="transcript_recognize_roles",
    title="Recognize Speaker Roles in Transcript",
    description=(
        "Classifies each utterance in a Speech-to-Text v2 response dictionary "
        "as `AGENT` (channelTag=2) or `CUSTOMER` (channelTag=1) using Gemini "
        "on Vertex AI, returning both predictions and an updated transcript."
    ),
    safety=registry.Safety.READ,
    idempotent=False,
    open_world=True,
    toolset="transcripts",
    confirm=False,
    output_model=models.RoleRecognitionOutput,
)
def transcript_recognize_roles(
    speech_v2_transcript: Dict[str, Any],
    model_name: str = "gemini-2.5-pro",
    project_id: Optional[str] = None,
    location: Optional[str] = None,
    *,
    cx: Optional[context.CxContext] = None,
) -> models.RoleRecognitionOutput:
    """Predicts AGENT/CUSTOMER roles for a Speech v2 transcript dictionary.

    Args:
        speech_v2_transcript: Speech-to-Text v2 response dictionary (`{'results': [...]}`).
        model_name: Vertex AI Gemini model identifier.
        project_id: Optional target GCP project ID override.
        location: Optional target GCP location override.
        cx: Optional execution `CxContext`.

    Returns:
        `RoleRecognitionOutput` with per-utterance predictions and updated transcript.

    Raises:
        errors.InvalidArgumentError: If `speech_v2_transcript` lacks `'results'`.
    """
    if not isinstance(speech_v2_transcript, dict) or "results" not in speech_v2_transcript:
        raise errors.InvalidArgumentError(
            "speech_v2_transcript must be a Speech v2 dictionary containing 'results'.",
            hint=(
                "Pass a dict shaped like "
                "`{'results': [{'alternatives': [{'transcript': '...'}]}]}`."
            ),
        )
    target = context.CxContext.resolve(cx, project_id, location)
    speech_fmt = workflow_format.Speech()
    rr_input = speech_fmt.v2_json_to_dict(speech_v2_transcript)

    recognizer = role_recognizer.RoleRecognizer(
        model_name=model_name,
        project_id=target.project_id,
        location=target.location,
        auth=target.auth,
        config=target.config,
    )
    predictions_doc = recognizer.predict_roles(rr_input)
    combined = recognizer.combine_dict(speech_v2_transcript, predictions_doc)
    predictions = list(predictions_doc.get("predictions", []))

    return models.RoleRecognitionOutput(
        model_name=model_name,
        predictions=predictions,
        transcript=combined,
    )
