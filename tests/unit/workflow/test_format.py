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

"""Unit tests for the format module."""

from datetime import datetime
from typing import Generator
from unittest.mock import MagicMock, mock_open, patch

import jsonschema
import pytest

from cxidk.workflow.format import Dlp, Insights, Speech


@pytest.fixture(name="mock_auth", autouse=True)
def fixture_mock_auth() -> Generator[MagicMock, None, None]:
    """Mocks google.auth.default to prevent DefaultCredentialsError."""
    with patch("google.auth.default") as mock_auth_default:
        mock_credentials = MagicMock()
        mock_credentials.valid = True
        mock_credentials.token = "test_token"
        mock_auth_default.return_value = (mock_credentials, "test-project")
        yield mock_auth_default


class TestDlp:
    """Tests for the Dlp class."""

    def test_from_conversation_json(self) -> None:
        """Test that from_conversation_json raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            Dlp().from_conversation_json()

    def test_from_recognize_response(self) -> None:
        """Test from_recognize_response correctly converts data."""
        dlp_formatter = Dlp()
        input_data = {
            "results": [
                {
                    "alternatives": [
                        {
                            "transcript": "hello world",
                            "words": [
                                {"word": "hello"},
                                {"word": "world"},
                            ],
                        }
                    ]
                },
                {
                    "alternatives": [
                        {
                            "transcript": "goodbye",
                            "words": [{"word": "goodbye"}],
                        }
                    ]
                },
            ]
        }
        result = dlp_formatter.from_recognize_response(input_data)
        expected = {
            "transcript_header": [{"name": "transcript_0"}, {"name": "transcript_1"}],
            "transcript": [{"string_value": "hello world"}, {"string_value": "goodbye"}],
            "word_header": [{"name": "word_0"}, {"name": "word_1"}, {"name": "word_2"}],
            "word": [
                {"string_value": "hello"},
                {"string_value": "world"},
                {"string_value": "goodbye"}
            ],
        }
        assert result == expected


class TestInsights:
    """Tests for the Insights class."""

    @patch("jsonschema.validate")
    @patch("builtins.open", new_callable=mock_open, read_data='{"key": "value"}')
    def test_from_aws_with_datetime(self, _: MagicMock, mock_validate: MagicMock) -> None:
        """Test from_aws with a datetime string."""
        insights = Insights()
        transcript = {
            "Transcript": [
                {
                    "ParticipantId": "AGENT",
                    "BeginOffsetMillis": 100,
                    "Content": "Hello",
                }
            ]
        }
        datetime_string = "2023/01/01 12:00:00"
        result = insights.from_aws(transcript, datetime_string)
        mock_validate.assert_called_once()
        assert len(result["entries"]) == 1
        assert result["entries"][0]["role"] == "AGENT"

    @patch("jsonschema.validate")
    @patch("builtins.open", new_callable=mock_open, read_data='{"key": "value"}')
    @patch("cxidk.workflow.format.datetime")
    def test_from_aws_no_datetime(
        self, mock_datetime: MagicMock, _: MagicMock, mock_validate: MagicMock
    ) -> None:
        """Test from_aws without a datetime string."""
        mock_datetime.now.return_value = datetime(2023, 1, 1, 12, 0, 0)
        insights = Insights()
        transcript = {
            "Transcript": [
                {
                    "ParticipantId": "CUSTOMER",
                    "BeginOffsetMillis": 200,
                    "Content": "Hi",
                }
            ]
        }
        result = insights.from_aws(transcript)
        mock_validate.assert_called_once()
        assert len(result["entries"]) == 1
        assert result["entries"][0]["role"] == "CUSTOMER"

    @patch("builtins.open", new_callable=mock_open, read_data='{"key": "value"}')
    def test_from_aws_invalid_schema(self, _: MagicMock) -> None:
        """Test from_aws with invalid schema."""
        insights = Insights()
        with patch("jsonschema.validate", side_effect=jsonschema.ValidationError("test")):
            with pytest.raises(jsonschema.ValidationError):
                insights.from_aws({})

    @patch("jsonschema.validate")
    @patch("builtins.open", new_callable=mock_open, read_data='{"key": "value"}')
    def test_from_genesys_cloud(self, _: MagicMock, mock_validate: MagicMock) -> None:
        """Test from_genesys_cloud."""
        insights = Insights()
        transcript = {
            "transcripts": [
                {
                    "phrases": [
                        {
                            "participantPurpose": "external",
                            "startTimeMs": 1000,
                            "text": "Hello",
                        }
                    ]
                }
            ]
        }
        result = insights.from_genesys_cloud(transcript)
        mock_validate.assert_called_once()
        assert len(result["entries"]) == 1
        assert result["entries"][0]["role"] == "CUSTOMER"

    def test_from_verint(self) -> None:
        """Test that from_verint raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            Insights().from_verint()

    def test_from_nice(self) -> None:
        """Test that from_nice raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            Insights().from_nice()

    def test_from_dlp_recognize_response(self) -> None:
        """Test from_dlp_recognize_response correctly reconstructs the conversation."""
        insights = Insights()
        original_conversation = {
            "results": [
                {"alternatives": [{"transcript": "original first"}]},
                {"alternatives": [{"transcript": "original second"}]},
            ]
        }
        # Mock the complex dlp_item object
        mock_dlp_item = MagicMock()
        mock_dlp_item.item.table.rows[0].values = [
            MagicMock(string_value="redacted first"),
            MagicMock(string_value="redacted second"),
        ]

        reconstructed = insights.from_dlp_recognize_response(mock_dlp_item, original_conversation)

        assert reconstructed["results"][0]["alternatives"][0]["transcript"] == "redacted first"
        assert reconstructed["results"][1]["alternatives"][0]["transcript"] == "redacted second"

class TestSpeech:
    """Tests for the Speech class."""

    def test_v1_recognizer_to_dict(self) -> None:
        """Test v1_recognizer_to_dict."""
        mock_response = MagicMock()
        type(mock_response).to_json = MagicMock(return_value='{"key": "value"}')
        result = Speech().v1_recognizer_to_dict(mock_response)
        assert result == {"key": "value"}

    def test_v1_recognizer_to_json(self) -> None:
        """Test v1_recognizer_to_json."""
        mock_response = MagicMock()
        type(mock_response).to_json = MagicMock(return_value='{"key": "value"}')
        result = Speech().v1_recognizer_to_json(mock_response)
        assert result == '{"key": "value"}'

    def test_v2_recognizer_to_json(self) -> None:
        """Test v2_recognizer_to_json."""
        mock_response = MagicMock()
        type(mock_response).to_json = MagicMock(return_value='{"key": "value"}')
        result = Speech().v2_recognizer_to_json(mock_response)
        assert result == '{"key": "value"}'

    def test_v2_recognizer_to_dict(self) -> None:
        """Test v2_recognizer_to_dict."""
        mock_response = MagicMock()
        type(mock_response).to_json = MagicMock(return_value='{"key": "value"}')
        result = Speech().v2_recognizer_to_dict(mock_response)
        assert result == {"key": "value"}

    def test_v2_json_to_dict(self) -> None:
        """Test v2_json_to_dict."""
        v2_json = {
            "results": [
                {"alternatives": [{"transcript": "Hello"}]},
                {"alternatives": [{"transcript": "Hi"}]},
                {"no_alternatives": []},
                {"alternatives": [{"no_transcript": ""}]},
            ]
        }
        result = Speech().v2_json_to_dict(v2_json)
        expected = {"results": [{"uid": 0, "text": "Hello"}, {"uid": 1, "text": "Hi"}]}
        assert result == expected
