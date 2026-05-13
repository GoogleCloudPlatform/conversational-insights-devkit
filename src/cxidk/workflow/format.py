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

"""A class for all Insigths things related"""

import json
import os
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

# pyright: reportMissingModuleSource=false
import jsonschema
from google.cloud.speech_v1 import types as types_v1
from google.cloud.speech_v2 import types as types_v2


class Role(Enum):
    """An enum to represent the role of a speaker in a conversation."""

    AGENT = "AGENT"
    CUSTOMER = "CUSTOMER"


_MICROSECONDS_PER_SECOND = 1000000


class Dlp:
    """Provides methods for converting data formats for Cloud DLP.

    This class handles the transformation of conversation data into the table
    format required by the Cloud Data Loss Prevention (DLP) API.
    """

    def __init__(self):
        """Initializes the Dlp format converter."""

    def from_recognize_response(self, data_input):
        """Converts a Speech-to-Text response into a DLP table format.

        This method takes a standard speech recognition response, which contains
        transcript alternatives and word-level details, and restructures it
        into a table format suitable for processing with the Cloud DLP API.
        The table separates full transcript segments and individual words.

        Args:
            data_input: A dictionary or JSON string representing a speech
                recognition response.

        Returns:
            A dictionary structured as a DLP table with headers and rows.
        """
        # Parse the input if it's a string, otherwise assume it's a dict
        if isinstance(data_input, str):
            data = json.loads(data_input)
        else:
            data = data_input

        results = data.get("results", [])

        transcript_list = []
        transcript_headers = []
        word_list = []
        word_headers = []
        word_counter = 0

        for t_idx, item in enumerate(results):
            if not item.get("alternatives") or not item["alternatives"][0].get(
                "transcript"
            ):
                continue
            # 1. Handle Transcripts
            phrase = item["alternatives"][0]["transcript"]
            transcript_list.append({"string_value": phrase})
            transcript_headers.append({"name": f"transcript_{t_idx}"})

            # 2. Handle Words
            for word_info in item["alternatives"][0].get("words", []):
                word_list.append({"string_value": word_info["word"]})
                word_headers.append({"name": f"word_{word_counter}"})
                word_counter += 1
        return {
            "transcript_header": transcript_headers,
            "transcript": transcript_list,
            "word_header": word_headers,
            "word": word_list,
        }

    def from_conversation_json(self):
        """Converts from a conversation JSON to a DLP table. (Not implemented)."""
        raise NotImplementedError


class Insights:
    """Provides methods for converting various transcript formats to the Insights format.

    This class is a utility for transforming conversation transcripts from
    different providers (like AWS, Genesys Cloud) into the standard
    `JsonConversationInput` format used by Contact Center AI Insights.
    """

    def __init__(self):
        """Initializes the Insights format converter."""

    def from_aws(
        self, transcript: dict, transcript_datetime_string: Optional[str] = None
    ) -> dict:
        """Converts an AWS Transcribe transcript to the Insights format.

        Since AWS transcripts use a millisecond offset from the start, this
        method uses either a provided datetime string or the current time as
        a baseline to calculate absolute timestamps for the Insights format.

        Args:
            transcript: AWS transcript to convert.

        Returns:
            Insights JsonConversationInput format
        """
        # validate transcript_datetime format
        if transcript_datetime_string:
            datetime_object = datetime.strptime(
                transcript_datetime_string, "%Y/%m/%d %H:%M:%S"
            )
            transcript_timestamp = int(datetime_object.timestamp())
        else:
            current_datetime = datetime.now()
            transcript_timestamp = int(current_datetime.timestamp())

        # load aws transcript schema
        file_path = os.path.join(
            os.path.dirname(__file__), "utils/schemas", "aws_schema.json"
        )
        with open(file_path, "r", encoding="utf-8") as file:
            aws_schema = json.load(file)

        # validate the transcript with aws_schema
        jsonschema.validate(instance=transcript, schema=aws_schema)

        insights_transcript: Dict[str, list[dict]] = {"entries": []}

        for entry in transcript["Transcript"]:
            user_id = 1 if entry["ParticipantId"] == "AGENT" else 2
            ent = {
                "role": entry["ParticipantId"],
                "start_timestamp_usec": int(
                    (entry["BeginOffsetMillis"] / 1000) + transcript_timestamp
                )
                * _MICROSECONDS_PER_SECOND,
                "text": entry["Content"],
                "user_id": user_id,
            }
            insights_transcript["entries"].append(ent)

        return insights_transcript

    def from_genesys_cloud(self, transcript: dict) -> dict:
        """Converts a Genesys Cloud transcript to the Insights format.

        This method maps participant roles and converts millisecond-based
        timestamps from a Genesys Cloud transcript into the format required by Insights.

        Args:
            transcript: Genesys Cloud transcript to convert.

        Returns:
            Insights JsonConversationInput format
        """
        # load genesys_cloud transcript schema
        file_path = os.path.join(
            os.path.dirname(__file__), "utils/schemas", "genesys_cloud_schema.json"
        )
        with open(file_path, "r", encoding="utf-8") as file:
            genesys_cloud_schema = json.load(file)

        # validate the transcript with genesys_cloud_schema
        jsonschema.validate(instance=transcript, schema=genesys_cloud_schema)

        insights_transcript: Dict[str, list[dict]] = {"entries": []}

        for entry in transcript["transcripts"][0]["phrases"]:
            role = (
                Role.CUSTOMER
                if entry["participantPurpose"] == "external"
                else Role.AGENT
            )
            user_id = 1 if role == Role.AGENT else 2

            ent = {
                "role": role.value,
                # Genesys Cloud contains the timestamps in milliseconds of epochtime.
                # Since Insights need the timestamps in microseconds, multiply by 1000
                "start_timestamp_usec": entry["startTimeMs"] * 1000,
                "text": entry["text"],
                "user_id": user_id,
            }
            insights_transcript["entries"].append(ent)

        return insights_transcript

    def from_insights_bq(self):
        """Converts from Insights BigQuery format. (Not implemented)."""
        raise NotImplementedError

    def from_verint(self):
        """Converts from Verint transcript format. (Not implemented)."""
        raise NotImplementedError

    def from_nice(self):
        """Converts from NICE transcript format. (Not implemented)."""
        raise NotImplementedError

    def from_dlp_recognize_response(
        self, dlp_item: str, original_conversation: dict
    ) -> dict:
        """Converts a DLP de-identification response back to a recognize response format.

        This method reconstructs a speech recognition transcript by replacing the
        original text with the redacted text from a DLP process, while preserving
        the original timestamps and other metadata.

        Args:
            dlp_item: The response from a DLP de-identify content request, which
                contains the redacted table data.
            original_conversation: The original conversation transcript in a
                recognize response format (as a dictionary).

        Returns:
            A dictionary in the recognize response format with redacted transcripts.
        """
        reconstructed_conversation = original_conversation
        redacted_transcripts = [
            value.string_value for value in dlp_item.item.table.rows[0].values # type: ignore[attr-defined] # pylint: disable=line-too-long
        ]

        for i, result in enumerate(reconstructed_conversation.get("results", [])):
            if i < len(redacted_transcripts):
                result["alternatives"][0]["transcript"] = redacted_transcripts[i]

        return reconstructed_conversation


