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

"""Unit and security tests for `cxidk.ai.mcp` server, elicitation, auth, and HTTP app."""

from typing import Any
from unittest.mock import MagicMock

import httpx
from mcp import Client
from mcp import types
import pytest

from cxidk import CxContext
from cxidk import errors
from cxidk.ai.mcp import Policy
from cxidk.ai.mcp import SecuredMcpHttpApp
from cxidk.ai.mcp import audit
from cxidk.ai.mcp import build_http_app
from cxidk.ai.mcp import build_server
from cxidk.workflow import ops


async def test_mcp_stdio_read_only_tools_resources_and_prompts(
    demo_cx: CxContext,
) -> None:
    """Verifies tool schema hygiene, annotations, resources, and prompts via `mcp.Client`."""
    policy = Policy(
        transport="stdio",
        default_project_id="demo-proj-01",
        default_location="us-central1",
        allowed_projects=("demo-proj-01",),
        toolsets=("core", "transcripts"),
        allow_writes=False,
    )
    server = build_server(policy=policy, cx=demo_cx)

    async with Client(server, raise_exceptions=True) as client:
        listed = await client.list_tools()
        tool_map = {t.name: t for t in listed.tools}

        assert "insights_calculate_stats" in tool_map
        assert "transcript_convert" in tool_map
        assert "config_apply_import" not in tool_map

        for tool_def in listed.tools:
            props = tool_def.input_schema.get("properties", {})
            assert "cx" not in props
            assert "ctx" not in props
            assert "principal" not in props
            assert "signing_key" not in props
            assert tool_def.output_schema is not None
            assert tool_def.annotations is not None
            assert tool_def.annotations.read_only_hint is True

        res_list = await client.list_resources()
        uris = {str(r.uri) for r in res_list.resources}
        assert "cxidk://schemas/insights-conversation" in uris
        assert "cxidk://reference/filter-syntax" in uris

        schema_res = await client.read_resource(
            "cxidk://schemas/insights-conversation"
        )
        assert "entries" in str(schema_res.contents[0])

        prompts_list = await client.list_prompts()
        prompt_names = {p.name for p in prompts_list.prompts}
        assert "investigate_conversations" in prompt_names
        assert "promote_configuration" in prompt_names


async def test_mcp_elicitation_gate_and_cross_project_policy(
    mocker: MagicMock, demo_cx: CxContext
) -> None:
    """Verifies write confirmation gate and cross-project policy enforcement."""
    cx = demo_cx
    policy = Policy(
        transport="stdio",
        default_project_id="demo-proj-01",
        default_location="us-central1",
        allowed_projects=("demo-proj-01",),
        toolsets=("core", "writes"),
        allow_writes=True,
        allow_unattended_writes=False,
    )
    server = build_server(policy=policy, cx=cx)

    mock_ops = mocker.patch("cxidk.ai.tools.config.ops.ConfigOps")
    mock_ops.return_value.export.return_value = ops.ExportReport(
        uri="gs://cx-bundles/out.json",
        source_project_id="demo-proj-01",
        source_location="us-central1",
    )

    async def _decline_cb(
        context: Any, params: Any
    ) -> types.ElicitResult:
        _ = (context, params)
        return types.ElicitResult(action="decline")

    async with Client(server, elicitation_callback=_decline_cb) as client:
        declined = await client.call_tool(
            "config_export_bundle",
            {"bundle_uri": "gs://cx-bundles/out.json"},
        )
        assert declined.is_error is True
        assert "decline" in str(declined.content).lower()
        mock_ops.return_value.export.assert_not_called()

        # Cross-project confused-deputy call must fail before touching GCP
        blocked = await client.call_tool(
            "insights_calculate_stats",
            {"project_id": "unauthorized-proj"},
        )
        assert blocked.is_error is True
        assert "POLICY_VIOLATION" in str(blocked.content)

    async def _false_approve_cb(
        context: Any, params: Any
    ) -> types.ElicitResult:
        _ = (context, params)
        return types.ElicitResult(
            action="accept",
            content={"approve": False},
        )

    async with Client(server, elicitation_callback=_false_approve_cb) as client:
        false_approved = await client.call_tool(
            "config_export_bundle",
            {"bundle_uri": "gs://cx-bundles/out.json"},
        )
        assert false_approved.is_error is True
        assert "CONFIRMATION_DECLINED" in str(false_approved.content)
        mock_ops.return_value.export.assert_not_called()

    async def _accept_cb(
        context: Any, params: Any
    ) -> types.ElicitResult:
        _ = (context, params)
        return types.ElicitResult(
            action="accept",
            content={"approve": True},
        )

    async with Client(server, elicitation_callback=_accept_cb) as client:
        approved = await client.call_tool(
            "config_export_bundle",
            {"bundle_uri": "gs://cx-bundles/out.json"},
        )
        assert approved.is_error is False
        assert approved.structured_content is not None
        assert (
            approved.structured_content["bundle_uri"]
            == "gs://cx-bundles/out.json"
        )
        mock_ops.return_value.export.assert_called_once()


