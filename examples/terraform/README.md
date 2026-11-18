# Terraform Examples (`examples/terraform/`)

Reference **Terraform (`>= 1.5`)** configurations demonstrating how to deploy
`cxidk` workloads on **Google Cloud Run** and **Cloud Run Functions (2nd Gen)**
with least-privilege IAM, Secret Manager, and explicit regional CCAI Insights
endpoints.

| Directory | Target Service | Use Case |
| :--- | :--- | :--- |
| [`cloud_run_mcp/`](cloud_run_mcp/README.md) | **Cloud Run v2 Service** (`google_cloud_run_v2_service`) | Deploy the stateless Streamable HTTP **`cxidk-mcp`** server with IAP/OIDC verification, Secret Manager `CXIDK_PLAN_SIGNING_KEY`, and default PII redaction. |
| [`cloud_run_function_ingest/`](cloud_run_function_ingest/README.md) | **Cloud Run Functions 2nd Gen** (`google_cloudfunctions2_function`) | Event-driven **GCS -> Eventarc -> Python 3.12 Function** using `cxidk` (`CxContext`, `format.Insights`, `storage.Gcs`, `insights.Ingestion`) to convert AWS / Genesys transcripts and ingest into CCAI Insights. |
