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

"""Unit tests for the Cloud Speech wrapper."""

# pylint: disable=redefined-outer-name
# pylint: disable=protected-access
# pylint: disable=line-too-long
# pylint: disable=no-member
# pylint: disable=unused-argument

import uuid
from typing import Dict
from unittest.mock import MagicMock

import pytest

from cxidk.wrapper.speech import (
    V1,
    V2,
    TextToSpeech,
    AudioChannels,
    Encodings,
    types_v1,
    types_v2,
    texttospeech,
)

# --- Mocks and Fixtures ---


# Fixture to mock all external client libraries
@pytest.fixture(autouse=True)
def mock_clients(mocker: MagicMock) -> Dict[str, MagicMock]:
    """Mocks all Google Cloud clients used in the speech module."""
    mock_v1 = mocker.patch(
        "cxidk.wrapper.speech.speech_v1.SpeechClient", autospec=True
    )
    mock_v2 = mocker.patch(
        "cxidk.wrapper.speech.speech_v2.SpeechClient", autospec=True
    )
    mock_tts = mocker.patch(
        "cxidk.wrapper.speech.texttospeech.TextToSpeechClient", autospec=True
    )
    return {"v1": mock_v1, "v2": mock_v2, "tts": mock_tts}


# Fixture to mock the 'cxidk.core.base' dependency
@pytest.fixture(autouse=True)
def mock_base(mocker: MagicMock) -> Dict[str, MagicMock]:
    """Mocks cxidk.core.base.Auth and cxidk.core.base.Config."""
    # Patch 'base' as it's imported in speech.py
    mock_auth = mocker.patch("cxidk.wrapper.speech.base.Auth", autospec=True)
    mock_config = mocker.patch("cxidk.wrapper.speech.base.Config", autospec=True)

    # Add creds attribute to the mock_auth instance
    mock_auth.return_value.creds = "mock-credentials"

    # Mock the return value of the config object's method
    mock_config.return_value.set_speech_endpoint.return_value = "speech-endpoint"
    mock_config.return_value.set_texttospeech_endpoint.return_value = "tts-endpoint"

    return {"Auth": mock_auth, "Config": mock_config}


# Fixture to mock uuid.uuid4 for predictable IDs
@pytest.fixture
def mock_uuid(mocker: MagicMock) -> MagicMock:
    """Mocks uuid.uuid4 to return a fixed UUID."""
    mock_uuid_patch = mocker.patch("cxidk.wrapper.speech.uuid.uuid4", autospec=True)
    # A fixed UUID for predictable test results
    mock_uuid_patch.return_value = uuid.UUID("12345678-1234-5678-1234-567812345678")
    return mock_uuid_patch


@pytest.fixture
def mock_auth_instance() -> MagicMock:
    """Provides a mock instance of base.Auth."""
    mock_auth = MagicMock()
    mock_auth.creds = "mock-credentials"
    return mock_auth


@pytest.fixture
def mock_config_instance() -> MagicMock:
    """Provides a mock instance of base.Config."""
    mock_config = MagicMock()
    mock_config.set_speech_endpoint.return_value = "speech-endpoint"
    mock_config.set_texttospeech_endpoint.return_value = "tts-endpoint"
    return mock_config


# --- Test Class for V1 ---


