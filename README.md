<details open="open">
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-conversational-insights-devkit">About the Conversational Insights DevKit</a>
      <ul>
        <li><a href="#key-features">Key Features</a></li>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#environment-setup">Environment Setup</a></li>
        <li><a href="#authentication">Authentication</a></li>
      </ul>
    </li>
    <li>
      <a href="#library-architecture">Library Architecture</a>
      <ul>
        <li><a href="#core">Core</a></li>
        <li><a href="#wrapper">Wrapper</a></li>
        <li><a href="#workflows">Workflows</a></li>
      </ul>
    </li>
    <li><a href="#usage-examples">Usage Examples</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#license">License</a></li>
  </ol>
</details>

# Conversational Insights DevKit

The Conversational Insights DevKit is a high-level Python library designed to simplify and enhance your interaction with Google's [Conversational Insights API](https://cloud.google.com/python/docs/reference/contactcenterinsights/latest/google.cloud.contact_center_insights_v1.types.AnnotatorSelector). It extends the official Python Client, offering a more user-friendly and Pythonic interface for developers and maintainers looking to leverage conversational AI at scale.

## Key Features
The DevKit empowers you to perform a wide range of actions efficiently, including:
*   Ingest single or bulk conversations with associated metadata.
*   Transcribe mono audio files using Speech-to-Text V1 with diarization.
*   Perform speaker role recognition in transcripts using Gemini.
*   Create and manage Speech-to-Text V2 recognizers.
*   Configure BigQuery exports for conversational insights data.
*   Modify global Conversational Insights settings.
*   Transform transcript data formats from various vendors (e.g., Genesys Cloud, AWS) to Insights-compatible formats.
*   ...and much more, streamlining your conversational AI workflows!

## Built With
*   Python 3.8+

# Getting Started

This section guides you through setting up your development environment and authenticating with Google Cloud Platform.

## Environment Setup
Before you begin, ensure your Google Cloud Platform credentials are configured and install the necessary dependencies.

1.  **GCP CLI Setup (if not already done):**
    ```sh
    gcloud auth login
    gcloud auth application-default login # Authenticates the gcloud CLI to access Google Cloud APIs
    gcloud config set project <YOUR_GCP_PROJECT_ID>
    ```
    Replace `<YOUR_GCP_PROJECT_ID>` with your actual Google Cloud Project ID.

2.  **Install Dependencies:**
    ```sh
    python3 -m venv venv
    source ./venv/bin/activate
    python3 -m pip install -r requirements.txt
    ```

## Authentication
The DevKit supports various authentication methods, adapting to your execution environment.

### Google Colab
For Google Colab notebooks, use the following interactive authentication method:
```python
project_id = '<YOUR_GCP_PROJECT_ID>' # Replace with your GCP Project ID

# This will launch an interactive prompt to authenticate with GCP in your browser.
!gcloud auth application-default login --no-launch-browser

# This sets your active project for subsequent API calls, ensuring proper billing and quota usage.
!gcloud auth application-default set-quota-project $project_id
```

