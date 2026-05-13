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

"""Manages conversations with virtual agents.

This module provides classes for interacting with different virtual agent
platforms, including PolySynth and Dialogflow.
"""

import time
from typing import Any, Dict, Optional
import uuid
import logging
from google.cloud import dialogflow_v2beta1
from google.cloud.dialogflow_v2beta1.services.conversations import ConversationsClient
from google.cloud.dialogflow_v2beta1.services.participants import ParticipantsClient
from google.cloud.dialogflow_v2beta1.services.conversation_profiles import (
    ConversationProfilesClient,
)
import requests
import google.auth
from google.auth.transport.requests import Request

from cxidk.core import base

_EXPECTED_RESOURCE_TYPES = ["type.googleapis.com/google.cloud.ces.v1.App"]


class PolySynth:
    """A client for interacting with the PolySynth conversational agent API.

    This class provides a wrapper for the PolySynth API, simplifying session
    creation, message sending, authentication, and the handling of long-running
    operations.

    Attributes:
        project_id: The ID of the Google Cloud project.
        location: The Google Cloud location for the API endpoint.
        auth: An authentication handler object.
        config: A configuration handler object.
        credentials_token: The OAuth 2.0 access token.
        agent_id: The ID of the agent for the current session.
        current_session_id: The fully qualified ID of the current session.
    """

    api_version = "v1beta"

    def __init__(
        self,
        project_id: str,
        location: str,
        env: str = "stg",
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ) -> None:
        """Initializes the PolySynth client.

        Args:
            project_id: The ID of the Google Cloud project.
            location: The Google Cloud location for the API endpoint.
            env: The target environment, such as "stg" or "prod".
            auth: An optional, pre-configured authentication handler.
            config: An optional, pre-configured configuration handler.
        """

        self.project_id = project_id
        self.location = location
        self.auth = auth or base.Auth()
        self.config = config or base.Config(environment=base.Environments(env))
        self.credentials_token: Optional[str] = None
        self.agent_id: Optional[str] = None
        self.current_session_id: Optional[str] = None
        self._set_credentials()

    @property
    def parent(self) -> str:
        """Constructs the parent resource string for API requests.

        Returns:
            The formatted parent string, e.g., 'projects/{id}/locations/{loc}'.
        """
        return f"projects/{self.project_id}/locations/{self.location}"

    @property
    def base_url(self) -> str:
        """Constructs the base URL for the PolySynth API.

        Returns:
            The base URL for the API endpoint.
        """
        return f"{self.config.set_polysynth_endpoint()}{self.api_version}/"

    def _set_credentials(self) -> Optional[str]:
        """Retrieves and refreshes the default application credentials.

        This method obtains the default credentials, refreshes them if they are
        expired, and stores the access token.

        Returns:
            The access token as a string, or None if it could not be retrieved.
        """
        credentials, _ = google.auth.default()
        if not credentials.valid or credentials.expired:
            credentials.refresh(Request())

        if credentials.token:
            self.credentials_token = credentials.token
        else:
            logging.info("Could not retrieve access token.")

        return self.credentials_token

    def _make_request(
        self,
        method,
        url,
        headers=None,
        json=None,
        params=None,
        operation_timeout=300,
    ):
        """Makes an authenticated HTTP request and handles long-running operations.

        Args:
            method: The HTTP method (e.g., "GET", "POST").
            url: The URL endpoint for the request.
            headers: Optional dictionary of request headers.
            json: Optional JSON payload for the request body.
            params: Optional dictionary of URL parameters.
            operation_timeout: The timeout in seconds for polling long-running operations.

        Returns:
            The JSON response from the API as a dictionary, or None if the
            request fails.
        """
        access_token = self._set_credentials()

        if not access_token:
            logging.info("Failed to get access token.")
            return None

        if headers is None:
            headers = {}

        headers["Authorization"] = f"Bearer {access_token}"  # Add authorization header
        if json is not None and "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"  # Ensure Content-Type for JSON
        try:
            response = requests.request(
                method, self.base_url + url, headers=headers,
                json=json, params=params, timeout=operation_timeout
            )
            response.raise_for_status()
            response_json = response.json()

            # Check for long-running operation
            if "name" in response_json and "done" in response_json:
                if not response_json["done"]:
                    return self._poll_operation(
                        response_json["name"], timeout=operation_timeout
                    )
                return response_json  # Operation already complete
            return response_json

        except requests.exceptions.RequestException:
            logging.info("Response content: %s", "")
            return None

    def _poll_operation(
        self,
        operation_name,
        timeout=300,
        initial_sleep=2,
        poll_interval=5,
    ):
        """Polls a long-running operation until it completes or times out.

        Args:
            operation_name: The name of the operation to poll.
            timeout: The maximum time in seconds to wait for completion.
            initial_sleep: The initial delay before the first poll.
            poll_interval: The interval in seconds between poll attempts.

        Returns:
            The response payload from the completed operation, or None on timeout.

        Raises:
            RuntimeError: If the operation fails.
        """
        start_time = time.time()
        if initial_sleep > 0:
            time.sleep(initial_sleep)

        while time.time() - start_time < timeout:
            operation_url = f"{operation_name}"

            result = self._make_request("GET", operation_url)

            if result and isinstance(result, dict):
                if "done" in result:
                    if result.get("done"):
                        logging.info(
                            "Operation %s completed (via Operation object).",
                            operation_name,
                        )
                        if "response" in result:
                            return result.get("response")
                        if "error" in result:
                            error_details = result.get("error")
                            logging.error(
                                "Operation %s failed: %s", operation_name, error_details
                            )
                            raise RuntimeError(
                                f"Operation {operation_name} failed: {error_details}"
                            )
                        logging.warning(
                            "Operation %s completed (via Op) without 'response' or 'error'.",
                            operation_name,
                        )
                        return {}  # Indicate success without payload
                    logging.debug(
                        "Operation %s pending (via Op). Sleeping for %ss.",
                        operation_name,
                        poll_interval,
                    )
                if result.get("@type") in _EXPECTED_RESOURCE_TYPES:
                    logging.info(
                        "Operation %s completed (detected final resource type).",
                        operation_name,
                    )
                    return result
                logging.warning(
                    "Polling %s: Received unexpected dictionary format. "
                    "Retrying after %ss. Response: %s",
                    operation_name,
                    poll_interval,
                    result,
                )
            elif result is None:
                logging.warning(
                    "Polling %s: No result/error from request. Retrying after %ss.",
                    operation_name,
                    poll_interval,
                )
            else:
                logging.error(
                    "Polling %s: Received completely unexpected response type (%s). "
                    "Retrying after %ss. Response: %s",
                    operation_name,
                    type(result),
                    poll_interval,
                    result,
                )

            time.sleep(poll_interval)

        logging.error(
            "Operation %s timed out after %s seconds.", operation_name, timeout
        )
        return None

    def create_session(self, agent_id: str, unique_id: Optional[str] = None) -> str:
        """Creates a new conversational session for a given agent.

        Args:
            agent_id: The identifier of the agent.
            unique_id: An optional unique identifier for the session. If not
                provided, a random UUID is generated.
        Returns:
            The fully qualified session ID string.
        """
        self.agent_id = agent_id
        if unique_id:
            session_id = unique_id
        else:
            session_id = str(uuid.uuid4())

        self.current_session_id = (
            f"{self.parent}/apps/{self.agent_id}/sessions/{session_id}"
        )
        return self.current_session_id

    def send_message(self, text: str, session_id: Optional[str] = None):
        """Sends a text message to a conversational session and gets a response.

        Args:
            text: The user's text input to send to the agent.
            session_id: The ID of the session to which the message should be
                sent.

        Returns:
            The agent's text response as a concatenated string. If no text is
            returned, it provides the raw session output or a session end message.
        """
        payload = {"config": {"session": session_id}}
        # Construct the input part - currently only text
        session_input: Dict[str, Any] = {}
        if text is not None:
            session_input["text"] = text

        payload["inputs"] = session_input
        url = f"{session_id}:runSession"
        session_output = self._make_request("POST", url, json=payload)

        text_response = ''
        try:
            if session_output and session_output.get("outputs"):
                for response in session_output["outputs"]:
                    if response.get("text"):
                        text_response += response["text"] + "\n"

            if len(text_response) != 0:
                answer = text_response
            else:
                answer = session_output

        except Exception as e:  # pylint: disable=broad-exception-caught
            answer = 'session ended'
            logging.info("An error occurred: %s", e)

        return answer


