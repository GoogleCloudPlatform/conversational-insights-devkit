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

from src.core import base
from src.wrapper import storage 
from src.wrapper import speech

from google.cloud.speech_v1 import types as types_v1
from google.cloud.speech_v2 import types as types_v2

_PROBER_PROJECT_ID = 'insights-python-tooling-prober'

_NEW_CONFIG = base.Config(
    region = 'europe-west1'
)

# def test_storage_other_region():
#     europe_west1_bucket = 'europe-west1-tmp-prober'
#     storage_client = storage.Gcs(
#         config = _NEW_CONFIG,
#         project_id = _PROBER_PROJECT_ID,
#         bucket_name = europe_west1_bucket        
#     )
#     list_files = storage_client.list_bucket()
#     assert list_files == ['20241018_12158479.json', '20250213_10140144.json', '20250213_34535013.json', '20250213_71063770.json', '20250213_97963193.json']


def test_speech_other_region():
    audio_location = 'gs://audios-tmp-prober/mono-audio-1-short.wav'
    sp = speech.V1(
        config = _NEW_CONFIG,
    )
    transcript = sp.create_transcription(
        audio_file_path = audio_location,
        audio_type = speech.AudioChannels.MONO,
        encoding = speech.Encodings.MULAW
    )
    assert type(transcript) is types_v1.cloud_speech.LongRunningRecognizeResponse