def test_audit_log_sanitizer_redacts_sensitive_fields() -> None:
    """Ensures transcripts, tokens, and signing keys never enter audit logs."""
    cleaned = audit.sanitize_args_for_audit(
        {
            "conversation_id": "conv-1",
            "transcript": {"entries": [{"text": "SSN 123-45-6789"}]},
            "plan_token": "eyJ.secret.sig",
            "authorization": "Bearer ya29.secret",
        }
    )
    assert cleaned["conversation_id"] == "conv-1"
    assert cleaned["transcript"] == "<redacted>"
    assert cleaned["plan_token"] == "<redacted>"
    assert cleaned["authorization"] == "<redacted>"


async def test_http_app_security_headers_auth_origin_and_rate_limit(
    mocker: MagicMock, demo_cx: CxContext
) -> None:
    """Verifies HTTP security headers, 401/403/405/429 responses, and IAP auth."""
    cx = demo_cx

    # Unauthenticated HTTP must refuse non-loopback bind
    dev_policy = Policy(
        transport="http",
        default_project_id="demo-proj-01",
        default_location="us-central1",
        require_auth=False,
    )
    with pytest.raises(errors.PolicyViolationError, match="Refusing to bind"):
        build_http_app(policy=dev_policy, cx=cx, host="0.0.0.0")

    # Loopback dev app enforces Origin check against DNS rebinding
    dev_app = build_http_app(policy=dev_policy, cx=cx, host="127.0.0.1")
    assert isinstance(dev_app, SecuredMcpHttpApp)
    async with dev_app.lifespan():
        transport = httpx.ASGITransport(app=dev_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1:8080"
        ) as client:
            evil_origin = await client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
                headers={"Origin": "https://evil.example"},
            )
            assert evil_origin.status_code == 403

    # Production IAP-protected app
    prod_policy = Policy(
        transport="http",
        default_project_id="demo-proj-01",
        default_location="us-central1",
        require_auth=True,
        iap_audience="/projects/123/locations/us-central1/services/cxidk-mcp",
        rate_limit_per_minute=2,
        allow_ephemeral_plan_key=False,
    )
    mock_verify_token = mocker.patch(
        "cxidk.ai.mcp.auth.id_token.verify_token",
        return_value={
            "iss": "https://cloud.google.com/iap",
            "sub": "accounts.google.com:111",
            "email": "op@example.com",
        },
    )
    app = build_http_app(
        policy=prod_policy,
        cx=cx,
        host="0.0.0.0",
        transport_request=MagicMock(),
    )

    async with app.lifespan():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="https://cxidk.run.app"
        ) as client:
            health = await client.get("/healthz")
            assert health.status_code == 200
            assert health.headers["x-content-type-options"] == "nosniff"
            assert health.headers["x-frame-options"] == "DENY"
            assert health.headers["cache-control"] == "no-store"
            assert "default-src 'none'" in health.headers["content-security-policy"]

            bad_health_method = await client.post("/healthz")
            assert bad_health_method.status_code == 405

            bad_mcp_method = await client.get("/mcp")
            assert bad_mcp_method.status_code == 405

            unauth = await client.post("/mcp", json={})
            assert unauth.status_code == 401
            assert unauth.headers["x-frame-options"] == "DENY"

            init_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "1.0"},
                },
            }
            iap_headers = {
                "x-goog-iap-jwt-assertion": "signed.iap.jwt",
                "Accept": "application/json, text/event-stream",
            }
            ok_resp = await client.post(
                "/mcp", json=init_payload, headers=iap_headers
            )
            assert ok_resp.status_code == 200
            assert ok_resp.headers["x-content-type-options"] == "nosniff"

            # Second request consumes remaining bucket token; third hits 429
            await client.post("/mcp", json=init_payload, headers=iap_headers)
            limited = await client.post(
                "/mcp", json=init_payload, headers=iap_headers
            )
            assert limited.status_code == 429

            # Wrong issuer claim is rejected with 401 before rate limiter
            mock_verify_token.return_value = {
                "iss": "https://accounts.google.com",
                "sub": "accounts.google.com:111",
                "email": "op@example.com",
            }
            bad_iss = await client.post(
                "/mcp", json=init_payload, headers=iap_headers
            )
            assert bad_iss.status_code == 401
