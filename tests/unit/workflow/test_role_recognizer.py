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

"""Unit tests for the role_recognizer module."""

import json
from unittest.mock import MagicMock, patch

from cxidk.workflow.role_recognizer import RoleRecognizer
from cxidk.wrapper import vertex


@patch("cxidk.workflow.role_recognizer.vertex.Generator")
def test_role_recognizer_init_defaults(mock_generator_cls: MagicMock) -> None:
    """Test RoleRecognizer initialization with default values."""
    recognizer = RoleRecognizer()
    assert recognizer.model_name == "gemini-2.5-pro"
    assert recognizer.prompt == recognizer._DEFAULT_PROMPT  # pylint: disable=protected-access
    mock_generator_cls.assert_called_once()
    assert mock_generator_cls.call_args.kwargs["version"] == "gemini-2.5-pro"


@patch("cxidk.workflow.role_recognizer.vertex.Generator")
def test_role_recognizer_init_custom(mock_generator_cls: MagicMock) -> None:
    """Test RoleRecognizer initialization with custom values."""
    recognizer = RoleRecognizer(
        model_name="custom-model",
        prompt="custom prompt",
        project_id="my-project",
        location="europe-west1",
    )
    assert recognizer.model_name == "custom-model"
    assert recognizer.prompt == "custom prompt"
    mock_generator_cls.assert_called_once_with(
        project_id="my-project",
        location="europe-west1",
        version="custom-model",
        auth=None,
        config=None,
    )


@patch("cxidk.workflow.role_recognizer.vertex.Generator")
def test_predict_roles(mock_generator_cls: MagicMock) -> None:
    """Test the predict_roles method."""
    mock_gen_instance = MagicMock()
    mock_gen_instance.content.return_value = (
        '{"predictions": [{"role": "AGENT", "uid": 1}]}'
    )
    mock_generator_cls.return_value = mock_gen_instance

    recognizer = RoleRecognizer()
    conversation = {"results": [{"alternatives": [{"transcript": "Hello"}]}]}
    roles = recognizer.predict_roles(conversation)

    mock_gen_instance.content.assert_called_once_with(
        prompt=recognizer.prompt.format(conversation=conversation),
        temperature=0.0,
        top_p=0.95,
        top_k=40,
        output_mime_type=vertex.MimeTypes.APPLICATION_JSON,
        output_schema=recognizer._RESPONSE_SCHEMA,  # pylint: disable=protected-access
    )
    assert roles == {"predictions": [{"role": "AGENT", "uid": 1}]}


@patch("cxidk.workflow.role_recognizer.vertex.Generator")
def test_combine(_: MagicMock) -> None:
    """Test the combine method."""
    recognizer = RoleRecognizer()
    conversation = {
        "results": [
            {"alternatives": [{"transcript": "Hello"}], "channelTag": 0},
            {"alternatives": [{"transcript": "Hi"}], "channelTag": 0},
        ]
    }
    roles = {
        "predictions": [
            {"role": "AGENT", "uid": 1},
            {"role": "CUSTOMER", "uid": 2},
        ]
    }
    combined = recognizer.combine(conversation, roles)
    expected_conversation = {
        "results": [
            {
                "alternatives": [{"transcript": "Hello", "channelTag": 2}],
                "channelTag": 2,
            },
            {
                "alternatives": [{"transcript": "Hi", "channelTag": 1}],
                "channelTag": 1,
            },
        ]
    }
    assert json.loads(combined) == expected_conversation


@patch("cxidk.workflow.role_recognizer.vertex.Generator")
def test_combine_with_missing_prediction(_: MagicMock) -> None:
    """Test the combine method with a missing prediction."""
    recognizer = RoleRecognizer()
    conversation = {
        "results": [
            {"alternatives": [{"transcript": "Hello"}], "channelTag": 0},
            {"alternatives": [{"transcript": "Hi"}], "channelTag": 0},
        ]
    }
    roles = {"predictions": [{"role": "AGENT", "uid": 1}]}
    combined = recognizer.combine(conversation, roles)
    expected_conversation = {
        "results": [
            {
                "alternatives": [{"transcript": "Hello", "channelTag": 2}],
                "channelTag": 2,
            },
            {
                "alternatives": [{"transcript": "Hi", "channelTag": 1}],
                "channelTag": 1,
            },
        ]
    }
    assert json.loads(combined) == expected_conversation


@patch("cxidk.workflow.role_recognizer.vertex.Generator")
def test_combine_with_malformed_prediction(_: MagicMock) -> None:
    """Test the combine method with a malformed prediction."""
    recognizer = RoleRecognizer()
    conversation = {
        "results": [
            {"alternatives": [{"transcript": "Hello"}], "channelTag": 0},
            {"alternatives": [{"transcript": "Hi"}], "channelTag": 0},
        ]
    }
    roles = {"predictions": [{"uid": 1}]}  # Missing "role"
    combined = recognizer.combine(conversation, roles)
    expected_conversation = {
        "results": [
            {
                "alternatives": [{"transcript": "Hello", "channelTag": 1}],
                "channelTag": 1,
            },
            {
                "alternatives": [{"transcript": "Hi", "channelTag": 1}],
                "channelTag": 1,
            },
        ]
    }
    assert json.loads(combined) == expected_conversation
