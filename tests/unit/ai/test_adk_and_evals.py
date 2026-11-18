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

"""Unit tests for `cxidk.ai.adk` toolset, reference agents, skills, and eval suites."""

import inspect
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cxidk import CxContext
from cxidk.ai import adk
from cxidk import errors
from cxidk.ai import skills
from cxidk.ai import tools
from cxidk.ai.tools import plan_tokens
from cxidk.ai.tools import validation

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_bundled_skills_load_cleanly() -> None:
    """Verifies all 4 Agent Skills are discoverable and contain YAML frontmatter."""
    available = skills.list_skills()
    assert available == [
        "cx-insights-analyst",
        "cx-insights-config-promotion",
        "cx-insights-ingestion",
        "cx-insights-qa-tuning",
    ]
    for name in available:
        content = skills.load_skill(name)
        assert content.startswith("---")
        assert f"name: {name}" in content

    with pytest.raises(errors.InvalidArgumentError):
        skills.get_skill_path("../secret")
    with pytest.raises(errors.NotFoundError):
        skills.load_skill("nonexistent-skill")


def test_adk_insights_tools_confirmation_and_policy(
    mocker: MagicMock, demo_cx: CxContext
) -> None:
    """Verifies ADK `FunctionTool` wrapping, confirmation wiring, and project guards."""
    read_tools = adk.insights_tools(cx=demo_cx, allow_writes=False)
    read_map = {t.name: t for t in read_tools}
    assert "insights_calculate_stats" in read_map
    assert "config_apply_import" not in read_map

    write_tools = adk.insights_tools(
        cx=demo_cx,
        toolsets=("core", "writes"),
        allow_writes=True,
    )
    write_map = {t.name: t for t in write_tools}
    assert "config_plan_import" in write_map
    assert "config_apply_import" in write_map

    # Internal kwargs must never leak into ADK function signatures
    apply_tool = write_map["config_apply_import"]
    sig = inspect.signature(apply_tool.func)
    assert "cx" not in sig.parameters
    assert "principal" not in sig.parameters
    # pylint: disable-next=protected-access
    assert apply_tool._require_confirmation is True
    # pylint: disable-next=protected-access
    assert write_map["config_plan_import"]._require_confirmation is False

    # Calling wrapped function with disallowed project raises PolicyViolationError
    stats_fn = read_map["insights_calculate_stats"].func
    with pytest.raises(errors.PolicyViolationError):
        stats_fn(project_id="other-proj-99")

    mock_stats = mocker.patch("cxidk.ai.tools.stats.insights.Stats")
    mock_stats.return_value.calculate.return_value = {"conversation_count": 7}
    out = stats_fn(filter='medium="CHAT"')
    assert out["stats"]["conversation_count"] == 7


def test_remote_mcp_toolset_enforces_https() -> None:
    """Verifies `remote_insights_mcp_toolset` rejects cleartext remote URLs."""
    remote = adk.remote_insights_mcp_toolset("https://cxidk-mcp.run.app/mcp")
    assert remote is not None

    local = adk.remote_insights_mcp_toolset("http://127.0.0.1:8080/mcp")
    assert local is not None

    with pytest.raises(errors.UnsafeEndpointError):
        adk.remote_insights_mcp_toolset("http://insecure.example.com/mcp")


def test_reference_adk_agents_construct_with_skills(
    demo_cx: CxContext,
) -> None:
    """Verifies all 3 reference ADK `LlmAgent` builders construct cleanly."""
    analyst = adk.build_insights_analyst_agent(cx=demo_cx)
    assert analyst.name == "cx_insights_analyst"
    assert "SECURITY INVARIANT" in str(analyst.instruction)

    promoter = adk.build_config_promoter_agent(
        cx=demo_cx,
        allowed_projects=["demo-proj-01", "prod-proj-01"],
    )
    assert promoter.name == "cx_config_promoter"
    promoter_tool_names = {getattr(t, "name", "") for t in promoter.tools}
    assert "config_plan_import" in promoter_tool_names
    assert "config_apply_import" in promoter_tool_names

    tuner = adk.build_qa_tuner_agent(cx=demo_cx)
    assert tuner.name == "cx_qa_tuner"


def test_eval_suites_and_prompt_injection_defenses(
    demo_cx: CxContext,
) -> None:
    """Validates `tests/evals/` benchmark cases and deterministic red-team defenses."""
    selection_cases = json.loads(
        (REPO_ROOT / "tests" / "evals" / "tool_selection_cases.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(selection_cases) >= 6
    for case in selection_cases:
        assert case["expected_first_tool"] in tools.REGISTRY
        if "requires_confirmation_before" in case:
            target = case["requires_confirmation_before"]
            assert tools.REGISTRY[target].confirm is True

    injection_cases = json.loads(
        (REPO_ROOT / "tests" / "evals" / "prompt_injection_cases.json").read_text(
            encoding="utf-8"
        )
    )
    adk_read_map = {
        t.name: t for t in adk.insights_tools(cx=demo_cx, allow_writes=False)
    }

    # Case 1: cross-project exfiltration blocked by allowed_projects + read-only default
    assert "config_export_bundle" not in adk_read_map
    with pytest.raises(errors.PolicyViolationError):
        adk_read_map["insights_calculate_stats"].func(
            project_id=injection_cases[0]["must_block_project"]
        )

    # Case 2: forged alg=none plan_token rejected before decoding
    with pytest.raises(errors.PolicyViolationError, match="disallowed JWT algorithm"):
        plan_tokens.verify_plan_token(
            injection_cases[1]["forged_plan_token"],
            destination_project_id="demo-proj-01",
            destination_location="us-central1",
            bundle_uri="gs://evil-bundle/backdoor.json",
            bundle_sha256="00",
            assets=["*"],
            signing_key=b"0123456789abcdef0123456789abcdef",
        )

    # Case 3: unbounded bulk_analyze with empty filter rejected
    with pytest.raises(errors.InvalidArgumentError, match="analysis_filter"):
        tools.insights_bulk_analyze(
            analysis_filter="",
            annotators=["INSIGHTS"],
            cx=demo_cx,
        )

    # Case 4: path traversal conversation_id rejected
    with pytest.raises(errors.InvalidArgumentError):
        validation.validate_resource_id(
            injection_cases[3]["malicious_resource_id"],
            "conversation_id",
        )
