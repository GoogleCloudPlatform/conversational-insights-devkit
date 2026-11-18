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

"""Google Agent Development Kit (ADK) toolset adapters for `cxidk.ai.tools`."""

import inspect
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence
from urllib.parse import urlparse

from google.adk.tools import FunctionTool
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)
from pydantic import BaseModel

from cxidk.ai import tools as cx_tools
from cxidk.core import context
from cxidk.core import errors
from cxidk.ai import policy as ai_policy
from cxidk.ai.tools import registry
from cxidk.ai.tools import validation


def _build_adk_callable(
    spec: registry.ToolSpec,
    policy: ai_policy.Policy,
    base_cx: Optional[context.CxContext],
    principal: str,
) -> Callable[..., Dict[str, Any]]:
    """Wraps a `ToolSpec` into a typed synchronous function for ADK `FunctionTool`."""
    public_params = registry.public_parameters(spec)
    adk_sig = inspect.Signature(
        parameters=public_params,
        return_annotation=Dict[str, Any],
    )

    def _adk_fn(**kwargs: Any) -> Dict[str, Any]:
        call_kwargs = dict(kwargs)
        policy.enforce_tool_call(spec, call_kwargs)
        policy.inject_internal_kwargs(
            spec,
            call_kwargs,
            base_cx=base_cx,
            principal_sub=principal,
        )

        result = spec.fn(**call_kwargs)
        if isinstance(result, BaseModel):
            dumped: Dict[str, Any] = result.model_dump(mode="json")
            return dumped
        if isinstance(result, dict):
            return result
        return {"result": result}

    annotations: Dict[str, Any] = {
        param.name: param.annotation
        for param in public_params
        if param.annotation is not inspect.Parameter.empty
    }
    annotations["return"] = Dict[str, Any]
    _adk_fn.__name__ = spec.name
    _adk_fn.__doc__ = spec.description
    _adk_fn.__signature__ = adk_sig  # type: ignore[attr-defined]
    _adk_fn.__annotations__ = annotations
    return _adk_fn


def insights_tools(
    cx: Optional[context.CxContext] = None,
    *,
    toolsets: Iterable[str] = ("core", "transcripts"),
    allow_writes: bool = False,
    allowed_projects: Optional[Sequence[str]] = None,
    transcript_mode: validation.TranscriptMode = "redacted",
    principal: str = "adk-agent",
) -> List[FunctionTool]:
    """Builds in-process ADK `FunctionTool` instances from `cxidk.ai.tools`.

    Mutating tools where `spec.confirm` is True automatically set
    `require_confirmation=True` for ADK human-in-the-loop `ToolConfirmation`.

    Args:
        cx: Optional base `CxContext` providing default project, location, and auth.
        toolsets: Enabled toolset names (`'core'`, `'transcripts'`, `'writes'`).
        allow_writes: Whether mutating write tools may be exposed.
        allowed_projects: Optional explicit allowlist of GCP project IDs.
        transcript_mode: Default transcript redaction mode (`'full'`, `'redacted'`,
            or `'omit'`).
        principal: Audit/plan-token subject identifier bound to tool calls.

    Returns:
        List of ADK `FunctionTool` instances matching the enabled toolsets.

    Raises:
        InvalidArgumentError: If any entry in `allowed_projects` is invalid.
    """
    _ = cx_tools.REGISTRY
    default_proj = cx.project_id if cx is not None else None
    default_loc = cx.location if cx is not None else None
    if allowed_projects is not None:
        validated_allowed = tuple(
            context.validate_project_id(proj) for proj in allowed_projects
        )
    elif default_proj:
        validated_allowed = (default_proj,)
    else:
        validated_allowed = ()

    eff_sets = tuple(toolsets)
    policy = ai_policy.Policy(
        transport="stdio",
        default_project_id=default_proj,
        default_location=default_loc,
        allowed_projects=validated_allowed,
        toolsets=eff_sets,
        allow_writes=allow_writes,
        transcript_mode=transcript_mode,
        allow_ephemeral_plan_key=True,
    )

    specs = registry.list_specs(toolsets=eff_sets, allow_writes=allow_writes)
    return [
        FunctionTool(
            _build_adk_callable(spec, policy, cx, principal),
            require_confirmation=spec.confirm,
        )
        for spec in specs
    ]


def remote_insights_mcp_toolset(
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    header_provider: Optional[Callable[..., Any]] = None,
    tool_filter: Optional[List[str]] = None,
    require_confirmation: bool = False,
) -> McpToolset:
    """Connects an ADK agent to a remote Cloud Run `cxidk-mcp` HTTP endpoint.

    Args:
        url: Remote `https://.../mcp` endpoint (or loopback `http://127.0.0.1` for dev).
        headers: Optional static HTTP headers (such as `Authorization`).
        header_provider: Optional dynamic per-request header callback for OIDC tokens.
        tool_filter: Optional allowlist of MCP tool names to expose.
        require_confirmation: Whether ADK should require confirmation on all tools.

    Returns:
        Configured ADK `McpToolset` over `StreamableHTTPConnectionParams`.

    Raises:
        UnsafeEndpointError: If `url` is neither HTTPS nor loopback HTTP.
    """
    parsed = urlparse(url)
    is_https = parsed.scheme == "https" and bool(parsed.hostname)
    is_loopback_http = (
        parsed.scheme == "http"
        and parsed.hostname in ai_policy.LOOPBACK_HOSTS
    )
    if not (is_https or is_loopback_http):
        raise errors.UnsafeEndpointError(
            f"Remote MCP URL must use HTTPS (or loopback HTTP for dev): {url!r}",
            hint="Use `https://<service>.run.app/mcp` for Cloud Run deployments.",
        )

    conn_params = StreamableHTTPConnectionParams(
        url=url,
        headers=dict(headers or {}),
    )
    return McpToolset(
        connection_params=conn_params,
        tool_filter=tool_filter,
        require_confirmation=require_confirmation,
        header_provider=header_provider,
    )
