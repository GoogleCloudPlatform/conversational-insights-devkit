<!-- mcp-name: io.github.GoogleCloudPlatform/cxidk -->

# Conversational Insights DevKit (`cxidk` 2.0)

The **Conversational Insights DevKit (`cxidk`)** is an AI-native Python library,
Model Context Protocol (**MCP**) server, and **Google Agent Development Kit (ADK)**
integration for [Google Cloud Conversational Insights](https://cloud.google.com/contact-center/insights/docs)
(formerly **Contact Center AI / CCAI Insights**, part of **Customer Engagement Suite**).

## Key Features

- **Read & Analytics APIs**: Token-budgeted conversation listing (`BASIC` view by
  default), transcript retrieval with Cloud DLP / regex PII redaction, QA scorecard
  analysis inspection, `calculate_stats`, and `query_metrics` time-series slicing.
- **Guarded Configuration Promotion (`ConfigOps`)**: Atomic GCS bundle export,
  dry-run `plan()` with cryptographic HS256 `plan_token` binding, and create-only
  `import_()` across projects and regions.
- **Vendor Transcript Onboarding**: Deterministic JSON Schema validation and
  conversion for **AWS Transcribe** and **Genesys Cloud**, plus **Gemini** speaker
  role classification (`AGENT` vs. `CUSTOMER`) via `google-genai`.
- **MCP Server (`cxidk-mcp`)**: Ready for Gemini CLI, Claude Code, Cursor, VS Code
  (`stdio`), and remote multi-user **Cloud Run** deployments (Streamable HTTP with
  IAP/OIDC auth, MCP elicitation confirmation, OpenTelemetry, and audit logging).
- **Google ADK Integration (`cxidk.ai.adk`)**: First-class `FunctionTool` (`require_confirmation`
  wired automatically), remote `McpToolset`, bundled `SKILL.md` Agent Skills, and
  reference agents (`insights_analyst`, `config_promoter`, `qa_tuner`).

## When to Use `cxidk` vs. `google-cloud-contact-center-insights`

`google-cloud-contact-center-insights` provides low-level auto-generated gRPC/Protobuf
bindings. Use **`cxidk`** on top when building workflows, pipelines, or AI agents:

| Developer / Agent Task | `cxidk` Python Entrypoint | MCP / ADK Tool |
| --- | --- | --- |
| Aggregate call volume, sentiment, and QA metrics | `cxidk.wrapper.insights.Stats` | `insights_calculate_stats`, `insights_query_metrics` |
| Read conversations with PII masking & turn budgets | `cxidk.wrapper.insights.Conversations` | `insights_list_conversations`, `insights_get_conversation` |
| Export, dry-run plan, and promote Insights configs | `cxidk.workflow.ops.ConfigOps` | `config_export_bundle`, `config_plan_import`, `config_apply_import` |
| Convert AWS Transcribe or Genesys Cloud JSON | `cxidk.workflow.format.Insights` | `transcript_validate`, `transcript_convert` |
| Classify `AGENT` vs. `CUSTOMER` speaker roles | `cxidk.workflow.role_recognizer.RoleRecognizer` | `transcript_recognize_roles` |
| Evaluate & tune Quality AI (QAI) scorecards | `cxidk.wrapper.insights.Scorecards`, `cxidk.workflow.insight_refinements` | `insights_list_scorecards`, `insights_get_scorecard`, `insights_list_scorecard_revisions`, `insights_list_analyses` |
| Build confirmation-gated Google ADK agents | `cxidk.ai.adk.insights_tools`, `cxidk.ai.skills` | All 19 `@cx_tool` functions |

## Requirements & Installation

Requires **Python 3.11+**.

```bash
python3 -m venv .venv
source .venv/bin/activate

# Core SDK
pip install cxidk

# With MCP server + Google ADK + Speech + DLP extras
pip install "cxidk[mcp,adk,speech,dlp]"

# Local editable install for contributors
pip install -e ".[all,dev]"
```

## Quickstart 1: Python SDK (`CxContext` & Read APIs)

```python
from cxidk import CxContext
from cxidk.ai.tools import insights_calculate_stats, insights_list_conversations

cx = CxContext(project_id="my-gcp-project", location="us-central1")

stats = insights_calculate_stats(filter='medium="PHONE_CALL"', cx=cx)
print(stats.stats)

page = insights_list_conversations(page_size=10, cx=cx)
for convo in page.conversations:
    print(convo.get("name"))
```

## Quickstart 2: Gemini CLI Extension & Local MCP Server (`stdio`)

Authenticate with Application Default Credentials:

```bash
gcloud auth application-default login
```

Install in one command as a **Gemini CLI Extension** (wires `cxidk-mcp`, environment
settings, and all 4 Agent Skills automatically):

```bash
gemini extensions install https://github.com/GoogleCloudPlatform/conversational-insights-devkit
```

Or add `cxidk-mcp` directly to **Gemini CLI** (`~/.gemini/settings.json`), **Claude
Desktop / Claude Code**, **VS Code**, or **Cursor** via `uvx` (or an installed `.venv`):

```json
{
  "mcpServers": {
    "cxidk": {
      "command": "uvx",
      "args": ["--from", "cxidk[mcp]", "cxidk-mcp", "--transport", "stdio"],
      "env": {
        "CXIDK_PROJECT_ID": "your-gcp-project",
        "CXIDK_LOCATION": "us-central1"
      }
    }
  }
}
```

Write tools are **disabled by default**. Pass `"--allow-writes"` (or set
`CXIDK_ALLOW_WRITES=true`) to enable guarded promotion and ingestion tools with
interactive MCP elicitation confirmation.

## Quickstart 3: Google ADK Agents

```python
from cxidk import CxContext
from cxidk.ai.adk import build_insights_analyst_agent, build_config_promoter_agent

cx = CxContext(project_id="my-gcp-project", location="us-central1")

# Read-only analyst agent with redacted transcript defaults
analyst = build_insights_analyst_agent(cx=cx)

# Guarded release agent (requires plan_token + ADK ToolConfirmation on writes)
promoter = build_config_promoter_agent(
    cx=cx,
    allowed_projects=["dev-insights", "prod-insights"],
)
```

## Quickstart 4: Vendor Transcript Conversion & Ingestion

```python
import json
import uuid
from cxidk.workflow import format as cx_format
from cxidk.workflow import role_recognizer as rr
from cxidk.wrapper import insights, speech, storage

project_id = "your-gcp-project"
location = "us-central1"
bucket_name = "your-insights-staging-bucket"
parent = f"projects/{project_id}/locations/{location}"

# Convert an AWS Transcribe JSON payload locally
with open("tests/integration/data/aws_transcript.json", "r", encoding="utf-8") as f:
    aws_payload = json.load(f)

insights_json = cx_format.Insights().from_aws(transcript=aws_payload)

# Upload to GCS and ingest into CCAI Insights
gcs = storage.Gcs(project_name=project_id, bucket_name=bucket_name)
blob_name = f"{uuid.uuid4()}.json"
gcs.upload_blob(file_name=blob_name, data=json.dumps(insights_json))

ingestor = insights.Ingestion(
    parent=parent,
    transcript_path=f"gs://{bucket_name}/{blob_name}",
)
operation = ingestor.single(language_code="en-US")
print(f"Ingestion operation started: {operation.name}")
```

## Cloud Run & Terraform Deployment

- [`deploy/mcp-cloud-run/README.md`](deploy/mcp-cloud-run/README.md): Container image and
  `gcloud run deploy` script for stateless Streamable HTTP `cxidk-mcp` behind IAP/OIDC.
- [`examples/terraform/`](examples/terraform/README.md): Reference Terraform modules for
  deploying **`cxidk-mcp` on Cloud Run** ([`cloud_run_mcp/`](examples/terraform/cloud_run_mcp/README.md))
  and **event-driven transcript ingestion on Cloud Run Functions (2nd Gen)**
  ([`cloud_run_function_ingest/`](examples/terraform/cloud_run_function_ingest/README.md)).

## Documentation for AI Systems

- [`llms.txt`](llms.txt): Concise machine-readable index of Python SDK modules,
  registered MCP/ADK tools, resources, prompts, and Agent Skills (also accessible
  offline via `cxidk.get_llms_txt()` or `cxidk-mcp --print-llms-txt`).
- [`llms-full.txt`](llms-full.txt): Self-contained full-context Markdown bundle
  inlining quickstarts, SDK & tool schemas, filter syntax, and `SKILL.md` playbooks.
- [`AGENTS.md`](AGENTS.md) / [`GEMINI.md`](GEMINI.md) / [`CLAUDE.md`](CLAUDE.md):
  Contributor & coding-agent guardrails.
- [`GEMINI_EXTENSION.md`](GEMINI_EXTENSION.md) & [`gemini-extension.json`](gemini-extension.json):
  Gemini CLI Extension runtime context and configuration manifest.
- `src/cxidk/ai/skills/` (mirrored at `skills/`): Portable `SKILL.md` playbooks.

## License

Distributed under the Apache 2.0 License. See [`LICENSE.txt`](LICENSE.txt) for details.
