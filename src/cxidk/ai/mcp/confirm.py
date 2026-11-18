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

"""Interactive MCP elicitation confirmation gate for mutating tools.

Uses MCP 2.3 `Resolve` + `Elicit` dependency injection so human-in-the-loop
confirmation works identically over stateful `stdio`, in-memory `Client`, and
stateless Cloud Run Streamable HTTP (`requestState` multi-round-trip).
"""

import inspect
from typing import Any, Callable, Dict, List

from mcp.server.mcpserver import Elicit
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel
from pydantic import Field

from cxidk.ai import policy as ai_policy
from cxidk.ai.tools import registry


_HIDDEN_CONFIRM_KEYS = frozenset(
    {"ctx", "confirm_outcome", "plan_token"} | registry.INTERNAL_TOOL_PARAMS
)


class ConfirmAction(BaseModel):
    """Minimal primitive-only schema required by the MCP elicitation spec."""

    approve: bool = Field(
        default=False,
        description="Set true to confirm executing this mutating operation.",
    )


def requires_confirmation(
    spec: registry.ToolSpec,
    kwargs: Dict[str, Any],
    policy: ai_policy.Policy,
) -> bool:
    """Determines whether a specific tool call requires interactive confirmation.

    Args:
        spec: Registered `ToolSpec` being invoked.
        kwargs: Tool invocation keyword arguments.
        policy: Active MCP server `Policy`.

    Returns:
        True when interactive elicitation confirmation is required.
    """
    if not spec.confirm or policy.allow_unattended_writes:
        return False
    return kwargs.get("dry_run") is not True


def format_confirmation_message(
    spec: registry.ToolSpec, kwargs: Dict[str, Any]
) -> str:
    """Formats a concise human-readable confirmation prompt for a write tool.

    Args:
        spec: Registered `ToolSpec` requiring confirmation.
        kwargs: Tool invocation keyword arguments.

    Returns:
        Human-readable confirmation prompt string.
    """
    if spec.summary_fn is not None:
        detail = spec.summary_fn(kwargs)
    else:
        safe_keys = sorted(k for k in kwargs if k not in _HIDDEN_CONFIRM_KEYS)
        pairs = ", ".join(f"{k}={kwargs[k]!r}" for k in safe_keys)
        detail = f"{spec.name}({pairs})"
    return f"Confirm mutating action — {spec.title}: {detail}"


def build_confirmation_resolver(
    spec: registry.ToolSpec,
    public_params: List[inspect.Parameter],
    policy: ai_policy.Policy,
) -> Callable[..., Any]:
    """Builds an MCP `Resolve(...)` callable returning `Elicit(...)` when needed.

    Args:
        spec: Registered `ToolSpec` requiring confirmation.
        public_params: Public tool parameters mirrored onto the resolver signature.
        policy: Active MCP server `Policy`.

    Returns:
        Resolver function compatible with `mcp.server.mcpserver.Resolve`.
    """

    def _resolve_confirm(**kwargs: Any) -> Any:
        if not requires_confirmation(spec, kwargs, policy):
            return ConfirmAction(approve=True)
        prompt = format_confirmation_message(spec, kwargs)
        return Elicit(prompt, ConfirmAction)

    _resolve_confirm.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        parameters=public_params
    )
    _resolve_confirm.__annotations__ = {
        p.name: p.annotation
        for p in public_params
        if p.annotation is not inspect.Parameter.empty
    }
    return _resolve_confirm


def verify_confirmation_outcome(
    outcome: Any,
    spec: registry.ToolSpec,
    kwargs: Dict[str, Any],
    policy: ai_policy.Policy,
) -> None:
    """Verifies the resolved `ConfirmAction` approved execution.

    Args:
        outcome: Resolved `ConfirmAction` returned by MCP elicitation.
        spec: Registered `ToolSpec` being executed.
        kwargs: Tool invocation keyword arguments.
        policy: Active MCP server `Policy`.

    Raises:
        ToolError: If confirmation was declined or canceled.
    """
    if not requires_confirmation(spec, kwargs, policy):
        return
    approved = bool(
        isinstance(outcome, ConfirmAction) and outcome.approve is True
    )
    if not approved:
        raise ToolError(
            f"[CONFIRMATION_DECLINED] Execution of {spec.name!r} was not "
            "approved (`approve=False`). No changes were made."
        )
