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

"""Unit tests for the Vertex AI Gemini API wrapper."""

from typing import Any, Dict, Generator as TypingGenerator
from unittest.mock import ANY, MagicMock, patch

import pytest

# Import the code to be tested
from cxidk.core import base
from cxidk.wrapper.vertex import Generator, GeminiModels, MimeTypes

# --- Constants for Reusability ---
TEST_PROJECT_ID = "test-project-id"
TEST_LOCATION = "us-central1"
TEST_PROMPT = "Why is the sky blue?"
TEST_SYSTEM_INSTRUCTION = "Respond as a pirate."
EXPECTED_RESPONSE_TEXT = "Arr, 'tis because of the scattering of light, matey!"


# --- Pytest Fixtures for Mocks ---
@pytest.fixture(autouse=True)
def mock_auth_fixture() -> TypingGenerator[MagicMock, None, None]:
    """Mocks cxidk.core.base.default to prevent DefaultCredentialsError."""
    with patch("cxidk.core.base.default") as mock_auth_default:
        mock_credentials = MagicMock()
        mock_credentials.valid = True
        mock_credentials.token = "test_token"
        mock_auth_default.return_value = (mock_credentials, "test-project")
        yield mock_auth_default


@pytest.fixture(name="mock_genai_client")
def fixture_mock_genai_client() -> TypingGenerator[MagicMock, None, None]:
    """A pytest fixture that mocks the genai.Client and its nested methods."""
    # Patch the Client where it's looked up (in the 'vertex' module)
    with patch("cxidk.wrapper.vertex.genai.Client") as mock_client_class:
        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance
        yield mock_client_instance


@pytest.fixture(name="mock_base_config")
def fixture_mock_base_config() -> MagicMock:
    """A pytest fixture that mocks the cxidk.core.base.Config object."""
    return MagicMock(spec=base.Config)


@pytest.fixture(name="mock_base_auth")
def fixture_mock_base_auth() -> MagicMock:
    """A pytest fixture that mocks the cxidk.core.base.Auth object."""
    return MagicMock(spec=base.Auth)


# --- Test Cases ---

###
# Tests for the __init__ method
###


@patch("cxidk.wrapper.vertex.genai.Client")
def test_generator_init_with_defaults(mock_genai_client_class: MagicMock) -> None:
    """Verifies Generator initializes correctly when auth/config are not provided."""
    mock_genai_client_instance = MagicMock()
    mock_genai_client_class.return_value = mock_genai_client_instance
    with patch("cxidk.wrapper.vertex.base") as mock_base:
        generator = Generator(project_id=TEST_PROJECT_ID, location=TEST_LOCATION)

        # Assert that default objects were created
        mock_base.Auth.assert_called_once()
        mock_base.Config.assert_called_once()

        # Assert attributes were set correctly
        assert generator.project_id == TEST_PROJECT_ID
        assert generator.location == TEST_LOCATION
        assert generator.version == GeminiModels.GEMINI_2_5_FLASH
        assert generator.client == mock_genai_client_instance

        # Assert the genai Client class was instantiated with correct parameters
        mock_genai_client_class.assert_called_once_with(
            vertexai=True, project=TEST_PROJECT_ID, location=TEST_LOCATION
        )


def test_generator_init_with_provided_dependencies(
    mock_genai_client: MagicMock, mock_base_config: MagicMock, mock_base_auth: MagicMock
) -> None:
    """Verifies Generator initializes correctly when auth/config objects are provided."""
    generator = Generator(
        project_id=TEST_PROJECT_ID,
        location=TEST_LOCATION,
        version=GeminiModels.GEMINI_2_5_PRO, # type: ignore
        auth=mock_base_auth,
        config=mock_base_config,
    )

    # Assert provided objects are used instead of creating new ones
    assert generator.auth == mock_base_auth
    assert generator.config == mock_base_config
    assert generator.version == GeminiModels.GEMINI_2_5_PRO
    assert generator.client == mock_genai_client


###
# Tests for the content method
###


def test_content_generation_success_and_parameter_passing(
    mock_genai_client: MagicMock,
) -> None:
    """
    Verifies that the content method correctly calls the Gemini API
    with all parameters and successfully extracts the response text.
    """
    # Mock the chain of objects in the response
    mock_part = MagicMock()
    mock_part.text = EXPECTED_RESPONSE_TEXT
    mock_content = MagicMock()
    mock_content.parts = [mock_part]
    mock_candidate = MagicMock()
    mock_candidate.content = mock_content
    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    mock_genai_client.models.generate_content.return_value = mock_response

    # Patch the 'types' module to capture the config object
    with patch("cxidk.wrapper.vertex.types") as mock_types:
        generator = Generator(project_id=TEST_PROJECT_ID, location=TEST_LOCATION)
        output_schema: Dict[str, Any] = {
            "type": "object",
            "properties": {"response": {"type": "string"}},
        }

        response_text = generator.content(
            prompt=TEST_PROMPT,
            system_instruction=TEST_SYSTEM_INSTRUCTION,
            top_k=50,
            temperature=0.8,
            top_p=0.9,
            output_schema=output_schema,
            output_mime_type=MimeTypes.APPLICATION_JSON,
        )

        # Assert the response was extracted correctly
        assert response_text == EXPECTED_RESPONSE_TEXT

        # Assert the underlying API call was made correctly
        mock_genai_client.models.generate_content.assert_called_once()
        mock_types.GenerateContentConfig.assert_called_once_with(
            system_instruction=TEST_SYSTEM_INSTRUCTION,
            candidate_count=1,
            temperature=0.8,
            top_k=50,
            top_p=0.9,
            response_mime_type=MimeTypes.APPLICATION_JSON,
            response_schema=output_schema,
            safety_settings=ANY,
        )


@pytest.mark.parametrize(
    "malformed_response_config",
    [
        {"candidates": []},
        {"candidates": [MagicMock(content=None)]},
        {
            "candidates": [MagicMock(content=MagicMock(parts=[]))]
        },
        {
            "candidates": [MagicMock(content=MagicMock(parts=[MagicMock(text=None)]))]
        },
    ],
)
def test_content_handles_empty_or_malformed_responses(
    mock_genai_client: MagicMock, malformed_response_config: Dict[str, Any]
) -> None:
    """
    Verifies that the content method returns an empty string when the API
    response is missing expected attributes.
    """
    # Configure the mock response based on the test parameter
    mock_response = MagicMock(**malformed_response_config)
    mock_genai_client.models.generate_content.return_value = mock_response

    generator = Generator(project_id=TEST_PROJECT_ID, location=TEST_LOCATION)
    response_text = generator.content(prompt=TEST_PROMPT)

    assert response_text == ""
