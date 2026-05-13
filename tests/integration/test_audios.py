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

"""Integration tests for the audio generation."""

import uuid
import json

from cxidk.wrapper import storage
from cxidk.workflow import audio
from cxidk.wrapper import speech

_PROJECT_ID = "insights-python-tooling-prober"
_PROBER_BUCKET = "upload-tmp-prober"
_SENTENCE = "Hi, good mornning how can I help you today?"
_FULL_TRANSCRIPT = """{
  "entries": [
    {
      "text": "Hello",
      "role": "AGENT",
      "user_id": 2,
      "start_timestamp_usec": 1000000
    },
    {
      "text": "Hi, good mornning how can I help you today?",
      "role": "CUSTOMER",
      "user_id": 1,
      "start_timestamp_usec": 2000000
    },
    {
      "text": "Yeah, I need help with my billing information",
      "role": "AGENT",
      "user_id": 2,
      "start_timestamp_usec": 3000000
    }
  ]
}
"""

def test_generate_full_audio():
    """Test generate full audio."""
    audio_generator = audio.GenerateAudio(
        project_id = _PROJECT_ID,
    )
    file_name = f"{uuid.uuid4()}.wav"
    audio_generator.single(
        transcript=json.loads(_FULL_TRANSCRIPT),
        audio_file_path=f"gs://{_PROBER_BUCKET}/{file_name}"
    )
    gcs = storage.Gcs(
        project_id = _PROJECT_ID,
        bucket_name = _PROBER_BUCKET
    )
    assert file_name in gcs.list_bucket()

def test_sythesize_sentence():
    """Test sythesize sentence."""
    sp = speech.TextToSpeech(
        project_id = _PROJECT_ID
    )
    audio_generated = sp.synthesize(
        text = _SENTENCE,
        voice = "en-US-Wavenet-D",
        language_code = "en-US",
        sample_rate_hertz = 3200
    )

    assert len(audio_generated) > 0
    assert isinstance(audio_generated, bytes)
