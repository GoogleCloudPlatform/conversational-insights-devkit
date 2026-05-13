#!/bin/bash

# Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# -----------------------------------------------------------------------------
# Script to build and deploy the Topic Refinement Pipeline to Cloud Run.
# -----------------------------------------------------------------------------

# Exit on any error
set -e

# --- Configuration (Update these or set as ENV vars) ---
PROJECT_ID=$(gcloud config get-value project)
SERVICE_NAME="qai-topic-refinement"
REGION="us-central1"
IMAGE_TAG="gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest"

# Environment Variables for the Service
# Note: These should match your RefinementSettings in scripts/run_topic_refinement.py
ENV_VARS="GCP_PROJECT_ID=${PROJECT_ID},\
GCP_PROJECT_NUMBER=$(gcloud projects describe ${PROJECT_ID} --format='value(projectNumber)'),\
GCP_LOCATION_ID=${REGION},\
LLM_MODEL_NAME=gemini-3.1-flash-lite-preview,\
BQ_DATASET_ID=adk_analytics,\
BQ_MAIN_TABLE=insights,\
PROMPT_GCS_URI=gs://${PROJECT_ID}-staging/prompts/topic_refinement_v2.txt,\
CCAI_ISSUE_MODEL_ID=1234567890"

echo "--------------------------------------------------------"
echo "🚀 Starting Deployment for: ${SERVICE_NAME}"
echo "📍 Project: ${PROJECT_ID}"
echo "📍 Region:  ${REGION}"
echo "--------------------------------------------------------"

# 1. Build the container using Cloud Build
echo "📦 Building container image..."
gcloud builds submit --tag "${IMAGE_TAG}" qai_pipeline/

# 2. Deploy to Cloud Run
echo "🚀 Deploying to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
    --image "${IMAGE_TAG}" \
    --region "${REGION}" \
    --platform managed \
    --set-env-vars "${ENV_VARS}" \
    --no-allow-unauthenticated \
    --timeout 300 \
    --memory 1Gi \
    --cpu 1

# 3. Get the URL
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" --platform managed --region "${REGION}" --format='value(status.url)')

echo "--------------------------------------------------------"
echo "✅ Deployment Complete!"
echo "🔗 Service URL: ${SERVICE_URL}"
echo ""
echo "💡 To ad-hoc trigger the pipeline, run:"
echo "curl -X POST -H \"Authorization: Bearer \$(gcloud auth print-identity-token)\" \\"
echo "     -H \"Content-Type: application/json\" \\"
echo "     -d '{\"batch_size\": 50}' \\"
echo "     ${SERVICE_URL}"
echo "--------------------------------------------------------"
