# Terraform Example: Deploy `cxidk-mcp` on Google Cloud Run

Provisions a hardened, stateless Streamable HTTP deployment of `cxidk-mcp` on
**Google Cloud Run v2** (`google_cloud_run_v2_service`), matching the security
posture of [`deploy/mcp-cloud-run/`](../../../deploy/mcp-cloud-run/README.md).

## What This Module Creates

- **APIs**: `run.googleapis.com`, `secretmanager.googleapis.com`,
  `contactcenterinsights.googleapis.com`, and `dlp.googleapis.com`.
- **Least-Privilege Runtime Identity**: Dedicated service account
  (`<service_name>-sa`) granted `roles/contactcenterinsights.viewer` (or
  `roles/contactcenterinsights.editor` only when `allow_writes = true`) and
  optional `roles/dlp.user`.
- **Secret Manager Plan Signing Key**: 64-character random HS256 signing key
  stored in Secret Manager (`<service_name>-plan-signing-key`) with secret-scoped
  `roles/secretmanager.secretAccessor` so `plan_token`s verify across scaled
  instances.
- **Hardened Cloud Run v2 Service**:
  - Authenticated-only IAM (`allUsers` / `allAuthenticatedUsers` blocked via
    variable validation).
  - Application-layer JWT verification (`iap_audience` or `oauth_audience`
    enforced via variable validation).
  - `CXIDK_TRANSCRIPT_MODE=redacted` and `CXIDK_ALLOW_WRITES=false` by default.
  - Startup and liveness probes against `GET /healthz`.

## Usage

1. **Build and push the `cxidk-mcp` container image** from the repository root:

   ```bash
   export PROJECT_ID="my-gcp-project"
   export REGION="us-central1"
   export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/cxidk/cxidk-mcp:2.0.0"

   gcloud artifacts repositories create cxidk \
     --repository-format=docker \
     --location="${REGION}" \
     --project="${PROJECT_ID}"

   gcloud builds submit . \
     --project="${PROJECT_ID}" \
     --tag="${IMAGE}" \
     --file=deploy/mcp-cloud-run/Dockerfile
   ```

2. **Deploy with Terraform**:

   ```bash
   cd examples/terraform/cloud_run_mcp
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars with your project_id, container_image, and audience

   terraform init
   terraform plan
   terraform apply
   ```

3. **Connect from a Google ADK Agent**:

   ```python
   from cxidk.ai.adk import remote_insights_mcp_toolset

   toolset = remote_insights_mcp_toolset(
       mcp_url="https://cxidk-mcp-xxxx.a.run.app/mcp",
       bearer_token=id_token,
   )
   ```
