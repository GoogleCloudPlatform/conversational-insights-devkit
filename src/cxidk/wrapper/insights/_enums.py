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

"""Shared constants and enumerations for CCAI Insights wrappers."""

import enum
from enum import StrEnum

from google.cloud import contact_center_insights_v1
from google.cloud.contact_center_insights_v1 import types

_RETRY_ATTEMPTS = 4
_ISSUE_MODEL_DEPLOYED = "DEPLOYED"
_LRO_POLL_INTERVAL = 5.0
_LRO_TIMEOUT = 1800.0


class Masks(StrEnum):
    """Enum for supported field masks in update requests."""
    #Note that the types has to be camelcase becaus it's the api requirement
    ANALYSIS = "analysisConfig"
    TTL = "conversationTtl"
    PUBSUB = "pubsubNotificationSettings"
    LANGUAGE = "languageCode"
    SPEECH_RECOGNIZER = "speechConfig.speechRecognizer"
    DLP = "redactionConfig.inspectTemplate,redactionConfig.deidentifyTemplate"

class Annotators(StrEnum):
    """Enum for supported annotators."""
    QAI = "QAI"
    INSIGHTS = "INSIGHTS"
    TOPIC_MODEL = "TOPIC MODEL"
    SUMMARIZATION = "SUMMARIZATION"

class AgentType(enum.Enum):
    """Enum for supported agent types."""
    HUMAN_AGENT = types.ConversationParticipant.Role.HUMAN_AGENT
    AUTOMATED_AGENT = types.ConversationParticipant.Role.AUTOMATED_AGENT

class Mediums(enum.Enum):
    """Enum for supported conversation mediums."""
    PHONE_CALL = contact_center_insights_v1.Conversation.Medium.PHONE_CALL
    CHAT = contact_center_insights_v1.Conversation.Medium.CHAT
