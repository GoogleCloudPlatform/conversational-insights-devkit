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

"""Unit and security tests for `cxidk.ai.tools`, validators, and HS256 plan tokens."""

import base64
import json
from typing import Dict, List
from unittest.mock import MagicMock

import jwt
import pytest

from cxidk import CxContext
from cxidk import errors
from cxidk.ai import tools
from cxidk.ai.tools import plan_tokens
from cxidk.ai.tools import validation
from cxidk.workflow import ops


def test_registry_filtering_and_safety_defaults() -> None:
    """Read-only toolsets exclude write tools unless `allow_writes=True`."""
    read_specs = tools.list_specs(allow_writes=False)
    assert read_specs
    assert all(spec.safety == tools.Safety.READ for spec in read_specs)
    assert all(spec.toolset != "writes" for spec in read_specs)

    all_specs = tools.list_specs(
        toolsets=("core", "transcripts", "writes"),
        allow_writes=True,
    )
    names = {spec.name for spec in all_specs}
    assert "config_plan_import" in names
    assert "config_apply_import" in names
    assert "insights_bulk_analyze" in names
    assert tools.REGISTRY["config_apply_import"].confirm is True
    assert tools.REGISTRY["config_plan_import"].confirm is False


def test_input_validators_block_traversal_and_injection() -> None:
    """Allowlist validators block path traversal, bad schemes, and control chars."""
    assert validation.validate_resource_id("conv_123-abc") == "conv_123-abc"
    with pytest.raises(errors.InvalidArgumentError):
        validation.validate_resource_id("../../settings")
    with pytest.raises(errors.InvalidArgumentError):
        validation.validate_resource_id("conv/nested")

    bucket, obj = validation.validate_gcs_uri("gs://my-bucket/bundles/v1.json")
    assert bucket == "my-bucket"
    assert obj == "bundles/v1.json"
    with pytest.raises(errors.InvalidArgumentError):
        validation.validate_gcs_uri("https://storage.googleapis.com/b/o")
    with pytest.raises(errors.InvalidArgumentError):
        validation.validate_gcs_uri("gs://my-bucket/../escape.json")

    proj, loc, op_id = validation.validate_operation_name(
        "projects/demo-proj-01/locations/us-central1/operations/op-99"
    )
    assert (proj, loc, op_id) == ("demo-proj-01", "us-central1", "op-99")
    with pytest.raises(errors.InvalidArgumentError):
        validation.validate_operation_name("projects/bad/operations/1")

    with pytest.raises(errors.InvalidArgumentError):
        validation.validate_filter("medium=\"CHAT\"\x00")