class TestV1:
    """Tests for the V1 (Speech-to-Text v1) wrapper."""

    @pytest.fixture
    def v1_wrapper(self) -> V1:
        """Returns an initialized V1 wrapper with mocks."""
        return V1()

    def test_v1_init_defaults(
        self, mock_base: Dict[str, MagicMock], mock_clients: Dict[str, MagicMock]
    ) -> None:
        """Test V1 initialization with default auth and config."""
        V1()
        mock_base["Auth"].assert_called_once()
        mock_base["Config"].assert_called_once()
        mock_base["Config"].return_value.set_speech_endpoint.assert_called_once()
        mock_clients["v1"].assert_called_with(
            client_options="speech-endpoint", credentials="mock-credentials"
        )

    def test_v1_init_provided(
        self,
        mock_base: Dict[str, MagicMock],
        mock_clients: Dict[str, MagicMock],
        mock_auth_instance: MagicMock,
        mock_config_instance: MagicMock,
    ) -> None:
        """Test V1 initialization with provided auth and config."""
        V1(auth=mock_auth_instance, config=mock_config_instance)

        # Ensure default constructors are NOT called
        mock_base["Auth"].assert_not_called()
        mock_base["Config"].assert_not_called()

        # Ensure provided config is used
        mock_config_instance.set_speech_endpoint.assert_called_once()
        mock_clients["v1"].assert_called_with(
            client_options="speech-endpoint", credentials="mock-credentials"
        )

    def test_setup_recognition_config_stereo(self, v1_wrapper: V1) -> None:
        """Test _setup_recognition_config for default stereo."""
        config = v1_wrapper._setup_recognition_config(
            language="en-US",
            encoding=Encodings.LINEAR16,
            model="default",
            sample_rate_hertz=16000,
            audio_type=AudioChannels.STEREO,
        )
        assert config.audio_channel_count == 2
        # Diarization should not be set for stereo
        assert not config.diarization_config

    def test_setup_recognition_config_mono_diarization(self, v1_wrapper: V1) -> None:
        """Test _setup_recognition_config for mono (channels=1) with diarization."""
        config = v1_wrapper._setup_recognition_config(
            language="en-US",
            encoding=Encodings.LINEAR16,
            model="default",
            sample_rate_hertz=16000,
            audio_type=AudioChannels.MONO,  # This will be overridden by channels=1
            channels=1,
        )
        assert config.audio_channel_count == 1
        assert config.diarization_config
        assert config.diarization_config.enable_speaker_diarization is True
        assert config.diarization_config.min_speaker_count == 1

    def test_setup_recognition_config_explicit_channels(self, v1_wrapper: V1) -> None:
        """Test _setup_recognition_config respects explicit channels over audio_type."""
        config = v1_wrapper._setup_recognition_config(
            language="en-US",
            encoding=Encodings.LINEAR16,
            model="default",
            sample_rate_hertz=16000,
            audio_type=AudioChannels.MONO,  # This should be ignored
            channels=2,  # This should be used
        )
        assert config.audio_channel_count == 2
        # Diarization should not be set for 2 channels
        assert not config.diarization_config

    def test_create_transcription(self, v1_wrapper: V1, mocker: MagicMock) -> None:
        """Test the create_transcription method."""
        mock_operation = MagicMock()
        mock_operation.result.return_value = "transcription_result"

        v1_wrapper.client.long_running_recognize.return_value = mock_operation # type: ignore[attr-defined]

        # Mock the config setup to isolate the test
        mocker.patch.object(
            v1_wrapper, "_setup_recognition_config", return_value="mock_config"
        )

        gcs_uri = "gs://bucket/file.wav"
        result = v1_wrapper.create_transcription(
            audio_file_path=gcs_uri,
            language="es-US",
            audio_type=AudioChannels.MONO,
            model="short",
            sample_rate=16000,
            encoding=Encodings.LINEAR16,
        )

        v1_wrapper._setup_recognition_config.assert_called_once_with( # type: ignore[attr-defined]
            channels=1,
            audio_type=AudioChannels.MONO,
            language="es-US",
            encoding=Encodings.LINEAR16,
            model="short",
            sample_rate_hertz=16000,
        )

        mock_audio = types_v1.RecognitionAudio(uri=gcs_uri)
        v1_wrapper.client.long_running_recognize.assert_called_once_with( # type: ignore[attr-defined]
            config="mock_config",
            audio=mock_audio,
        )
        assert result == "transcription_result"


# --- Test Class for V2 ---