class Speech:
    """Provides methods for converting Speech-to-Text API responses.

    This class contains utilities to transform the response objects from
    Google's Speech-to-Text API (both v1 and v2) into more common formats
    like dictionaries or JSON strings.
    """

    def __init__(self):
        """Initializes the Speech format converter."""

    def v1_recognizer_to_dict(
        self, recognizer_response: types_v1.LongRunningRecognizeResponse
    ) -> dict:
        """Converts a Speech-to-Text v1 response object to a dictionary.

        Args:
            recognizer_response: The response object from a v1 long-running
                recognition job.

        Returns:
            The response data as a dictionary.
        """
        dict_response = json.loads(
            type(recognizer_response).to_json(recognizer_response)
        )
        return dict_response

    def v1_recognizer_to_json(
        self, recognizer_response: types_v1.LongRunningRecognizeResponse
    ) -> str:
        """Converts a Speech-to-Text v1 response object to a JSON string.

        Args:
            recognizer_response: The response object from a v1 long-running
                recognition job.

        Returns:
            The response data as a JSON-formatted string.
        """
        dict_response = json.loads(
            type(recognizer_response).to_json(recognizer_response)
        )
        return json.dumps(dict_response)

    def v2_recognizer_to_json(
        self, recognizer_response: types_v2.cloud_speech.RecognizeResponse
    ) -> str:
        """Converts a Speech-to-Text v2 response object to a JSON string.

        Args:
            recognizer_response: The response object from a v2 recognition job.

        Returns:
            The response data as a JSON-formatted string.
        """
        dict_response = json.loads(
            type(recognizer_response).to_json(recognizer_response)
        )
        return json.dumps(dict_response)

    def v2_recognizer_to_dict(
        self, recognizer_response: types_v2.cloud_speech.RecognizeResponse
    ) -> dict:
        """Converts a Speech-to-Text v2 response object to a dictionary.

        Args:
            recognizer_response: The response object from a v2 recognition job.

        Returns:
            The response data as a dictionary.
        """
        dict_response = json.loads(
            type(recognizer_response).to_json(recognizer_response)
        )
        return dict_response

    def v2_json_to_dict(
        self,
        v2_json: dict,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Extracts transcript text from a Speech v2 JSON dictionary.

        This method processes a dictionary representation of a Speech-to-Text v2
        response and extracts the transcript text from each alternative,
        formatting it into a simplified dictionary structure for role recognition.

        Args:
            v2_json: A dictionary representing a v2 speech recognition response.

        Returns:
            A dictionary containing a list of results, where each result has a
            unique ID and the transcribed text.
        """
        rr_format_data: Dict[str, List[Dict[str, Any]]] = {"results": []}
        uid = 0
        for item in v2_json["results"]:
            if "alternatives" not in item:
                continue
            for alternative in item["alternatives"]:
                if "transcript" not in alternative:
                    continue
                rr_format_data["results"].append(
                    {"uid": uid, "text": alternative["transcript"]}
                )
                uid += 1
        return rr_format_data
