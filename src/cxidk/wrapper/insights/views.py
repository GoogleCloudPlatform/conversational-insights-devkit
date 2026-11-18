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

"""Authorized views and correlation configuration clients for CCAI Insights."""

from typing import Any
from typing import Dict
from typing import Optional

from cxidk.core import base
from cxidk.wrapper.insights._enums import _RETRY_ATTEMPTS


class AuthorizedViews:
    """Manages authorized views for Contact Center AI Insights.

    This class provides methods to create, list, get, and delete authorized
    view sets and the authorized views within them, using direct REST API calls.

    Attributes:
        parent: The parent resource name (e.g., 'projects/p/locations/l').
        project_id: The Google Cloud project ID.
        location: The Google Cloud location.
    """

    def __init__(
        self,
        parent: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ) -> None:
        """Initializes the AuthorizedViews client.

        Args:
            parent: The parent resource name (e.g., 'projects/p/locations/l').
            auth: An optional, pre-configured authentication object.
            config: An optional, pre-configured configuration object.
        """

        self.auth = auth or base.Auth()
        self.parent = parent
        parts = self.parent.split("/")
        self.project_id = parts[1]
        self.location = parts[3]
        self.config = config or base.Config(region=self.location)
        self._view_sets_endpoint = "authorizedViewSets"

        resolved_base = self.config.insights_base_url(self.location)
        if not isinstance(resolved_base, str):
            resolved_base = "https://contactcenterinsights.googleapis.com/v1/"

        self.request = base.Request(
            project_id=self.project_id,
            location=self.location,
            auth=self.auth,
            config=self.config,
            base_url=f"{resolved_base}{self.parent}/",
        )

    def _make_request(
        self, endpoint: str, method: str, payload: Optional[Dict]
    ) -> Optional[Dict]:
        """Makes a REST API request and returns the JSON response.

        Args:
            endpoint: The API endpoint to target.
            method: The HTTP method to use (e.g., 'GET', 'POST').
            payload: The JSON payload for the request.

        Returns:
            A dictionary representing the JSON response, or None on empty body."""
        # The annotation is load-bearing for static analysis: `Request.make`
        # dispatches through a helper, which defeats pylint's return-type
        # inference and leaves every downstream caller "uninferable".
        response: Optional[Dict[str, Any]] = self.request.make(
            endpoint=endpoint,
            method=method,
            payload=payload,
            raise_on_error=True,
        )
        return response if response else None

    def create_view_set(
        self,
        authorized_view_set_name: str,
    ) -> Optional[Dict]:
        """Creates a new authorized view set.

        Args:
            authorized_view_set_name: The name of the authorized view set.

        Returns:
            A dictionary representing the created authorized view set.
        """
        return self._make_request(
            endpoint=self._view_sets_endpoint,
            method=base.Methods.POST, # type: ignore[arg-type]
            payload={"displayName": authorized_view_set_name},
        )

    def list_view_set(
        self,
        params: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict]:
        """Lists all authorized view sets in the project.

        Args:
            params: A dictionary of parameters to include in the request.

        Returns:
            A dictionary containing a list of authorized view sets.
        """
        return self._make_request(
            endpoint=self._view_sets_endpoint,
            method=base.Methods.GET, # type: ignore[arg-type]
            payload=params,
        )

    def get_view_set(
        self,
        view_set_id: str,
        params: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict]:
        """Retrieves a specific authorized view set by its ID.

        Args:
            view_set_id: The ID of the authorized view set.
            params: A dictionary of parameters to include in the request.

        Returns:
            A dictionary representing the authorized view set.
        """
        endpoint = f"{self._view_sets_endpoint}/{view_set_id}"
        return self._make_request(
            endpoint=endpoint,
            method=base.Methods.GET, # type: ignore[arg-type]
            payload=params
        )

    def delete_view_set(
        self,
        view_set_id: str,
    ) -> Optional[Dict]:
        """Deletes a specific authorized view set.

        Args:
            view_set_id: The ID of the authorized view set to delete.

        Returns:
            An empty dictionary upon successful deletion.
        """
        endpoint = f"{self._view_sets_endpoint}/{view_set_id}"
        return self._make_request(
            endpoint=endpoint,
            method=base.Methods.DELETE, # type: ignore[arg-type]
            payload={},
        )

    def create_view(
        self,
        authorized_view_set_id: str,
        display_name: str,
        conversation_filter: Optional[str] = None,
    ) -> Optional[Dict]:
        """Creates a new authorized view within a specified view set.

        Args:
            authorized_view_set_id: The ID of the authorized view set.
            display_name: The display name of the view.
            conversation_filter: The filter to apply to conversations.

        Returns:
            A dictionary representing the created authorized view.
        """
        endpoint = f"{self._view_sets_endpoint}/{authorized_view_set_id}/authorizedViews"
        payload = {
                "displayName": display_name,
        }
        if conversation_filter:
            payload["conversationFilter"] = conversation_filter

        return self._make_request(
            endpoint=endpoint,
            method=base.Methods.POST, # type: ignore[arg-type]
            payload=payload,
        )

    def list_view(
        self,
        view_set_id: str,
        params: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict]:
        """Lists authorized views within a set.

        Args:
            view_set_id: The ID of the authorized view set.
            params: A dictionary of parameters to include in the request.

        Returns:
            A dictionary containing a list of authorized views.
        """
        endpoint = f"{self._view_sets_endpoint}/{view_set_id}/authorizedViews"
        return self._make_request(
            endpoint=endpoint,
            method=base.Methods.GET, # type: ignore[arg-type]
            payload=params,
        )

    def get_view(
        self,
        view_set_id: str,
        view_id: str,
        params: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict]:
        """Retrieves a specific authorized view by its ID.

        Args:
            view_set_id: The ID of the authorized view set.
            view_id: The ID of the authorized view.
            params: A dictionary of parameters to include in the request.

        Returns:
            A dictionary representing the authorized view.
        """
        endpoint = (
            f"{self._view_sets_endpoint}/{view_set_id}"
            f"/authorizedViews/{view_id}"
        )
        return self._make_request(
            endpoint=endpoint,
            method=base.Methods.GET, # type: ignore[arg-type]
            payload=params,
        )

    def delete_view(
        self,
        view_set_id: str,
        view_id: str,
    ) -> Optional[Dict]:
        """Deletes a specific authorized view.

        Args:
            view_set_id: The ID of the authorized view set.
            view_id: The ID of the authorized view.

        Returns:
            An empty dictionary upon successful deletion.
        """
        endpoint = (
            f"{self._view_sets_endpoint}/{view_set_id}"
            f"/authorizedViews/{view_id}"
        )
        return self._make_request(
            endpoint=endpoint,
            method=base.Methods.DELETE, # type: ignore[arg-type]
            payload={},
        )


