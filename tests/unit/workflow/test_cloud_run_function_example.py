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

"""Unit tests for the Cloud Run Function (2nd Gen) Terraform example handler."""

import importlib.util
import json
from pathlib import Path
from typing import Any
from unittest import mock

from cloudevents.http import CloudEvent
import pytest

_HANDLER_PATH = (
    Path(__file__).resolve().parents[3]
    / "examples"
    / "terraform"
    / "cloud_run_function_ingest"
    / "function"
    / "ingest_handler.py"
)


def _load_handler_module() -> Any:
    """Loads `ingest_handler.py` from `examples/terraform/`."""
    spec = importlib.util.spec_from_file_location("ingest_handler", _HANDLER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_gcs_event(bucket: str, name: str) -> CloudEvent:
    """Builds a minimal GCS `object.v1.finalized` CloudEvent."""
    attributes = {
        "type": "google.cloud.storage.object.v1.finalized",
        "source": f"//storage.googleapis.com/projects/_/buckets/{bucket}",
    }
    return CloudEvent(attributes, {"bucket": bucket, "name": name})


def test_skips_staging_and_non_json_objects() -> None:
    """Staging writes and non-JSON blobs are skipped to prevent trigger loops."""
    handler = _load_handler_module()

    staging_res = handler.process_gcs_event(
        _make_gcs_event("my-bucket", "staging/call-101.json")
    )
    assert staging_res == {"status": "skipped", "object": "staging/call-101.json"}

    audio_res = handler.process_gcs_event(
        _make_gcs_event("my-bucket", "raw/aws/call-101.wav")
    )
    assert audio_res == {"status": "skipped", "object": "raw/aws/call-101.wav"}


def test_rejects_unsafe_conversation_stem() -> None:
    """Conversation filename stems with unsafe characters raise ValueError."""
    handler = _load_handler_module()
    with pytest.raises(ValueError, match="Conversation filename stem"):
        handler.ingest_gcs_transcript(
            _make_gcs_event("my-bucket", "raw/aws/bad$id!.json")
        )


def test_converts_aws_transcript_and_starts_ingestion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AWS transcripts are converted to staging/ and ingested into Insights."""
    handler = _load_handler_module()
    monkeypatch.setenv("CXIDK_PROJECT_ID", "demo-proj")
    monkeypatch.setenv("CXIDK_LOCATION", "us-central1")

    aws_payload = {
        "Channel": "VOICE",
        "Transcript": [
            {
                "BeginOffsetMillis": 0,
                "Content": "Hello, how can I help?",
                "Id": "turn-1",
                "ParticipantId": "AGENT",
            }
        ],
    }

    fake_ctx = mock.MagicMock()
    fake_ctx.project_id = "demo-proj"
    fake_ctx.parent = "projects/demo-proj/locations/us-central1"
    fake_ctx.auth = mock.MagicMock()
    fake_ctx.config = mock.MagicMock()

    fake_gcs = mock.MagicMock()
    fake_gcs.download_blob.return_value = json.dumps(aws_payload)

    fake_op = mock.MagicMock()
    fake_op.name = "projects/demo-proj/locations/us-central1/operations/op-1"
    fake_op.done = False
    fake_ingestor = mock.MagicMock()
    fake_ingestor.single.return_value = fake_op

    monkeypatch.setattr(handler.context.CxContext, "from_env", lambda: fake_ctx)
    monkeypatch.setattr(handler.storage, "Gcs", lambda **_kw: fake_gcs)
    monkeypatch.setattr(
        handler.insights, "Ingestion", mock.MagicMock(return_value=fake_ingestor)
    )

    result = handler.process_gcs_event(
        _make_gcs_event("landing-bkt", "raw/aws/call-1001.json")
    )

    assert result["status"] == "ingesting"
    assert result["conversation_id"] == "call-1001"
    assert result["transcript_uri"] == "gs://landing-bkt/staging/call-1001.json"
    fake_gcs.upload_blob.assert_called_once()
    fake_ingestor.single.assert_called_once_with(
        language_code="en-US",
        conversation_id="call-1001",
        labels={"source_vendor": "aws"},
    )


def test_ingests_native_insights_transcript_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Native Insights transcripts skip staging conversion and ingest directly."""
    handler = _load_handler_module()
    fake_ctx = mock.MagicMock()
    fake_ctx.project_id = "demo-proj"
    fake_ctx.parent = "projects/demo-proj/locations/us-central1"
    fake_ctx.auth = mock.MagicMock()
    fake_ctx.config = mock.MagicMock()

    fake_gcs = mock.MagicMock()
    fake_ingestor = mock.MagicMock()
    fake_ingestor.single.return_value = {"name": "op-direct", "done": False}

    monkeypatch.setattr(handler.context.CxContext, "from_env", lambda: fake_ctx)
    monkeypatch.setattr(handler.storage, "Gcs", lambda **_kw: fake_gcs)
    monkeypatch.setattr(
        handler.insights, "Ingestion", mock.MagicMock(return_value=fake_ingestor)
    )

    assert (
        handler.ingest_gcs_transcript(
            _make_gcs_event("landing-bkt", "raw/insights/call-2002.json")
        )
        is None
    )
    fake_gcs.download_blob.assert_not_called()
    fake_gcs.upload_blob.assert_not_called()