class TestV2:
    """Tests for the V2 (Speech-to-Text v2) wrapper."""

    PROJECT_ID = "test-project"
    LOCATION = "global"

    @pytest.fixture
    def v2_wrapper(self) -> V2:
        """Returns a default V2 wrapper."""
        return V2(project_id=self.PROJECT_ID, location=self.LOCATION)

    def test_v2_init_defaults(
        self, mock_base: Dict[str, MagicMock], mock_clients: Dict[str, MagicMock]
    ) -> None:
        """Test V2 initialization with default parameters."""
        V2(project_id=self.PROJECT_ID)
        mock_base["Auth"].assert_called_once()
        mock_clients["v2"].assert_called_with(
            client_options="speech-endpoint", credentials="mock-credentials"
        )

    def test_v2_init_provided(
        self,
        mock_base: Dict[str, MagicMock],
        mock_clients: Dict[str, MagicMock],
        mock_auth_instance: MagicMock,
        mock_config_instance: MagicMock,
    ) -> None:
        """Test V2 initialization with provided auth and config."""
        v2 = V2(
            project_id=self.PROJECT_ID,
            auth=mock_auth_instance,
            config=mock_config_instance,
            diarization=True,
            model="telephony",
            language_code="fr-FR",
        )

        mock_base["Auth"].assert_not_called()
        mock_base["Config"].assert_not_called()
        mock_clients["v2"].assert_called_with(
            client_options="speech-endpoint", credentials="mock-credentials"
        )

        assert v2.diarization is True
        assert v2.model == "telephony"
        assert v2.language_code == "fr-FR"

    def test_generate_id(self, v2_wrapper: V2, mock_uuid: MagicMock) -> None:
        """Test _generate_id produces a predictable ID."""
        name = "test-name"
        expected_id = "test-name-1234567812345"
        result = v2_wrapper._generate_id(name)

        mock_uuid.assert_called_once()
        assert result == expected_id

    def test_setup_recognizer_default(self, v2_wrapper: V2) -> None:
        """Test _setup_recognizer with default options."""
        recognizer = v2_wrapper._setup_recognizer(name="test")

        assert recognizer.default_recognition_config.model == "long"
        assert recognizer.default_recognition_config.language_codes == ["en-US"]
        # Default: Auto decoding IS enabled
        assert recognizer.default_recognition_config.auto_decoding_config is not None
        # Default: Diarization is NOT enabled
        assert not recognizer.default_recognition_config.features.diarization_config
        # Default: Translation is NOT enabled
        assert not recognizer.default_recognition_config.translation_config

    def test_setup_recognizer_diarization(self) -> None:
        """Test _setup_recognizer with diarization enabled."""
        v2 = V2(project_id=self.PROJECT_ID, diarization=True)
        recognizer = v2._setup_recognizer(name="test")
        assert recognizer.default_recognition_config.features.diarization_config
        assert (
            recognizer.default_recognition_config.features.diarization_config.min_speaker_count
            == 1
        )

    def test_setup_recognizer_no_auto_decoding(self) -> None:
        """Test _setup_recognizer with auto_decoding disabled."""
        v2 = V2(project_id=self.PROJECT_ID, auto_decoding=False)
        recognizer = v2._setup_recognizer(name="test")
        assert not recognizer.default_recognition_config.auto_decoding_config

    def test_setup_recognizer_translation_ok(self) -> None:
        """Test _setup_recognizer with translation enabled."""
        v2 = V2(
            project_id=self.PROJECT_ID,
            translation=True,
            translate_languange="es",
        )
        recognizer = v2._setup_recognizer(name="test")
        assert recognizer.default_recognition_config.translation_config
        assert (
            recognizer.default_recognition_config.translation_config.target_language
            == "es"
        )

    def test_setup_recognizer_translation_fail(self) -> None:
        """Test _setup_recognizer raises error if translation is on but language is missing."""
        v2 = V2(project_id=self.PROJECT_ID, translation=True, translate_languange=None)
        with pytest.raises(AttributeError, match="Translate language is not set"):
            v2._setup_recognizer(name="test")


    def test_create_recognizer(self, v2_wrapper: V2, mock_uuid: MagicMock) -> None:
        """Test create_recognizer method."""
        mock_operation = MagicMock()
        mock_operation.result.return_value.name = "recognizer-name"
        v2_wrapper.client.create_recognizer.return_value = mock_operation # type: ignore[attr-defined]

        expected_id = "default-insights-recognizer-1234567812345"

        result = v2_wrapper.create_recognizer()

        assert result == "recognizer-name"
        v2_wrapper.client.create_recognizer.assert_called_once() # type: ignore[attr-defined]
        call_args = v2_wrapper.client.create_recognizer.call_args[1] # type: ignore[attr-defined]

        assert (
            call_args["parent"]
            == f"projects/{self.PROJECT_ID}/locations/{self.LOCATION}"
        )
        assert call_args["recognizer_id"] == expected_id
        assert call_args["recognizer"].display_name == "default-insights-recognizer"

    def test_create_transcription_with_recognizer(self, v2_wrapper: V2) -> None:
        """Test create_transcription with an existing recognizer path."""
        mock_operation = MagicMock()
        mock_operation.result.return_value = "transcription_result_v2"
        v2_wrapper.client.batch_recognize.return_value = mock_operation # type: ignore[attr-defined]

        recognizer_path = "projects/p/locations/l/recognizers/r"
        gcs_uri = "gs://bucket/file.mp3"
        v2_wrapper.tmp_storage = "gs://tmp-bucket"

        result = v2_wrapper.create_transcription(
            audio_file_path=gcs_uri,
            recognizer_path=recognizer_path,
        )

        assert result == "transcription_result_v2"

        expected_request = types_v2.BatchRecognizeRequest(
            recognizer=recognizer_path,
            files=[types_v2.BatchRecognizeFileMetadata(uri=gcs_uri)],
            recognition_output_config=types_v2.RecognitionOutputConfig(
                gcs_output_config=types_v2.GcsOutputConfig(uri="gs://tmp-bucket"),
            ),
        )
        v2_wrapper.client.batch_recognize.assert_called_once_with( # type: ignore[attr-defined]
            request=expected_request
        )

    def test_create_transcription_no_recognizer(
        self, v2_wrapper: V2, mocker: MagicMock
    ) -> None:
        """Test create_transcription creates a recognizer if none is provided."""
        mock_operation = MagicMock()
        mock_operation.result.return_value = "transcription_result_v2"
        v2_wrapper.client.batch_recognize.return_value = mock_operation # type: ignore[attr-defined]

        # Mock the create_recognizer method
        mock_create = mocker.patch.object(
            v2_wrapper, "create_recognizer", return_value="new-recognizer-path"
        )

        gcs_uri = "gs://bucket/file.mp3"
        result = v2_wrapper.create_transcription(audio_file_path=gcs_uri)

        # Ensure it created a new recognizer
        mock_create.assert_called_once()

        assert result == "transcription_result_v2"

        # Ensure batch_recognize was called with the *new* path
        call_args = v2_wrapper.client.batch_recognize.call_args[1] # type: ignore[attr-defined]
        assert call_args["request"].recognizer == "new-recognizer-path"


