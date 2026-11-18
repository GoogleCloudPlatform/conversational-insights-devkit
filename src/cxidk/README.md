# Conversational Insights DevKit (`cxidk`)

`cxidk` is organized into four bottom-up architectural layers:

1. **[`core/`](core/README.md)**: Authentication (`Auth`), regional endpoint configuration (`Config`), resilient HTTPS `Request` handling, `CxContext`, and typed `CxidkError` exceptions.
2. **[`wrapper/`](wrapper/README.md)**: Thin, Pythonic clients around Google Cloud SDKs (`insights/`, `speech.py`, `sensitive_data_protection.py`, `storage.py`, `vertex.py`, `agents.py`, `iam.py`, `sheets.py`).
3. **[`workflow/`](workflow/README.md)**: Higher-level domain pipelines (`ops.py` configuration promotion, `format.py` vendor transcript conversion, `role_recognizer.py`, `views_manager.py`, and `insight_refinements/`).
4. **[`ai/`](ai/README.md)**: Agentic & LLM integration layer (`tools/`, `mcp/`, `adk/`, `skills/`, and `policy.py`).
