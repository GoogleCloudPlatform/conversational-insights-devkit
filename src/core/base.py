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

"""Base for other classes."""

import logging
from typing import List, Dict, Any, Optional
from collections import defaultdict
from google.api_core.client_options import ClientOptions

from google.auth import default
from google.oauth2 import service_account
from google.auth.transport.requests import Request


GLOBAL_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
]

## Note that every product (storage, speech, dlp..) has their own region list
## but to reduce the possible compability errors we will lock in the insights region list
## which is also supported for the other products

REGION_LIST = [
    "global",
    "us-central1",
    "us-east1",
    "us-west1",
    "europe-west1",
    "europe-west2",
    "europe-west3",
    "asia-south1",
    "asia-southeast1",
    "asia-northeast1",
    "northamerica-northeast1",
    "australia-southeast1",
]

SUPPORTED_ENVIROMENTS = ["prod"]
TOOL_NAME = "pyInsights"
SECONDS_IN_A_YEAR = 86400
DEFAULT_REGION = None
DEFAULT_ENVIROMENT = "prod"

MICROSECONDS_IN_SECOND = 1000000
MILLISECONDS_IN_SECOND = 1000

class Auth:
    # pylint: disable=too-few-public-methods
    """Core Class for managing Auth and other shared functions"""

    def __init__(
        self,
        creds: Optional[service_account.Credentials] = None,
        creds_path: Optional[str] = None,
        creds_dict: Optional[Dict[str, str]] = None,
        scope: Optional[List[str]] = None,
    ):
        self.scopes = GLOBAL_SCOPES
        if scope:
            self.scopes += scope

        if creds:
            self.creds = creds
            self.creds.refresh(Request())
            self.token = self.creds.token

        elif creds_path:
            self.creds = service_account.Credentials.from_service_account_file(
                creds_path, scopes=self.scopes
            )
            self.creds.refresh(Request())
            self.token = self.creds.token

        elif creds_dict:
            self.creds = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=self.scopes
            )
            self.creds.refresh(Request())
            self.token = self.creds.token

        else:
            self.creds, _ = default()
            self.creds.refresh(Request())
            self.token = self.creds.token
            self._check_and_update_scopes(self.creds)

        self.api_calls_dict: defaultdict[Any, int] = defaultdict(int)

    def _check_and_update_scopes(self, creds: Any):
        """Update Credentials scopes if possible based on creds type."""
        if creds.requires_scopes:
            self.creds.scopes.extend(GLOBAL_SCOPES)
        else:
            logging.info("Found user creds, skipping global scopes...")


class Config:
    """Class for all generic configurations applicable to all classes"""

    def __init__(
        self,
        region: str = DEFAULT_REGION,
        enviroment: str = DEFAULT_ENVIROMENT,
    ):
        self.region = region

        if region:
            self.region = region.lower()

        self.enviroment = enviroment.lower()

        if self.region in REGION_LIST or self.region is None:
            if self.enviroment in SUPPORTED_ENVIROMENTS:
                self.insights_endpoint = self.set_insights_endpoint()
                self.speech_endpoint = self.set_speech_endpoint()
                self.storage_endpoint = self.set_storage_endpoint()
                self.dlp_endpoint = self.set_dlp_endpoint()
                self.vertex_endpoint = self.set_vertex_endpoint()
            else:
                raise ValueError(
                    f"Enviroment {self.enviroment} is not on the supported list",
                    f"of enviroments: {SUPPORTED_ENVIROMENTS}"
                )

        else:
            raise ValueError(
                f"Region {self.region} is not on the supported list of regions: {REGION_LIST}"
            )

        if self.enviroment not in SUPPORTED_ENVIROMENTS:
            raise ValueError(
                f"Enviroment {self.enviroment} is not on the supported list",
                f"of enviroments: {SUPPORTED_ENVIROMENTS}",
            )

    def set_insights_endpoint(self) -> ClientOptions:
        """Set base endpoint for Insights"""

        insights_enviroments = {"prod": "contactcenterinsights"}
        enviroment = insights_enviroments[self.enviroment]

        if self.region is None:
            path = f"{enviroment}.googleapis.com"
        else:
            path = f"{self.region}-{enviroment}.googleapis.com"

        return ClientOptions(api_endpoint=str(path))

    def set_speech_endpoint(self) -> ClientOptions:
        """Set base endpoint Speech"""

        speech_enviroments = {"prod": "speech"}
        enviroment = speech_enviroments[self.enviroment]

        if self.region is None:
            path = f"{enviroment}.googleapis.com"
        else:
            path = f"{self.region}-{enviroment}.googleapis.com"

        return ClientOptions(api_endpoint=str(path))

    def set_storage_endpoint(self) -> ClientOptions:
        """Set base endpoint DLP"""

        storage_enviroments = {"prod": "storage"}
        enviroment = storage_enviroments[self.enviroment]

        if self.region is None:
            path = f"https://{enviroment}.googleapis.com"
        else:
            path = f"{self.region}-{enviroment}.googleapis.com"

        return ClientOptions(api_endpoint=str(path))

    def set_dlp_endpoint(self) -> ClientOptions:
        """Set base endpoint DLP"""

        dlp_enviroments = {"prod": "dlp"}
        enviroment = dlp_enviroments[self.enviroment]

        if self.region is None:
            path = f"https://{enviroment}.googleapis.com"
        else:
            path = f"{self.region}-{enviroment}.googleapis.com"

        return ClientOptions(api_endpoint=str(path))

    def set_vertex_endpoint(self) -> ClientOptions:
        """Set base endpoint DLP"""

        vertex_enviroments = {"prod": "aiplatform"}
        enviroment = vertex_enviroments[self.enviroment]

        if self.region is None:
            path = f"https://{enviroment}.googleapis.com"
        else:
            path = f"{self.region}-{enviroment}.googleapis.com"

        return ClientOptions(api_endpoint=str(path))
