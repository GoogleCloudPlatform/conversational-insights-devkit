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

"""Generates `llms.txt`, `llms-full.txt`, and synced skill manifests for AI discovery."""

import argparse
from pathlib import Path
import sys
from typing import Dict, List, Optional

from cxidk.ai.mcp import resources as mcp_resources
from cxidk.ai import skills
from cxidk.ai import tools
from cxidk.ai.tools import registry
from cxidk.core import base

REPO_ROOT = Path(__file__).resolve().parents[2]
REPO_URL = "https://github.com/GoogleCloudPlatform/conversational-insights-devkit"
BLOB_BASE = f"{REPO_URL}/blob/main"
RAW_BASE = (
    "https://raw.githubusercontent.com/"
    "GoogleCloudPlatform/conversational-insights-devkit/main"
)


def _sdk_module_lines() -> List[str]:
    """Returns Markdown bullets indexing public Python SDK modules and classes."""
    return [
        (
            "- `cxidk.CxContext`: Validated regional execution context "
            "(`project_id`, `location`, `auth`, `config`)."
        ),
        (
            "- `cxidk.get_llms_txt()`: Returns the wheel-bundled `llms.txt` "
            "index offline."
        ),
        (
            "- `cxidk.wrapper.insights`: CCAI Insights clients — read "
            "(`Conversations`, `Analyses`, `Stats`), write/LRO (`Settings`, "
            "`Ingestion`, `Analysis`, `Export`, `LongRunningOperation`), "
            "typed QA scorecard views (`Scorecards`: `list()`, `get()`, "
            "`list_revisions()`), collections (`PhraseMatchers`, `IssueModels`, "
            "`QaScorecards`, `QaQuestionTags`, `AnalysisRules`, "
            "`AutoLabelingRules`, `AssessmentRules`), and views "
            "(`AuthorizedViews`, `CorrelationConfig`)."
        ),
        (
            "- `cxidk.wrapper` adjacent GCP clients: `storage.Gcs`, "
            "`vertex.Generator` (`google-genai`), "
            "`sensitive_data_protection.Dlp`, `speech` (`V1`/`V2`), `agents` "
            "(Dialogflow CX / CES), `iam`, and `sheets`."
        ),
        (
            "- `cxidk.workflow.ops.ConfigOps`: Atomic GCS `export()`, dry-run "
            "`plan()`, and create-only `import_()` across GCP projects and "
            "regions (`Asset`, `ExportOptions`, `ImportOptions`)."
        ),
        (
            "- `cxidk.workflow.format.Insights`: Deterministic vendor "
            "transcript converters (`from_aws()`, `from_genesys_cloud()`, "
            "`from_dlp_recognize_response()`)."
        ),
        (
            "- `cxidk.workflow.role_recognizer.RoleRecognizer`: Gemini speaker "
            "role classification (`AGENT` vs. `CUSTOMER`) on Speech-to-Text "
            "transcripts."
        ),
        (
            "- `cxidk.workflow.views_manager`: High-level authorized view set "
            "management."
        ),
        (
            "- `cxidk.workflow.insight_refinements`: Quality AI (QAI) "
            "scorecard evaluation (`evaluation.EvaluationReporter`), prompt "
            "optimization (`optimization`), and topic refinement "
            "(`topic_refinement`)."
        ),
        (
            "- `cxidk.ai.tools`: Transport-agnostic `@cx_tool` registry "
            "(`REGISTRY`) and Pydantic output models."
        ),
        (
            "- `cxidk.ai.mcp.build_server`: `MCPServer` factory for `stdio` "
            "and Cloud Run Streamable HTTP (`build_http_app`)."
        ),
        (
            "- `cxidk.ai.adk`: `insights_tools()` `FunctionTool` builder with "
            "`require_confirmation`, `remote_insights_mcp_toolset()`, and "
            "reference agents (`build_insights_analyst_agent`, "
            "`build_config_promoter_agent`, `build_qa_tuner_agent`)."
        ),
    ]