### Cloud Functions / Cloud Run
When deploying on serverless platforms like [Cloud Functions](https://cloud.google.com/functions) or [Cloud Run](https://cloud.google.com/run), the DevKit automatically picks up default environment credentials from the associated service account.

1.  Add this library to your `requirements.txt` file in your Cloud Function or Cloud Run service.
2.  Ensure the service account associated with your Cloud Function/Run service has the appropriate Dialogflow and Conversational Insights IAM roles (e.g., `Contact Center AI Insights Editor`).

### Local Python Environment
For local development, the DevKit can leverage your `gcloud CLI` credentials.

1.  Install the [gcloud CLI](https://cloud.google.com/sdk/docs/install).
2.  Initialize gcloud: `gcloud init`.
3.  Log in to your GCP account: `gcloud auth login`.
4.  Verify your active principal account: `gcloud auth list`.

This process authenticates your GCP principal account with the `gcloud CLI`, allowing the DevKit to automatically pick up these credentials for API calls.

# Library Architecture
The Conversational Insights DevKit is structured into three main components, designed for flexibility and ease of use:

## Core
Located in `src/cxidk/core`, this folder contains the fundamental building blocks of the DevKit, directly mapping to core resource types of the Conversational Insights API.
*   Offers high-level classes and methods for direct API interaction.
*   Serves as the foundation for constructing more complex tools and workflows.
*   Manages foundational functionalities such as authentication and global configurations.

## Wrapper
The `src/cxidk/wrapper` folder provides an additional layer of simplicity on top of the underlying SDK implementations.
*   Streamlines manipulation of global Conversational Insights configurations.
*   Facilitates single and bulk conversation ingestion, including metadata.
*   Manages Google Cloud Storage (GCS) blobs (creation, listing, etc.).
*   Generates transcriptions from audio files using Speech-to-Text V1 and V2.

## Workflows
The `src/cxidk/workflow` folder introduces new classes and methods designed to address common needs not directly supported by existing API offerings.
*   Transforms transcripts from vendors like Genesys Cloud to an Insights-compatible format.
*   Transforms transcripts from vendors like AWS to an Insights-compatible format.
*   Performs speaker role recognition within transcripts using Gemini.
*   QAI Scorecard Optimization: Meta-prompting workflow to evaluate and refine QA scorecard logic using Gemini 3.0 reasoning.
*   Granular Topic Refinement: End-to-end pipeline for refining CCAI Issue Models into deeper L2 categories via BigQuery and Gemini.

# Usage Examples
Now that you understand the library's structure, here are some practical examples demonstrating its core functionalities.

## Ingest Audio with Role Recognition
This example demonstrates a complete workflow: transcribing a mono audio file, performing role recognition using Gemini, combining the results, uploading the transcript to GCS, and then ingesting it into Conversational Insights.

```python
import uuid
from cxidk.workflow import role_recognizer as rr
from cxidk.wrapper import speech, format, storage
from cxidk.core import insights

# Placeholder values for demonstration. Update these with your actual details.
_PROBER_PROJECT_ID = "your-gcp-project-id"
_MONO_SHORT_AUDIO_LOCATION = "path/to/your/audio.wav" # e.g., 'data/sample_mono_audio.wav'
_TMP_PROBER_BUCKET = "your-gcs-bucket-name" # e.g., 'my-insights-temp-bucket'
_PARENT = f"projects/{_PROBER_PROJECT_ID}/locations/global" # Or specific location like 'us-central1'

# Initialize components
sp = speech.V2(project_id=_PROBER_PROJECT_ID)
ft = format.Speech()
role_recognizer = rr.RoleRecognizer()
gcs = storage.Gcs(
  project_name=_PROBER_PROJECT_ID,
  bucket_name=_TMP_PROBER_BUCKET
)

# 1. Create transcription using STT V2
transcript = sp.create_transcription(
  audio_file_path=_MONO_SHORT_AUDIO_LOCATION,
  recognizer_path='projects/<project-number>/locations/global/recognizers/<recognizer-id>' # IMPORTANT: Update with your recognizer path
)

# 2. Convert transcription to a dictionary format
transcript = ft.v2_recognizer_to_dict(transcript)

# 3. Predict roles in the transcript using Gemini
roles = role_recognizer.predict_roles(conversation=transcript)

# 4. Combine transcript with recognized roles
transcript = role_recognizer.combine(transcript, roles)

# 5. Upload the processed transcript to GCS
file_name = f'{uuid.uuid4()}.json'
gcs.upload_blob(
  file_name=file_name,
  data=transcript
)
gcs_path = f"gs://{_TMP_PROBER_BUCKET}/{file_name}"

# 6. Ingest the conversation into Conversational Insights
ingestion = insights.Ingestion(
  parent=_PARENT,
  transcript_path=gcs_path
)
operation = ingestion.single() # Initiates the ingestion and returns an operation object
print(f"Ingestion operation initiated: {operation.name}")
```

## Ingesting a Single Conversation
This example demonstrates how to ingest a pre-processed conversation from a GCS path directly into Conversational Insights.

```python
# Assuming 'gcs_path' is already defined from a previous step or directly provided
# Example: gcs_path = "gs://your-bucket/your-transcript.json"
# _PARENT should be defined as "projects/your-gcp-project-id/locations/global" or specific location

ingestion = insights.Ingestion(
  parent=_PARENT, # e.g., "projects/your-gcp-project-id/locations/global"
  transcript_path=gcs_path
)
operation = ingestion.single()
print(f"Ingestion operation initiated: {operation.name}")
```

## Vendor Transcript Conversion
Convert a transcript from a third-party vendor format (e.g., AWS) into a format compatible with Conversational Insights.

```python
import json
from cxidk.wrapper import format

# Load your AWS transcript data
# For a full example, refer to `tests/integration/data/aws_transcript.json`
with open('tests/integration/data/aws_transcript.json', 'r') as f:
  aws_data = json.load(f)

# Initialize the Insights format utility
ft = format.Insights()

# Convert the AWS transcript
aws_transcript = ft.from_aws(transcript=aws_data)

print("AWS transcript converted successfully.")
# The 'aws_transcript' variable now holds the Insights-compatible data
```

For more end-to-end examples, refer to the integration tests located under `/tests/integration/test_ingestion.py`.

# Contributing
We welcome contributions, bug reports, and feature requests! Please follow these steps to contribute:

1.  **Fork** the Project repository.
2.  **Create** your Feature Branch (`git checkout -b feature/AmazingFeature`).
3.  **Commit** your Changes (`git commit -m 'Add some AmazingFeature'`).
4.  **Push** to the Branch (`git push origin feature/AmazingFeature`).
5.  **Open** a Pull Request.

# License
Distributed under the Apache 2.0 License. See [LICENSE](LICENSE.txt) for more information.
```
