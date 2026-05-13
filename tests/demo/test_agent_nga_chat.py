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

"""Unit tests for the agentic_nga_chat runner."""

import json
from unittest.mock import MagicMock, patch

from cxidk.workflow.demo_artifacts.runners.agentic_nga_chat import main


@patch('cxidk.workflow.demo_artifacts.runners.agentic_nga_chat.main.import_config')
@patch('cxidk.workflow.demo_artifacts.runners.agentic_nga_chat.main.content_generator.Generator')
@patch('cxidk.workflow.demo_artifacts.runners.agentic_nga_chat.main.agents.PolySynth')
@patch('random.randint', return_value=1)
@patch('random.uniform', return_value=1)
@patch('time.sleep', return_value=None)
def test_runner_success(
    _mock_sleep, _mock_uniform, _mock_randint, mock_polysynth, mock_generator, mock_import_config
):
    """Tests the runner function for a successful execution."""
    mock_config = {
        "projects": [
            {
                "project_id": "test-project",
                "generation_profile": {
                    "theme": "some-theme",
                    "max_conversations_per_run": {"agentic": 1}
                },
                "virtual_agents": [
                    {
                        "type": "next-gen",
                        "agent": "test-agent",
                        "location": "us-central1",
                        "environment": "test-env",
                        "topics": "some-topics"
                    }
                ],
                "environments": ["test-env"]
            }
        ]
    }
    mock_import_config.return_value = [json.dumps(mock_config)]

    mock_gen_instance = MagicMock()
    mock_generator.return_value = mock_gen_instance
    mock_gen_instance.create_turn.side_effect = [
        json.dumps({"message": "hello"}),
        json.dumps({"message": "quit"})
    ]

    mock_poly_instance = MagicMock()
    mock_polysynth.return_value = mock_poly_instance
    mock_poly_instance.create_session.return_value = "session-123"
    mock_poly_instance.send_message.return_value = "response from agent"

    result = main.runner(None)

    assert result == "1 conversations generated"
    mock_import_config.assert_called_once()
    mock_generator.assert_called_with(project_id='insights-pipeline-producer', location='us-central1') # pylint: disable=C0301
    mock_gen_instance.create_parameters.assert_called_once()
    mock_polysynth.assert_called_once_with(
        project_id='test-project', location='us-central1', env='test-env'
    )
    mock_poly_instance.create_session.assert_called_once_with(agent_id='test-agent')
    assert mock_gen_instance.create_turn.call_count == 2
    mock_poly_instance.send_message.assert_called_once_with(session_id='session-123', text='hello')


@patch('cxidk.workflow.demo_artifacts.runners.agentic_nga_chat.main.import_config')
def test_runner_no_theme(mock_import_config, caplog):
    """Tests the runner when a project has no theme configured."""
    mock_config = {
        "projects": [
            {
                "project_id": "test-project-no-theme",
                "generation_profile": {
                    "theme": "",
                    "max_conversations_per_run": {"agentic": 1}
                },
                "virtual_agents": []
            }
        ]
    }
    mock_import_config.return_value = [json.dumps(mock_config)]

    main.runner(None)

    assert "Project (test-project-no-theme) not fully configured" in caplog.text