def test_plan_tokens_enforce_hs256_expiry_and_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies `plan_tokens` rejects alg=none, short keys, expiry, and claim mismatches."""
    monkeypatch.delenv("CXIDK_PLAN_SIGNING_KEY", raising=False)
    with pytest.raises(errors.PolicyViolationError, match="CXIDK_PLAN_SIGNING_KEY"):
        plan_tokens.resolve_signing_key(allow_ephemeral=False)
    with pytest.raises(errors.PolicyViolationError, match="at least 32 bytes"):
        plan_tokens.resolve_signing_key(explicit_key=b"too-short")

    secret_key = b"0123456789abcdef0123456789abcdef"
    digest = plan_tokens.compute_bundle_digest({"manifest": {"v": 1}})
    tok = plan_tokens.issue_plan_token(
        destination_project_id="prod-proj-01",
        destination_location="us-central1",
        bundle_uri="gs://bundles/rel.json",
        bundle_sha256=digest,
        assets=["*"],
        activate_imported=False,
        principal="alice@example.com",
        signing_key=secret_key,
    )
    claims = plan_tokens.verify_plan_token(
        tok,
        destination_project_id="prod-proj-01",
        destination_location="us-central1",
        bundle_uri="gs://bundles/rel.json",
        bundle_sha256=digest,
        assets=["*"],
        activate_imported=False,
        principal="alice@example.com",
        signing_key=secret_key,
    )
    assert claims["dst_project"] == "prod-proj-01"

    # Reject forged alg=none JWT before decoding
    none_hdr = base64.urlsafe_b64encode(
        json.dumps({"alg": "none", "typ": "JWT"}).encode()
    ).rstrip(b"=")
    none_body = base64.urlsafe_b64encode(b"{}").rstrip(b"=")
    forged_none = f"{none_hdr.decode()}.{none_body.decode()}."
    with pytest.raises(errors.PolicyViolationError, match="disallowed JWT algorithm"):
        plan_tokens.verify_plan_token(
            forged_none,
            destination_project_id="prod-proj-01",
            destination_location="us-central1",
            bundle_uri="gs://bundles/rel.json",
            bundle_sha256=digest,
            assets=["*"],
            signing_key=secret_key,
        )

    # Reject tampered bundle digest or wrong principal
    with pytest.raises(errors.PolicyViolationError, match="bundle SHA-256 digest"):
        plan_tokens.verify_plan_token(
            tok,
            destination_project_id="prod-proj-01",
            destination_location="us-central1",
            bundle_uri="gs://bundles/rel.json",
            bundle_sha256="deadbeef",
            assets=["*"],
            principal="alice@example.com",
            signing_key=secret_key,
        )

    # Reject expired token
    expired_tok = jwt.encode(
        {**claims, "exp": 1},
        secret_key,
        algorithm="HS256",
    )
    with pytest.raises(errors.PolicyViolationError, match="expired"):
        plan_tokens.verify_plan_token(
            expired_tok,
            destination_project_id="prod-proj-01",
            destination_location="us-central1",
            bundle_uri="gs://bundles/rel.json",
            bundle_sha256=digest,
            assets=["*"],
            principal="alice@example.com",
            signing_key=secret_key,
        )


def test_conversation_redaction_and_transcript_tools(
    mocker: MagicMock, demo_cx: CxContext
) -> None:
    """Verifies PII masking in `insights_get_conversation` and local transcript tools."""
    cx = demo_cx
    mock_conv_cls = mocker.patch("cxidk.ai.tools.conversations.insights.Conversations")
    mock_conv_cls.return_value.get.return_value = {
        "name": "projects/demo-proj-01/locations/us-central1/conversations/c-1",
        "latest_summary": {"text": "Customer jane@example.com called."},
        "transcript": {
            "transcript_segments": [
                {"text": "My email is jane@example.com and SSN 123-45-6789."},
                {"text": "Call me at 415-555-0199."},
            ]
        },
    }

    redacted = tools.insights_get_conversation(
        "c-1",
        transcript_mode="redacted",
        max_turns=1,
        cx=cx,
    )
    assert redacted.truncated_turns is True
    segs = redacted.conversation["transcript"]["transcript_segments"]
    assert len(segs) == 1
    assert "jane@example.com" not in segs[0]["text"]
    assert "[EMAIL_ADDRESS]" in segs[0]["text"]
    assert "[US_SOCIAL_SECURITY_NUMBER]" in segs[0]["text"]
    assert "[EMAIL_ADDRESS]" in redacted.conversation["latest_summary"]["text"]

    omitted = tools.insights_get_conversation(
        "c-1", transcript_mode="omit", cx=cx
    )
    assert omitted.conversation["transcript"]["omitted"] is True

    bad_aws: Dict[str, List[object]] = {"Transcript": []}
    bad_val = tools.transcript_validate("aws", bad_aws)
    assert bad_val.valid is False
    assert any("Channel" in err for err in bad_val.errors)

    aws_doc = {
        "Channel": "VOICE",
        "Transcript": [
            {
                "ParticipantId": "CUSTOMER",
                "Id": "1",
                "BeginOffsetMillis": 0,
                "Content": "Hello support",
            }
        ],
    }
    val_out = tools.transcript_validate("aws", aws_doc)
    assert val_out.valid is True
    conv_out = tools.transcript_convert("aws", aws_doc, "2025/01/01 00:00:00")
    assert conv_out.entry_count == 1
    assert tools.transcript_validate("insights", conv_out.transcript).valid is True


def test_config_plan_and_apply_roundtrip_and_dry_run_ingestion(
    mocker: MagicMock, demo_cx: CxContext
) -> None:
    """Verifies `config_plan_import` -> `config_apply_import` and `dry_run` writes."""
    cx = demo_cx
    signing_key = b"abcdef0123456789abcdef0123456789"
    bundle_doc = {
        "manifest": {
            "schema_version": 1,
            "source_project_id": "src-proj-01",
            "source_location": "us-central1",
            "assets": ["phrase_matchers"],
        },
        "assets": {"phrase_matchers": [{"displayName": "Greeting"}]},
    }

    mock_ops_cls = mocker.patch("cxidk.ai.tools.config.ops.ConfigOps")
    ops_inst = mock_ops_cls.return_value
    ops_inst.bundle_io.read_json.return_value = bundle_doc
    ops_inst.plan.return_value = ops.PlanReport(
        uri="gs://cx-bundles/b1.json",
        source_project_id="src-proj-01",
        source_location="us-central1",
        destination_project_id="demo-proj-01",
        destination_location="us-central1",
        will_create={"phrase_matchers": 1},
    )
    ops_inst.import_.return_value = ops.ImportReport(
        uri="gs://cx-bundles/b1.json",
        destination_project_id="demo-proj-01",
        destination_location="us-central1",
        assets={
            "phrase_matchers": ops.AssetOutcome(
                asset="phrase_matchers", count=1
            )
        },
    )

    plan_out = tools.config_plan_import(
        "gs://cx-bundles/b1.json",
        cx=cx,
        signing_key=signing_key,
    )
    assert plan_out.will_create == {"phrase_matchers": 1}

    apply_out = tools.config_apply_import(
        "gs://cx-bundles/b1.json",
        plan_token=plan_out.plan_token,
        cx=cx,
        signing_key=signing_key,
    )
    assert apply_out.total_created == 1

    # Mutate bundle in GCS after plan -> must reject before calling import_()
    ops_inst.bundle_io.read_json.return_value = {
        **bundle_doc,
        "assets": {"phrase_matchers": [{"displayName": "Injected"}]},
    }
    with pytest.raises(errors.PolicyViolationError, match="SHA-256"):
        tools.config_apply_import(
            "gs://cx-bundles/b1.json",
            plan_token=plan_out.plan_token,
            cx=cx,
            signing_key=signing_key,
        )

    # Dry-run ingestion & bulk analyze execute zero mutating calls
    dry_ingest = tools.insights_ingest_conversation(
        transcript_uri="gs://cx-bundles/t1.json",
        dry_run=True,
        cx=cx,
    )
    assert dry_ingest.dry_run is True

    mock_stats = mocker.patch("cxidk.ai.tools.ingestion.insights.Stats")
    mock_stats.return_value.calculate.return_value = {"conversation_count": 20}
    dry_bulk = tools.insights_bulk_analyze(
        analysis_filter='medium="CHAT"',
        annotators=["INSIGHTS"],
        analysis_percentage=50.0,
        dry_run=True,
        cx=cx,
    )
    assert dry_bulk.dry_run is True
    assert dry_bulk.preview["estimated_analyzed_conversations"] == 10