# --- Test Class for TextToSpeech ---


class TestTextToSpeech:
    """Tests for the TextToSpeech wrapper."""

    PROJECT_ID = "tts-project"

    @pytest.fixture
    def tts_wrapper(self) -> TextToSpeech:
        """Returns an initialized TextToSpeech wrapper."""
        return TextToSpeech(project_id=self.PROJECT_ID)

    def test_tts_init_defaults(
        self, mock_base: Dict[str, MagicMock], mock_clients: Dict[str, MagicMock]
    ) -> None:
        """Test TextToSpeech initialization with default auth and config."""
        TextToSpeech(project_id=self.PROJECT_ID)
        mock_base["Auth"].assert_called_once()
        config_mock = mock_base["Config"]
        config_mock.assert_called_once()
        config_mock.return_value.set_texttospeech_endpoint.assert_called_once()
        mock_clients["tts"].assert_called_with(
            client_options="tts-endpoint", credentials="mock-credentials"
        )

    def test_tts_init_provided(
        self,
        mock_base: Dict[str, MagicMock],
        mock_clients: Dict[str, MagicMock],
        mock_auth_instance: MagicMock,
        mock_config_instance: MagicMock,
    ) -> None:
        """Test TextToSpeech initialization with provided auth and config."""
        TextToSpeech(
            project_id=self.PROJECT_ID,
            auth=mock_auth_instance,
            config=mock_config_instance,
        )

        mock_base["Auth"].assert_not_called()
        mock_config_instance.set_texttospeech_endpoint.assert_called_once()
        mock_clients["tts"].assert_called_with(
            client_options="tts-endpoint", credentials="mock-credentials"
        )

    def test_synthesize(self, tts_wrapper: TextToSpeech) -> None:
        """Test the synthesize method."""
        mock_response = MagicMock()
        mock_response.audio_content = b"fake_audio_bytes"
        tts_wrapper.client.synthesize_speech.return_value = mock_response # type: ignore[attr-defined]

        text = "Hello world"
        result = tts_wrapper.synthesize(
            text=text,
            voice="en-US-Test-A",
            language_code="en-US",
            sample_rate_hertz=16000,
        )

        assert result == b"fake_audio_bytes"

        expected_input = texttospeech.SynthesisInput(text=text)
        expected_voice = texttospeech.VoiceSelectionParams(
            language_code="en-US", name="en-US-Test-A"
        )
        expected_audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
        )

        tts_wrapper.client.synthesize_speech.assert_called_once_with( # type: ignore[attr-defined]
            input=expected_input,
            voice=expected_voice,
            audio_config=expected_audio_config,
        )
