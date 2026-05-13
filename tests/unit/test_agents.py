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

"""Unit tests for the virtual agents wrapper."""

from typing import Generator
from unittest.mock import ANY, MagicMock, patch

import pytest
import requests

from cxidk.wrapper import agents


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
def mock_polysynth_auth_fixture() -> Generator[MagicMock, None, None]:
    """Mocks google.auth.default for PolySynth tests."""
    with patch("google.auth.default") as mock_auth_default:
        mock_credentials = MagicMock()
        mock_credentials.valid = True
        mock_credentials.token = "test_token"
        mock_auth_default.return_value = (mock_credentials, "test-project")
        yield mock_auth_default


@pytest.mark.usefixtures("mock_polysynth_auth_fixture")
class TestPolySynth:
    """Unit tests for the PolySynth agent wrapper."""

    def test_polysynth_init(self) -> None:
        """Test PolySynth initialization."""
        client = agents.PolySynth(project_id="test_project", location="us-central1")

        assert client.project_id == "test_project"
        assert client.location == "us-central1"
        assert client.auth is not None
        assert client.config is not None
        assert client.credentials_token == "test_token"

    def test_polysynth_properties(self) -> None:
        """Test PolySynth properties."""
        client = agents.PolySynth(project_id="test_project", location="us-central1")

        assert client.parent == "projects/test_project/locations/us-central1"
        assert (
            client.base_url
            == "https://staging-ces-googleapis.sandbox.google.com/v1beta/"
        )

    def test_polysynth_set_credentials_refresh(
            self, mock_polysynth_auth_fixture: MagicMock # pylint: disable=redefined-outer-name
    ) -> None:
        """Test PolySynth _set_credentials with token refresh."""
        mock_credentials = MagicMock()
        mock_credentials.valid = False
        mock_credentials.expired = True
        mock_credentials.token = "new_token"
        mock_polysynth_auth_fixture.return_value = (mock_credentials, "test_project")

        client = agents.PolySynth(project_id="test_project", location="us-central1")

        mock_credentials.refresh.assert_called_once_with(ANY)
        assert client.credentials_token == "new_token"

    def test_polysynth_set_credentials_no_token(
            self, mock_polysynth_auth_fixture: MagicMock # pylint: disable=redefined-outer-name
    ) -> None:
        """Test PolySynth _set_credentials with no token."""
        mock_credentials = MagicMock()
        mock_credentials.valid = True
        mock_credentials.token = None
        mock_polysynth_auth_fixture.return_value = (mock_credentials, "test_project")

        client = agents.PolySynth(project_id="test_project", location="us-central1")

        assert client.credentials_token is None

    @patch("requests.request")
    def test_polysynth_make_request_success(self, mock_request: MagicMock) -> None:
        """Test PolySynth _make_request success."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": "test"}
        mock_request.return_value = mock_response

        client = agents.PolySynth(project_id="test_project", location="us-central1")
        response = client._make_request("GET", "test_url")  # pylint: disable=protected-access

        assert response == {"data": "test"}

    @patch("requests.request")
    def test_polysynth_make_request_failure(self, mock_request: MagicMock) -> None:
        """Test PolySynth _make_request failure."""
        mock_request.side_effect = requests.exceptions.RequestException

        client = agents.PolySynth(project_id="test_project", location="us-central1")
        response = client._make_request("GET", "test_url")  # pylint: disable=protected-access

        assert response is None

    @patch("time.sleep", return_value=None)
    @patch.object(agents.PolySynth, "_make_request")
    def test_polysynth_poll_operation_success(self,
        mock_make_request: MagicMock, _: MagicMock
    ) -> None:
        """Test PolySynth _poll_operation success."""
        mock_response_pending = {"name": "op1", "done": False}
        mock_response_done = {
            "name": "op1",
            "done": True,
            "response": "result",
        }
        mock_make_request.side_effect = iter([mock_response_pending, mock_response_done])

        client = agents.PolySynth(project_id="test_project", location="us-central1")
        result = client._poll_operation("op1")  # pylint: disable=protected-access

        assert result == "result"

    @patch("time.sleep", return_value=None)
    @patch.object(agents.PolySynth, "_make_request")
    def test_polysynth_poll_operation_timeout(self,
        mock_make_request: MagicMock, _: MagicMock
    ) -> None:
        """Test PolySynth _poll_operation timeout."""
        mock_make_request.return_value = {"name": "op1", "done": False}

        client = agents.PolySynth(project_id="test_project", location="us-central1")
        result = client._poll_operation(  # pylint: disable=protected-access
            "op1", timeout=0.1, initial_sleep=0
        )

        assert result is None

    @patch("time.sleep", return_value=None)
    @patch.object(agents.PolySynth, "_make_request")
    def test_polysynth_poll_operation_error(
        self,
        mock_make_request: MagicMock, _: MagicMock
    ) -> None:
        """Test PolySynth _poll_operation with an error."""
        mock_response_error = {
            "name": "op1",
            "done": True,
            "error": "error details",
        }
        mock_make_request.return_value = mock_response_error

        client = agents.PolySynth(project_id="test_project", location="us-central1")

        with pytest.raises(RuntimeError):
            client._poll_operation("op1")  # pylint: disable=protected-access

    def test_polysynth_create_session(self) -> None:
        """Test PolySynth create_session."""
        client = agents.PolySynth(project_id="test_project", location="us-central1")
        session_id = client.create_session("agent1", unique_id="session1")

        assert client.agent_id == "agent1"
        assert (
            session_id
            == "projects/test_project/locations/us-central1/apps/agent1/sessions/session1"
        )

    @patch("uuid.uuid4")
    def test_polysynth_create_session_no_unique_id(self, mock_uuid: MagicMock) -> None:
        """Test PolySynth create_session without a unique_id."""
        mock_uuid.return_value = "random_uuid"

        client = agents.PolySynth(project_id="test_project", location="us-central1")
        session_id = client.create_session("agent1")

        assert (
            session_id
            == "projects/test_project/locations/us-central1/apps/agent1/sessions/random_uuid"
        )

    @patch.object(agents.PolySynth, "_make_request")
    def test_polysynth_send_message(self, mock_make_request: MagicMock) -> None:
        """Test PolySynth send_message."""
        mock_make_request.return_value = {
            "outputs": [{"text": "response1"}, {"text": "response2"}]
        }

        client = agents.PolySynth(project_id="test_project", location="us-central1")
        response = client.send_message("hello", session_id="session1")

        assert response == "response1\nresponse2\n"


@patch("cxidk.wrapper.agents.ConversationsClient")
@patch("cxidk.wrapper.agents.ParticipantsClient")
def test_dialogflow_init(
    mock_participants_client: MagicMock,
    mock_conversations_client: MagicMock,
) -> None:
    """Test Dialogflow initialization."""
    client = agents.Dialogflow(
        project_id="test_project",
        location="us-central1",
        conversation_profile="test_profile",
    )

    assert client.project_id == "test_project"
    assert client.location == "us-central1"
    assert client.conversation_profile == "test_profile"
    assert client.parent == "projects/test_project/locations/us-central1"
    mock_conversations_client.assert_called_once()
    mock_participants_client.assert_called_once()


@patch("cxidk.wrapper.agents.ConversationsClient")
@patch("cxidk.wrapper.agents.ParticipantsClient")
def test_dialogflow_create_conversation(
    mock_participants_client: MagicMock,  # pylint: disable=unused-argument
    mock_conversations_client: MagicMock,
) -> None:
    """Test Dialogflow create_conversation."""
    mock_conv_client_instance = mock_conversations_client.return_value
    mock_conv_client_instance.create_conversation.return_value.name = "conv1"

    client = agents.Dialogflow(
        project_id="test_project",
        location="us-central1",
        conversation_profile="test_profile",
    )
    conv_name = client.create_conversation()

    assert conv_name == "conv1"
    assert client.conversation_name == "conv1"


@patch("cxidk.wrapper.agents.ConversationsClient")
@patch("cxidk.wrapper.agents.ParticipantsClient")
def test_dialogflow_create_participant(
    mock_participants_client: MagicMock,
    mock_conversations_client: MagicMock,  # pylint: disable=unused-argument
) -> None:
    """Test Dialogflow create_participant."""
    mock_part_client_instance = mock_participants_client.return_value
    mock_part_client_instance.create_participant.return_value.name = "part1"

    client = agents.Dialogflow(
        project_id="test_project",
        location="us-central1",
        conversation_profile="test_profile",
    )
    client.conversation_name = "conv1"
    part_name = client.create_participant()

    assert part_name == "part1"
    assert client.participant_name == "part1"


@patch("cxidk.wrapper.agents.ConversationsClient")
@patch("cxidk.wrapper.agents.ParticipantsClient")
def test_dialogflow_create_participant_no_conv(
    mock_participants_client: MagicMock,  # pylint: disable=unused-argument
    mock_conversations_client: MagicMock,  # pylint: disable=unused-argument
) -> None:
    """Test Dialogflow create_participant without a conversation."""
    client = agents.Dialogflow(
        project_id="test_project",
        location="us-central1",
        conversation_profile="test_profile",
    )

    with pytest.raises(RuntimeError):
        client.create_participant()


@patch("cxidk.wrapper.agents.ConversationProfilesClient")
@patch("cxidk.wrapper.agents.ConversationsClient")
@patch("cxidk.wrapper.agents.ParticipantsClient")
def test_dialogflow_create_conversation_profile(
    mock_participants_client: MagicMock,  # pylint: disable=unused-argument
    mock_conversations_client: MagicMock,  # pylint: disable=unused-argument
    mock_conv_profiles_client: MagicMock,
) -> None:
    """Test Dialogflow create_conversation_profile."""
    mock_prof_client_instance = mock_conv_profiles_client.return_value
    mock_prof_client_instance.create_conversation_profile.return_value.name = "prof1"

    client = agents.Dialogflow(
        project_id="test_project",
        location="us-central1",
        conversation_profile="test_profile",
    )
    response = client.create_conversation_profile("agent_path", "display_name")

    assert response.name == "prof1"


@patch("cxidk.wrapper.agents.ConversationsClient")
@patch("cxidk.wrapper.agents.ParticipantsClient")
def test_dialogflow_send_message(
    mock_participants_client: MagicMock,
    mock_conversations_client: MagicMock,  # pylint: disable=unused-argument
) -> None:
    """Test Dialogflow send_message."""
    mock_part_client_instance = mock_participants_client.return_value
    mock_part_client_instance.analyze_content.return_value.reply_text = "response"

    client = agents.Dialogflow(
        project_id="test_project",
        location="us-central1",
        conversation_profile="test_profile",
    )
    client.participant_name = "part1"
    reply = client.send_message("hello")

    assert reply == "response"


@patch("cxidk.wrapper.agents.ConversationsClient")
@patch("cxidk.wrapper.agents.ParticipantsClient")
def test_dialogflow_send_message_no_participant(
    mock_participants_client: MagicMock,  # pylint: disable=unused-argument
    mock_conversations_client: MagicMock,  # pylint: disable=unused-argument
) -> None:
    """Test Dialogflow send_message without a participant."""
    client = agents.Dialogflow(
        project_id="test_project",
        location="us-central1",
        conversation_profile="test_profile",
    )

    with pytest.raises(RuntimeError):
        client.send_message("hello")


@patch("cxidk.wrapper.agents.ConversationsClient")
@patch("cxidk.wrapper.agents.ParticipantsClient")
def test_dialogflow_complete_conversation(
    mock_participants_client: MagicMock,  # pylint: disable=unused-argument
    mock_conversations_client: MagicMock,
) -> None:
    """Test Dialogflow complete_conversation."""
    mock_conv_client_instance = mock_conversations_client.return_value

    client = agents.Dialogflow(
        project_id="test_project",
        location="us-central1",
        conversation_profile="test_profile",
    )
    client.conversation_name = "conv1"
    client.complete_conversation()

    mock_conv_client_instance.complete_conversation.assert_called_once_with(
        name="conv1"
    )


@patch("cxidk.wrapper.agents.ConversationsClient")
@patch("cxidk.wrapper.agents.ParticipantsClient")
def test_dialogflow_complete_conversation_no_conv(
    mock_participants_client: MagicMock,  # pylint: disable=unused-argument
    mock_conversations_client: MagicMock,  # pylint: disable=unused-argument
) -> None:
    """Test Dialogflow complete_conversation without a conversation."""
    client = agents.Dialogflow(
        project_id="test_project",
        location="us-central1",
        conversation_profile="test_profile",
    )

    with pytest.raises(RuntimeError):
        client.complete_conversation()