def render_llms_txt() -> str:
    """Builds the deterministic `llms.txt` Markdown index.

    Returns:
        Rendered `llms.txt` Markdown text.
    """
    all_specs = tools.list_specs(
        toolsets=("core", "transcripts", "writes"),
        allow_writes=True,
    )
    lines: List[str] = [
        "# Conversational Insights DevKit (cxidk)",
        "",
        (
            "> AI-native Python SDK, Model Context Protocol (MCP) server "
            "(`cxidk-mcp`), and Google ADK toolset for Google Cloud "
            "Conversational Insights (formerly Contact Center AI / CCAI "
            "Insights, part of Customer Engagement Suite)."
        ),
        "",
        "## Core Documentation & Context",
        "",
        (
            f"- [README.md]({BLOB_BASE}/README.md): Installation, intent map "
            "vs. `google-cloud-contact-center-insights`, Python SDK, MCP, and "
            "ADK quickstarts."
        ),
        (
            f"- [llms-full.txt]({RAW_BASE}/llms-full.txt): Single-file "
            "full-context bundle inlining quickstarts, SDK/tool schemas, "
            "filter syntax, and all `SKILL.md` playbooks."
        ),
        (
            f"- [AGENTS.md]({BLOB_BASE}/AGENTS.md): Repository architecture "
            "and non-negotiable safety invariants."
        ),
        (
            f"- [GEMINI_EXTENSION.md]({BLOB_BASE}/GEMINI_EXTENSION.md): "
            "Gemini CLI Extension operational runtime context."
        ),
        (
            "- [deploy/mcp-cloud-run/README.md]"
            f"({BLOB_BASE}/deploy/mcp-cloud-run/README.md): Remote Cloud Run "
            "Streamable HTTP MCP deployment."
        ),
        (
            "- [examples/terraform/README.md]"
            f"({BLOB_BASE}/examples/terraform/README.md): Reference Terraform "
            "modules for Cloud Run MCP and event-driven ingestion."
        ),
        "",
        "## Python SDK Modules (`cxidk`)",
        "",
        *_sdk_module_lines(),
        "",
        "## Registered AI Tools (`cxidk.ai.tools` / `cxidk-mcp`)",
        "",
    ]

    for spec in all_specs:
        confirm_tag = "confirmation=required" if spec.confirm else "confirmation=none"
        lines.append(
            f"- `{spec.name}` (`toolset={spec.toolset}`, `safety={spec.safety.value}`, "
            f"{confirm_tag}): {spec.description}"
        )

    lines.extend(
        [
            "",
            "## MCP Resources & Prompts",
            "",
            (
                "- `cxidk://schemas/insights-conversation`: JSON Schema for "
                "`JsonConversationInput`."
            ),
            (
                "- `cxidk://reference/filter-syntax`: CCAI Insights filter "
                "expression cheat sheet."
            ),
            (
                "- `cxidk://reference/annotators`: Annotator selectors and "
                "supported GCP regions."
            ),
            (
                "- `cxidk://reference/llms-txt`: Bundled `llms.txt` Python SDK "
                "and AI tool index."
            ),
            (
                "- `cxidk://skills/{skill_name}`: Bundled operational "
                "`SKILL.md` playbooks exposed via MCP `resources/list`."
            ),
            (
                "- Prompt `investigate_conversations`: "
                "Aggregate-first conversation investigation workflow."
            ),
            (
                "- Prompt `promote_configuration`: "
                "Export -> dry-run plan -> confirmed import workflow."
            ),
            (
                "- Prompt `onboard_vendor_transcripts`: "
                "Validate -> convert -> dry-run ingest workflow."
            ),
            "",
            "## Bundled Agent Skills (`cxidk.ai.skills`)",
            "",
        ]
    )

    for skill_name in skills.list_skills():
        skill_url = f"{BLOB_BASE}/src/cxidk/ai/skills/{skill_name}/SKILL.md"
        lines.append(f"- [{skill_name}]({skill_url})")

    lines.append("")
    return "\n".join(lines)


