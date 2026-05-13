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

""" Role recognition class for conversation transcripts. """

import json
import pathlib
from vertexai.generative_models import GenerationConfig, GenerativeModel


class RoleRecognizer:
    """Identifies speaker roles in a conversation transcript using a generative model.

    This class uses a large language model (like Gemini) to analyze a
    conversation transcript and assign either an 'AGENT' or 'CUSTOMER' role
    to each utterance. It is designed to handle standard customer service
    interactions as well as agent-to-agent conversations by differentiating
    the primary support provider from the recipient.

    Attributes:
        model: An instance of the Vertex AI GenerativeModel.
    """

    _SCHEMA_DIR = pathlib.Path(__file__).parent.parent / "common/utils/schemas/"
    _RESPONSE_MIME_TYPE = "application/json"
    _TEMPERATURE = 0
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
                                "CUSTOMER"
                            ]
                        },
                        "uid": {
                            "type": "integer"
                        }
                    },
                    "required": [
                        "role",
                        "uid"
                    ]
                }
            }
        },
        "required": [
            "predictions"
        ]
    }

    def __init__(self, model_name: str = "gemini-2.5-pro", prompt: str = ""):
        """Initializes the RoleRecognizer.

        Args:
            model_name: The name of the generative model to use (e.g.,
                "gemini-2.5-pro").
            prompt: An optional custom prompt to override the default role
                recognition instructions for the model.
        """
        self.model_name = model_name
        self.prompt = prompt

        self.model = GenerativeModel(model_name=self.model_name)
        self.generation_config = GenerationConfig(
            temperature=self._TEMPERATURE,
            top_p=self._TOP_P,
            top_k=self._TOP_K,
            response_mime_type=self._RESPONSE_MIME_TYPE,
            response_schema=self._RESPONSE_SCHEMA,
        )

        if not self.prompt:
            self.prompt = self._DEFAULT_PROMPT

    def predict_roles(self, conversation: dict) -> dict:
        """Predicts roles in a conversation transcript.
        
        Args:
            conversation: A dictionary representing the conversation, typically
                containing a list of utterances or text segments.
        
        Returns:
            A dictionary containing the role predictions from the model, where
            each prediction maps a role to an utterance ID.
        """
        response = self.model.generate_content(
            self.prompt.format(conversation=conversation),
            generation_config=self.generation_config,
            stream=False,
        )
        return json.loads(response.text)

    def combine(self, conversation: dict, roles: dict) -> str:
        """Combines the original transcript with the predicted roles.

        This method updates the input conversation dictionary by assigning the
        appropriate channel tag (1 for CUSTOMER, 2 for AGENT) to each utterance
        based on the role predictions.

        Args:
            conversation: The original conversation dictionary.
            roles: The role prediction dictionary returned by `predict_roles`.
        Returns:
            A JSON string representing the updated conversation with channel tags.
        """
        for index, result in enumerate(conversation["results"]):
            try:
                if roles["predictions"][index]["role"] == "AGENT":
                    result["alternatives"][0]["channelTag"] = 2
                    result["channelTag"] = 2
                if roles["predictions"][index]["role"] == "CUSTOMER":
                    result["alternatives"][0]["channelTag"] = 1
                    result["channelTag"] = 1
            except (IndexError, KeyError):
                # if error defaults to customer
                result["alternatives"][0]["channelTag"] = 1
                result["channelTag"] = 1

        return json.dumps(conversation)
