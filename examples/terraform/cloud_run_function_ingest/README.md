# Terraform Example: Event-Driven CCAI Insights Ingestion on Cloud Run Functions

Deploys a **2nd-Gen Cloud Run Function** (`google_cloudfunctions2_function`)
triggered via **Eventarc** whenever a transcript JSON file lands in Google Cloud
Storage, using `cxidk` as a Python library to normalize vendor payloads and
ingest them into CCAI Insights.

## Architecture & Routing

```text
gs://<transcripts-bucket>/
├── raw/aws/<call_id>.json      ──► cxidk.workflow.format.Insights.from_aws()      ──► staging/<call_id>.json ──► CCAI Insights
├── raw/genesys/<call_id>.json  ──► cxidk.workflow.format.Insights.from_genesys_cloud() ──► staging/<call_id>.json ──► CCAI Insights
├── raw/insights/<call_id>.json ─────────────────────────────────────────────────────────────────────────────► CCAI Insights
└── staging/<call_id>.json      ──► Ignored by handler (prevents recursive Eventarc loops)
```

## Security Posture

- **Private Buckets**: Uniform bucket-level access and
  `public_access_prevention = "enforced"` on both landing and source buckets.
- **Internal-Only Ingress**: `ingress_settings = "ALLOW_INTERNAL_ONLY"` with
  `roles/run.invoker` granted exclusively to the dedicated Eventarc/runtime
  service account.
- **Bucket-Scoped Storage IAM**: `roles/storage.objectAdmin` is bound only to
  the landing bucket rather than project-wide.
- **Explicit Regional Endpoints**: `CXIDK_LOCATION` is validated against
  `"global"` and resolved via `CxContext.from_env()`.

## Usage

1. *(If `cxidk` is not yet published to an Artifact Registry Python repo)* build
   a wheel into `function/vendor/` and reference `./vendor/cxidk-2.0.0-py3-none-any.whl`
   in `function/requirements.txt`:

   ```bash
   python -m build --wheel --outdir examples/terraform/cloud_run_function_ingest/function/vendor
   ```

2. **Deploy with Terraform**:

   ```bash
   cd examples/terraform/cloud_run_function_ingest
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars with your project_id

   terraform init
   terraform plan
   terraform apply
   ```

3. **Test End-to-End Ingestion**:

   ```bash
   BUCKET="$(terraform output -raw transcripts_bucket_name)"
   gcloud storage cp sample_aws_transcript.json "gs://${BUCKET}/raw/aws/call-1001.json"
   ```
