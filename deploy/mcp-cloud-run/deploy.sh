#!/usr/bin/env bash
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

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-us-central1}"
INSIGHTS_LOCATION="${INSIGHTS_LOCATION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-cxidk-mcp}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-cxidk-mcp-sa@${PROJECT_ID}.iam.gserviceaccount.com}"
PLAN_SECRET_NAME="${PLAN_SECRET_NAME:-cxidk-plan-signing-key}"
IAP_AUDIENCE="${IAP_AUDIENCE:?Set IAP_AUDIENCE (for example /projects/<num>/locations/${REGION}/services/${SERVICE_NAME})}"

echo "Deploying ${SERVICE_NAME} to Cloud Run (${PROJECT_ID}/${REGION})..."

gcloud run deploy "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --source=. \
  --dockerfile=deploy/mcp-cloud-run/Dockerfile \
  --no-allow-unauthenticated \
  --service-account="${SERVICE_ACCOUNT}" \
  --set-env-vars="CXIDK_PROJECT_ID=${PROJECT_ID},CXIDK_LOCATION=${INSIGHTS_LOCATION},CXIDK_TRANSCRIPT_MODE=redacted,CXIDK_IAP_AUDIENCE=${IAP_AUDIENCE}" \
  --set-secrets="CXIDK_PLAN_SIGNING_KEY=${PLAN_SECRET_NAME}:latest"
