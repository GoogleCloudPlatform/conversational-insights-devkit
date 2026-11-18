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
import time
from collections import defaultdict
from enum import StrEnum
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlsplit
import requests

from google.api_core.client_options import ClientOptions
from google.auth import credentials as auth_credentials
from google.auth import default
from google.auth.transport.requests import Request as auth_request
from google.oauth2 import service_account

from cxidk.core import errors
from cxidk.core import retry

logger = logging.getLogger(__name__)

GLOBAL_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
]

REGION_LIST = [
    "us",
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


class Methods(StrEnum):
    """Enumeration of supported HTTP request methods."""

    GET = "get"
    POST = "post"
    PATCH = "patch"
    DELETE = "delete"


class Environments(StrEnum):
    """Enumeration of supported deployment environments."""

    STAGING = "stg"
    PRODUCTION = "prod"


SUPPORTED_ENVIRONMENTS = [Environments.PRODUCTION, Environments.STAGING]

_HTTP_VERBS = frozenset(
    [Methods.GET, Methods.POST, Methods.PATCH, Methods.DELETE]
)

_SUCCESS_STATUS_CODES = frozenset(range(200, 300))

_TRUSTED_HOST_SUFFIXES = (
    ".googleapis.com",
    ".sandbox.google.com",
)


def is_trusted_google_host(hostname: Optional[str]) -> bool:
    """Checks whether `hostname` is an official Google Cloud API endpoint.

    Args:
        hostname: Lowercased hostname parsed from a URL.

    Returns:
        True only when the hostname belongs to `googleapis.com` or
        `sandbox.google.com` with safe DNS label characters.
    """
    if not hostname:
        return False
    host = hostname.strip().lower()
    if any(ch in host for ch in ("/", "?", "#", "@", " ", "\t", "\r", "\n")):
        return False
    if host == "googleapis.com":
        return True
    return any(
        host.endswith(suffix) and len(host) > len(suffix)
        for suffix in _TRUSTED_HOST_SUFFIXES
    )


def validate_request_url(url: str) -> None:
    """Validates that an outbound authenticated URL uses HTTPS on a Google host.

    Prevents SSRF and bearer-token exfiltration when region or resource strings
    are influenced by untrusted caller/model inputs.

    Args:
        url: Full target URL.

    Raises:
        errors.UnsafeEndpointError: If the scheme is not HTTPS, credentials are
            embedded in the URL, or the host is outside Google Cloud APIs.
    """
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https":
        raise errors.UnsafeEndpointError(
            f"Refusing authenticated request to non-HTTPS URL: {url!r}",
            hint="Use an `https://*.googleapis.com/` base URL.",
        )
    if parsed.username is not None or parsed.password is not None:
        raise errors.UnsafeEndpointError(
            f"Refusing authenticated request to URL with userinfo: {url!r}",
            hint="Remove embedded credentials from the endpoint URL.",
        )
    if not is_trusted_google_host(parsed.hostname):
        raise errors.UnsafeEndpointError(
            f"Refusing to attach Google Cloud credentials to untrusted host: {parsed.hostname!r}",
            hint="Target host must end with `.googleapis.com`.",
        )


class ApiError(errors.CxidkError, RuntimeError):
    """Raised when a REST API call returns a non-2xx response.

    `Request.make` raises `ApiError` by default when an HTTP call returns a
    non-2xx status code unless `raise_on_error=False` is explicitly passed.

    Attributes:
        method: The HTTP method used.
        url: The full request URL.
        status_code: The HTTP status code returned.
        body: The raw response body, useful for the API's error detail.
    """

    def __init__(
        self, method: str, url: str, status_code: int, body: str
    ) -> None:
        """Initializes the error.

        Args:
            method: The HTTP method used.
            url: The full request URL.
            status_code: The HTTP status code returned.
            body: The raw response body.
        """
        mapped = errors.from_http(method, url, status_code, body)
        self.method = method
        self.url = url
        self.body = body
        super().__init__(
            f"{method.upper()} {url} failed with HTTP {status_code}: {body}",
            code=mapped.code,
            hint=mapped.hint,
            status_code=status_code,
            details=mapped.details,
        )


_DEFAULT_TIMEOUT = 60
SECONDS_IN_A_DAY = 86400
# Deprecated alias kept for backward compatibility with 1.x callers.
SECONDS_IN_A_YEAR = SECONDS_IN_A_DAY
MILLISECONDS_IN_SECOND = 1000
MICROSECONDS_IN_SECOND = 1000000
ENDPOINT_SUFFIX = "googleapis.com"
INSIGHTS_API_VERSION = "v1"
GLOBAL_LOCATION = "global"


class Auth:
    """Manages authentication and credentials for Google Cloud APIs.

    This class handles the logic for obtaining and refreshing authentication
    credentials, whether they are provided directly, via a file path, a
    dictionary, or through application default credentials.

    Attributes:
        creds: Active Google Cloud credentials instance.
        token: Cached OAuth2 access token string.
        api_calls_dict: A defaultdict to track API call counts.
    """

    creds: Any = None
    token: Optional[str] = None

    def __init__(
        self,
        creds: Optional[auth_credentials.Credentials] = None,
        creds_path: Optional[str] = None,
        creds_dict: Optional[Dict[str, str]] = None,
        scope: Optional[List[str]] = None,
    ):
        """Initializes the Auth object and retrieves credentials.

        This constructor determines the credential source, retrieves them,
        and refreshes the token when needed. It supports service account
        credentials from a file, a dictionary, a provided credentials object,
        or application default credentials.

        Args:
            creds: An optional pre-existing credentials object.
            creds_path: The file path to a service account JSON key file.
            creds_dict: A dictionary containing service account key information.
            scope: A list of additional OAuth 2.0 scopes to request.
        """
        self.scopes: List[str] = list(GLOBAL_SCOPES)
        if scope:
            for item in scope:
                if item not in self.scopes:
                    self.scopes.append(item)

        if creds is not None:
            self.creds: auth_credentials.Credentials = creds
            self.token = self.ensure_valid_token()

        elif creds_path:
            self.creds = service_account.Credentials.from_service_account_file(
                creds_path, scopes=self.scopes
            )
            self.token = self.ensure_valid_token()

        elif creds_dict is not None:
            self.creds = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=self.scopes
            )
            self.token = self.ensure_valid_token()

        else:
            default_creds, _ = default(scopes=self.scopes)
            self.creds = default_creds
            self._check_and_update_scopes(self.creds)
            self.token = self.ensure_valid_token()

        self.api_calls_dict: defaultdict[Any, int] = defaultdict(int)

    def ensure_valid_token(self) -> Optional[str]:
        """Returns a valid bearer token, refreshing credentials if expired.

        Returns:
            The active OAuth2 bearer token string, or None if unavailable.
        """
        is_ready = (
            getattr(self.creds, "valid", False) is True
            and getattr(self.creds, "expired", False) is False
            and isinstance(getattr(self.creds, "token", None), str)
        )
        if not is_ready:
            self.creds.refresh(auth_request())
        self.token = self.creds.token
        return self.token

    def _check_and_update_scopes(self, creds: auth_credentials.Credentials):
        """Updates credential scopes if the credential type supports it.

        For credential types that require explicit scope definition, this method
        appends the configured scopes without mutating global state.

        Args:
            creds: The credentials object to check and potentially update.
        """
        # `requires_scopes`/`scopes` only exist on scoped credentials, so the
        # isinstance check also prevents an AttributeError for credential types
        # that do not implement the Scoped interface.
        if isinstance(creds, auth_credentials.Scoped) and creds.requires_scopes:
            existing = list(creds.scopes or [])
            for required in self.scopes:
                if required not in existing:
                    creds.scopes.append(required)


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
        self.environment = (
            environment if environment is not None else Environments.PRODUCTION
        )
        if self.environment not in SUPPORTED_ENVIRONMENTS:
            raise errors.InvalidArgumentError(
                f"environment {self.environment} is not on the supported list "
                f"of environments: {SUPPORTED_ENVIRONMENTS}"
            )

        self.region: Optional[str] = (
            self.validate_location(region) if region is not None else None
        )

    @staticmethod
    def validate_location(location: str) -> str:
        """Validates a Google Cloud location against `REGION_LIST`.

        Args:
            location: Candidate location string.

        Returns:
            Lowercased, validated location identifier.

        Raises:
            errors.InvalidArgumentError: If `location` is not in `REGION_LIST`.
        """
        if not isinstance(location, str) or not location.strip():
            raise errors.InvalidArgumentError(
                "Location must be a non-empty string.",
                hint=f"Supported locations: {REGION_LIST}",
            )
        normalized = location.strip().lower()
        if normalized not in REGION_LIST:
            raise errors.InvalidArgumentError(
                f"Region {normalized} is not on the supported list of regions: {REGION_LIST}",
                hint=f"Choose one of: {', '.join(REGION_LIST)}",
            )
        return normalized

    def insights_host(self, location: Optional[str] = None) -> str:
        """Resolves the Contact Center Insights hostname for a location.

        This is the single authoritative regional-endpoint resolver. Callers
        that build REST URLs by hand should use it rather than hardcoding a
        host, so that regional resources remain reachable.

        The `global` location is deliberately special-cased: it is served by the
        unprefixed host, not by `global-contactcenterinsights...`, which does
        not resolve.

        Args:
            location: The Google Cloud location (e.g. 'us-central1' or
                'global'). Defaults to the configured region.

        Returns:
            The hostname to use for API requests, without a scheme.

        Raises:
            errors.InvalidArgumentError: If `location` is not a valid region.
        """
        insights_environments = {
            Environments.PRODUCTION: f"contactcenterinsights.{ENDPOINT_SUFFIX}",
            Environments.STAGING: f"staging-contactcenterinsights.sandbox.{ENDPOINT_SUFFIX}",
        }
        base_host = insights_environments[self.environment]

        effective = (
            self.validate_location(location)
            if location is not None
            else self.region
        )
        if (
            effective is None
            or effective == GLOBAL_LOCATION
            or self.environment == Environments.STAGING
        ):
            return base_host
        return f"{effective}-{base_host}"

    def insights_base_url(self, location: Optional[str] = None) -> str:
        """Builds the versioned REST base URL for Contact Center Insights.

        Args:
            location: The Google Cloud location. Defaults to the configured
                region.

        Returns:
            A URL of the form ``https://<host>/v1/``.
        """
        return f"https://{self.insights_host(location)}/{INSIGHTS_API_VERSION}/"

    def set_insights_endpoint(self) -> ClientOptions:
        """Constructs the client options for the Contact Center Insights API.

        Returns:
            A ClientOptions object configured with the appropriate API endpoint
            based on the region and environment.
        """
        return ClientOptions(api_endpoint=self.insights_host())

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

        if self.region is None or self.region == GLOBAL_LOCATION:
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

        if self.region is None or self.region == GLOBAL_LOCATION:
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

        if self.region is None or self.region == GLOBAL_LOCATION:
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

        if self.region is None or self.region == GLOBAL_LOCATION:
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

        if self.region is None or self.region == GLOBAL_LOCATION:
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

    def set_agent_studio_endpoint(self) -> str:
        """Constructs the base URL for the Agent Studio API.

        Returns:
            The base URL string for the API endpoint based on the
            configured environment.
        """
        agent_studio_environments = {
            Environments.PRODUCTION: "https://ces.googleapis.com/",
            Environments.STAGING: "https://staging-ces-googleapis.sandbox.google.com/",
        }

        return str(agent_studio_environments[self.environment])


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

    def make(
        self,
        endpoint: str,
        method: str,
        payload: Optional[Dict[str, Any]],
        timeout: int = _DEFAULT_TIMEOUT,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        raise_on_error: bool = True,
        max_attempts: int = 1,
    ) -> Optional[Dict[str, Any]]:
        """Makes an authenticated HTTP request to an API endpoint.

        Args:
            endpoint: The API endpoint to call.
            method: The HTTP method to use (e.g., 'get', 'post', 'patch').
            payload: A dictionary of parameters to include in the request body
                or as URL parameters for GET requests.
            timeout: The request timeout in seconds.
            headers: Optional dictionary of custom request headers.
            params: Optional query-string parameters. These are sent in
                addition to `payload` for non-GET methods, which is what makes
                `updateMask` and `*Id` create parameters expressible.
            raise_on_error: When True (the default in cxidk 2.0), a non-2xx
                response raises `ApiError` instead of returning an empty
                dictionary.
            max_attempts: Total attempts for transient failures (429/5xx). The
                default of 1 disables retries so existing callers are
                unaffected.

        Returns:
            The JSON response from the API as a dictionary, or an empty
            dictionary/None if the request fails with `raise_on_error=False` or
            returns no content.

        Raises:
            errors.UnsafeEndpointError: If the target URL is not an HTTPS
                Google Cloud API endpoint.
            errors.InvalidArgumentError: If `method` is unsupported when
                `raise_on_error` is True.
            ApiError: If `raise_on_error` is True and the API returns a non-2xx
                response.
        """
        url = self.base_url + endpoint
        validate_request_url(url)

        verb = str(method).lower()
        if verb not in _HTTP_VERBS:
            if raise_on_error:
                raise errors.InvalidArgumentError(
                    f"Unsupported HTTP method: {method!r}",
                    hint=f"Supported methods: {[v.value for v in Methods]}",
                )
            return None

        if payload:
            payload = {k: v for k, v in payload.items() if v is not None}
        req_headers = dict(headers) if headers is not None else {}
        if "Authorization" not in req_headers:
            creds = self.auth.creds
            if (
                getattr(creds, "expired", False) is True
                or getattr(creds, "valid", True) is False
                or getattr(creds, "token", None) is None
            ):
                creds.refresh(auth_request())
                if "token" in getattr(self.auth, "__dict__", {}):
                    self.auth.token = creds.token
            req_headers["Authorization"] = f"Bearer {creds.token}"

        # `params` is only forwarded when supplied, so that calls made by
        # existing code keep exactly the argument list they had before.
        extra: Dict[str, Any] = {"params": params} if params else {}

        def _send() -> requests.Response:
            if verb == Methods.GET:
                merged = {**(payload or {}), **(params or {})} or None
                return requests.get(
                    url, params=merged, headers=req_headers, timeout=timeout
                )
            if verb == Methods.POST:
                return requests.post(
                    url,
                    json=payload,
                    headers=req_headers,
                    timeout=timeout,
                    **extra,
                )
            if verb == Methods.PATCH:
                return requests.patch(
                    url,
                    json=payload,
                    headers=req_headers,
                    timeout=timeout,
                    **extra,
                )
            return requests.delete(
                url, json=payload, headers=req_headers, timeout=timeout, **extra
            )

        response = self._send_with_retry(_send, max_attempts)

        # Membership rather than a range comparison: test doubles frequently
        # leave `status_code` as a mock, where `<=` raises but `in` is safe.
        if response.status_code in _SUCCESS_STATUS_CODES:
            body: Dict[str, Any] = response.json() if response.text else {}
            return body

        if raise_on_error:
            raise ApiError(
                method=verb,
                url=url,
                status_code=response.status_code,
                body=response.text,
            )
        return {}

    @staticmethod
    def _send_with_retry(
        send: Callable[[], requests.Response],
        max_attempts: int,
    ) -> requests.Response:
        """Sends a request, retrying transient rate-limit and server errors.

        Args:
            send: A zero-argument callable performing the request.
            max_attempts: Total attempts, including the first.

        Returns:
            The final `requests.Response`, successful or not.
        """
        response = send()
        for attempt in range(max_attempts - 1):
            if response.status_code not in retry.RETRYABLE_STATUS_CODES:
                return response
            delay = retry.compute_delay(attempt)
            logger.warning(
                "Retryable HTTP %s on attempt %d/%d; sleeping %.2fs",
                response.status_code,
                attempt + 1,
                max_attempts,
                delay,
            )
            time.sleep(delay)
            response = send()
        return response
