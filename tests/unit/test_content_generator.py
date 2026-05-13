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

"""Unit tests for the content_generator module."""

from typing import Generator as GeneratorType
from unittest.mock import MagicMock, mock_open, patch

import pytest

from cxidk.workflow.content_generator import Generator


@pytest.fixture(autouse=True)
def mock_auth_fixture() -> GeneratorType[MagicMock, None, None]:
    """Mocks cxidk.core.base.default to prevent DefaultCredentialsError."""
    with patch("cxidk.core.base.default") as mock_auth_default:
        mock_credentials = MagicMock()
        mock_credentials.valid = True
        mock_credentials.token = "test_token"
        mock_auth_default.return_value = (mock_credentials, "test-project")
        yield mock_auth_default


class TestGenerator:
    """Tests for the Generator class."""

    @patch("cxidk.workflow.content_generator.vertex.Generator")
    def test_init(self, mock_vertex_generator: MagicMock) -> None:
        """Test Generator initialization."""
        generator = Generator(project_id="test-project", location="us-central1")
        mock_vertex_generator.assert_called_once_with(
            project_id="test-project", location="us-central1"
        )
        assert generator.generator == mock_vertex_generator.return_value

    @patch("builtins.open", new_callable=mock_open, read_data='{"key": "value"}')
    @patch("cxidk.workflow.content_generator.vertex.Generator")
    def test_create_conversation(self, mock_vertex_generator: MagicMock, _: MagicMock) -> None:
        """Test create_conversation."""
        mock_generator_instance = mock_vertex_generator.return_value
        mock_generator_instance.content.return_value = "{}"
        generator = Generator(project_id="test-project", location="us-central1")

        # Define a minimal set of valid parameters for testing
        base_parameters = {
            "sentiment_journeys": "Stable",
            "company_name": "TestCorp",
            "topics": "billing",
            "theme": "testing",
            "hint": "",
            "long_conversation": False,
            "bad_sentiment": False,
            "bad_performance": False,
            "model": "gemini-2.5-flash",
            "language": ["en-US"],
            "temperature": 0.9, "topp": 0.9, "topk": 35,
        }

        # Test with base parameters
        generator.create_conversation(parameters=base_parameters)
        mock_generator_instance.content.assert_called_once()

        # Test with parameters
        mock_generator_instance.content.reset_mock()
        updated_parameters = base_parameters.copy()
        updated_parameters.update({"long_conversation": True, "bad_sentiment": True})
        generator.create_conversation(parameters=updated_parameters)
        mock_generator_instance.content.assert_called_once()

    @patch("random.choice", side_effect=lambda x: x[0])
    @patch("random.randint", return_value=5)
    @patch("random.uniform")
    def test_create_parameters(
        self,
        mock_uniform: MagicMock,
        __: MagicMock,
        ___: MagicMock
    ) -> None:
        """Test create_parameters with a generation profile."""
        generator = Generator(project_id="test-project", location="us-central1")
        # A complete generation profile is needed for the method to work
        generation_profile = {
            "theme": ["Entertainment"],
            "model": "gemini-2.5-pro",
            "topics": ["billing"],
            "probabilities": {
                "long_conversation": [0.1, 0.1],
                "bad_sentiment": [0.1, 0.1],
                "bad_performance": [0.1, 0.1],
            },
            "sentiment_journeys": ["Neutral to High"],
            "temperature": [0.8, 1],
            "topk": [30, 40],
            "topp": [0.9, 1],
            "language": ["en-US"],
            "prompt_hint": [""],
        }
        # Set side_effect to control the return values of random.uniform
        # 1st call (long_convo prob): 0.1, 2nd (bad_sentiment prob): 0.1, 3rd (bad_perf prob): 0.1
        # 4th call (check for long_convo): 0.09 (which is < 0.1, so True)
        mock_uniform.side_effect = [0.1, 0.1, 0.1, 0.09, 0.1, 0.1, 0.8, 0.9, 5]
        params = generator.create_parameters(generation_profile=generation_profile)
        assert params["long_conversation"] is True

    @patch("builtins.open", new_callable=mock_open, read_data='{"key": "value"}')
    @patch("cxidk.workflow.content_generator.vertex.Generator")
    def test_create_turn(self, mock_vertex_generator: MagicMock, _: MagicMock) -> None:
        """Test create_turn."""
        mock_generator_instance = mock_vertex_generator.return_value
        mock_generator_instance.content.return_value = "{}"
        generator = Generator(project_id="test-project", location="us-central1")

        # Test with no history
        generator.create_turn()
        mock_generator_instance.content.assert_called_once()

        # Test with history
        mock_generator_instance.content.reset_mock()
        generator.create_turn(conversation_history=["hello"])
        mock_generator_instance.content.assert_called_once()

    @patch("random.randint", return_value=123456)
    @patch("builtins.open", new_callable=mock_open, read_data='{"agents": [{}]}')
    @patch("cxidk.workflow.content_generator.vertex.Generator")
    def test_create_agents(
        self, mock_vertex_generator: MagicMock, _: MagicMock, __: MagicMock
    ) -> None:
        """Test create_agents."""
        mock_generator_instance = mock_vertex_generator.return_value
        mock_generator_instance.content.return_value = '{"agents": [{}]}'
        generator = Generator(project_id="test-project", location="us-central1")
        result = generator.create_agents()
        assert result["agents"][0]["agent_id"] == "123456"

    @patch("random.randint", return_value=0)
    def test_create_metadata(self, _: MagicMock) -> None:
        """Test create_metadata."""
        generator = Generator(project_id="test-project", location="us-central1")
        agents = {"agents": [{"name": "test_agent"}]}
        metadata = generator.create_metadata(agents=agents)
        assert metadata["agent_info"][0]["name"] == "test_agent"

    @patch("builtins.open", new_callable=mock_open, read_data='{"agents": [{"name": "default"}]}')
    @patch("random.randint", return_value=0)
    def test_create_metadata_no_agents(self, _: MagicMock, __: MagicMock) -> None:
        """Test create_metadata with no agents provided."""
        generator = Generator(project_id="test-project", location="us-central1")
        metadata = generator.create_metadata()
        assert metadata["agent_info"][0]["name"] == "default"

    def test_create_metadata_no_agent_list(self) -> None:
        """Test create_metadata with no agent list available."""
        generator = Generator(project_id="test-project", location="us-central1")
        with patch("builtins.open", side_effect=FileNotFoundError):
            with pytest.raises(FileNotFoundError):
                generator.create_metadata()
