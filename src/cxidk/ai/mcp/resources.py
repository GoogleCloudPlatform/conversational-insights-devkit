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

"""Read-only MCP reference resources for CCAI Insights schemas, filters, and annotators."""

from mcp.server import MCPServer

import cxidk
from cxidk.ai import skills
from cxidk.ai.tools import transcripts
from cxidk.core import base

FILTER_SYNTAX_MARKDOWN = """# CCAI Insights Filter Syntax Reference

Use these filter expressions in `insights_list_conversations`, `insights_calculate_stats`,
`insights_query_metrics`, and `insights_bulk_analyze`:

## Common Fields
- **Medium**: `medium="PHONE_CALL"` or `medium="CHAT"`
- **Time window**: `create_time > "2025-01-01T00:00:00Z" AND create_time < "2025-02-01T00:00:00Z"`
- **Has completed analysis**: `latest_analysis:*`
- **Missing analysis**: `NOT latest_analysis:*`
- **Agent ID**: `agent_id="agent-42"`
- **Custom labels**: `labels.department="billing"`
- **Customer satisfaction**: `quality_metadata.customer_satisfaction_rating <= 2`
- **Client sentiment**: `latest_analysis.client_sentiment_score < -0.3`

## Boolean Combinators
Combine predicates with uppercase `AND`, `OR`, and `NOT`, using parentheses to group.
"""

ANNOTATORS_MARKDOWN_TEMPLATE = """# CCAI Insights Annotators & Regional Endpoints

## Supported Annotator Selectors
- `INSIGHTS`: Runs sentiment, entity, intent, phrase matcher (smart highlighter),
  silence, and interruption annotators.
- `SUMMARIZATION`: Generates structured conversation summaries.
- `TOPIC MODEL`: Classifies conversations against the deployed issue/topic model.
- `QAI`: Quality AI scorecard evaluation (configured via analysis/assessment rules
  and global settings; not supported in legacy `bulk_analyze` selector).

## Supported Regional Locations
{regions}
"""


def _register_skill_resource(server: MCPServer, skill_name: str) -> None:
    """Registers a single bundled `SKILL.md` playbook as an MCP resource."""

    @server.resource(
        f"cxidk://skills/{skill_name}",
        name=f"skill-{skill_name}",
        title=f"Agent Skill: {skill_name}",
        description=(
            f"Operational CCAI Insights playbook (`{skill_name}/SKILL.md`)."
        ),
        mime_type="text/markdown",
    )
    def _read_skill() -> str:
        """Returns the Markdown playbook for `skill_name`."""
        return skills.load_skill(skill_name)


def register_resources(server: MCPServer) -> None:
    """Registers static reference and skill resources on `server`.

    Args:
        server: Target `MCPServer` instance.
    """

    @server.resource(
        "cxidk://schemas/insights-conversation",
        name="insights-conversation-schema",
        title="CCAI Insights JsonConversationInput Schema",
        description="JSON Schema for CCAI Insights transcript uploads (`{'entries': [...]}`).",
        mime_type="application/json",
    )
    def get_conversation_schema() -> str:
        """Returns the bundled `JsonConversationInput` JSON Schema."""
        return transcripts.read_schema_text("insights")

    @server.resource(
        "cxidk://reference/filter-syntax",
        name="insights-filter-syntax",
        title="CCAI Insights Filter Syntax Cheat Sheet",
        description="Reference guide for Insights filter expressions.",
        mime_type="text/markdown",
    )
    def get_filter_syntax() -> str:
        """Returns the CCAI Insights filter expression Markdown guide."""
        return FILTER_SYNTAX_MARKDOWN.strip()

    @server.resource(
        "cxidk://reference/annotators",
        name="insights-annotators-and-regions",
        title="CCAI Insights Annotators & Regions Reference",
        description="Supported annotator selectors and CCAI Insights GCP regions.",
        mime_type="text/markdown",
    )
    def get_annotators_reference() -> str:
        """Returns supported annotator selectors and GCP regional endpoints."""
        region_lines = "\n".join(f"- `{reg}`" for reg in base.REGION_LIST)
        return ANNOTATORS_MARKDOWN_TEMPLATE.format(regions=region_lines).strip()

    @server.resource(
        "cxidk://reference/llms-txt",
        name="cxidk-llms-txt",
        title="cxidk LLM & Agent API Index (llms.txt)",
        description=(
            "Machine-readable index of cxidk Python SDK modules, MCP/ADK tools, "
            "resources, prompts, and Agent Skills."
        ),
        mime_type="text/markdown",
    )
    def get_llms_txt_resource() -> str:
        """Returns the bundled `llms.txt` index."""
        return cxidk.get_llms_txt()

    for skill_name in skills.list_skills():
        _register_skill_resource(server, skill_name)
