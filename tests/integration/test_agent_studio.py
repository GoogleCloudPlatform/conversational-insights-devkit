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

"""End-to-end integration test for Agent Studio interaction."""

import logging
from cxidk.core import base
from cxidk.wrapper import agents

_PROJECT_ID = "ccai-insights-ux"
_LOCATION = "us"
_AGENT_ID = "90435a01-f8a0-42e9-a1e8-4a6417e9bfb4"


def test_agent_studio_e2e_conversation():
    """End-to-end test generating a conversation using AgentStudio."""
    agent_studio = agents.AgentStudio(
        project_id=_PROJECT_ID,
        location=_LOCATION,
        env=base.Environments.PRODUCTION,
    )

    session_id = agent_studio.create_session(agent_id=_AGENT_ID)
    logging.info("Created Agent Studio Session ID: %s", session_id)
    expected_prefix = f"projects/{_PROJECT_ID}/locations/{_LOCATION}/apps/{_AGENT_ID}/sessions/"
    assert session_id.startswith(expected_prefix)

    # Send first message to initialize conversation
    response_1 = agent_studio.send_message(text="Hello", session_id=session_id)
    logging.info("Agent Studio Response 1: %s", response_1)
    assert response_1 is not None

    # Send follow-up message in the same session
    response_2 = agent_studio.send_message(text="Can you help me?", session_id=session_id)
    logging.info("Agent Studio Response 2: %s", response_2)
    assert response_2 is not None
