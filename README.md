<!-- TABLE OF CONTENTS -->
<details open="open">
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#introduction">Introduction</a>
      <ul>
        <li><a href="#what-can-i-do">What Can I Do?</a></li>
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
      <a href="#library-composition">Library Composition</a>
      <ul>
        <li><a href="#core">Core</a></li>
        <li><a href="#common">Common</a></li>
        <li><a href="#workflows">Workflows</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#license">License</a></li>
  </ol>
</details>

<!-- INTRODUCTION -->
# Introduction

The Python Conversational Insights Library is a high level API that extends the official Google [Python Client for Conversational Insights](https://cloud.google.com/python/docs/reference/contactcenterinsights/latest/google.cloud.contact_center_insights_v1.types.AnnotatorSelector). Python Conversational Insights Library makes using Conversational Insights easier, more friendly, and more pythonic for developers, and maintainers.

# What Can I Do?
With the Python Conversational Insights Library you can perform many actions at scale including, but not limited to:
- Ingest single conversations with metadata
- Ingest many conversations (bulk) with metadata
- Transcrible mono audio files using STT V1 with Diarization
- Perform Role Recognition in transcripts using Gemini
- Create recoginizers using STT V2
- Setup bq export
- Change the global settings from Conversational Insights
- Transform transcript data format from Genesys Cloud to Insights
- Transform transcript data format from AWS to Insights 
- ...and much, much more!

## Built With
* Python 3.8+

<!-- AUTHENTICATION -->
# Authentication  
Authentication can vary depending on how and where you are interacting with Library.

## Google Colab
If you're using this Library with a [Google Colab](https://colab.research.google.com/) notebook, you can add the following to the top of your notebook for easy authentication:
```py
project_id = '<YOUR_GCP_PROJECT_ID>'

# this will launch an interactive prompt that allows you to auth with GCP in a browser
!gcloud auth application-default login --no-launch-browser

# this will set your active project to the `project_id` above
!gcloud auth application-default set-quota-project $project_id
```

## Cloud Functions / Cloud Run
If you're using SCRAPI with [Cloud Functions](https://cloud.google.com/functions) or [Cloud Run](https://cloud.google.com/run), SCRAPI can pick up on the default environment creds used by these services without any additional configuration! 

1. Add this library `requirements.txt` to your cloud function `requirements.txt` file.
2. Ensure the Cloud Function / Cloud Run service account has the appropriate Dialogflow IAM Role

## Local Python Environment
Similar to Cloud Functions / Cloud Run, This Library can pick up on your local authentication creds _if you are using the gcloud CLI._

1. Install [gcloud CLI](https://cloud.google.com/sdk/docs/install).
2. Run `gcloud init`.
3. Run `gcloud auth login`
4. Run `gcloud auth list` to ensure your principal account is active.

This will authenticate your principal GCP account with the gcloud CLI, and this Library can pick up the creds from here.


<!-- GETTING STARTED -->
# Getting Started
## Environment Setup
Set up Google Cloud Platform credentials and install dependencies.
```sh
gcloud auth login
gcloud auth application-default login
gcloud config set project <project name>
```
```sh
python3 -m venv venv
source ./venv/bin/activate
pip install -r requirements.txt
```

# Library Composition
Here is a brief overview of the Python Conversational Insights Library's structure and the motivation behind that structure.

## Core  
The [Core](/src/core) folder is synonymous with the core Resource types in pretty much all classes
* This folder contains the high level building blocks
* These classes and methods can be used to build higher level methods or custom tools and applications
* This folder contain general things like Authentication and global configurations

## Common
The [Common](/src/common) folder contains the wrappers build around the current methods implemented in the SDK's the idea here is to add a new level of simplicity on top of the current implmentation. 
- Manipulate global configurations from Conversational Insights
- Ingest conversations (single and bulk) with metadata
- Create/list blobs in a GCS
- Create transcriptions from audios in STT V1 and V2
- Transcript mono audio files with STT V1

## Workflows
The [Workflows](/src/workflows) folder contains new classes and methods to fulfill current needs that the current offering doesn't support out of the box
- Format transcripts from Genesys cloud to Conversational Insights
- Format transcripts from AWS to Conversational Insights
- Format transcripts from Genesys cloud to Conversational Insights
- Recognize roles in a transcript using Gemini

<!-- USAGE -->
# Usage
Now that you're familiar with the with the structuce of the library here are some examples on how to use the functions.


## Ingest audio using role recognition
```py
sp = speech.V2(project_id = _PROBER_PROJECT_ID)
ft = format.Speech()
role_recognizer = rr.RoleRecognizer()
file_name = f'{uuid.uuid4()}.json'
transcript = sp.create_transcription(
  audio_file_path = _MONO_SHORT_AUDIO_LOCATION,
  recognizer_path = 'projects/<project-number>/locations/global/recognizers -global-prober'
)
transcript = ft.v2_recognizer_to_dict(transcript)
gcs = storage.Gcs(
  project_name = _PROBER_PROJECT_ID,
  bucket_name = _TMP_PROBER_BUCKET
)
roles = role_recognizer.predict_roles(conversation=transcript)
transcript = role_recognizer.combine(transcript, roles)
gcs.upload_blob(
  file_name = file_name,
  data = transcript
)
gcs_path = f"gs://{_TMP_PROBER_BUCKET}/{file_name}"
```

## Ingesting a conversation
```py
ingestion = insights.Ingestion(
  parent = _PARENT,
  transcript_path = gcs_path
)
operation = ingestion.single()
```

## Vendor transcript conversion
```py
with open('tests/integration/data/aws_transcript.json', 'r') as f:
  aws_data = json.load(f)

ft = format.Insights()
aws_transcript = ft.from_aws(transcript= aws_data)
```

Also check under `/tests/integration/test_ingestion.py` for more examples on how to use end-to-end the library.

<!-- CONTRIBUTING -->
# Contributing
We welcome any contributions or feature requests you would like to submit!

1. Fork the Project
2. Create your Feature Branch (git checkout -b feature/AmazingFeature)
3. Commit your Changes (git commit -m 'Add some AmazingFeature')
4. Push to the Branch (git push origin feature/AmazingFeature)
5. Open a Pull Request

<!-- LICENSE -->
# License
Distributed under the Apache 2.0 License. See [LICENSE](LICENSE.txt) for more information.