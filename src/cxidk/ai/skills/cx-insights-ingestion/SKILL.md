---
name: cx-insights-ingestion
description: Validate, convert, role-classify, and ingest third-party contact center transcripts (AWS Transcribe, Genesys Cloud, Speech-to-Text v2) into Google Cloud Contact Center AI Insights. Use when onboarding transcripts, running speaker diarization/role recognition, or planning bulk analysis.
---

# CCAI Insights Transcript Onboarding & Ingestion Skill

## 1. Validate & Convert Vendor Payloads Locally
- Before uploading or ingesting any third-party transcript, validate its structure with `transcript_validate(schema_format="aws" | "genesys_cloud", transcript=...)`.
- Convert deterministically using `transcript_convert(source_format=..., transcript=...)` into CCAI Insights `JsonConversationInput` (`{"entries": [...]}`).
- Verify the converted payload with `transcript_validate(schema_format="insights", transcript=...)`.
- For Speech-to-Text v2 transcripts lacking speaker roles, call `transcript_recognize_roles` to classify utterances into `CUSTOMER` (`channelTag=1`) and `AGENT` (`channelTag=2`).

## 2. Guarded Ingestion Workflow
- Stage the validated JSON transcript or audio file in Google Cloud Storage (`gs://<bucket>/<object>`).
- Always run a preflight check first: `insights_ingest_conversation(..., dry_run=True)` to validate the GCS URI, `conversation_id`, `medium`, and DLP redaction template settings without mutating project data.
- Execute the live upload (`dry_run=False`) only after human confirmation; poll completion non-blockingly via `insights_get_operation(operation_name=...)`.

## 3. Guarded Bulk Analysis
- Bulk analysis is billable per minute/conversation. Never pass an empty filter.
- Always run `insights_bulk_analyze(..., dry_run=True)` (or `insights_calculate_stats`) first and report `matched_conversations` and `estimated_analyzed_conversations` to the user before requesting confirmation for `dry_run=False`.
