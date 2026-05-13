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

"""A wrapper for the Google Cloud Vertex AI Gemini API."""

from typing import Any, Dict, Optional
from strenum import StrEnum
from google.genai import types
from google import genai

from cxidk.core import base


class GeminiModels(StrEnum):
    """Enum for supported Gemini models."""

    GEMINI_2_5_PRO = "gemini-2.5-pro"
    GEMINI_2_5_FLASH = "gemini-2.5-flash"


class MimeTypes(StrEnum):
    """Enum for supported MIME types."""

    TEXT_PLAIN = "text/plain"
    APPLICATION_JSON = "application/json"


_DEFAULT_SAFETY_SETTINGS = [
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=types.HarmBlockThreshold.BLOCK_NONE,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=types.HarmBlockThreshold.BLOCK_NONE,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=types.HarmBlockThreshold.BLOCK_NONE,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=types.HarmBlockThreshold.BLOCK_NONE,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY,
        threshold=types.HarmBlockThreshold.BLOCK_NONE,
    ),
]


class Generator:
    """A class to generate content using the Gemini models on Google Cloud Vertex AI.

    This class provides a simple, reusable interface for interacting with the Gemini API,
    handling client initialization and content generation with configurable parameters.

    Attributes:
        project_id: The Google Cloud project ID.
        location: The location where the Vertex AI endpoint is hosted (e.g., 'us-central1').
        version: The name of the Gemini model to use.
        auth: An authentication object.
        config: A configuration object.
        client: A Gemini API client.
    """

    def __init__(
        self,
        project_id: str,
        location: str,
        version: Optional[GeminiModels] = None,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ):
        """Initializes the Generator with project and location details.

        Args:
            project_id: The Google Cloud project ID.
            location: The location where the Vertex AI endpoint is hosted.
            version: The name of the Gemini model to use.
            auth: An authentication object.
            config: A configuration object.
        """
        self.auth = auth or base.Auth()
        self.config = config or base.Config()

        self.project_id = project_id
        self.location = location
        self.version = version if version is not None else GeminiModels.GEMINI_2_5_FLASH

        self.client = genai.Client(
            vertexai=True, project=self.project_id, location=self.location
        )

    def content(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        top_k: Optional[int] = 40,
        temperature: Optional[float] = 1,
        top_p: Optional[float] = 0.95,
        output_schema: Optional[Dict[str, Any]] = None,
        output_mime_type: str = MimeTypes.TEXT_PLAIN,
    ) -> str:
        """Generates content based on a text prompt using the configured Gemini model.

        Args:
            prompt: The user's input prompt as a string.
            system_instruction: An optional system instruction to guide the model's behavior.
            top_k: The number of highest probability tokens to consider.
            temperature: A value controlling the randomness of the output.
            top_p: The cumulative probability of tokens to consider.
            output_mime_type: The desired MIME type of the output.
            output_schema: An optional schema to enforce a specific structure on the output.

        Returns:
            The generated content as a string.
        """

        raw_gemini_response = self.client.models.generate_content(
            model=self.version,
            contents=[prompt],
            # https://ai.google.dev/api/generate-content#generationconfig
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                candidate_count=1,
                temperature=temperature,
                top_k=top_k,
                top_p=top_p,
                response_mime_type=output_mime_type,
                response_schema=output_schema,
                safety_settings=_DEFAULT_SAFETY_SETTINGS,
            ),
        )
        if (
            raw_gemini_response.candidates
            and raw_gemini_response.candidates[0].content
            and raw_gemini_response.candidates[0].content.parts
        ):
            return raw_gemini_response.candidates[0].content.parts[0].text or ""
        return ""
