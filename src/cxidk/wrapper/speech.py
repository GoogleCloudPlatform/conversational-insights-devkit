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

"""A wrapper for Google Cloud Speech-to-Text and Text-to-Speech APIs.

This module provides classes to simplify interactions with Google Cloud's
speech services. It includes wrappers for both v1 and v2 of the Speech-to-Text
API for transcription, and a wrapper for the Text-to-Speech API for synthesizing
speech from text.
"""

import uuid
import enum
from typing import Optional
from google.cloud import texttospeech
from google.cloud import speech_v1
from google.cloud.speech_v1 import types as types_v1

from google.cloud import speech_v2
from google.cloud.speech_v2 import types as types_v2

from cxidk.core import base

_GS_PREFIX = "gs://"
_TMP_DEFAULT_STORAGE = "/tmp"

class AudioChannels(enum.IntEnum):
    """Enum for audio channel options."""
    MONO = 1
    STEREO = 2

class Encodings(enum.Enum):
    """Enum for audio encoding types, simplifying options for the user."""
    LINEAR16 = types_v1.RecognitionConfig.AudioEncoding.LINEAR16
    FLAC = types_v1.RecognitionConfig.AudioEncoding.FLAC
    MULAW = types_v1.RecognitionConfig.AudioEncoding.MULAW
    AMR = types_v1.RecognitionConfig.AudioEncoding.AMR
    AMR_WB = types_v1.RecognitionConfig.AudioEncoding.AMR_WB
    OGG_OPUS = types_v1.RecognitionConfig.AudioEncoding.OGG_OPUS
    WEBM_OPUS = types_v1.RecognitionConfig.AudioEncoding.WEBM_OPUS

