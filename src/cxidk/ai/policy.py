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

"""Server-side policy enforcement for cxidk MCP servers."""

from dataclasses import dataclass
import inspect
import os
from typing import Any, Dict, FrozenSet, Iterable, Literal, Optional, Tuple

from cxidk.core import base
from cxidk.core import context
from cxidk.core import errors
from cxidk.ai.tools import registry
from cxidk.ai.tools import validation

TransportType = Literal["stdio", "http"]
TranscriptPolicyMode = validation.TranscriptMode

LOOPBACK_HOSTS: FrozenSet[str] = frozenset({"127.0.0.1", "::1", "localhost"})
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _env_bool(name: str, default: bool = False) -> bool:
    """Parses a boolean environment variable."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


def parse_csv(raw: Optional[str]) -> Tuple[str, ...]:
    """Splits a comma-separated string into non-empty trimmed items.

    Args:
        raw: Optional comma-separated string value.

    Returns:
        Tuple of stripped non-empty items.
    """
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _resolve_allowed_projects(
    raw_allowed: Optional[str], default_project: Optional[str]
) -> Tuple[str, ...]:
    """Resolves the project allowlist, defaulting to `[default_project]` when set."""
    items = parse_csv(raw_allowed)
    if items == ("*",):
        return ()
    if items:
        return tuple(context.validate_project_id(proj) for proj in items)
    if default_project:
        return (context.validate_project_id(default_project),)
    return ()


@dataclass(frozen=True)
class Policy:
    """Immutable runtime security policy for an MCP or ADK tool surface.

    Attributes:
        transport: Active MCP transport (`'stdio'` or `'http'`).
        default_project_id: Default GCP project ID when omitted in tool calls.
        default_location: Default GCP location when omitted in tool calls.
        allowed_projects: Tuple of permitted GCP project IDs (empty allows all).
        toolsets: Enabled toolset names.
        allow_writes: Whether write tools (`toolset='writes'`) are exposed.
        allow_unattended_writes: Whether interactive confirmation is bypassed.
        transcript_mode: Default transcript privacy mode (`full`, `redacted`, `omit`).
        max_result_chars: Maximum serialized tool output size in characters.
        rate_limit_per_minute: Token-bucket requests per minute per principal.
        require_auth: Whether IAP or OIDC authentication is mandatory.
        iap_audience: Expected IAP JWT audience when IAP is enabled.
        oauth_audience: Expected OIDC Bearer audience when OAuth is enabled.
        allow_ephemeral_plan_key: Whether ephemeral HMAC keys are allowed.
    """

    transport: TransportType = "stdio"
    default_project_id: Optional[str] = None
    default_location: Optional[str] = None
    allowed_projects: Tuple[str, ...] = ()
    toolsets: Tuple[str, ...] = ("core", "transcripts")
    allow_writes: bool = False
    allow_unattended_writes: bool = False
    transcript_mode: TranscriptPolicyMode = "full"
    max_result_chars: int = 60000
    rate_limit_per_minute: int = 60
    require_auth: bool = False
    iap_audience: Optional[str] = None
    oauth_audience: Optional[str] = None
    allow_ephemeral_plan_key: bool = True

    def enforce_project(self, project_id: Optional[str]) -> Optional[str]:
        """Validates `project_id` against format rules and `allowed_projects`.

        Args:
            project_id: Candidate project ID from the tool call, or None.

        Returns:
            Validated effective project ID, or None if neither explicit nor default.

        Raises:
            errors.PolicyViolationError: If `project_id` is outside `allowed_projects`.
        """
        candidate = project_id or self.default_project_id
        if candidate is None:
            return None
        validated = context.validate_project_id(candidate)
        if self.allowed_projects and validated not in self.allowed_projects:
            raise errors.PolicyViolationError(
                f"Project {validated!r} is not in the server's allowed_projects policy.",
                hint=(
                    f"Allowed projects: {list(self.allowed_projects)}. Update "
                    "`CXIDK_ALLOWED_PROJECTS` if cross-project access is intended."
                ),
            )
        return validated

    def enforce_location(self, location: Optional[str]) -> Optional[str]:
        """Validates `location` against supported CCAI Insights regions.

        Args:
            location: Candidate location from the tool call, or None.

        Returns:
            Validated effective location, or None if neither explicit nor default.
        """
        candidate = location or self.default_location
        if candidate is None:
            return None
        return base.Config.validate_location(candidate)

    def enforce_tool_call(
        self,
        spec: registry.ToolSpec,
        call_kwargs: Dict[str, Any],
    ) -> Tuple[str, str]:
        """Enforces write-gating and project/location allowlists on a tool call.

        Args:
            spec: Registered `ToolSpec` being invoked.
            call_kwargs: Mutable dictionary of public tool keyword arguments;
                resolved `project_id` and `location` defaults are populated in place.

        Returns:
            `(effective_project_id, effective_location)` strings for audit logging.

        Raises:
            errors.PolicyViolationError: If writes are disabled or project is disallowed.
        """
        if not self.allow_writes and (
            spec.toolset == "writes" or spec.safety != registry.Safety.READ
        ):
            raise errors.PolicyViolationError(
                f"Write tool {spec.name!r} is disabled by server policy.",
                hint="Start `cxidk-mcp` with `--allow-writes` or `CXIDK_ALLOW_WRITES=true`.",
            )

        if spec.name == "insights_get_operation" and "operation_name" in call_kwargs:
            op_proj, op_loc, _ = validation.validate_operation_name(
                str(call_kwargs["operation_name"])
            )
            self.enforce_project(op_proj)
            self.enforce_location(op_loc)
            return op_proj, op_loc

        params = inspect.signature(spec.fn).parameters
        eff_proj = ""
        eff_loc = ""
        if "project_id" in params:
            resolved_proj = self.enforce_project(call_kwargs.get("project_id"))
            if resolved_proj is not None:
                call_kwargs["project_id"] = resolved_proj
                eff_proj = resolved_proj
        if "location" in params:
            resolved_loc = self.enforce_location(call_kwargs.get("location"))
            if resolved_loc is not None:
                call_kwargs["location"] = resolved_loc
                eff_loc = resolved_loc
        return eff_proj, eff_loc

    def inject_internal_kwargs(
        self,
        spec: registry.ToolSpec,
        call_kwargs: Dict[str, Any],
        *,
        base_cx: Optional[context.CxContext],
        principal_sub: str,
    ) -> None:
        """Populates server-controlled internal keyword arguments accepted by `spec.fn`.

        Args:
            spec: Registered `ToolSpec` being invoked.
            call_kwargs: Mutable tool keyword arguments dictionary.
            base_cx: Optional base `CxContext` providing credentials and defaults.
            principal_sub: Verified caller subject bound to plan tokens and audits.
        """
        params = inspect.signature(spec.fn).parameters
        if "cx" in params:
            call_kwargs["cx"] = base_cx
        if "default_transcript_mode" in params:
            call_kwargs["default_transcript_mode"] = self.transcript_mode
        if "principal" in params:
            call_kwargs["principal"] = principal_sub
        if "allow_ephemeral_key" in params:
            call_kwargs["allow_ephemeral_key"] = self.allow_ephemeral_plan_key

    @classmethod
    def from_env(
        cls,
        *,
        transport: TransportType = "stdio",
        allow_writes: Optional[bool] = None,
        toolsets: Optional[Iterable[str]] = None,
    ) -> "Policy":
        """Builds a `Policy` from environment variables and CLI overrides.

        Args:
            transport: Target MCP transport (`'stdio'` or `'http'`).
            allow_writes: Optional explicit override for `CXIDK_ALLOW_WRITES`.
            toolsets: Optional explicit override for `CXIDK_TOOLSETS`.

        Returns:
            Constructed immutable `Policy` instance.
        """
        default_proj_raw, default_loc_raw = context.resolve_env_defaults()
        default_proj = (
            context.validate_project_id(default_proj_raw)
            if default_proj_raw
            else None
        )
        default_loc = (
            base.Config.validate_location(default_loc_raw)
            if default_loc_raw
            else None
        )

        eff_writes = (
            allow_writes
            if allow_writes is not None
            else _env_bool("CXIDK_ALLOW_WRITES", default=False)
        )
        if toolsets is not None:
            eff_toolsets = tuple(str(t).strip() for t in toolsets if str(t).strip())
        else:
            env_sets = parse_csv(os.environ.get("CXIDK_TOOLSETS"))
            eff_toolsets = env_sets or (
                ("core", "transcripts", "writes")
                if eff_writes
                else ("core", "transcripts")
            )

        default_mode: TranscriptPolicyMode = (
            "redacted" if transport == "http" else "full"
        )
        eff_mode = validation.validate_transcript_mode(
            os.environ.get("CXIDK_TRANSCRIPT_MODE", default_mode),
            "CXIDK_TRANSCRIPT_MODE",
        )

        local_dev_http = _env_bool("CXIDK_LOCAL_DEV_HTTP", default=False)
        require_auth = transport == "http" and not local_dev_http
        allow_ephemeral = transport == "stdio" or local_dev_http

        return cls(
            transport=transport,
            default_project_id=default_proj,
            default_location=default_loc,
            allowed_projects=_resolve_allowed_projects(
                os.environ.get("CXIDK_ALLOWED_PROJECTS"), default_proj
            ),
            toolsets=eff_toolsets,
            allow_writes=eff_writes,
            allow_unattended_writes=_env_bool(
                "CXIDK_ALLOW_UNATTENDED_WRITES", default=False
            ),
            transcript_mode=eff_mode,
            max_result_chars=max(
                1024, int(os.environ.get("CXIDK_MAX_RESULT_CHARS", "60000"))
            ),
            rate_limit_per_minute=max(
                1, int(os.environ.get("CXIDK_RATE_LIMIT_PER_MINUTE", "60"))
            ),
            require_auth=require_auth,
            iap_audience=os.environ.get("CXIDK_IAP_AUDIENCE") or None,
            oauth_audience=os.environ.get("CXIDK_OAUTH_AUDIENCE") or None,
            allow_ephemeral_plan_key=allow_ephemeral,
        )
