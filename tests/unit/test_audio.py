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

"""Unit tests for the audio module."""

from typing import Generator
from unittest.mock import MagicMock, patch, mock_open

import pytest
from pytest_mock import MockerFixture

from cxidk.workflow.audio import GenerateAudio, RedactAudio, Utils


@pytest.fixture(autouse=True)
def mock_auth_fixture() -> Generator[MagicMock, None, None]:
    """Mocks cxidk.core.base.default to prevent DefaultCredentialsError."""
    with patch("cxidk.core.base.default") as mock_auth_default:
        mock_credentials = MagicMock()
        mock_credentials.valid = True
        mock_credentials.token = "test_token"
        mock_auth_default.return_value = (mock_credentials, "test-project")
        yield mock_auth_default


@pytest.fixture
def mock_tts_client(mocker: MockerFixture) -> MagicMock:
    """Mocks the TextToSpeech client."""
    return mocker.patch("cxidk.workflow.audio.speech.TextToSpeech")


@pytest.fixture
def mock_gcs_client(mocker: MockerFixture) -> MagicMock:
    """Mocks the Gcs client."""
    return mocker.patch("cxidk.workflow.audio.storage.Gcs")


@pytest.fixture
def mock_dlp_client(mocker: MockerFixture) -> MagicMock:
    """Mocks the DLP client."""
    return mocker.patch("cxidk.workflow.audio.sensitive_data_protection.DLP")


@pytest.fixture
def mock_format_dlp(mocker: MockerFixture) -> MagicMock:
    """Mocks the format.Dlp class."""
    return mocker.patch("cxidk.workflow.audio.ft.Dlp")


@pytest.fixture
def mock_format_insights(mocker: MockerFixture) -> MagicMock:
    """Mocks the format.Insights class."""
    return mocker.patch("cxidk.workflow.audio.ft.Insights")


@pytest.fixture(name="mock_audio_segment")
def fixture_mock_audio_segment(mocker: MockerFixture) -> MagicMock:
    """Mocks the AudioSegment class."""
    return mocker.patch("cxidk.workflow.audio.AudioSegment", new=FakeAudioSegment) # type: ignore[return-value] # pylint: disable=line-too-long


class FakeAudioSegment:
    """A fake AudioSegment class for testing."""

    def __init__(self, length=0, frame_rate=16000, data=b""):
        self.length = length
        self.frame_rate = frame_rate
        self.data = data

    def __len__(self):
        return self.length

    def __add__(self, other):
        return FakeAudioSegment(self.length + other.length)

    def __getitem__(self, key):
        if isinstance(key, slice):
            start = key.start or 0
            stop = key.stop or self.length
            # Handle slicing from the end, e.g., audio[x:]
            if key.stop is None:
                new_length = self.length - start
            else:
                new_length = stop - start
            return FakeAudioSegment(length=new_length)
        return self

    def export(self, *_, **__):
        """Fake export method."""
        return self

    @classmethod
    def empty(cls):
        """Fake empty method."""
        return cls()

    @classmethod
    def from_file(cls, *_, **__):
        """Fake from_file method."""
        return cls(1000)

    @classmethod
    def silent(cls, *_, **__):
        """Fake silent method."""
        return cls(100)

    @classmethod
    def from_mono_audiosegments(cls, *_, **__):
        """Fake from_mono_audiosegments method."""
        return cls(1000)