def _render_tool_signatures() -> List[str]:
    """Renders public parameter and output field details for every `@cx_tool`."""
    all_specs = tools.list_specs(
        toolsets=("core", "transcripts", "writes"),
        allow_writes=True,
    )
    out: List[str] = ["## Detailed AI Tool Signatures (`cxidk.ai.tools`)", ""]
    for spec in all_specs:
        params = registry.public_parameters(spec)
        param_parts = [str(param) for param in params]
        sig_str = f"{spec.name}({', '.join(param_parts)})"
        out.append(f"### `{spec.name}`")
        out.append("")
        out.append(f"- **Signature**: `{sig_str}`")
        out.append(
            f"- **Toolset / Safety**: `toolset={spec.toolset}`, "
            f"`safety={spec.safety.value}`, `confirm={spec.confirm}`"
        )
        if spec.output_model is not None:
            fields = ", ".join(f"`{k}`" for k in spec.output_model.model_fields)
            out.append(
                f"- **Output Model (`{spec.output_model.__name__}`)**: {fields}"
            )
        out.append(f"- **Summary**: {spec.description}")
        out.append("")
    return out


def render_llms_full_txt() -> str:
    """Builds the self-contained `llms-full.txt` context bundle for LLMs/RAG.

    Returns:
        Rendered `llms-full.txt` Markdown text.
    """
    readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8").strip()
    agents_text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8").strip()
    region_lines = "\n".join(f"- `{reg}`" for reg in base.REGION_LIST)
    annotators_md = mcp_resources.ANNOTATORS_MARKDOWN_TEMPLATE.format(
        regions=region_lines
    ).strip()

    sections: List[str] = [
        render_llms_txt().strip(),
        "---",
        readme_text,
        "---",
        agents_text,
        "---",
        "\n".join(_render_tool_signatures()).strip(),
        "---",
        mcp_resources.FILTER_SYNTAX_MARKDOWN.strip(),
        "---",
        annotators_md,
    ]

    for skill_name in skills.list_skills():
        sections.append("---")
        sections.append(skills.load_skill(skill_name).strip())

    return "\n\n".join(sections) + "\n"


def expected_artifacts() -> Dict[Path, str]:
    """Computes expected file contents for all generated discovery artifacts."""
    llms_txt = render_llms_txt()
    llms_full_txt = render_llms_full_txt()
    targets: Dict[Path, str] = {
        REPO_ROOT / "llms.txt": llms_txt,
        REPO_ROOT / "src" / "cxidk" / "llms.txt": llms_txt,
        REPO_ROOT / "llms-full.txt": llms_full_txt,
    }
    for skill_name in skills.list_skills():
        targets[REPO_ROOT / "skills" / skill_name / "SKILL.md"] = (
            skills.load_skill(skill_name)
        )
    return targets


def main(argv: Optional[List[str]] = None) -> int:
    """Writes or verifies `llms.txt`, `llms-full.txt`, and synced skill files.

    Args:
        argv: Optional CLI arguments (`--check` verifies zero drift).

    Returns:
        Zero on success, `1` if `--check` detects missing or stale files.
    """
    parser = argparse.ArgumentParser(
        description="Generate or verify cxidk LLM discovery artifacts."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify generated files match repository state without writing.",
    )
    args = parser.parse_args(argv)
    targets = expected_artifacts()

    if args.check:
        stale: List[str] = []
        for path, expected in targets.items():
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                label = (
                    str(path.relative_to(REPO_ROOT))
                    if path.is_relative_to(REPO_ROOT)
                    else str(path)
                )
                stale.append(label)
        if stale:
            sys.stderr.write(
                "Stale LLM discovery artifacts (run "
                "`python .github/scripts/gen_llms_txt.py`):\n"
                + "\n".join(f"  - {rel}" for rel in stale)
                + "\n"
            )
            return 1
        return 0

    for path, content in targets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
