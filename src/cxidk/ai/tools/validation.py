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

"""Strict allowlist input validators for AI-invoked tool parameters."""

import re
from typing import Literal, Optional, Tuple, cast

from cxidk.core import base
from cxidk.core import context
from cxidk.core import errors

TranscriptMode = Literal["full", "redacted", "omit"]
VALID_TRANSCRIPT_MODES: Tuple[TranscriptMode, ...] = (
    "full",
    "redacted",
    "omit",
)

_RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9._~-]{1,128}$")
_GCS_URI_RE = re.compile(
    r"^gs://([a-z0-9][a-z0-9._-]{1,61}[a-z0-9])/([^\r\n\x00]+)$"
)
_OPERATION_NAME_RE = re.compile(
    r"^projects/([a-z][a-z0-9-]{4,28}[a-z0-9])"
    r"/locations/([a-z0-9-]+)"
    r"/operations/([A-Za-z0-9._~-]{1,128})$"
)
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def validate_resource_id(value: str, field_name: str = "resource_id") -> str:
    """Validates a single GCP resource ID segment against path traversal.

    Args:
        value: Raw resource identifier supplied by the caller.
        field_name: Parameter name used in error messages.

    Returns:
        Trimmed, validated resource ID segment.

    Raises:
        errors.InvalidArgumentError: If `value` is empty, contains traversal
            sequences, or includes disallowed characters.
    """
    if not isinstance(value, str) or not value.strip():
        raise errors.InvalidArgumentError(
            f"{field_name} must be a non-empty string.",
            hint=f"Pass only the bare {field_name} (without slashes).",
        )
    cleaned = value.strip()
    if ".." in cleaned or not _RESOURCE_ID_RE.match(cleaned):
        raise errors.InvalidArgumentError(
            f"Invalid {field_name}: {value!r}",
            hint=(
                f"{field_name} may only contain letters, digits, `.`, `_`, `~`, "
                "or `-` (max 128 chars, no slashes or `..`)."
            ),
        )
    return cleaned


def validate_gcs_uri(
    uri: str, field_name: str = "gcs_uri"
) -> Tuple[str, str]:
    """Validates a `gs://bucket/object` URI and rejects traversal segments.

    Args:
        uri: Cloud Storage URI (`gs://<bucket>/<object>`).
        field_name: Parameter name used in error messages.

    Returns:
        A `(bucket_name, object_path)` tuple.

    Raises:
        errors.InvalidArgumentError: If `uri` is not a valid `gs://` object URI.
    """
    if not isinstance(uri, str) or not uri.strip():
        raise errors.InvalidArgumentError(
            f"{field_name} must be a non-empty gs:// URI.",
            hint="Use format `gs://<bucket>/<object-path>`.",
        )
    cleaned = uri.strip()
    match = _GCS_URI_RE.match(cleaned)
    if not match:
        raise errors.InvalidArgumentError(
            f"Invalid Cloud Storage URI for {field_name}: {uri!r}",
            hint="URI must start with `gs://` followed by a valid bucket and object path.",
        )
    bucket, obj_path = match.group(1), match.group(2)
    segments = obj_path.split("/")
    if any(seg in ("", ".", "..") for seg in segments):
        raise errors.InvalidArgumentError(
            f"Invalid object path in {field_name}: {uri!r}",
            hint="Object path must not contain empty, `.`, or `..` segments.",
        )
    return bucket, obj_path


def validate_operation_name(operation_name: str) -> Tuple[str, str, str]:
    """Validates a full CCAI Insights operation name and extracts its components.

    Args:
        operation_name: Full `projects/{project}/locations/{location}/operations/{id}` path.

    Returns:
        A `(project_id, location, operation_id)` tuple.

    Raises:
        errors.InvalidArgumentError: If `operation_name` is malformed.
    """
    if not isinstance(operation_name, str) or not operation_name.strip():
        raise errors.InvalidArgumentError(
            "operation_name must be a non-empty string.",
            hint="Expected `projects/{project}/locations/{location}/operations/{id}`.",
        )
    cleaned = operation_name.strip()
    match = _OPERATION_NAME_RE.match(cleaned)
    if not match:
        raise errors.InvalidArgumentError(
            f"Invalid operation_name format: {operation_name!r}",
            hint="Expected `projects/{project}/locations/{location}/operations/{id}`.",
        )
    proj = context.validate_project_id(match.group(1))
    loc = base.Config.validate_location(match.group(2))
    op_id = validate_resource_id(match.group(3), "operation_id")
    return proj, loc, op_id


def validate_filter(
    filter_str: Optional[str], max_length: int = 2048
) -> str:
    """Validates an Insights filter string length and character safety.

    Args:
        filter_str: Optional CCAI Insights filter expression.
        max_length: Maximum allowed character count.

    Returns:
        Sanitized filter string (empty string when `filter_str` is empty/None).

    Raises:
        errors.InvalidArgumentError: If `filter_str` exceeds `max_length` or
            contains ASCII control characters.
    """
    if not filter_str:
        return ""
    if len(filter_str) > max_length:
        raise errors.InvalidArgumentError(
            f"Filter exceeds maximum length of {max_length} characters.",
            hint="Narrow or simplify the Insights filter expression.",
        )
    if _CONTROL_CHARS_RE.search(filter_str):
        raise errors.InvalidArgumentError(
            "Filter contains disallowed control characters.",
            hint="Use printable Insights filter expressions only.",
        )
    return filter_str.strip()


def validate_page_token(
    page_token: Optional[str], max_length: int = 2048
) -> str:
    """Validates pagination cursor length and character safety.

    Args:
        page_token: Optional pagination token from a prior response.
        max_length: Maximum allowed character count.

    Returns:
        Sanitized pagination token (empty string when `page_token` is empty/None).

    Raises:
        errors.InvalidArgumentError: If `page_token` is oversized or contains
            control characters.
    """
    if not page_token:
        return ""
    if len(page_token) > max_length or _CONTROL_CHARS_RE.search(page_token):
        raise errors.InvalidArgumentError(
            "Invalid page_token.",
            hint="Pass the exact `next_page_token` returned by the previous page.",
        )
    return page_token.strip()


def validate_page_size(
    page_size: int,
    *,
    minimum: int = 1,
    maximum: int = 100,
) -> int:
    """Validates pagination `page_size` bounds.

    Args:
        page_size: Requested page size.
        minimum: Minimum allowed page size.
        maximum: Maximum allowed page size.

    Returns:
        Validated `page_size` integer.

    Raises:
        errors.InvalidArgumentError: If `page_size` is outside `[minimum, maximum]`.
    """
    if page_size < minimum or page_size > maximum:
        raise errors.InvalidArgumentError(
            f"page_size must be between {minimum} and {maximum}.",
            hint=f"Use page_size=25 for exploration or up to {maximum} per page.",
        )
    return page_size


def validate_transcript_mode(
    mode: str,
    field_name: str = "transcript_mode",
) -> TranscriptMode:
    """Validates a transcript privacy mode string.

    Args:
        mode: Candidate transcript mode (`'full'`, `'redacted'`, or `'omit'`).
        field_name: Field or env variable name used in error messages.

    Returns:
        Validated `TranscriptMode` literal.

    Raises:
        errors.InvalidArgumentError: If `mode` is not a supported transcript mode.
    """
    cleaned = mode.strip().lower()
    if cleaned not in VALID_TRANSCRIPT_MODES:
        raise errors.InvalidArgumentError(
            f"Unsupported {field_name}: {mode!r}",
            hint="Choose 'full', 'redacted', or 'omit'.",
        )
    return cast(TranscriptMode, cleaned)