class TestGenerateAudio:
    """Tests for the GenerateAudio class."""

    def test_init(self) -> None:
        """Test GenerateAudio initialization."""
        audio_generator = GenerateAudio(project_id="test-project")
        assert audio_generator.project_id == "test-project"

    @patch.object(GenerateAudio, "single")
    def test_bulk(self, mock_single: MagicMock) -> None:
        """Test the bulk method."""
        audio_generator = GenerateAudio(project_id="test-project")
        transcripts: list[dict] = [{"entries": []}, {"entries": []}]
        audio_generator.bulk(transcripts, "/tmp/audio.wav")
        assert mock_single.call_count == 2

    @patch("cxidk.workflow.audio.speech.TextToSpeech")
    @patch("cxidk.workflow.audio.AudioSegment", new=FakeAudioSegment)
    def test_single_local_save(self, mock_tts: MagicMock) -> None:
        """Test the single method for local file saving."""
        mock_tts_instance = mock_tts.return_value
        mock_tts_instance.synthesize.return_value = b"audio_data"

        audio_generator = GenerateAudio(project_id="test-project")
        transcript = {
            "entries": [
                {"text": "hello", "role": "AGENT"},
                {"text": "hi", "role": "CUSTOMER"},
            ]
        }
        with patch.object(FakeAudioSegment, "export") as mock_export:
            audio_generator.single(transcript, "/tmp/audio.wav")
            mock_export.assert_called_with("/tmp/audio.wav", format="wav")

    @patch("cxidk.workflow.audio.storage.Gcs")
    @patch("cxidk.workflow.audio.speech.TextToSpeech")
    @patch("cxidk.workflow.audio.AudioSegment", new=FakeAudioSegment)
    def test_single_gcs_upload(self, mock_tts: MagicMock, mock_gcs: MagicMock) -> None:
        """Test the single method for GCS upload."""
        mock_tts_instance = mock_tts.return_value
        mock_tts_instance.synthesize.return_value = b"audio_data"
        mock_gcs_instance = mock_gcs.return_value

        audio_generator = GenerateAudio(project_id="test-project")
        transcript: dict = {"entries": [{"text": "hello", "role": "AGENT"}]}
        audio_generator.single(transcript, "gs://bucket/audio.wav")
        mock_gcs_instance.upload_blob.assert_called_once()

    def test_single_invalid_transcript(self) -> None:
        """Test single with an invalid transcript."""
        audio_generator = GenerateAudio(project_id="test-project")
        with pytest.raises(ValueError):
            audio_generator.single({}, "/tmp/audio.wav")

    @patch("cxidk.workflow.audio.AudioSegment", new=FakeAudioSegment)
    def test_single_empty_audio(self) -> None:
        """Test single with empty combined audio."""
        audio_generator = GenerateAudio(project_id="test-project")
        transcript: dict = {"entries": []}
        with pytest.raises(ValueError, match="Combined audio is empty."):
            audio_generator.single(transcript, "/tmp/audio.wav")


class TestUtils:
    """Tests for the Utils class."""

    def test_init(self) -> None:
        """Test Utils initialization."""
        utils = Utils(project_id="test-project")
        assert utils.project_id == "test-project"

    @patch("builtins.open", new_callable=mock_open)
    def test_save_audio_locally(self, mock_file: MagicMock) -> None:
        """Test save_audio_locally."""
        utils = Utils()
        byte_data = b"test audio data"
        output_file = "test.wav"
        utils.save_audio_locally(byte_data, output_file)
        mock_file.assert_called_once_with(output_file, "wb")
        mock_file().write.assert_called_once_with(byte_data)


