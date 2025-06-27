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

import pytest
import json
import uuid
from src.wrapper import insights
from src.wrapper import speech
from src.wrapper import storage
from src.workflow import format
from src.workflow import role_recognizer as rr

from google.api_core.operation import Operation
from google.cloud.speech_v1 import types as types_v1
from google.cloud.speech_v2 import types as types_v2

_MONO_SHORT_AUDIO_LOCATION = 'gs://audios-tmp-prober/mono-audio-1-short.wav'
_MONO_AUDIO_LOCATION = 'gs://audios-tmp-prober/mono-audio-1.wav'
_SHORT_AUDIO_LOCATION = 'gs://audios-tmp-prober/stereo-audio-1-short.wav' 
_AUDIO_LOCATION = 'gs://audios-tmp-prober/stereo-audio-1.wav'

_TRANSCRIPTS_BULK_PATH = 'gs://transcripts-tmp-prober/'
_METADATA_BULK_PATH = 'gs://metadata-tmp-prober/'
_TRANSCRIPT = 'gs://transcripts-tmp-prober/conversation-15.json'

_TMP_PROBER_BUCKET = 'upload-tmp-prober'
_PROBER_PROJECT_ID = 'insights-python-tooling-prober'
_LOCATION = 'us-central1'
_PARENT = f'projects/{_PROBER_PROJECT_ID}/locations/{_LOCATION}'

def reset_insights_settings():
    """This method will reset some insights configurations and make a default configuration
    - It will delete any DLP configuration
    - It will delete any Speech configuration
    - It will set the ttl to 365 days
    - It will set the language to english
    - It will set the annotators to utilize all ootb annotators
    - It will set auto-analysis to 0%
    """
    settings = insights.Settings(
        project_id = _PROBER_PROJECT_ID,
        parent = _PARENT
    )
    settings.update_ttl(ttl_in_days = 365)
    settings.update_global_language(language_code = 'en-US')
    settings.update_global_dlp(inspect_template='', deidentify_template='')
    settings.update_global_speech(speech_recognizer_path='')
    settings.update_global_auto_analysis(
        runtime_percentage = 0,
        upload_percentage = 0,
        analysis_annotators = [insights.Annotators.INSIGHTS]
    )

## Test ingesting audio file
def test_ingest_audio():
    """Test ingesting audio files to insights"""
    reset_insights_settings()

    ingestion = insights.Ingestion(
        parent = _PARENT,
        audio_path = _SHORT_AUDIO_LOCATION
    )
    ## Short Audio ingestion, no metadata
    operation = ingestion.single()
    assert type(operation) is Operation

    ## Long Audio ingestion, no metadata
    ingestion.audio_path = _AUDIO_LOCATION
    operation = ingestion.single()
    assert type(operation) is Operation

    ## Long Audio ingestion, with metadata
    operation = ingestion.single(
        agent = {
            "name":"test",
            "id":"test001",
            "team":"test"
        },
        customer_satisfaction = 5,
        labels = {"key":"value","key1":"value1"}
    )
    assert type(operation) is Operation
    
## Test ingesting transcript
def test_ingest_transcript():
    """Test ingesting a transcript files to insights"""
    reset_insights_settings()


    ingestion = insights.Ingestion(
        parent = _PARENT,
        transcript_path = _TRANSCRIPT
    )
    ## Single transcript ingestion, no metadata
    operation = ingestion.single()
    assert type(operation) is Operation

    ## Single transcript ingestion, with metadata
    operation = ingestion.single(
        agent = {
            "name":"test",
            "id":"test001",
            "team":"test"
        },
        customer_satisfaction = 5,
        labels = {"key":"value","key1":"value1"}
    )
    assert type(operation) is Operation

    ingestion.transcript_path = _TRANSCRIPTS_BULK_PATH
    
    ## Bulk transcript ingestion, no metadata
    operation = ingestion.bulk(
        metadata_path = _METADATA_BULK_PATH
    )
    assert type(operation) is Operation

    ## Bulk transcript ingestion, with metadata
    operation = ingestion.bulk()
    assert type(operation) is Operation

