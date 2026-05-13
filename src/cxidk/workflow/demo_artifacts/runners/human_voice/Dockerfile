# Use an official Google Cloud Functions base image for Python 3.12
FROM us-docker.pkg.dev/cloud-functions/python/3.13:latest

# Switch to the root user to install system packages
USER root

# Update the package manager, install ffmpeg, and clean up
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Copy the requirements file and install Python dependencies
# COPY requirements.txt .
# RUN pip install -r requirements.txt

# Switch back to a non-privileged user for security
USER nonroot

# Copy the rest of the application code
COPY . .

# The base image's entrypoint will run the Functions Framework


### Command to deploy
# gcloud functions deploy cxidk-pipeline-human-voice  \
#   --gen2 \
#   --runtime=python313 \
#   --region=us-central1 \
#   --source=. \
#   --entry-point=runner \
#   --trigger-http \
#   --no-allow-unauthenticated \
#   --service-account insights-pipeline-producer@insights-pipeline-producer.iam.gserviceaccount.com \
#   --memory=4GB \
#   --cpu=2 \
#   --timeout=3600
