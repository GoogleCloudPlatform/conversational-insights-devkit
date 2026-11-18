# `cxidk` AI Tool-Selection & Security Red-Team Evaluations

This directory holds evaluation datasets validating tool-selection trajectories
and deterministic defense-in-depth guardrails against indirect prompt injection
in conversation transcripts:

- `tool_selection_cases.json`: Canonical prompt-to-tool trajectory benchmarks
  covering progressive disclosure (`insights_calculate_stats` before listing),
  transcript validation before conversion, and mandatory `config_plan_import`
  before `config_apply_import`.
- `prompt_injection_cases.json`: Adversarial caller utterances attempting
  cross-project exfiltration, `alg: none` JWT `plan_token` forgery, unbounded
  denial-of-wallet `insights_bulk_analyze`, and `../../` resource path traversal.

All deterministic server-side defenses for these cases are executed in CI via
`pytest tests/unit/ai/test_adk_and_evals.py`.
