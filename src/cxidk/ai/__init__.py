"""AI & agentic integration layer (`tools`, `mcp`, `adk`, `skills`, `policy`)."""

import importlib
from typing import TYPE_CHECKING, Any

from cxidk.ai import policy
from cxidk.ai import skills
from cxidk.ai import tools
from cxidk.ai.policy import Policy

if TYPE_CHECKING:
    from cxidk.ai import adk
    from cxidk.ai import mcp

__all__ = [
    "Policy",
    "adk",
    "mcp",
    "policy",
    "skills",
    "tools",
]


def __getattr__(name: str) -> Any:
    """Lazily loads optional `mcp` and `adk` subpackages on attribute access."""
    if name in ("adk", "mcp"):
        return importlib.import_module(f"cxidk.ai.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