## Test ingesting mono audio file with sttv1 diarization
def test_ingest_audio_with_diarization():
    """Test ingesting mono audio files to insights using STTv1 diarization"""
    reset_insights_settings()
    sp = speech.V1()
    transcript = sp.create_transcription(
        audio_file_path = _MONO_SHORT_AUDIO_LOCATION,
        audio_type = speech.AudioChannels.MONO,
        encoding = speech.Encodings.MULAW
    )
    assert type(transcript) is types_v1.cloud_speech.LongRunningRecognizeResponse

    ft = format.Speech()
    transcript = ft.v1_recognizer_to_json(transcript)

    gcs = storage.Gcs(
        project_name = _PROBER_PROJECT_ID,
        bucket_name = _TMP_PROBER_BUCKET
    )

    file_name = f'{uuid.uuid4()}.json'

    gcs.upload_blob(
        file_name = file_name,
        data = transcript
    )

    gcs_path = f"gs://{_TMP_PROBER_BUCKET}/{file_name}"
    ingestion = insights.Ingestion(
        parent = _PARENT,
        transcript_path = gcs_path
    )
    operation = ingestion.single()
    assert type(operation) is Operation

## Test ingesting transcript with role recognition
def test_ingest_audio_with_role_recognition():
    reset_insights_settings()
    sp = speech.V2(
        project_id = _PROBER_PROJECT_ID
    )
    transcript = sp.create_transcription(
        audio_file_path = _MONO_SHORT_AUDIO_LOCATION,
        recognizer_path = 'projects/668409284854/locations/global/recognizers/global-prober'
    )
    assert type(transcript) is types_v2.cloud_speech.RecognizeResponse
    
    ft = format.Speech()
    transcript = ft.v2_recognizer_to_dict(transcript)
    gcs = storage.Gcs(
        project_name = _PROBER_PROJECT_ID,
        bucket_name = _TMP_PROBER_BUCKET
    )
    file_name = f'{uuid.uuid4()}.json'
    
    role_recognizer = rr.RoleRecognizer()
    roles = role_recognizer.predict_roles(conversation=transcript)
    transcript = role_recognizer.combine(transcript, roles)

    gcs.upload_blob(
        file_name = file_name,
        data = transcript
    )
    gcs_path = f"gs://{_TMP_PROBER_BUCKET}/{file_name}"
    
    ingestion = insights.Ingestion(
        parent = _PARENT,
        transcript_path = gcs_path
    )
    operation = ingestion.single()
    
    assert type(operation) is Operation

## Test ingesting aws transcript 
def test_ingest_vendor_transcript():
    # reset_insights_settings()
    with open('tests/integration/data/aws_transcript.json', 'r') as f:
        aws_data = json.load(f)

    with open('tests/integration/data/genesys_transcript.json', 'r') as f:
        genesys_data = json.load(f)

    ##Format the files
    ft = format.Insights()
    aws_transcript = ft.from_aws(transcript= aws_data)
    genesys_transcript = ft.from_genesys_cloud(transcript= genesys_data)
    
    ## Store formated transcripts to GCS
    genesys_file_name = f'{uuid.uuid4()}_genesys.json'
    aws_file_name = f'{uuid.uuid4()}_aws.json'
    gcs = storage.Gcs(
        project_name = _PROBER_PROJECT_ID,
        bucket_name = _TMP_PROBER_BUCKET
    )
    gcs.upload_blob(
        file_name = aws_file_name,
        data = json.dumps(aws_transcript)
    )
    gcs.upload_blob(
        file_name = genesys_file_name,
        data = json.dumps(genesys_transcript)
    )

    ## Ingest the conversations
    ingestion = insights.Ingestion(
        parent = _PARENT,
        transcript_path = f'gs://{_TMP_PROBER_BUCKET}/{aws_file_name}'
    )

    ## Ingesting AWS transcript
    operation = ingestion.single(
        agent = {
            "name":"aws_transcript",
            "id":"aws_transcript",
            "team":"aws_transcript"
        }
    )
    assert type(operation) is Operation

    ## Ingesting Genesys transcript
    ingestion.transcript_path =  f'gs://{_TMP_PROBER_BUCKET}/{genesys_file_name}'
    operation = ingestion.single(
        agent = {
            "name":"genesys_transcript",
            "id":"genesys_transcript",
            "team":"genesys_transcript"
        }
    )
    assert type(operation) is Operation


