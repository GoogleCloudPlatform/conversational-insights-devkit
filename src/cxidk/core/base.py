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
from collections import defaultdict
from typing import Any, Dict, List, Optional
import requests

from google.api_core.client_options import ClientOptions
from google.auth import default
from google.auth.transport.requests import Request as auth_request
from google.oauth2 import service_account
from strenum import StrEnum

GLOBAL_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
]

REGION_LIST = [
    "us",
    "global",
    "us",
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

class Methods(StrEnum):
    """Enumeration of supported HTTP request methods."""

    GET = "get"
    POST = "post"
    DELETE = "delete"

class Environments(StrEnum):
    """Enumeration of supported deployment environments."""

    STAGING = "stg"
    PRODUCTION = "prod"

SUPPORTED_ENVIRONMENTS = [Environments.PRODUCTION, Environments.STAGING]

_DEFAULT_TIMEOUT = 60
SECONDS_IN_A_YEAR = 86400
MILLISECONDS_IN_SECOND = 1000
MICROSECONDS_IN_SECOND = 1000000
ENDPOINT_SUFFIX = "googleapis.com"

logging.basicConfig(
    level=getattr(logging, "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True,
)
logging.getLogger(__name__)


class Auth:
    """Manages authentication and credentials for Google Cloud APIs.

    This class handles the logic for obtaining and refreshing authentication
    credentials, whether they are provided directly, via a file path, a
    dictionary, or through application default credentials.

    Attributes:
        api_calls_dict: A defaultdict to track API call counts.
    """

    def __init__(
        self,
        creds: Optional[service_account.Credentials] = None,
        creds_path: Optional[str] = None,
        creds_dict: Optional[Dict[str, str]] = None,
        scope: Optional[List[str]] = None,
    ):
        """Initializes the Auth object and retrieves credentials.

        This constructor determines the credential source, retrieves them,
        and refreshes the token. It supports service account credentials from
        a file, a dictionary, a provided credentials object, or application
        default credentials.

        Args:
            creds: An optional pre-existing service account credentials object.
            creds_path: The file path to a service account JSON key file.
            creds_dict: A dictionary containing service account key information.
            scope: A list of additional OAuth 2.0 scopes to request.
        """
        self.scopes = GLOBAL_SCOPES
        if scope:
            self.scopes += scope

        if creds:
            self.creds = creds
            self.creds.refresh(auth_request())
            self.token = self.creds.token

        elif creds_path:
            self.creds = service_account.Credentials.from_service_account_file(
                creds_path, scopes=self.scopes
            )
            self.creds.refresh(auth_request())
            self.token = self.creds.token

        elif creds_dict is not None:
            self.creds = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=self.scopes
            )
            self.creds.refresh(auth_request())
            self.token = self.creds.token

        else:
            self.creds, _ = default()
            self.creds.refresh(auth_request())
            self.token = self.creds.token
            self._check_and_update_scopes(self.creds)

        self.api_calls_dict: defaultdict[Any, int] = defaultdict(int)

    def _check_and_update_scopes(self, creds: Any):
        """Updates credential scopes if the credential type supports it.

        For credential types that require explicit scope definition, this method
        appends the globally required scopes.

        Args:
            creds: The credentials object to check and potentially update.
        """
        if creds.requires_scopes:
            self.creds.scopes.extend(GLOBAL_SCOPES)


class Config:
    """Manages generic configurations for API endpoints and environments.

    This class is responsible for validating and storing configuration details
    like region and environment, and for constructing the correct API endpoint URLs.
    """

    def __init__(
        self,
        region: Optional[str] = None,
        environment: Optional[Environments] = None,
    ):
        """Initializes the Config object.

        Args:
            region: The Google Cloud region (e.g., 'us-central1').
            environment: The deployment environment, either 'prod' or 'stg'.
                Defaults to 'prod'.

        Raises:
            ValueError: If the provided region or environment is not supported.
        """
        self.region = region
        self.environment = (
            environment if environment is not None else Environments.PRODUCTION
        )

        if region:
            self.region = region.lower()

        if self.environment not in SUPPORTED_ENVIRONMENTS:
            raise ValueError(
                f"environment {self.environment} is not on the supported list",
                f"of environments: {SUPPORTED_ENVIRONMENTS}",
            )

        if self.region is not None and self.region not in REGION_LIST:
            raise ValueError(
                f"Region {self.region} is not on the supported list of regions: {REGION_LIST}"
            )

    def set_insights_endpoint(self) -> ClientOptions:
        """Constructs the client options for the Contact Center Insights API.

        Returns:
            A ClientOptions object configured with the appropriate API endpoint
            based on the region and environment.
        """
        insights_environments = {
            Environments.PRODUCTION: f"contactcenterinsights.{ENDPOINT_SUFFIX}",
            Environments.STAGING: f"staging-contactcenterinsights.sandbox.{ENDPOINT_SUFFIX}",
        }
        if self.region is None or self.environment == Environments.STAGING:
            path = insights_environments[self.environment]
        else:
            path = f"{self.region}-{insights_environments[self.environment]}"
        return ClientOptions(api_endpoint=str(path))

    def set_texttospeech_endpoint(self) -> ClientOptions:
        """Constructs the client options for the Text-to-Speech API.

        Returns:
            A ClientOptions object configured with the appropriate API endpoint
            based on the region and environment.
        """
        text_to_speech_environments = {
            Environments.PRODUCTION: f"texttospeech.{ENDPOINT_SUFFIX}",
            Environments.STAGING: f"texttospeech.{ENDPOINT_SUFFIX}",
        }

        if self.region is None:
            path = text_to_speech_environments[self.environment]
        else:
            path = f"{self.region}-{text_to_speech_environments[self.environment]}"

        return ClientOptions(api_endpoint=str(path))

    def set_speech_endpoint(self) -> ClientOptions:
        """Constructs the client options for the Speech-to-Text API.

        Returns:
            A ClientOptions object configured with the appropriate API endpoint
            based on the region and environment.
        """
        speech_environments = {
            Environments.PRODUCTION: f"speech.{ENDPOINT_SUFFIX}",
            Environments.STAGING: f"speech.{ENDPOINT_SUFFIX}",
        }

        if self.region is None:
            path = speech_environments[self.environment]
        else:
            path = f"{self.region}-{speech_environments[self.environment]}"

        return ClientOptions(api_endpoint=str(path))

    def set_storage_endpoint(self) -> ClientOptions:
        """Constructs the client options for the Cloud Storage API.

        Returns:
            A ClientOptions object configured with the appropriate API endpoint
            based on the region and environment.
        """
        storage_environments = {
            Environments.PRODUCTION: f"storage.{ENDPOINT_SUFFIX}",
            Environments.STAGING: f"storage.{ENDPOINT_SUFFIX}",
        }

        if self.region is None:
            path = f"https://{storage_environments[self.environment]}"
        else:
            path = f"{self.region}-{storage_environments[self.environment]}"

        return ClientOptions(api_endpoint=str(path))

    def set_dlp_endpoint(self) -> ClientOptions:
        """Constructs the client options for the Cloud DLP API.

        Returns:
            A ClientOptions object configured with the appropriate API endpoint
            based on the region and environment.
        """
        dlp_environments = {
            Environments.PRODUCTION: f"dlp.{ENDPOINT_SUFFIX}",
            Environments.STAGING: f"dlp.{ENDPOINT_SUFFIX}",
        }

        if self.region is None:
            path = f"https://{dlp_environments[self.environment]}"
        else:
            path = f"{self.region}-{dlp_environments[self.environment]}"

        return ClientOptions(api_endpoint=str(path))

    def set_vertex_endpoint(self) -> ClientOptions:
        """Constructs the client options for the Vertex AI API.

        Returns:
            A ClientOptions object configured with the appropriate API endpoint
            based on the region and environment.
        """
        vertex_environments = {
            Environments.PRODUCTION: f"aiplatform.{ENDPOINT_SUFFIX}",
            Environments.STAGING: f"aiplatform.{ENDPOINT_SUFFIX}",
        }

        if self.region is None:
            path = f"https://{vertex_environments[self.environment]}"
        else:
            path = f"{self.region}-{vertex_environments[self.environment]}"

        return ClientOptions(api_endpoint=str(path))

    def set_polysynth_endpoint(self) -> str:
        """Constructs the base URL for the PolySynth API.

        Returns:
            The base URL string for the API endpoint based on the
            configured environment.
        """
        polysynth_environments = {
            Environments.PRODUCTION: "https://ces.googleapis.com/",
            Environments.STAGING: "https://staging-ces-googleapis.sandbox.google.com/",
        }

        return str(polysynth_environments[self.environment])


class Request:
    """A wrapper for making authenticated REST API requests."""

    def __init__(
        self,
        project_id: str,
        location: str,
        base_url: Optional[str] = None,
        auth: Optional[Auth] = None,
        config: Optional[Config] = None,
    ) -> None:
        """Initializes the Request client.

        Args:
            project_id: The Google Cloud project ID.
            location: The Google Cloud location.
            base_url: The base URL for the API endpoint.
            auth: An optional, pre-configured authentication object.
            config: An optional, pre-configured configuration object.
        """

        self.auth = auth or Auth()
        self.config = config or Config()
        self.project_id = project_id
        self.location = location
        self.base_url = base_url or ""

    def make( # pylint: disable=R0911
        self,
        endpoint: str,
        method: str,
        payload: Optional[Dict[str, str]],
        timeout: int = _DEFAULT_TIMEOUT,
        headers: Optional[Dict[str, str]] = None
    ) -> Optional[Dict[str, str]]:
        """Makes an authenticated HTTP request to an API endpoint.

        Args:
            endpoint: The API endpoint to call.
            method: The HTTP method to use (e.g., 'get', 'post').
            payload: A dictionary of parameters to include in the request body
                or as URL parameters for GET requests.
            timeout: The request timeout in seconds.
            headers: Optional dictionary of custom request headers.

        Returns:
            The JSON response from the API as a dictionary, or an empty
            dictionary/None if the request fails or returns no content.
        """
        endpoint =  self.base_url + endpoint
        if payload:
            payload = {k: v for k, v in payload.items() if v is not None}
        if headers is None:
            headers = {}
        if "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {self.auth.creds.token}"

        if method == Methods.GET:
            response = requests.get(
                endpoint,
                params=payload,
                headers=headers,
                timeout=timeout,
            )
            if response.status_code == 200 and response.text:
                return response.json()
            return {}

        if method == Methods.POST:
            response= requests.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=timeout
            )
            if response.status_code == 200 and response.text:
                return response.json()
            return {}

        if method == Methods.DELETE:
            response = requests.delete(
                endpoint,
                json=payload,
                headers=headers,
                timeout=timeout
            )
            if response.status_code == 200 and response.text:
                return response.json()
            return {}

        return None