class CorrelationConfig:
    """The correlation configuration singleton for a project and location.

    Unlike every other configuration asset this is not a collection: one
    `CorrelationConfig` exists per project and location, with the individual
    correlation rules nested inside it. There is no create or delete, only get
    and update, which is why importing rules means appending to the existing
    list rather than creating new resources.
    """

    def __init__(
        self,
        project_id: str,
        location: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ) -> None:
        """Initializes the correlation config client.

        Args:
            project_id: The Google Cloud project ID.
            location: The Google Cloud location.
            auth: An optional, pre-configured authentication object.
            config: An optional, pre-configured configuration object.
        """
        self.project_id = project_id
        self.location = location
        self.auth = auth or base.Auth()
        self.config = config or base.Config(region=location)
        self.name = (
            f"projects/{project_id}/locations/{location}/correlationConfig"
        )
        self.request = base.Request(
            project_id=project_id,
            location=location,
            auth=self.auth,
            config=self.config,
            base_url=self.config.insights_base_url(location),
        )

    def get(self) -> Dict[str, Any]:
        """Retrieves the correlation configuration.

        Returns:
            The correlation config dictionary, empty when never configured.
        """
        return (
            self.request.make(
                endpoint=self.name,
                method=base.Methods.GET,
                payload=None,
                raise_on_error=True,
                max_attempts=_RETRY_ATTEMPTS,
            )
            or {}
        )

    def update(
        self, body: Dict[str, Any], update_mask: str = "fullConversationConfig"
    ) -> Dict[str, Any]:
        """Updates the correlation configuration.

        Args:
            body: The configuration body to write.
            update_mask: A comma-separated FieldMask limiting the write.

        Returns:
            The updated correlation config dictionary.
        """
        return (
            self.request.make(
                endpoint=self.name,
                method=base.Methods.PATCH,
                payload=body,
                params={"updateMask": update_mask},
                raise_on_error=True,
                max_attempts=_RETRY_ATTEMPTS,
            )
            or {}
        )
