#!/bin/bash
# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -euo pipefail

# --- 1. CONFIGURATION ---
export PROJECT_ID="${PROJECT_ID:-insights-pipeline-producer}"
export REGION="${REGION:-us-central1}"
export GCS_BUCKET_NAME="${GCS_BUCKET_NAME:-insights-pipeline-producer-configs}"
export SERVICE_NAME="${SERVICE_NAME:-ces-demo-studio}"
export UI_SA_NAME="${UI_SA_NAME:-ces-demo-studio-ui}"
export SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_EMAIL:-${UI_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com}"
export REPO_NAME="${REPO_NAME:-ces-demo-studio-repo}"

# Expected Cloud Run IAP JWT audience, e.g.:
#   /projects/<PROJECT_NUMBER>/locations/<REGION>/services/<SERVICE_NAME>
# For standalone non-IAP deployments, leave IAP_EXPECTED_AUDIENCE unset and mount
# a Secret Manager secret via --set-secrets="CONFIG_API_KEY=<SECRET_NAME>:latest".
export IAP_EXPECTED_AUDIENCE="${IAP_EXPECTED_AUDIENCE:-}"

# Explicit comma-separated allowlists enforced at ingress and stats refresh:
export ALLOWED_PROJECT_IDS="${ALLOWED_PROJECT_IDS:-}"
export ALLOWED_BUCKETS="${ALLOWED_BUCKETS:-}"
export AUTHORIZED_IAP_GROUPS="${AUTHORIZED_IAP_GROUPS:-group:ccai-champions@google.com,group:aai-org@google.com}"
# -------------------------------------------------------------

# --- Validation ---
if [[ "$PROJECT_ID" == "your-gcp-project-id" ]]; then
  echo "ERROR: PROJECT_ID is still set to the placeholder value."
  exit 1
fi

if [[ ! -f "Dockerfile" ]]; then
  echo "ERROR: Dockerfile not found in the current directory."
  echo "Run this script from src/cxidk/workflow/demo_artifacts/ui/."
  exit 1
fi

if [[ -z "$IAP_EXPECTED_AUDIENCE" ]]; then
  echo "ERROR: IAP_EXPECTED_AUDIENCE must be set before deploying with Cloud Run IAP."
  echo "Example: export IAP_EXPECTED_AUDIENCE=\"/projects/987339129652/locations/${REGION}/services/${SERVICE_NAME}\""
  echo "(For standalone API-key deployments, configure Secret Manager and pass --set-secrets=\"CONFIG_API_KEY=...\" instead.)"
  exit 1
fi

if [[ -z "$ALLOWED_PROJECT_IDS" || -z "$ALLOWED_BUCKETS" ]]; then
  echo "ERROR: ALLOWED_PROJECT_IDS and ALLOWED_BUCKETS must be set (comma-separated) before deployment."
  exit 1
fi

echo "--- Configuration ---"
echo "Project ID:           $PROJECT_ID"
echo "Region:               $REGION"
echo "Service Name:         $SERVICE_NAME"
echo "UI Service Account:   $SERVICE_ACCOUNT_EMAIL"
echo "GCS Bucket:           $GCS_BUCKET_NAME"
echo "IAP Audience:         $IAP_EXPECTED_AUDIENCE"
echo "---------------------"
read -r -p "Press Enter to start deployment..."

# --- 2. GCP SETUP & DEDICATED UI SERVICE ACCOUNT ---
echo "Configuring gcloud to use project: $PROJECT_ID"
gcloud config set project "$PROJECT_ID"

echo "Enabling necessary Google Cloud services..."
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    iam.googleapis.com \
    iap.googleapis.com \
    storage.googleapis.com \
    contactcenterinsights.googleapis.com

if ! gcloud iam service-accounts describe "$SERVICE_ACCOUNT_EMAIL" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "Creating dedicated least-privilege UI service account '$SERVICE_ACCOUNT_EMAIL'..."
  gcloud iam service-accounts create "$UI_SA_NAME" \
    --project="$PROJECT_ID" \
    --display-name="CES Demo Studio UI (least privilege)"
fi

# --- 3. ARTIFACT REGISTRY ---
echo "Checking for Artifact Registry repository '$REPO_NAME'..."
if ! gcloud artifacts repositories describe "$REPO_NAME" --location="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "Creating Artifact Registry repository '$REPO_NAME'..."
  gcloud artifacts repositories create "$REPO_NAME" \
    --repository-format=docker \
    --location="$REGION" \
    --description="Repository for the CES Demo Studio service"
fi

# --- 4. BUILD & PUSH ---
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}:latest"
echo "Building and pushing container image to: $IMAGE_URI"
gcloud builds submit --tag "$IMAGE_URI" .

# --- 5. DEPLOY TO CLOUD RUN (AUTHENTICATED + IAP ONLY) ---
echo "Deploying container to Cloud Run service: $SERVICE_NAME"
# Uses custom ';'-delimited --set-env-vars syntax (^;^) so comma-separated allowlists parse cleanly.
# For standalone non-IAP deployments, replace IAP_EXPECTED_AUDIENCE with:
#   --set-secrets="CONFIG_API_KEY=ces-demo-config-api-key:latest"
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE_URI" \
  --platform managed \
  --region "$REGION" \
  --timeout=3600 \
  --no-allow-unauthenticated \
  --iap \
  --service-account="$SERVICE_ACCOUNT_EMAIL" \
  --set-env-vars="^;^GCS_BUCKET_NAME=${GCS_BUCKET_NAME};IAP_EXPECTED_AUDIENCE=${IAP_EXPECTED_AUDIENCE};ALLOWED_PROJECT_IDS=${ALLOWED_PROJECT_IDS};ALLOWED_BUCKETS=${ALLOWED_BUCKETS}" \
  --quiet

# --- 6. LEAST-PRIVILEGE BUCKET & IAP ACCESS ---
echo "Granting Storage Object User role to UI service account on gs://${GCS_BUCKET_NAME}..."
gcloud storage buckets add-iam-policy-binding "gs://${GCS_BUCKET_NAME}" \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/storage.objectUser" \
    --condition=None

IFS=',' read -r -a IAP_MEMBERS <<< "$AUTHORIZED_IAP_GROUPS"
for member in "${IAP_MEMBERS[@]}"; do
  trimmed_member="$(echo "$member" | xargs)"
  if [[ -n "$trimmed_member" ]]; then
    echo "Granting IAP-secured Web App User to authorized member ${trimmed_member}..."
    gcloud iap web add-iam-policy-binding \
      --resource-type=cloud-run \
      --service="$SERVICE_NAME" \
      --region="$REGION" \
      --member="$trimmed_member" \
      --role="roles/iap.httpsResourceAccessor"
  fi
done

# --- 7. FINAL OUTPUT ---
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --platform managed --region "$REGION" --format 'value(status.url)')
echo ""
echo "DEPLOYMENT COMPLETE: $SERVICE_URL"
echo ""
echo "--------------------------------------------------------------------------------"
echo "LEAST-PRIVILEGE IAM SEPARATION:"
echo "1. Grant the UI service account '${SERVICE_ACCOUNT_EMAIL}' ONLY:"
echo "     - roles/contactcenterinsights.viewer on each allowlisted target project"
echo "       (for conversation count refreshes; do NOT grant Storage/Dialogflow/Insights Admin)."
echo "2. Keep privileged batch generation isolated to the dedicated runner service account,"
echo "   granting that runner SA only roles/storage.objectViewer (read-only) on"
echo "   gs://${GCS_BUCKET_NAME}."
echo "--------------------------------------------------------------------------------"
