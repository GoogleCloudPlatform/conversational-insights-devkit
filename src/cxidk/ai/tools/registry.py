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

"""Transport-agnostic tool registry shared by Python callers, MCP servers, and ADK agents."""

from dataclasses import dataclass
from enum import StrEnum
import inspect
import re
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Optional, Type

from pydantic import BaseModel

TOOL_NAME_PATTERN = re.compile(
    r"^(insights|transcript|config|speech|dlp)_[a-z][a-z0-9_]*$"
)

INTERNAL_TOOL_PARAMS: FrozenSet[str] = frozenset(
    {
        "cx",
        "default_transcript_mode",
        "principal",
        "signing_key",
        "allow_ephemeral_key",
    }
)


class Safety(StrEnum):
    """Safety classification for registered tools."""

    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


@dataclass(frozen=True)
class ToolSpec:
    """Transport-agnostic metadata and callable for an AI-invokable tool.

    Attributes:
        name: Globally unique snake_case tool name (`<domain>_<verb>_<noun>`).
        title: Concise human-readable title for UI/confirmation dialogs.
        description: Detailed model-facing guidance including when to use the tool.
        safety: Read, write, or destructive classification.
        idempotent: Whether repeated calls with identical args have identical effect.
        open_world: Whether the tool interacts with external network services.
        toolset: Logical group (`core`, `transcripts`, `writes`).
        confirm: Whether human confirmation is required before execution.
        fn: Underlying synchronous implementation accepting `cx: CxContext` or
            pure arguments.
        output_model: Optional Pydantic model describing structured output.
        summary_fn: Optional formatter producing a confirmation prompt from kwargs.
    """

    name: str
    title: str
    description: str
    safety: Safety
    idempotent: bool
    open_world: bool
    toolset: str
    confirm: bool
    fn: Callable[..., Any]
    output_model: Optional[Type[BaseModel]] = None
    summary_fn: Optional[Callable[[Dict[str, Any]], str]] = None


REGISTRY: Dict[str, ToolSpec] = {}


def public_parameters(spec: ToolSpec) -> List[inspect.Parameter]:
    """Returns external caller-visible `inspect.Parameter` items for `spec`.

    Strips server-controlled dependency-injected arguments (`INTERNAL_TOOL_PARAMS`)
    so MCP and ADK schemas expose identical public signatures.

    Args:
        spec: Registered `ToolSpec` to inspect.

    Returns:
        Ordered list of public `inspect.Parameter` definitions.
    """
    sig = inspect.signature(spec.fn)
    return [
        param
        for name, param in sig.parameters.items()
        if name not in INTERNAL_TOOL_PARAMS
    ]


def cx_tool(
    *,
    name: str,
    title: str,
    description: str,
    safety: Safety = Safety.READ,
    idempotent: bool = True,
    open_world: bool = True,
    toolset: str = "core",
    confirm: bool = False,
    output_model: Optional[Type[BaseModel]] = None,
    summary_fn: Optional[Callable[[Dict[str, Any]], str]] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Registers a function in the global `REGISTRY` with structured metadata.

    Args:
        name: Snake-case tool identifier matching `TOOL_NAME_PATTERN`.
        title: Human-readable title for UI and confirmation dialogs.
        description: Model-facing guidance describing behavior and preconditions.
        safety: `Safety` classification (`READ`, `WRITE`, or `DESTRUCTIVE`).
        idempotent: Whether repeated calls with identical inputs have no extra effect.
        open_world: Whether the tool communicates with external network services.
        toolset: Logical group (`core`, `transcripts`, or `writes`).
        confirm: Whether human-in-the-loop confirmation is required.
        output_model: Optional Pydantic `BaseModel` schema for structured output.
        summary_fn: Optional callable formatting confirmation prompt text.

    Returns:
        A decorator that registers the target callable in `REGISTRY`.

    Raises:
        ValueError: If `name` does not match `TOOL_NAME_PATTERN`.
    """
    if not TOOL_NAME_PATTERN.match(name):
        raise ValueError(
            f"Tool name {name!r} must match {TOOL_NAME_PATTERN.pattern}"
        )

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        """Stores `ToolSpec` in `REGISTRY` and returns `fn` unchanged.

        Args:
            fn: Target tool callable to register.

        Returns:
            Unmodified `fn` callable.
        """
        spec = ToolSpec(
            name=name,
            title=title,
            description=description.strip(),
            safety=safety,
            idempotent=idempotent,
            open_world=open_world,
            toolset=toolset,
            confirm=confirm,
            fn=fn,
            output_model=output_model,
            summary_fn=summary_fn,
        )
        REGISTRY[name] = spec
        return fn

    return decorator


def list_specs(
    *,
    toolsets: Optional[Iterable[str]] = None,
    allow_writes: bool = False,
) -> List[ToolSpec]:
    """Returns registered `ToolSpec` items in deterministic alphabetical order.

    Args:
        toolsets: Allowed toolset names (defaults to `("core", "transcripts")`).
        allow_writes: When False, excludes any tool in `"writes"` or with
            `safety != Safety.READ`.

    Returns:
        Sorted list of enabled `ToolSpec` definitions.
    """
    enabled_sets = (
        set(toolsets)
        if toolsets is not None
        else {"core", "transcripts", *({"writes"} if allow_writes else set())}
    )
    specs: List[ToolSpec] = []
    for spec in REGISTRY.values():
        if spec.toolset not in enabled_sets:
            continue
        if not allow_writes and (
            spec.toolset == "writes" or spec.safety != Safety.READ
        ):
            continue
        specs.append(spec)
    return sorted(specs, key=lambda item: item.name)
