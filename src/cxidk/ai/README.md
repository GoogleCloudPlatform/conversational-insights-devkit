# AI & Agentic Layer (`cxidk.ai`)

`cxidk.ai` isolates all LLM, Model Context Protocol (MCP), and Google Agent Development Kit (ADK) surfaces from the core Python SDK (`core`, `wrapper`, `workflow`).

## Submodules

- **`policy.py`**: Immutable `Policy` enforcing `CXIDK_ALLOW_WRITES`, `allowed_projects`, regional endpoints, and transcript privacy modes across both MCP and ADK.
- **`tools/`**: Transport-agnostic `@cx_tool` registry (`REGISTRY`), Pydantic output models, input allowlist validators, and HS256 `plan_token` verification.
- **`mcp/`**: `cxidk-mcp` server supporting local `stdio` and hardened Cloud Run Streamable HTTP (`--transport http`), IAP/OIDC verification, MCP elicitation confirmation, audit logs, and OpenTelemetry spans.
- **`adk/`**: Google ADK `insights_tools()`, `remote_insights_mcp_toolset()`, and reference `LlmAgent` builders (`insights_analyst`, `config_promoter`, `qa_tuner`).
- **`skills/`**: Portable `SKILL.md` playbooks discoverable via `list_skills()` and `load_skill()`.
