-- Copyright 2026 Google.
-- Schema definitions for the Granular Topic Enrichment pipeline.

-- Replace `your_project.your_dataset` with your actual project and dataset IDs before running.

-- 1. L1 Topic Definitions (Static mapping from CCAI Insights)
CREATE TABLE IF NOT EXISTS `your_project.your_dataset.l1_topic_definitions` (
    issue_model_id STRING,
    issue_id STRING,
    display_name STRING,
    description STRING,
    exported_at TIMESTAMP
);

-- 2. L2 Taxonomy Results (Enriched output from Gemini)
CREATE TABLE IF NOT EXISTS `your_project.your_dataset.l2_taxonomy_results` (
    conversation_id STRING,
    l1_issue_id STRING,
    l2_category STRING,
    reasoning STRING,
    model_version STRING,
    processed_at TIMESTAMP
);

-- 3. Topic Refinement Audit (Execution and FinOps metrics)
CREATE TABLE IF NOT EXISTS `your_project.your_dataset.topic_refinement_audit` (
    run_id STRING,
    conversation_id STRING,
    status STRING,
    error_message STRING,
    latency_ms FLOAT64,
    input_tokens INT64,
    output_tokens INT64
);
