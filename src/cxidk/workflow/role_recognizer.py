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

"""Role recognition class for conversation transcripts."""

import copy
import json
import os
from typing import Any, Dict, Optional

from cxidk.core import base
from cxidk.wrapper import vertex


class RoleRecognizer:
    """Identifies speaker roles in a conversation transcript using a generative model.

    This class uses a large language model (Gemini via `cxidk.wrapper.vertex.Generator`
    and `google-genai`) to analyze a conversation transcript and assign either an
    'AGENT' or 'CUSTOMER' role to each utterance. It is designed to handle standard
    customer service interactions as well as agent-to-agent conversations by
    differentiating the primary support provider from the recipient.

    Attributes:
        generator: An instance of `cxidk.wrapper.vertex.Generator`.
    """

    _RESPONSE_MIME_TYPE = vertex.MimeTypes.APPLICATION_JSON
    _TEMPERATURE = 0.0
    _TOP_P = 0.95
    _TOP_K = 40
    _DEFAULT_PROMPT = """
        You are a multilingual role recognition expert in identifying roles within a conversation transcript.

        Task:
        Identify the role (AGENT or CUSTOMER) of each utterance in the given conversation.
        If the conversation involves only two agents, assign one as the CUSTOMER and the other as the AGENT to maintain role differentiation.

        **Guidelines:**

        * Analyze the entire conversation to understand the context.
        * Assign the correct role to each line of the utterance based on its content and the flow of the conversation.
        * DO NOT add or split, modify or combine any utterances and sentences.

        **Important Considerations:**
            * **Agent-to-Agent Conversations:**
            In conversations between two agents, designate one as "AGENT" and the other as "CUSTOMER" based on the context of their interaction.
            Consider which agent is primarily providing information or support (AGENT) and which is primarily receiving it (CUSTOMER).
            The distinction can be subtle, so focus on the flow of information and assistance.

        **Few-Shot Examples:**

        **Example 1 (Agent-to-Customer):**
            *Input:*
                Utterance 1: "Hello, how can I help you today?"
                Utterance 2: "Hi, I'm having trouble logging in."
                Utterance 3: "Have you tried resetting your password?"
                Utterance 4: "Yes, but it's not working."
                Utterance 5: "Okay, let's try a different approach."
            *Output:*
                Utterance 1: "AGENT"
                Utterance 2: "CUSTOMER"
                Utterance 3: "AGENT"
                Utterance 4: "CUSTOMER"
                Utterance 5: "AGENT"

        **Example 2 (Agent-to-Agent):**
            *Input:*
                Utterance 1: "Hey, I'm having trouble with this customer's issue.  They're saying the order hasn't shipped yet."
                Utterance 2: "Okay, let me check the order status for you. What's the order number?"
                Utterance 3: "It's #12345."
                Utterance 4: "Thanks.  Looks like there was a delay at the warehouse. I'll update the customer and offer a discount."
            *Output:*
                Utterance 1: "CUSTOMER"
                Utterance 2: "AGENT"
                Utterance 3: "CUSTOMER"
                Utterance 4: "AGENT"

        Conversation:
        {conversation}
    """
    _RESPONSE_SCHEMA = {
        "type": "object",
        "properties": {
            "predictions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {
                            "type": "string",
                            "enum": [
                                "AGENT",
                                "CUSTOMER",
                            ],
                        },
                        "uid": {
                            "type": "integer",
                        },
                    },
                    "required": [
                        "role",
                        "uid",
                    ],
                },
            }
        },
        "required": [
            "predictions",
        ],
    }

    def __init__(
        self,
        model_name: str = "gemini-2.5-pro",
        prompt: str = "",
        *,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
        generator: Optional[vertex.Generator] = None,
    ):
        """Initializes the RoleRecognizer.

        Args:
            model_name: The name of the generative model to use (e.g.,
                "gemini-2.5-pro").
            prompt: An optional custom prompt to override the default role
                recognition instructions for the model.
            project_id: Optional GCP project ID (falls back to `CXIDK_PROJECT_ID`
                or `GOOGLE_CLOUD_PROJECT`).
            location: Optional GCP location (falls back to `CXIDK_LOCATION` or
                `us-central1`).
            auth: Optional `base.Auth` credentials object.
            config: Optional `base.Config` object.
            generator: Optional pre-configured `vertex.Generator` instance.
        """
        self.model_name = model_name
        self.prompt = prompt or self._DEFAULT_PROMPT

        resolved_project = (
            project_id
            or os.environ.get("CXIDK_PROJECT_ID")
            or os.environ.get("GOOGLE_CLOUD_PROJECT")
            or ""
        )
        resolved_location = (
            location or os.environ.get("CXIDK_LOCATION") or "us-central1"
        )

        self.generator = generator or vertex.Generator(
            project_id=resolved_project,
            location=resolved_location,
            version=self.model_name,
            auth=auth,
            config=config,
        )

    def predict_roles(self, conversation: Dict[str, Any]) -> Dict[str, Any]:
        """Predicts roles in a conversation transcript.

        Args:
            conversation: A dictionary representing the conversation, typically
                containing a list of utterances or text segments.

        Returns:
            A dictionary containing the role predictions from the model, where
            each prediction maps a role to an utterance ID.
        """
        response_text = self.generator.content(
            prompt=self.prompt.format(conversation=conversation),
            temperature=self._TEMPERATURE,
            top_p=self._TOP_P,
            top_k=self._TOP_K,
            output_mime_type=self._RESPONSE_MIME_TYPE,
            output_schema=self._RESPONSE_SCHEMA,
        )
        return json.loads(response_text)

    def combine_dict(
        self, conversation: Dict[str, Any], roles: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Returns a copy of `conversation` updated with predicted channel tags.

        Assigns channelTag 1 for CUSTOMER and 2 for AGENT on each utterance.

        Args:
            conversation: The original conversation dictionary.
            roles: The role prediction dictionary returned by `predict_roles`.

        Returns:
            Updated conversation dictionary with channel tags applied.
        """
        updated = copy.deepcopy(conversation)
        for index, result in enumerate(updated.get("results", [])):
            try:
                predicted_role = roles["predictions"][index]["role"]
                tag = 2 if predicted_role == "AGENT" else 1
                result["alternatives"][0]["channelTag"] = tag
                result["channelTag"] = tag
            except (IndexError, KeyError):
                # if error defaults to customer
                result["alternatives"][0]["channelTag"] = 1
                result["channelTag"] = 1
        return updated

    def combine(
        self, conversation: Dict[str, Any], roles: Dict[str, Any]
    ) -> str:
        """Combines the original transcript with the predicted roles as JSON.

        This method updates the input conversation dictionary by assigning the
        appropriate channel tag (1 for CUSTOMER, 2 for AGENT) to each utterance
        based on the role predictions.

        Args:
            conversation: The original conversation dictionary.
            roles: The role prediction dictionary returned by `predict_roles`.

        Returns:
            A JSON string representing the updated conversation with channel tags.
        """
        updated = self.combine_dict(conversation, roles)
        conversation.clear()
        conversation.update(updated)
        return json.dumps(conversation)
