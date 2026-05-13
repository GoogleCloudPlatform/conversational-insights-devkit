# Use an official Google Cloud Functions base image for Python 3.12
FROM gcr.io/google-appengine/python:2024-04-18-20_00_RC00

# Switch to the root user to install system packages
USER root

# Copy the requirements file and install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Switch back to a non-privileged user for security
USER nonroot

# Copy the rest of the application code
COPY . .

# The base image's entrypoint will run the Functions Framework


### Command to deploy
# gcloud functions deploy cxidk-pipeline-agentic-chat \
#   --gen2 \
#   --runtime=python313 \
#   --region=us-central1 \
#   --source=. \
#   --entry-point=runner \
#   --trigger-http \
#   --no-allow-unauthenticated \
#   --service-account insights-pipeline-runner@demos-ces.iam.gserviceaccount.com \
#   --memory=8GB \
#   --cpu=2 \
#   --timeout=3600
