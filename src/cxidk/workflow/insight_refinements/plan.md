# QAI Pipeline Refactoring Plan: Interface Realignment (Adapter Pattern)

## Role: Staff Software Engineer / Architect Review

This document tracks the iterative, 4-stage review and implementation plan for integrating the QAI optimization pipeline with the Devkit's core tooling (`src/wrapper/insights.py` and `src/core/base.py`).

---

### 1. Architecture Review (Resolved: The Adapter Pattern)

**Status:** Approved. We will preserve the QAI pipeline's strong Pydantic foundations while cleanly interfacing with the Devkit's generic wrappers.

**Core Changes:**
1.  **Preserve `BatchAnalysisInput` (Adapter):** We will keep the robust Pydantic model. We will add helper methods (`get_auth()`, `get_config()`) to it that instantiate and return the Devkit's `src.core.base.Auth` and `src.core.base.Config` objects.
2.  **Gut `ConversationAnalyzer`:** Delete the custom HTTP pagination logic in `analysis.py`.
3.  **Adopt `Analysis.bulk()`:** We will rewrite `run_batch_analysis` to use the Devkit's `src.wrapper.insights.Analysis.bulk()` method, passing the generated `Auth` and `Config`.
4.  **Enum Translation Layer:** We will write a clean mapper to translate the pipeline's boolean `annotator_selector` dictionary into the Devkit's `Annotators` Enum list.
5.  **Preserve `bq_client.py`:** Keep the custom SQL logic, as it handles QAI-specific data transformations (unnesting sentences, structuring for LLMs) that the generic `Export.to_bq()` cannot do.

---

### 2. Code Quality & Logic (In Progress)

**Status:** Ready for implementation.

**Action Items:**
1.  **Update `src/workflow/insight_refinements/schemas/input.py`:**
    *   Import `src.core.base`.
    *   Add `get_auth()`: Returns `base.Auth()`.
    *   Add `get_config()`: Returns `base.Config(region=self.gcp.location_id)`.
2.  **Rewrite `src/workflow/insight_refinements/analysis.py`:**
    *   Remove `requests` logic, `get_oauth_token`, `get_headers`, and `refresh_token_if_unauthorized`.
    *   Delete the `ConversationAnalyzer` class.
    *   Implement an `_annotator_dict_to_enum_list()` helper.
    *   Rewrite `run_batch_analysis(config: BatchAnalysisInput)` to instantiate `src.wrapper.insights.Analysis` and call `.bulk()`.

---

### 3. Test & Validation Strategy (Resolved: Integration Focus)

**Status:** Approved.

**Strategy:**
1.  Create `tests/integration/test_insight_refinements.py`.
2.  Execute the refactored pipeline against the `insights-python-tooling-prober` GCP project.
3.  Verify that `Analysis.bulk()` successfully triggers LROs and completes the workflow without regressions.

---

### 4. Performance & Scale (Resolved)

**Status:** Approved.

**Strategy:**
Leveraging `Analysis.bulk()` (which uses the `bulk_analyze_conversations` API) shifts the scaling and concurrent execution burden to Google's backend, vastly improving reliability over manual client-side pagination.
