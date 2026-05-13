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

"""Unit tests for the agentic_chat runner main.py."""

from unittest.mock import patch
import datetime
import json
from cxidk.workflow.demo_artifacts.runners.agentic_chat import main

def test_file_name_generator():
    """Tests that the file name generator returns the correct format."""
    file_name = main.file_name_generator()
    assert len(file_name) == 18
    assert datetime.datetime.strptime(file_name, "%y%m%d%H%M%S%f")

@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.import_config")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.storage.Gcs")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.content_generator.Generator")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.agents.Dialogflow")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.time.sleep")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.random")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.logging")
def test_runner_no_config(
    _mock_logging,
    _mock_random,
    _mock_sleep,
    _mock_dialogflow,
    _mock_generator,
    _mock_gcs,
    mock_import_config,
):
    """Tests that the runner handles no configs gracefully."""
    mock_import_config.return_value = []
    result = main.runner(None)
    assert result == "0 conversations generated"


@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.import_config")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.storage.Gcs")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.content_generator.Generator")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.agents.Dialogflow")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.time.sleep")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.random")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.logging")
def test_runner_partially_configured_project(
    mock_logging,
    mock_random,
    _mock_sleep,
    _mock_dialogflow,
    _mock_generator,
    _mock_gcs,
    mock_import_config,
):
    """Tests that the runner handles partially configured projects."""
    mock_config = {
        "projects": [
            {
                "project_id": "test-project-partial",
                "generation_profile": {
                    "theme": "",
                    "max_conversations_per_run": {"agentic": 0},
                },
            }
        ]
    }
    mock_import_config.return_value = [json.dumps(mock_config)]

    result = main.runner(None)

    assert result == "0 conversations generated"
    mock_logging.error.assert_called_with(
        "Project (%s) not fully configured", "test-project-partial"
    )
    mock_random.randint.assert_not_called()


@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.import_config")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.storage.Gcs")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.content_generator.Generator")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.agents.Dialogflow")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.time.sleep")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.random")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.logging")
def test_runner_no_virtual_agents(
    mock_logging,
    mock_random,
    _mock_sleep,
    _mock_dialogflow,
    _mock_generator,
    _mock_gcs,
    mock_import_config,
):
    """Tests that the runner handles projects with no virtual agents."""
    mock_config = {
        "projects": [
            {
                "project_id": "test-project-no-va",
                "generation_profile": {
                    "theme": "test-theme",
                    "max_conversations_per_run": {"agentic": 1},
                },
                "virtual_agents": [],
            }
        ]
    }
    mock_import_config.return_value = [json.dumps(mock_config)]

    result = main.runner(None)

    assert result == "0 conversations generated"
    mock_logging.info.assert_any_call(
        "No virtual agents found in the project %s configuration.",
        "test-project-no-va",
    )
    mock_random.randint.assert_not_called()


@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.import_config")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.storage.Gcs")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.content_generator.Generator")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.agents.Dialogflow")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.time.sleep")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.random")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.logging")
def test_runner_valid_config_quit(
    _mock_logging,
    mock_random,
    _mock_sleep,
    mock_dialogflow,
    mock_generator,
    _mock_gcs,
    mock_import_config,
):
    """Tests a valid run with a conversation that quits."""
    mock_config = {
        "projects": [
            {
                "project_id": "test-project",
                "generation_profile": {
                    "theme": "test-theme",
                    "max_conversations_per_run": {"agentic": 1},
                },
                "virtual_agents": [
                    {
                        "agent": "test-agent",
                        "type": "classic",
                        "location": "us-central1",
                        "conversation_profile": "test-profile",
                        "topics": "test-topics",
                        "environment": "test-env",
                    }
                ],
            }
        ]
    }
    mock_import_config.return_value = [json.dumps(mock_config)]
    mock_random.randint.return_value = 1
    mock_generator.return_value.create_turn.side_effect = [
        json.dumps({"message": "hello"}),
        json.dumps({"message": "quit"}),
    ]

    result = main.runner(None)

    assert result == "2 conversations generated"
    mock_dialogflow.return_value.complete_conversation.assert_called_once()


@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.import_config")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.storage.Gcs")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.content_generator.Generator")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.agents.Dialogflow")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.time.sleep")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.random")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.logging")
def test_runner_long_conversation(
    _mock_logging,
    mock_random,
    _mock_sleep,
    mock_dialogflow,
    mock_generator,
    _mock_gcs,
    mock_import_config,
):
    """Tests that a long conversation is terminated."""
    mock_config = {
        "projects": [
            {
                "project_id": "test-project",
                "generation_profile": {
                    "theme": "test-theme",
                    "max_conversations_per_run": {"agentic": 1},
                },
                "virtual_agents": [
                    {
                        "agent": "test-agent",
                        "type": "classic",
                        "location": "us-central1",
                        "conversation_profile": "test-profile",
                        "topics": "test-topics",
                        "environment": "test-env",
                    }
                ],
            }
        ]
    }
    mock_import_config.return_value = [json.dumps(mock_config)]
    mock_random.randint.return_value = 1
    mock_generator.return_value.create_turn.return_value = json.dumps(
        {"message": "hello"}
    )

    result = main.runner(None)

    assert result == "25 conversations generated"
    mock_dialogflow.return_value.complete_conversation.assert_called_once()


@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.import_config")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.storage.Gcs")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.content_generator.Generator")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.agents.Dialogflow")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.time.sleep")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.random")
@patch("cxidk.workflow.demo_artifacts.runners.agentic_chat.main.logging")
def test_runner_send_message_exception(
    mock_logging,
    mock_random,
    _mock_sleep,
    mock_dialogflow,
    mock_generator,
    _mock_gcs,
    mock_import_config,
):
    """Tests that the runner handles exceptions during message sending."""
    mock_config = {
        "projects": [
            {
                "project_id": "test-project",
                "generation_profile": {
                    "theme": "test-theme",
                    "max_conversations_per_run": {"agentic": 1},
                },
                "virtual_agents": [
                    {
                        "agent": "test-agent",
                        "type": "classic",
                        "location": "us-central1",
                        "conversation_profile": "test-profile",
                        "topics": "test-topics",
                        "environment": "test-env",
                    }
                ],
            }
        ]
    }
    mock_import_config.return_value = [json.dumps(mock_config)]
    mock_random.randint.return_value = 1
    mock_generator.return_value.create_turn.return_value = json.dumps(
        {"message": "hello"}
    )
    mock_dialogflow.return_value.send_message.side_effect = Exception(
        "Send message failed"
    )

    result = main.runner(None)

    assert result == "1 conversations generated"
    mock_dialogflow.return_value.complete_conversation.assert_called_once()
    mock_logging.error.assert_called_with(
        mock_dialogflow.return_value.send_message.side_effect
    )
