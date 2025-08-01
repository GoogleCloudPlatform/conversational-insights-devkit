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

"""A class for all Speech related things"""

import uuid
import enum
from typing import List, Optional
from google.cloud import speech_v1
from google.cloud.speech_v1 import types as types_v1

from google.cloud import speech_v2
from google.cloud.speech_v2 import types as types_v2

from src.core import base


class AudioChannels(enum.IntEnum):
    """Audio Channels"""
    MONO = 1
    STEREO = 2

class Encodings(enum.Enum):
    "Simplification of the encodings for end users"
    LINEAR16 = types_v1.RecognitionConfig.AudioEncoding.LINEAR16.value
    FLAC = types_v1.RecognitionConfig.AudioEncoding.FLAC.value
    MULAW = types_v1.RecognitionConfig.AudioEncoding.MULAW.value
    AMR = types_v1.RecognitionConfig.AudioEncoding.AMR.value
    AMR_WB = types_v1.RecognitionConfig.AudioEncoding.AMR_WB.value
    OGG_OPUS = types_v1.RecognitionConfig.AudioEncoding.OGG_OPUS.value
    WEBM_OPUS = types_v1.RecognitionConfig.AudioEncoding.WEBM_OPUS.value

class V1:
    """Shared Speech V1 wrapper"""

    def __init__(
        self,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ):
        self.auth = auth or base.Auth()
        self.config = config or base.Config()

        self.client = speech_v1.SpeechClient(
            client_options=self.config.set_speech_endpoint()
        )

    def create_transcription(
        self,
        audio_file_path: str,
        language: str = "en-US",
        audio_type: AudioChannels = AudioChannels.STEREO,
        model: str = "latest_short",
        sample_rate: int = 8000,
        encoding: Encodings = Encodings.MULAW,
    ) -> types_v1.LongRunningRecognizeResponse:

        """Creates a transcript based from audio files"""
        operation = self.client.long_running_recognize(
            config=self._setup_recognition_config(
                channels=audio_type.value,
                audio_type=audio_type,
                language=language,
                encoding=encoding.value,
                model=model,
                sample_rate_hertz=sample_rate,
            ),
            audio=speech_v1.RecognitionAudio(uri=audio_file_path),
        )
        return operation.result()

    def _setup_recognition_config(
        self,
        language: str,
        encoding: int,
        model: str,
        sample_rate_hertz: int,
        audio_type: AudioChannels = AudioChannels.STEREO,
        channels: Optional[int] = None,
    ) -> types_v1.RecognitionConfig:
        """Setup the recognition configuration"""

        if channels:
            channel_count = channels
        else:
            channel_count = audio_type.value

        config = speech_v1.RecognitionConfig(
            audio_channel_count=channel_count,
            sample_rate_hertz=sample_rate_hertz,
            language_code=language,
            encoding=encoding,
            model=model,
            enable_automatic_punctuation=True,
            enable_word_time_offsets=True,
        )

        if channels == 1:
            config.diarization_config = speech_v1.SpeakerDiarizationConfig(
                enable_speaker_diarization=True,
                min_speaker_count=1,
                max_speaker_count=2,
            )

        return config

class V2:
    """Shared Speech V2 wrapper"""

    def __init__(
        self,
        project_id: str,
        diarization: bool = False,
        auto_decoding: bool = True,
        model: Optional[str] = "long",
        location: Optional[str] = None,
        auth: Optional[base.Auth] = None,
        translation: Optional[bool] = False,
        config: Optional[base.Config] = None,
        tmp_storage: Optional[str] = None,
        language_code: Optional[str] = "en-US",
        translate_languange: Optional[str] = None,
    ):

        self.auth = auth or base.Auth()
        self.config = config or base.Config()
        self.project_id = project_id
        self.diarization = diarization
        self.auto_decoding = auto_decoding
        self.model = model
        self.location = location
        self.translation = translation
        self.tmp_storage = tmp_storage
        self.language_code = language_code
        self.translate_languange = translate_languange

        self.client = speech_v2.SpeechClient(
            client_options=self.config.set_speech_endpoint()
        )

    def _generate_id(self, default_name: str) -> str:
        return default_name + "-" + str(uuid.uuid4())[:15].lower().replace("-", "")

    def _setup_recognizer(
        self,
        name: str,
    ) -> types_v2.Recognizer:
        recognizer = types_v2.Recognizer(
            display_name=name,
            default_recognition_config=types_v2.RecognitionConfig(
                model=self.model,
                language_codes=[self.language_code],
                features=types_v2.RecognitionFeatures(
                    profanity_filter=True,
                    enable_word_time_offsets=True,
                    enable_word_confidence=True,
                    enable_automatic_punctuation=True,
                    enable_spoken_punctuation=True,
                    enable_spoken_emojis=True,
                ),
            ),
        )

        if self.diarization:
            recognizer.default_recognition_config.features = types_v2.RecognitionFeatures(
                profanity_filter=True,
                enable_word_time_offsets=True,
                enable_word_confidence=True,
                enable_automatic_punctuation=True,
                enable_spoken_punctuation=True,
                enable_spoken_emojis=True,
                diarization_config=types_v2.SpeakerDiarizationConfig(
                    min_speaker_count = 1,
                    max_speaker_count = 2
                ),
            )

        if self.auto_decoding:
            recognizer.default_recognition_config.auto_decoding_config = (
                types_v2.AutoDetectDecodingConfig()
            )
        if self.translation:
            if self.translate_languange:
                recognizer.default_recognition_config.translation_config = (
                    types_v2.TranslationConfig(target_language=self.translate_languange)
                )
            else:
                raise AttributeError("Translate language is not set")
        return recognizer

    def create_recognizer(
        self,
        name: str = "default-insights-recognizer"
    ) -> str:
        """Creates a regocnizer with settings"""

        operation = self.client.create_recognizer(
            parent=f"projects/{self.project_id}/locations/{self.location}",
            recognizer_id=self._generate_id(name),
            recognizer=self._setup_recognizer(name),
        )
        result = operation.result()
        return result.name

    def create_transcription(
        self,
        audio_file_path: str,
        recognizer_path: Optional[str] = None,
    ) -> types_v2.RecognizeResponse:
        """Creates a transcript based from audio files"""

        if not recognizer_path:
            recognizer_path = self.create_recognizer()

        operation = self.client.batch_recognize(
            request = types_v2.BatchRecognizeRequest(
                recognizer=recognizer_path,
                files=[types_v2.BatchRecognizeFileMetadata(uri=audio_file_path)],
                recognition_output_config=types_v2.RecognitionOutputConfig(
                    gcs_output_config=types_v2.GcsOutputConfig(uri=self.tmp_storage),
                )

            )
        )
        return operation