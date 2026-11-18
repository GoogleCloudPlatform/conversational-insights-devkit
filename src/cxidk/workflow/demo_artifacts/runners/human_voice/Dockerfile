# Use an official Google Cloud Functions base image for Python 3.13
FROM us-docker.pkg.dev/cloud-functions/python/3.13:latest

# Switch to the root user to install system packages
USER root

# Update the package manager, install ffmpeg, and clean up
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Copy the requirements file and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Switch back to a non-privileged user for security
USER nonroot

# Copy the rest of the application code
COPY . .

# The base image's entrypoint will run the Functions Framework


### Least-privilege IAM prerequisite on the shared config bucket:
# gcloud storage buckets add-iam-policy-binding gs://insights-pipeline-producer-configs \
#   --member="serviceAccount:insights-pipeline-runner@demos-ces.iam.gserviceaccount.com" \
#   --role="roles/storage.objectViewer"

### Command to deploy (uses ';'-delimited --set-env-vars for comma-separated allowlists)
# gcloud functions deploy cxidk-pipeline-human-voice \
#   --gen2 \
#   --runtime=python313 \
#   --region=us-central1 \
#   --source=. \
#   --entry-point=runner \
#   --trigger-http \
#   --no-allow-unauthenticated \
#   --service-account=insights-pipeline-runner@demos-ces.iam.gserviceaccount.com \
#   --set-env-vars="^;^ALLOWED_PROJECT_IDS=<COMMA_SEPARATED_PROJECT_IDS>;ALLOWED_BUCKETS=<COMMA_SEPARATED_BUCKET_NAMES>" \
#   --memory=4GB \
#   --cpu=2 \
#   --timeout=3600
