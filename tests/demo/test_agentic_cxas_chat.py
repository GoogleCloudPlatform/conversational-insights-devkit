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

"""Unit and confused-deputy security tests for the agentic_cxas_chat runner."""

import json
from unittest.mock import MagicMock, patch

import pytest

from cxidk.workflow.demo_artifacts.runners.agentic_cxas_chat import main


@patch("cxidk.workflow.demo_artifacts.runners.agentic_cxas_chat.main.import_config")
@patch(
    "cxidk.workflow.demo_artifacts.runners.agentic_cxas_chat.main.content_generator.Generator"
)
@patch(
    "cxidk.workflow.demo_artifacts.runners.agentic_cxas_chat.main.agents.AgentStudio"
)
@patch("random.randint", return_value=1)
@patch("random.uniform", return_value=1)
@patch("time.sleep", return_value=None)
def test_runner_success(
    _mock_sleep,
    _mock_uniform,
    mock_randint,
    mock_agent_studio,
    mock_generator,
    mock_import_config,
    monkeypatch,
):
    """Tests the runner function for a successful allowlisted execution."""
    monkeypatch.setenv("ALLOWED_PROJECT_IDS", "test-project")
    mock_config = {
        "projects": [
            {
                "project_id": "test-project",
                "generation_profile": {
                    "theme": "some-theme",
                    "max_conversations_per_run": {"agentic": 99},
                },
                "virtual_agents": [
                    {
                        "type": "cxas",
                        "agent": "test-agent",
                        "location": "us-central1",
                        "environment": "stg",
                        "topics": "some-topics",
                    }
                ],
                "environments": ["stg"],
            }
        ]
    }
    mock_import_config.return_value = [json.dumps(mock_config)]

    mock_gen_instance = MagicMock()
    mock_generator.return_value = mock_gen_instance
    mock_gen_instance.create_turn.side_effect = [
        json.dumps({"message": "hello"}),
        json.dumps({"message": "quit"}),
    ]

    mock_studio_instance = MagicMock()
    mock_agent_studio.return_value = mock_studio_instance
    mock_studio_instance.create_session.return_value = "session-123"
    mock_studio_instance.send_message.return_value = "response from agent"

    result = main.runner(None)

    assert result == "1 conversations generated"
    mock_randint.assert_called_once_with(0, 15)
    mock_import_config.assert_called_once()
    mock_generator.assert_called_with(
        project_id="insights-pipeline-producer", location="us-central1"
    )
    mock_gen_instance.create_parameters.assert_called_once()
    mock_agent_studio.assert_called_once_with(
        project_id="test-project", location="us-central1", env="stg"
    )
    mock_studio_instance.create_session.assert_called_once_with(agent_id="test-agent")
    assert mock_gen_instance.create_turn.call_count == 2
    mock_studio_instance.send_message.assert_called_once_with(
        session_id="session-123", text="hello"
    )


@patch("cxidk.workflow.demo_artifacts.runners.agentic_cxas_chat.main.import_config")
def test_runner_no_theme(mock_import_config, caplog, monkeypatch):
    """Tests the runner when an allowlisted project has no theme configured."""
    monkeypatch.setenv("ALLOWED_PROJECT_IDS", "test-project-no-theme")
    mock_config = {
        "projects": [
            {
                "project_id": "test-project-no-theme",
                "generation_profile": {
                    "theme": "",
                    "max_conversations_per_run": {"agentic": 1},
                },
                "virtual_agents": [],
            }
        ]
    }
    mock_import_config.return_value = [json.dumps(mock_config)]

    main.runner(None)

    assert "Project (test-project-no-theme) not fully configured" in caplog.text


@patch("cxidk.workflow.demo_artifacts.runners.agentic_cxas_chat.main.import_config")
@patch(
    "cxidk.workflow.demo_artifacts.runners.agentic_cxas_chat.main.content_generator.Generator"
)
@patch(
    "cxidk.workflow.demo_artifacts.runners.agentic_cxas_chat.main.agents.AgentStudio"
)
@patch("random.randint", return_value=1)
@patch("time.sleep", return_value=None)
def test_runner_fails_closed_and_skips_unallowlisted_project(
    _mock_sleep,
    _mock_randint,
    mock_agent_studio,
    mock_generator,
    mock_import_config,
    monkeypatch,
):
    """Unset allowlists fail closed; unallowlisted project is skipped."""
    monkeypatch.delenv("ALLOWED_PROJECT_IDS", raising=False)
    config = {
        "projects": [
            {
                "project_id": "attacker-owned-project",
                "generation_profile": {
                    "theme": "some-theme",
                    "max_conversations_per_run": {"agentic": 1},
                },
                "virtual_agents": [
                    {
                        "type": "cxas",
                        "agent": "test-agent",
                        "location": "us-central1",
                        "environment": "prod",
                        "topics": "t",
                    }
                ],
                "environments": ["prod"],
            },
            {
                "project_id": "valid-project",
                "generation_profile": {
                    "theme": "some-theme",
                    "max_conversations_per_run": {"agentic": 1},
                },
                "virtual_agents": [
                    {
                        "type": "cxas",
                        "agent": "test-agent",
                        "location": "us-central1",
                        "environment": "prod",
                        "topics": "t",
                    }
                ],
                "environments": ["prod"],
            },
        ]
    }
    mock_import_config.return_value = [json.dumps(config)]

    assert main.runner(None) == "0 conversations generated"
    mock_generator.assert_not_called()
    mock_agent_studio.assert_not_called()

    monkeypatch.setenv("ALLOWED_PROJECT_IDS", "valid-project")
    mock_generator.return_value.create_turn.return_value = json.dumps(
        {"message": "quit"}
    )
    assert main.runner(None) == "1 conversations generated"
    mock_agent_studio.assert_called_once_with(
        project_id="valid-project", location="us-central1", env="prod"
    )


@pytest.mark.parametrize(
    "bad_agent,bad_loc",
    [
        ("agent/../../hack", "us-central1"),
        ("agent1", "../other"),
        ("agent1", "us-central1?x=1"),
    ],
)
def test_validate_project_rejects_traversal(bad_agent, bad_loc, monkeypatch):
    """Path traversal in agent or location raises ValueError."""
    monkeypatch.setenv("ALLOWED_PROJECT_IDS", "valid-project")
    project = {
        "project_id": "valid-project",
        "generation_profile": {
            "theme": "some-theme",
            "max_conversations_per_run": {"agentic": 1},
        },
        "virtual_agents": [
            {
                "type": "cxas",
                "agent": bad_agent,
                "location": bad_loc,
                "environment": "prod",
            }
        ],
    }
    with pytest.raises(ValueError):
        main._validate_project(project)  # pylint: disable=protected-access
