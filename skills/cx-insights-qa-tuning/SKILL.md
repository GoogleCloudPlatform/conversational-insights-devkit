---
name: cx-insights-qa-tuning
description: Evaluate, audit, and iteratively refine Contact Center AI Quality AI (QAI) scorecards and question instructions using ground-truth feedback labels, Cohens Kappa agreement, and meta-prompting workflows.
---

# CCAI Insights QA Scorecard Tuning Skill

Use this workflow when diagnosing low agreement between human QA evaluators and CCAI Quality AI scorecards or refining QA question instructions:

## 1. Inspect Scorecard Structure & Question Tags
- Call `insights_list_scorecards` to inventory scorecards with their latest revision ID/state and question counts, then `insights_get_scorecard(scorecard_id=...)` to read every question's body, answer instructions, tags, answer choices with scores, and derived `max_score` / `weight_percent`.
- Call `insights_list_scorecard_revisions(scorecard_id=...)` and `insights_get_scorecard(scorecard_id=..., revision_id=...)` to compare an older revision's rubric against the current one before proposing changes.
- Call `insights_list_resources(resource_type="qa_question_tags")` for the full custom tag catalogue; `tag_labels` on each question already resolves custom tag resource names to display names.
- Sample scored conversations using `insights_list_conversations(filter="latest_analysis:*")` followed by `insights_list_analyses(conversation_id=...)` to compare model answers and rationales against expectations.

## 2. Python Refinement Workflows (`cxidk.workflow.insight_refinements`)
When orchestrating iterative scorecard tuning in Python:
- **Scorecard inspection**: `cxidk.wrapper.insights.Scorecards(project_id, location)` exposes `list()`, `get(scorecard_id, revision_id=None)`, and `list_revisions(scorecard_id)` returning the same typed, revision-aware views the tools use.
- **Ground-truth ingestion**: `cxidk.workflow.insight_refinements.bulk_feedback` uploads human feedback labels for calibration sets.
- **Agreement evaluation**: `cxidk.workflow.insight_refinements.evaluation.EvaluationReporter` computes accuracy and Cohen's Kappa; call `.format_report()` to obtain a structured string table without stdout side effects.
- **Instruction optimization**: `cxidk.workflow.insight_refinements.optimization` uses Gemini (`cxidk.wrapper.vertex.Generator`) to propose refined question instructions based on disagreement clusters.

## 3. Safe Rollout
- Test refined scorecards in a non-production project first, then promote them via `config_export_bundle` -> `config_plan_import` -> `config_apply_import` (`activate_imported=False`).
