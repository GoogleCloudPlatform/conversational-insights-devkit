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

"""Unit tests for the V1 and V2 classes."""

from typing import Any
from unittest import mock
from unittest.mock import MagicMock

import pytest

from google.cloud.speech_v1 import types as types_v1
from google.cloud.speech_v2 import types as types_v2

from src.wrapper.speech import V1, V2


@pytest.fixture(name="mock_v1_speech_client")
def fixture_mock_v1_speech_client():
    """Mocks the Google Cloud Speech V1 Client."""
    with mock.patch("google.cloud.speech_v1.SpeechClient") as mock_client:
        yield mock_client.return_value


@pytest.fixture(name="mock_v2_speech_client")
def fixture_mock_v2_speech_client():
    """Mocks the Google Cloud Speech V2 Client."""
    with mock.patch("google.cloud.speech_v2.SpeechClient") as mock_client:
        yield mock_client.return_value


@pytest.fixture(name="v1_instance")
def fixture_v1_instance(mock_v1_speech_client: Any):
    """Creates an instance of the V1 class with mocks."""
    # Disable for testing, if removed tests fails
    # pylint: disable=pointless-statement
    mock_v1_speech_client
    return V1(auth=mock.MagicMock(), config=mock.MagicMock())


@pytest.fixture(name="v2_instance")
def dixture_v2_instance(mock_v2_speech_client: Any):
    """Creates an instance of the V2 class with mocks."""
    # Disable for testing, if removed tests fails
    # pylint: disable=pointless-statement
    mock_v2_speech_client
    return V2(
        project_id="test-project",
        location="test-location",
        auth=mock.MagicMock(),
        config=mock.MagicMock(),
    )


def test_v1_create_transcription(v1_instance: V1, mock_v1_speech_client: Any):
    """Tests the create_transcription method."""
    mock_long_running_recognize = MagicMock()
    mock_long_running_recognize.return_value.result.return_value = (
        types_v1.LongRunningRecognizeResponse()
    )
    mock_v1_speech_client.long_running_recognize = mock_long_running_recognize
    v1_instance.create_transcription(audio_file_path="gs://test-bucket/test-audio.wav")
    mock_long_running_recognize.assert_called_once()


def test_v1_setup_number_of_channels_invalid(v1_instance: V1):
    """Tests the _setup_number_of_channels method with an invalid audio type."""
    with pytest.raises(ValueError):
        # Disabeling for testing pylint: disable=W0212
        v1_instance._setup_number_of_channels("invalid")


def test_v1_setup_recognition_config(v1_instance: V1):
    """Tests the _setup_recognition_config method."""
    # Disabeling for testing pylint: disable=W0212
    config = v1_instance._setup_recognition_config(
        language="en-US",
        encoding="LINEAR16",
        model="latest_short",
        sample_rate_hertz=8000,
        audio_type="stereo",
    )
    assert isinstance(config, types_v1.RecognitionConfig)


def test_v2_generate_id(v2_instance: V2):
    """Tests the _generate_id method."""
    # Disabeling for testing pylint: disable=W0212
    generated_id = v2_instance._generate_id("test-recognizer")
    # Assert that the ID starts with the provided name and has a UUID part
    assert generated_id.startswith("test-recognizer-")
    assert len(generated_id) > len("test-recognizer-")


def test_v2_setup_recognizer(v2_instance: V2):
    """Tests the _setup_recognizer method."""
    # Disabeling for testing pylint: disable=W0212
    recognizer = v2_instance._setup_recognizer(name="test-recognizer")
    assert isinstance(recognizer, types_v2.Recognizer)


def test_v2_create_recognizer(v2_instance: V2, mock_v2_speech_client: Any):
    """Tests the create_recognizer method."""
    mock_create_recognizer = MagicMock()
    mock_create_recognizer.return_value.result.return_value.name = (
        "projects/test-project/locations/test-location/recognizers/test-recognizer-id"
    )
    mock_v2_speech_client.create_recognizer = mock_create_recognizer
    recognizer_path = v2_instance.create_recognizer(name="test-recognizer")
    assert (
        recognizer_path
        == "projects/test-project/locations/test-location/recognizers/test-recognizer-id"
    )


def test_v2_create_transcription(v2_instance: V2, mock_v2_speech_client: Any):
    """Tests the create_transcription method."""
    mock_recognize = MagicMock()
    mock_recognize.return_value = types_v2.RecognizeResponse()
    mock_v2_speech_client.recognize = mock_recognize
    v2_instance.create_transcription(
        audio_file_path="gs://test-bucket/test-audio.wav",
        recognizer_path=(
            "projects/test-project/locations/test-location/recognizers"
            "mock_v2_speech_client/test-recognizer-id"
        ),
    )
    mock_recognize.assert_called_once()
