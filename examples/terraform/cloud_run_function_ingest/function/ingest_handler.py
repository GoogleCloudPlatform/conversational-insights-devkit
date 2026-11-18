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

"""Cloud Run Function (2nd Gen) Eventarc handler for CCAI Insights ingestion.

Triggered when a JSON transcript lands in a Cloud Storage bucket:
- `raw/aws/<id>.json`      -> Converted via `cxidk.workflow.format.Insights.from_aws`
                              into `staging/<id>.json` and ingested.
- `raw/genesys/<id>.json`  -> Converted via `Insights.from_genesys_cloud`
                              into `staging/<id>.json` and ingested.
- `raw/insights/<id>.json` -> Ingested directly into CCAI Insights.

Objects written outside `raw/` (including `staging/`) are ignored so staging
writes never re-trigger recursive ingestion loops.
"""

import json
import logging
import os
import posixpath
import re
from typing import Any, Dict, Optional, Tuple

from cloudevents.http import CloudEvent
import functions_framework

from cxidk.core import context
from cxidk.core import serialize
from cxidk.workflow import format as cx_format
from cxidk.wrapper import insights
from cxidk.wrapper import storage

logger = logging.getLogger(__name__)

_SAFE_CONVERSATION_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$")
_SUPPORTED_PREFIXES = ("raw/aws/", "raw/genesys/", "raw/insights/")


def _parse_object_route(object_name: str) -> Optional[Tuple[str, str]]:
    """Extracts `(vendor, stem)` for supported `raw/<vendor>/<id>.json` keys.

    Args:
        object_name: Cloud Storage object key from the CloudEvent payload.

    Returns:
        `(vendor, conversation_stem)` tuple, or `None` when the object should
        be skipped (for example `staging/` writes or non-JSON blobs).

    Raises:
        ValueError: If the filename stem is unsafe for a conversation ID.
    """
    normalized = posixpath.normpath(object_name.lstrip("/"))
    if normalized.startswith("..") or not normalized.endswith(".json"):
        return None
    if not normalized.startswith(_SUPPORTED_PREFIXES):
        return None

    parts = normalized.split("/")
    if len(parts) != 3:
        return None
    vendor = parts[1]
    stem = parts[2][:-5]
    if not _SAFE_CONVERSATION_ID_RE.match(stem):
        raise ValueError(
            f"Conversation filename stem {stem!r} must match "
            f"{_SAFE_CONVERSATION_ID_RE.pattern}."
        )
    return vendor, stem


def _stage_if_vendor_format(
    gcs_client: storage.Gcs,
    bucket_name: str,
    object_name: str,
    vendor: str,
    stem: str,
) -> str:
    """Converts vendor transcripts to `staging/<stem>.json` when needed.

    Args:
        gcs_client: Initialized `cxidk.wrapper.storage.Gcs` client.
        bucket_name: Source/staging GCS bucket name.
        object_name: Source GCS object key.
        vendor: One of `'aws'`, `'genesys'`, or `'insights'`.
        stem: Validated conversation ID stem.

    Returns:
        `gs://` URI ready for CCAI Insights ingestion.
    """
    if vendor == "insights":
        return f"gs://{bucket_name}/{object_name}"

    raw_payload = gcs_client.download_blob(
        file_name=object_name,
        content_type=storage.ContentType.JSON,
    )
    transcript_dict = json.loads(
        raw_payload.decode("utf-8")
        if isinstance(raw_payload, bytes)
        else raw_payload
    )
    converter = cx_format.Insights()
    converted = (
        converter.from_aws(transcript_dict)
        if vendor == "aws"
        else converter.from_genesys_cloud(transcript_dict)
    )

    staging_key = f"staging/{stem}.json"
    gcs_client.upload_blob(
        file_name=staging_key,
        data=json.dumps(converted),
        content_type=storage.ContentType.JSON,
    )
    return f"gs://{bucket_name}/{staging_key}"


def process_gcs_event(cloud_event: CloudEvent) -> Dict[str, Any]:
    """Processes a GCS finalized `CloudEvent` and starts Insights ingestion.

    Args:
        cloud_event: Eventarc `CloudEvent` carrying `bucket` and `name`.

    Returns:
        Structured dictionary describing either the skipped object or the
        started non-blocking CCAI Insights `Operation`.
    """
    data = cloud_event.data or {}
    bucket_name = str(data.get("bucket", "")).strip()
    object_name = str(data.get("name", "")).strip()
    if not bucket_name or not object_name:
        raise ValueError("CloudEvent data must include 'bucket' and 'name'.")

    route = _parse_object_route(object_name)
    if route is None:
        logger.info("Skipping non-matching GCS object: %s", object_name)
        return {"status": "skipped", "object": object_name}

    vendor, conversation_id = route
    ctx = context.CxContext.from_env()
    gcs_client = storage.Gcs(
        bucket_name=bucket_name,
        project_id=ctx.project_id,
        auth=ctx.auth,
        config=ctx.config,
    )
    transcript_uri = _stage_if_vendor_format(
        gcs_client=gcs_client,
        bucket_name=bucket_name,
        object_name=object_name,
        vendor=vendor,
        stem=conversation_id,
    )

    ingestor = insights.Ingestion(
        parent=ctx.parent,
        transcript_path=transcript_uri,
        dlp_redact_template=os.environ.get("CXIDK_DLP_REDACT_TEMPLATE") or None,
        dlp_deidentify_template=(
            os.environ.get("CXIDK_DLP_DEIDENTIFY_TEMPLATE") or None
        ),
        auth=ctx.auth,
        config=ctx.config,
    )
    language_code = os.environ.get("CXIDK_LANGUAGE_CODE", "en-US")
    operation = ingestor.single(
        language_code=language_code,
        conversation_id=conversation_id,
        labels={"source_vendor": vendor},
    )
    serialized_op = serialize.to_jsonable(operation)
    logger.info(
        "Started CCAI Insights ingestion for %s (%s): %s",
        conversation_id,
        transcript_uri,
        serialized_op,
    )
    return {
        "status": "ingesting",
        "conversation_id": conversation_id,
        "transcript_uri": transcript_uri,
        "operation": serialized_op,
    }


@functions_framework.cloud_event
def ingest_gcs_transcript(cloud_event: CloudEvent) -> None:
    """Cloud Run Functions 2nd-Gen Eventarc entrypoint."""
    process_gcs_event(cloud_event)
