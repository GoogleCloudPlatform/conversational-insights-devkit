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

"""Dependency-injectable runtime context for cxidk wrappers, tools, and MCP/ADK adapters."""

import os
import re
from typing import Optional, Tuple

from google.auth import credentials as auth_credentials

from cxidk.core import base
from cxidk.core import errors

_PROJECT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")


def validate_project_id(project_id: str) -> str:
    """Validates a Google Cloud project ID format.

    Args:
        project_id: Candidate GCP project ID.

    Returns:
        Trimmed, validated project ID.

    Raises:
        errors.InvalidArgumentError: If `project_id` is malformed.
    """
    if not isinstance(project_id, str) or not project_id.strip():
        raise errors.InvalidArgumentError(
            "project_id must be a non-empty string.",
            hint="Set `CXIDK_PROJECT_ID` or pass an explicit GCP project ID.",
        )
    cleaned = project_id.strip()
    if not _PROJECT_ID_RE.match(cleaned):
        raise errors.InvalidArgumentError(
            f"Invalid GCP project_id format: {cleaned!r}",
            hint=(
                "GCP project IDs must be 6-30 lowercase letters, digits, or "
                "hyphens, starting with a letter."
            ),
        )
    return cleaned


class CxContext:
    """Immutable-by-convention execution context for Google Cloud operations.

    Holds validated `project_id` and `location` alongside `Auth` and `Config`
    instances so callers, MCP servers, and ADK agents share credentials and
    regional endpoint routing consistently.

    Attributes:
        project_id: Validated Google Cloud project ID.
        location: Validated Google Cloud region or `global`.
        auth: `base.Auth` instance holding active credentials.
        config: `base.Config` instance managing regional endpoints.
    """

    def __init__(
        self,
        project_id: str,
        location: str,
        *,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
        credentials: Optional[auth_credentials.Credentials] = None,
        environment: Optional[base.Environments] = None,
    ) -> None:
        """Initializes a validated `CxContext`.

        Args:
            project_id: Google Cloud project ID.
            location: Google Cloud location (validated against `REGION_LIST`).
            auth: Optional pre-built `base.Auth`.
            config: Optional pre-built `base.Config`.
            credentials: Optional raw `google.auth.credentials.Credentials` used
                when `auth` is not provided.
            environment: Optional deployment environment (`prod` or `stg`).
        """
        self.project_id = validate_project_id(project_id)
        self.location = base.Config.validate_location(location)
        self.auth = auth if auth is not None else base.Auth(creds=credentials)
        self.config = (
            config
            if config is not None
            else base.Config(region=self.location, environment=environment)
        )

    @property
    def parent(self) -> str:
        """Returns the regional parent resource name.

        Returns:
            Resource path `projects/{project_id}/locations/{location}`.
        """
        return f"projects/{self.project_id}/locations/{self.location}"

    def for_target(
        self,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
    ) -> "CxContext":
        """Returns a context overriding `project_id` and/or `location` while reusing `auth`.

        Args:
            project_id: Optional override project ID.
            location: Optional override location.

        Returns:
            `self` when unchanged, or a derived `CxContext` sharing `self.auth`.
        """
        eff_project = (
            validate_project_id(project_id)
            if project_id is not None
            else self.project_id
        )
        eff_location = (
            base.Config.validate_location(location)
            if location is not None
            else self.location
        )
        if eff_project == self.project_id and eff_location == self.location:
            return self
        return CxContext(
            project_id=eff_project,
            location=eff_location,
            auth=self.auth,
            config=base.Config(
                region=eff_location,
                environment=self.config.environment,
            ),
        )

    @classmethod
    def from_env(
        cls,
        *,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
        auth: Optional[base.Auth] = None,
    ) -> "CxContext":
        """Constructs a `CxContext` from explicit args or environment variables.

        Reads `CXIDK_PROJECT_ID` (falling back to `GOOGLE_CLOUD_PROJECT`) and
        `CXIDK_LOCATION`. Fails fast with an actionable `InvalidArgumentError`
        rather than silently guessing a region.

        Args:
            project_id: Optional explicit project ID override.
            location: Optional explicit location override.
            auth: Optional pre-built `base.Auth`.

        Returns:
            Initialized `CxContext`.

        Raises:
            errors.InvalidArgumentError: If project or location is unset or invalid.
        """
        env_project, env_location = resolve_env_defaults()
        resolved_project = project_id or env_project
        if not resolved_project:
            raise errors.InvalidArgumentError(
                "No GCP project_id configured.",
                hint="Set `CXIDK_PROJECT_ID` (or `GOOGLE_CLOUD_PROJECT`) or pass `project_id`.",
            )

        resolved_location = location or env_location
        if not resolved_location:
            raise errors.InvalidArgumentError(
                "No CCAI Insights location configured.",
                hint=(
                    "Set `CXIDK_LOCATION` (for example `us-central1`, `europe-west1`, "
                    "or `global`) or pass `location` explicitly."
                ),
            )

        return cls(
            project_id=resolved_project,
            location=resolved_location,
            auth=auth,
        )

    @classmethod
    def resolve(
        cls,
        cx: Optional["CxContext"],
        project_id: Optional[str] = None,
        location: Optional[str] = None,
    ) -> "CxContext":
        """Resolves a target `CxContext` from an injected instance or environment.

        Args:
            cx: Optional pre-configured `CxContext` whose credentials are reused.
            project_id: Optional target GCP project ID override.
            location: Optional target GCP location override.

        Returns:
            Validated `CxContext` scoped to the effective project and location.
        """
        if cx is not None:
            return cx.for_target(project_id=project_id, location=location)
        return cls.from_env(project_id=project_id, location=location)


def resolve_env_defaults() -> Tuple[Optional[str], Optional[str]]:
    """Reads optional default project ID and location from environment variables.

    Returns:
        A `(project_id, location)` tuple where unset values are `None`.
    """
    raw_project = (
        os.environ.get("CXIDK_PROJECT_ID")
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or None
    )
    raw_location = os.environ.get("CXIDK_LOCATION") or None
    return raw_project, raw_location
