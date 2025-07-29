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
import jsonschema
from datetime import datetime
import time
import os
from typing import Dict, Optional
from google.cloud.speech_v1 import types as types_v1
from google.cloud.speech_v2 import types as types_v2
from enum import Enum

class Role(Enum):
    AGENT = "AGENT"
    CUSTOMER = "CUSTOMER"

_MICROSECONDS_PER_SECOND = 1000000

class Dlp:
    """Class to convert from DLP to Insights and from Insights to DLP"""

    def __init__(self):
        pass

    def from_conversation_json(self):
        "Converts from Conversation JSON to DLP Table"
        ## https://cloud.google.com/contact-center/insights/docs/conversation-data-format
        raise NotImplementedError

    def from_recognize_response(self):
        "Converts from Recognize Response to DLP Table"
        ## https://cloud.google.com/python/docs/reference/speech/latest/
        ## google.cloud.speech_v1.types.RecognizeResponse
        raise NotImplementedError

    def redact(self):
        """Redacts the contents from a DLP table"""
        raise NotImplementedError


class Insights:
    """Class to convert from other common formats to conversation_Json"""

    def __init__(self):
        pass

    def from_aws(self, transcript: dict, transcript_datetime_string: Optional[str] = None) -> dict:
        """Converts transcripts from AWS to Insights JsonConversationInput format
        
        Args:
            transcript: AWS transcript to convert.

        Returns:
            Insights JsonConversationInput format
        """
        # AWS transcripts provides time as offset. Does not contain date and time information.
        # So we take the current epoch at the time of import and then convert to insights compatible format

        # validate transcript_datetime format
        if transcript_datetime_string:
            try:
                datetime_object = datetime.strptime(transcript_datetime_string, '%Y/%m/%d %H:%M:%S')
                transcript_timestamp = int(datetime_object.timestamp())
            except ValueError:
                raise ValueError(f"Invalid datetime format")
        else:
            current_datetime = datetime.now()
            transcript_timestamp = int(current_datetime.timestamp())

        # load aws transcript schema
        file_path = os.path.join(os.path.dirname(__file__), "utils/schemas", "aws_schema.json")
        with open(file_path, 'r') as file:
            aws_schema = json.load(file)

        # validate the transcript with aws_schema
        try:
            jsonschema.validate(instance=transcript, schema=aws_schema)
        except jsonschema.exceptions.ValidationError as e:
            raise ValueError(f"Invalid AWS transcript")

        insights_transcript: Dict[str, list[dict]] = {"entries":[]}

        for entry in transcript['Transcript']:
            user_id = 1 if entry['ParticipantId'] == 'AGENT' else 2
            ent = {
                "role":entry['ParticipantId'],
                "start_timestamp_usec":int((entry['BeginOffsetMillis']/1000) + transcript_timestamp) * _MICROSECONDS_PER_SECOND,
                "text":entry['Content'],
                "user_id":user_id
            }
            insights_transcript['entries'].append(ent)

        return insights_transcript

    def from_genesys_cloud(self, transcript: dict) -> dict:
        """Converts transcripts from Genesys Cloud to conversation_json
        
        Args:
            transcript: Genesys Cloud transcript to convert.

        Returns:
            Insights JsonConversationInput format
        """

        # load genesys_cloud transcript schema
        file_path = os.path.join(os.path.dirname(__file__), "utils/schemas", "genesys_cloud_schema.json")
        with open(file_path, 'r') as file:
            genesys_cloud_schema = json.load(file)

        # validate the transcript with genesys_cloud_schema
        try:
            jsonschema.validate(instance=transcript, schema=genesys_cloud_schema)
        except jsonschema.exceptions.ValidationError as e:
            raise ValueError(f"Invalid Genesys transcript")
        
        insights_transcript: Dict[str, list[dict]] = {"entries":[]}

        for entry in transcript["transcripts"][0]["phrases"]:
            role = Role.CUSTOMER if entry["participantPurpose"] == "external" else Role.AGENT
            user_id = 1 if role == Role.AGENT else 2

            ent = {
                "role":role.value,
                # Genesys Cloud contains the timestamps in milliseconds of epochtime.
                # Since Insights need the timestamps in microseconds, multiply by 1000
                "start_timestamp_usec":entry["startTimeMs"] * 1000,
                "text":entry["text"],
                "user_id":user_id
            }
            insights_transcript['entries'].append(ent)
        
        return insights_transcript

    def from_verint(self):
        """Converts transcripts from Verint to conversation_json"""
        raise NotImplementedError

    def from_nice(self):
        """Converts transcripts from NICE to conversation_json"""
        raise NotImplementedError

    def from_dlp_table(self):
        """Converts transcripts from a DLP table to conversation_json"""
        raise NotImplementedError


class Speech:
    """Class to convert speech things to other things"""

    def __init__(self):
        pass

    def v1_recognizer_to_dict(
            self,
            recognizer_response: types_v1.LongRunningRecognizeResponse
        ) -> list[str]:
        """Converts Speech v1 return to list[str]"""
        dict_response = json.loads(type(recognizer_response).to_json(recognizer_response))
        return dict_response

    def v1_recognizer_to_json(
            self,
            recognizer_response: types_v1.LongRunningRecognizeResponse
        ) -> str:
        """Converts Speech v1 return to str(json)"""
        dict_response = json.loads(type(recognizer_response).to_json(recognizer_response))
        return json.dumps(dict_response)

    def v2_recognizer_to_json(
            self,
            recognizer_response: types_v2.cloud_speech.RecognizeResponse
        ) -> str:
        """Converts Speech v1 return to str(json)"""
        dict_response = json.loads(type(recognizer_response).to_json(recognizer_response))
        return json.dumps(dict_response)
    
    def v2_recognizer_to_dict(
            self,
            recognizer_response: types_v2.cloud_speech.RecognizeResponse
        ) -> list[str]:
        """Converts Speech v1 return to list[str]"""
        dict_response = json.loads(type(recognizer_response).to_json(recognizer_response))
        return dict_response
    
    def v2_json_to_dict(
            self,
            v2_json: dict,
        ) -> list[str]:
        """ Converts speech v2 json dict to list[str]"""
        rr_format_data = {"results":[]}
        uid = 0
        for item in v2_json["results"]:
            if "alternatives" not in item:
                continue
            for alternative in item["alternatives"]:
                if "transcript" not in alternative:
                    continue
                rr_format_data["results"].append({"uid":uid,"text":alternative["transcript"]})
                uid += 1
        return rr_format_data
