# Claude Code Guide (`CLAUDE.md`)

Follow all architecture, security, and quality-gate instructions in [`AGENTS.md`](AGENTS.md).

## Quick Commands

```bash
source .venv/bin/activate
pytest
mypy $(git ls-files '*.py')
pylint --rcfile=.pylintrc $(git ls-files '*.py')
python .github/scripts/gen_llms_txt.py
```

## Local MCP Server Registration

```bash
claude mcp add cxidk -- env CXIDK_PROJECT_ID=your-project CXIDK_LOCATION=us-central1 cxidk-mcp
```