class V1:
    """A wrapper for the Google Cloud Speech-to-Text v1 API.

    Attributes:
        auth: An authentication object.
        config: A configuration object.
        client: A Speech-to-Text v1 client.
    """

    def __init__(
        self,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ):
        """Initializes the V1 wrapper.
        
        Args:
            auth: An optional, pre-configured authentication object.
            config: An optional, pre-configured configuration object.
        """
        self.auth = auth or base.Auth()
        self.config = config or base.Config()

        self.client = speech_v1.SpeechClient(
            credentials=self.auth.creds,
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

        """Transcribes a long audio file using the Speech-to-Text v1 API.

        Args:
            audio_file_path: The GCS URI of the audio file (e.g., 'gs://bucket/file.wav').
            language: The BCP-47 language code of the speech in the audio.
            audio_type: The number of audio channels (mono or stereo).
            model: The recognition model to use (e.g., 'latest_short').
            sample_rate: The sample rate of the audio in Hertz.
            encoding: The audio encoding type (e.g., MULAW, LINEAR16).

        Returns:
            The result of the long-running recognition operation.
        """
        operation = self.client.long_running_recognize(
            config=self._setup_recognition_config(
                channels=audio_type.value,
                audio_type=audio_type,
                language=language,
                encoding=encoding,
                model=model,
                sample_rate_hertz=sample_rate,
            ),
            audio=speech_v1.RecognitionAudio(uri=audio_file_path),
        )
        return operation.result()

    def _setup_recognition_config(
        self,
        language: str,
        encoding: Encodings,
        model: str,
        sample_rate_hertz: int,
        audio_type: AudioChannels = AudioChannels.STEREO,
        channels: Optional[int] = None,
    ) -> types_v1.RecognitionConfig:
        """Sets up the recognition configuration for a v1 transcription request.

        Args:
            language: The BCP-47 language code of the speech.
            encoding: The audio encoding type.
            model: The recognition model to use.
            sample_rate_hertz: The sample rate of the audio in Hertz.
            audio_type: The number of audio channels (mono or stereo).
            channels: Overrides `audio_type` with a specific channel count.

        Returns:
            A configured `RecognitionConfig` object for a v1 API request.
        """

        if channels:
            channel_count = channels
        else:
            channel_count = audio_type.value

        config = speech_v1.RecognitionConfig(
            audio_channel_count=channel_count,
            sample_rate_hertz=sample_rate_hertz,
            language_code=language,
            encoding=encoding.value,
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
    """A wrapper for the Google Cloud Speech-to-Text v2 API.

    Attributes:
        project_id: The Google Cloud project ID.
        diarization: Whether to enable speaker diarization.
        auto_decoding: Whether to enable auto-decoding.
        model: The recognition model to use.
        location: The location of the Speech-to-Text service.
        auth: An authentication object.
        translation: Whether to enable translation.
        config: A configuration object.
        tmp_storage: A temporary storage location for transcription results.
        language_code: The language of the speech in the audio.
        translate_languange: The target language for translation.
        client: A Speech-to-Text v2 client.
    """

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
        """Initializes the V2 wrapper.

        Args:
            project_id: The Google Cloud project ID.
            diarization: If True, enables speaker diarization.
            auto_decoding: If True, enables automatic decoding of audio properties.
            model: The recognition model to use (e.g., 'long').
            location: The Google Cloud location for the Speech-to-Text service.
            auth: An optional, pre-configured authentication object.
            translation: If True, enables speech translation.
            config: An optional, pre-configured configuration object.
            tmp_storage: A GCS URI for storing temporary transcription results.
            language_code: The BCP-47 language code of the speech.
            translate_languange: The target BCP-47 language code for translation.
        """

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
            credentials=self.auth.creds,
            client_options=self.config.set_speech_endpoint()
        )

    def _generate_id(self, default_name: str) -> str:
        """Generates a unique ID for a resource.

        Args:
            default_name: The default name to use as a prefix.

        Returns:
            A unique ID string prefixed with the default name.
        """
        return default_name + "-" + str(uuid.uuid4())[:15].lower().replace("-", "")

    def _setup_recognizer(
        self,
        name: str,
    ) -> types_v2.Recognizer:
        """Configures a Recognizer object for a v2 transcription request.

        Args:
            name: The display name for the recognizer.

        Returns:
            A configured `Recognizer` object for a v2 API request.
        """
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
        """Creates a Recognizer resource in the Speech-to-Text v2 API.

        Args:
            name: The display name for the recognizer.

        Returns:
            The full resource name of the created recognizer.
        """

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
    ) -> types_v2.BatchRecognizeResponse:
        """Transcribes a long audio file using the Speech-to-Text v2 API.

        Args:
            audio_file_path: The GCS URI of the audio file (e.g., 'gs://bucket/file.wav').
            recognizer_path: The full resource name of the recognizer to use.
                If not provided, a new default recognizer will be created.

        Returns:
            The result of the batch recognition operation.
        """

        if not recognizer_path:
            recognizer_path = self.create_recognizer()

        # tmp_storage is mandatory for bactch recognize
        # if it's not passed we will use the same bucket
        if not self.tmp_storage:
            self.tmp_storage = audio_file_path.split("/")[2]
            self.tmp_storage = _GS_PREFIX + self.tmp_storage + _TMP_DEFAULT_STORAGE

        operation = self.client.batch_recognize(
            request=types_v2.BatchRecognizeRequest(
                recognizer=recognizer_path,
                files=[types_v2.BatchRecognizeFileMetadata(uri=audio_file_path)],
                recognition_output_config=types_v2.RecognitionOutputConfig(
                    gcs_output_config=types_v2.GcsOutputConfig(uri=self.tmp_storage),
                ),
            )
        )

        return operation.result()

class TextToSpeech:
    """A wrapper for the Google Cloud Text-to-Speech API.

    Attributes:
        project_id: The Google Cloud project ID.
        auth: An authentication object.
        config: A configuration object.
        client: A Text-to-Speech client.
    """

    def __init__(
        self,
        project_id: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    )->None:
        """Initializes the TextToSpeech wrapper.

        Args:
            project_id: The Google Cloud project ID.
            auth: An optional, pre-configured authentication object.
            config: An optional, pre-configured configuration object.
        """
        self.auth = auth or base.Auth()
        self.config = config or base.Config()
        self.project_id = project_id

        self.client = texttospeech.TextToSpeechClient(
            credentials=self.auth.creds,
            client_options=self.config.set_texttospeech_endpoint()
        )

    def synthesize(
        self,
        text: str,
        voice: str = "en-US-Wavenet-D",
        language_code: Optional[str]= "en-US",
        sample_rate_hertz: int = 32000
    ):
        """Synthesizes speech from a string of text.

        Args:
            text: The input text to synthesize.
            voice: The name of the voice to use (e.g., 'en-US-Wavenet-D').
            language_code: The BCP-47 language code of the voice.
            sample_rate_hertz: The desired sample rate of the output audio in Hertz.

        Returns:
            The synthesized audio content as raw bytes.
        """

        synthesis_input = texttospeech.SynthesisInput(text=text)

        voice = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=voice
        )
        #TO-DO: Support multiple encoding selection
        response = self.client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.LINEAR16,
                sample_rate_hertz=sample_rate_hertz
            )
        )
        return response.audio_content