class Dialogflow:
    """A client for managing conversations with a Dialogflow CX agent.

    This class wraps the Dialogflow v2beta1 API to simplify the process of
    creating conversations, adding participants, sending messages, and managing
    conversation profiles.

    Attributes:
        project_id: The ID of the Google Cloud project.
        location: The Google Cloud location for the API endpoint.
        conversation_profile: The name of the conversation profile to use.
        conversation_name: The resource name of the current conversation.
        participant_name: The resource name of the current participant.
    """
    def __init__(
        self,
        project_id: str,
        location: str,
        conversation_profile: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ):
        """Initializes the Dialogflow client.

        Args:
            project_id: The ID of the Google Cloud project.
            location: The Google Cloud location for the API endpoint.
            conversation_profile: The name of the conversation profile to use.
            auth: An optional, pre-configured authentication handler.
            config: An optional, pre-configured configuration handler.
        """
        self.project_id = project_id
        self.location = location
        self.auth = auth or base.Auth()
        self.config = config or base.Config()
        self.conversation_profile = conversation_profile
        self.parent = f"projects/{project_id}/locations/{location}"

        self.conversation_client = ConversationsClient()
        self.participant_client = ParticipantsClient()

        self.conversation_name: Optional[str] = None
        self.participant_name: Optional[str] = None

    def create_conversation(self) -> str:
        """Creates a new Dialogflow conversation.

        Returns:
            The resource name of the newly created conversation.
        """

        conversation = dialogflow_v2beta1.Conversation()
        conversation.conversation_profile = (
            f"{self.parent}/conversationProfiles/{self.conversation_profile}"
        )
        conversation.lifecycle_state = (
            dialogflow_v2beta1.Conversation.LifecycleState.IN_PROGRESS  # type: ignore[assignment]
        )
        response = self.conversation_client.create_conversation(
            parent=self.parent, conversation=conversation
        )
        self.conversation_name = response.name
        return self.conversation_name

    def create_participant(self):
        """Creates a new 'END_USER' participant in the current conversation.

        Returns:
            The resource name of the newly created participant.

        Raises:
            RuntimeError: If a conversation has not been created first.
        """
        if not self.conversation_name:
            raise RuntimeError(
                "Must call create_conversation() before create_participant()"
            )
        participant = dialogflow_v2beta1.Participant()
        participant.role = dialogflow_v2beta1.Participant.Role.END_USER
        new_participant = self.participant_client.create_participant(
            parent=self.conversation_name, participant=participant
        )
        self.participant_name = new_participant.name
        logging.info("Created participant: %s", self.participant_name)
        return self.participant_name

    def create_conversation_profile(
        self,
        virtual_agent_path: str,
        display_name: str,
    ):
        """Creates a new Dialogflow conversation profile for a virtual agent.

        Args:
            virtual_agent_path: The resource name of the virtual agent.
            display_name: The human-readable display name for the profile.

        Returns:
            The newly created ConversationProfile object.
        """
        client = ConversationProfilesClient()
        conversation_profile = dialogflow_v2beta1.ConversationProfile(
            display_name=display_name,
            automated_agent_config=dialogflow_v2beta1.AutomatedAgentConfig(
                agent=virtual_agent_path,
            ),
        )
        response = client.create_conversation_profile(
            parent=self.parent,
            conversation_profile=conversation_profile,
        )
        logging.info("Created conversation profile: %s", response.name)
        return response

    def send_message(self, text: str, language_code: str = "en-US") -> str:
        """Sends a text message from the participant and gets a reply.

        Args:
            text: The user's text input to send to the agent.
            language_code: The language of the input text (e.g., "en-US").

        Returns:
            The agent's text reply as a string.

        Raises:
            RuntimeError: If a participant has not been created first.
        """
        if not self.participant_name:
            raise RuntimeError("Must call create_participant() before send_message()")
        text_input = dialogflow_v2beta1.TextInput(
            text=text, language_code=language_code
        )
        request = dialogflow_v2beta1.AnalyzeContentRequest(
            participant=self.participant_name,
            text_input=text_input,
        )

        response = self.participant_client.analyze_content(request=request)

        return str(response.reply_text)

    def complete_conversation(self) -> None:
        """Marks the current conversation as complete.

        Raises:
            RuntimeError: If a conversation has not been created first.
        """
        if not self.conversation_name:
            raise RuntimeError(
                "Must call create_conversation() before complete_conversation()"
            )
        self.conversation_client.complete_conversation(
            name=self.conversation_name
        )
