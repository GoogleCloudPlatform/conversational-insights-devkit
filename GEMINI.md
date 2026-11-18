# Gemini Development Guide

This guide provides context for using Gemini to assist with development in the
`conversational-insights-devkit` repository (`cxidk` 2.0). See also
[`AGENTS.md`](AGENTS.md) for full architecture and security invariants.

## Project Overview

The Conversational Insights DevKit (`cxidk`) is an AI-native Python toolkit,
Model Context Protocol (MCP) server (`cxidk-mcp`), and Google ADK integration
for extracting insights, converting third-party transcripts (AWS, Genesys Cloud),
and safely promoting configuration across Google Cloud Contact Center AI (CCAI)
Insights environments.

## Development Setup

Requires **Python 3.11+**.

1. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -e ".[all,dev]"
   ```

## Running Quality Checks

This project enforces `pytest`, `mypy`, `pylint` (10.00/10), and Apache 2.0
license headers (`.github/HEADER_TEMPLATE.txt` on every `.py` file except
`**/__init__.py`).

* **Run tests:**
  ```bash
  pytest
  ```
* **Run linter:**
  ```bash
  pylint --rcfile=.pylintrc $(git ls-files '*.py')
  ```
* **Run type checker:**
  ```bash
  mypy $(git ls-files '*.py')
  ```
* **Regenerate `llms.txt`:**
  ```bash
  python .github/scripts/gen_llms_txt.py
  ```

## Project Structure

- `src/cxidk/`:
  - `core/`: `Auth`, `Config`, `Request`, `CxContext`, `errors`, `serialize`, `retry`.
  - `wrapper/`: CCAI Insights subpackage (`insights/`), Vertex AI (`google-genai`),
    Speech, Cloud DLP, Storage, CES Agents, IAM, and Sheets.
  - `workflow/`: `ConfigOps` promotion (`ops.py`), vendor formatters (`format.py`),
    Gemini role recognition (`role_recognizer.py`), and `insight_refinements/`.
  - `ai/`: Agentic & LLM layer (`policy.py`, `tools/`, `mcp/`, `adk/`, `skills/`).
- `deploy/mcp-cloud-run/`: Hardened Cloud Run container and deployment scripts for `cxidk-mcp`.
- `tests/`: `unit/{core,wrapper,workflow,ai}/`, `integration/`, and `evals/`.
