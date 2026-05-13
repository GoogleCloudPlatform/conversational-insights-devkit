#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status.

# --- 1. CONFIGURATION ---
# These variables define your GCP environment and service names.
# -------------------------------------------------------------
export PROJECT_ID="insights-pipeline-producer" # Your Google Cloud project ID
export REGION="us-central1"
export GCS_BUCKET_NAME="insights-pipeline-producer-configs"
export SERVICE_NAME="ces-demo-studio" # Cloud Run service name
export SERVICE_ACCOUNT_EMAIL="insights-pipeline-producer@insights-pipeline-producer.iam.gserviceaccount.com"
export REPO_NAME="ces-demo-studio-repo" # Artifact Registry Repo Name
# -------------------------------------------------------------

# --- Validation ---
if [[ "$PROJECT_ID" == "your-gcp-project-id" ]]; then
  echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
  echo "!!! ERROR: The PROJECT_ID is still the default value."
  echo "!!! Please edit the script if 'insights-pipeline-producer' is not correct."
  echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
  exit 1
fi

if [ ! -f "Dockerfile" ]; then
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo "!!! ERROR: Dockerfile not found in the current directory."
    echo "!!! Please run this script from the folder containing your application code."
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    exit 1
fi

echo "--- Configuration ---"
echo "Project ID:           $PROJECT_ID"
echo "Region:               $REGION"
echo "Service Name:         $SERVICE_NAME"
echo "Service Account:      $SERVICE_ACCOUNT_EMAIL"
echo "GCS Bucket:           $GCS_BUCKET_NAME"
echo "---------------------"
read -p "Press Enter to start deployment..."

# --- 2. GCP SETUP ---

echo "▶ Configuring gcloud to use project: $PROJECT_ID"
gcloud config set project $PROJECT_ID

echo "▶ Enabling necessary Google Cloud services..."
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    iam.googleapis.com \
    storage.googleapis.com \
    contactcenterinsights.googleapis.com

# --- 3. ARTIFACT REGISTRY ---

echo "▶ Checking for Artifact Registry repository '$REPO_NAME'..."
if ! gcloud artifacts repositories describe $REPO_NAME --location=$REGION --project=$PROJECT_ID >/dev/null 2>&1; then
  echo "  Repository not found. Creating it now..."
  gcloud artifacts repositories create $REPO_NAME \
    --repository-format=docker \
    --location=$REGION \
    --description="Repository for the CES Demo Studio service"
else
  echo "  Repository already exists."
fi

# --- 4. BUILD & PUSH ---

IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}:latest"
echo "▶ Building and pushing container image to: $IMAGE_URI"
# We assume the Dockerfile is in the current directory (.)
gcloud builds submit --tag $IMAGE_URI .

# --- 5. DEPLOY TO CLOUD RUN ---

echo "▶ Deploying container to Cloud Run service: $SERVICE_NAME"
gcloud run deploy $SERVICE_NAME \
  --image $IMAGE_URI \
  --platform managed \
  --region $REGION \
  --timeout=3600 \
  --allow-unauthenticated \
  --service-account=$SERVICE_ACCOUNT_EMAIL \
  --set-env-vars="GCS_BUCKET_NAME=$GCS_BUCKET_NAME" \
  --quiet

# --- 6. GRANT PERMISSIONS (Storage Admin) ---

echo "▶ Granting Storage Object Admin role to the service account on bucket $GCS_BUCKET_NAME..."
# Note: This assumes the bucket exists. If not, create it first or handle the error.
gcloud storage buckets add-iam-policy-binding gs://${GCS_BUCKET_NAME} \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/storage.objectAdmin" \
    --condition=None

echo "✔ Permissions granted successfully."

# --- 7. FINAL OUTPUT ---

SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format 'value(status.url)')
echo ""
echo "✔✔✔ DEPLOYMENT COMPLETE! ✔✔✔"
echo ""
echo "Your service '$SERVICE_NAME' is available at: $SERVICE_URL"
echo ""
echo "--------------------------------------------------------------------------------"
echo "NOTE: For this tool to function correctly, you must manually grant"
echo "the service account '${SERVICE_ACCOUNT_EMAIL}' the following roles on EACH"
echo "target project you add to the configuration:"
echo "  - Contact Center AI Insights Admin"
echo "  - Dialogflow API Admin"
echo "  - Storage Admin"
echo "  - Service Usage Admin"
echo "--------------------------------------------------------------------------------"
