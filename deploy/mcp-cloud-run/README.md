# Deploying `cxidk-mcp` on Google Cloud Run

This directory provides a hardened, stateless Streamable HTTP deployment of the
Conversational Insights DevKit MCP server (`cxidk-mcp`) on Google Cloud Run.

## Security Defaults

1. **Authenticated Ingress Only**: Deployed with `--no-allow-unauthenticated` and
   verified at the application layer via Identity-Aware Proxy (`CXIDK_IAP_AUDIENCE`)
   or OIDC Bearer tokens (`CXIDK_OAUTH_AUDIENCE`).
2. **No Token Passthrough**: Incoming client tokens authenticate the caller *to*
   `cxidk-mcp` only and are never forwarded to downstream Google Cloud APIs.
3. **Default Transcript Redaction**: `CXIDK_TRANSCRIPT_MODE=redacted` masks PII
   via Cloud DLP (when `CXIDK_DLP_DEIDENTIFY_TEMPLATE` is configured) plus regex
   defense-in-depth scrubbing.
4. **Read-Only by Default**: Mutating tools (`writes` toolset) are excluded unless
   `CXIDK_ALLOW_WRITES=true` is explicitly configured.
5. **Secret Manager Signing Key**: `CXIDK_PLAN_SIGNING_KEY` (>= 32 random bytes)
   is mounted from Secret Manager so `config_plan_import` / `config_apply_import`
   tokens verify across horizontally scaled Cloud Run instances.

## Prerequisites

```bash
export PROJECT_ID="my-gcp-project"
export REGION="us-central1"

# 1. Create dedicated least-privilege service account
gcloud iam service-accounts create cxidk-mcp-sa --project="${PROJECT_ID}"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:cxidk-mcp-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/contactcenterinsights.viewer"

# 2. Store 32-byte HS256 signing key in Secret Manager
openssl rand -hex 32 | gcloud secrets create cxidk-plan-signing-key \
  --project="${PROJECT_ID}" --data-file=-

gcloud secrets add-iam-policy-binding cxidk-plan-signing-key \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:cxidk-mcp-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

## Deploy

```bash
export IAP_AUDIENCE="/projects/1234567890/locations/${REGION}/services/cxidk-mcp"
bash deploy/mcp-cloud-run/deploy.sh
```

## Deploy (Terraform)

For a full Infrastructure-as-Code deployment (APIs, least-privilege service account,
Secret Manager signing key, and Cloud Run v2 service), see
[`examples/terraform/cloud_run_mcp/`](../../examples/terraform/cloud_run_mcp/README.md).

## Endpoints

- `GET /healthz`: Readiness / liveness probe (`200 OK`)
- `POST /mcp`: Stateless MCP Streamable HTTP JSON-RPC endpoint
