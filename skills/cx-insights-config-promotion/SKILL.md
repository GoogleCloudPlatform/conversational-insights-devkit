---
name: cx-insights-config-promotion
description: Export, dry-run plan, and safely promote Contact Center AI Insights configuration assets (QA scorecards, phrase matchers, issue models, analysis rules, auto-labeling rules, assessment rules) across environments (dev -> staging -> prod).
---

# CCAI Insights Configuration Promotion Skill

`cxidk` enforces **create-only, non-destructive** configuration promotion backed by cryptographic `plan_token` verification.

## Mandatory 4-Step Promotion Sequence

1. **Inspect Source & Destination**:
   - Use `insights_get_settings`, `insights_list_scorecards`, and `insights_list_resources` to audit active resources in the source and destination projects/locations.
   - Use `insights_get_scorecard(scorecard_id=...)` to capture the exact question set, answer scores, and tags of the latest revision that export will carry.
2. **Export Atomic GCS Bundle**:
   - Call `config_export_bundle(bundle_uri="gs://<bucket>/<path>.json", project_id=source_project, location=source_location)`.
   - Only active resources are exported by default (`active_only=True`).
3. **Generate Dry-Run Plan & Signed `plan_token`**:
   - Call `config_plan_import(bundle_uri=..., project_id=dest_project, location=dest_location, activate_imported=False)`.
   - Review `will_create`, `name_clashes`, and `cost_notes` with the operator.
4. **Confirmed Create-Only Apply**:
   - Only after explicit operator approval, call `config_apply_import` passing the exact `plan_token`, `bundle_uri`, `project_id`, `location`, and `assets` used during planning.
   - Keep `activate_imported=False` so imported `analysis_rules` land **INACTIVE** and incur zero immediate billing until deliberately enabled.
   - Remember: `issue_models` (topic models) are never auto-deployed by import because deployment is billable.
   - Verify parity afterwards with `insights_get_scorecard` against the destination project: question count, `total_max_score`, and `tag_labels` should match the source (imported scorecards arrive untuned, so `metrics` are expected to be absent).