class TestRedactAudio:
    """Tests for the RedactAudio class."""

    @pytest.fixture
    def redact_audio_instance(self) -> RedactAudio:
        """Returns an initialized RedactAudio instance."""
        return RedactAudio(
            project_id="test-project",
            location="us-central1",
            remote_audio_file_bucket="test-bucket",
            remote_audio_file_name="test-audio.wav",
        )

    def test_init(self) -> None:
        """Test RedactAudio initialization."""
        redactor = RedactAudio(
            project_id="p1",
            location="l1",
            remote_audio_file_bucket="b1",
            remote_audio_file_name="f1",
        )
        assert redactor.project_id == "p1"
        assert redactor.location == "l1"
        assert redactor.remote_audio_file_bucket == "b1"
        assert redactor.remote_audio_file_name == "f1"

    def test_find_redacted_word_timestamps(
        self, redact_audio_instance: RedactAudio
    ) -> None:
        """Test _find_redacted_word_timestamps."""
        original_transcript = {
            "results": [
                {
                    "alternatives": [
                        {
                            "words": [
                                {"word": "My", "startOffset": "0.1s", "endOffset": "0.5s"},
                                {"word": "name", "startOffset": "0.6s", "endOffset": "1.0s"},
                                {"word": "is", "startOffset": "1.1s", "endOffset": "1.3s"},
                                {"word": "John", "startOffset": "1.4s", "endOffset": "2.0s"},
                            ]
                        }
                    ]
                }
            ]
        }
        redacted_transcript = {
            "results": [
                {"alternatives": [{"transcript": "My name is [PERSON_NAME]"}]}
            ]
        }
        timestamps = redact_audio_instance._find_redacted_word_timestamps( # pylint: disable=protected-access
            original_transcript, redacted_transcript
        )
        assert timestamps == [(1.4, 2.0)]

    def test_find_redacted_word_timestamps_no_words(
        self, redact_audio_instance: RedactAudio
    ) -> None:
        """Test _find_redacted_word_timestamps with missing 'words' key."""
        original_transcript = {"results": [{"alternatives": [{"transcript": "text"}]}]}
        redacted_transcript = {"results": [{"alternatives": [{"transcript": "text"}]}]}
        with pytest.raises(
            ValueError, match="The 'words' key with word-level timestamps is missing"
        ):
            redact_audio_instance._find_redacted_word_timestamps( ## pylint: disable=protected-access
                original_transcript, redacted_transcript
            )

    @patch("cxidk.workflow.audio.AudioSegment", new=FakeAudioSegment)
    def test_replace_audio_segments(self, redact_audio_instance: RedactAudio) -> None:
        """Test _replace_audio_segments."""
        with patch.object(FakeAudioSegment, "export") as mock_export:
            redact_audio_instance._replace_audio_segments( # pylint: disable=protected-access
                "input.wav", [(1.0, 2.0)], "output.wav"
            )
            mock_export.assert_called_once_with("output.wav", format="wav")

    @patch("cxidk.workflow.audio.Utils.save_audio_locally")
    @patch.object(RedactAudio, "_replace_audio_segments")
    @patch.object(RedactAudio, "_find_redacted_word_timestamps", return_value=[(1.0, 2.0)])
    def test_process(
        self,
        mock_find_timestamps: MagicMock,
        mock_replace_segments: MagicMock,
        mock_save_locally: MagicMock,
        redact_audio_instance: RedactAudio,
        mock_dlp_client: MagicMock, # pylint: disable=redefined-outer-name
        mock_gcs_client: MagicMock, # pylint: disable=redefined-outer-name
        mock_format_dlp: MagicMock, # pylint: disable=redefined-outer-name
        mock_format_insights: MagicMock, # pylint: disable=redefined-outer-name
    ) -> None:
        """Test the main process method of RedactAudio."""
        mock_gcs_instance = mock_gcs_client.return_value
        mock_gcs_instance.download_blob.return_value = b"audio data"

        raw_transcript = {"results": []} # type: ignore[var-annotated]
        redacted_transcript = {"results": [{"alternatives": [{"transcript": "redacted"}]}]}
        mock_format_insights.return_value.from_dlp_recognize_response.return_value = redacted_transcript # pylint: disable=line-too-long

        result_path = redact_audio_instance.process(
            raw_transcript=raw_transcript,
            local_audio_file_path="local.wav",
            redacted_audio_file_path="redacted.wav",
            inspect_template="inspect-tmpl",
            deidentify_template="deidentify-tmpl",
        )

        mock_format_dlp.return_value.from_recognize_response.assert_called_once_with(
            data_input=raw_transcript
        )
        mock_dlp_client.return_value.redact.assert_called_once()
        mock_format_insights.return_value.from_dlp_recognize_response.assert_called_once()
        mock_gcs_client.assert_called_once_with(
            bucket_name="test-bucket", project_id="test-project"
        )
        mock_gcs_instance.download_blob.assert_called_once_with(
            file_name="test-audio.wav", content_type="audio/wav"
        )
        mock_save_locally.assert_called_once_with(
            byte_string_data=b"audio data", output_file_name="local.wav"
        )
        mock_find_timestamps.assert_called_once_with(
            original_transcript=raw_transcript, redacted_transcript=redacted_transcript
        )
        mock_replace_segments.assert_called_once_with(
            input_audio_path="local.wav",
            redacted_timestamps=[(1.0, 2.0)],
            output_audio_path="redacted.wav"
        )

        assert result_path == "redacted.wav"
