"""Model Context Protocol (MCP) server package for cxidk."""

import importlib
from typing import TYPE_CHECKING, Any

from cxidk.ai.policy import Policy

if TYPE_CHECKING:
    from cxidk.ai.mcp.http_app import SecuredMcpHttpApp
    from cxidk.ai.mcp.http_app import build_http_app
    from cxidk.ai.mcp.server import SERVER_INSTRUCTIONS
    from cxidk.ai.mcp.server import build_server

_LAZY_EXPORTS = {
    "SERVER_INSTRUCTIONS": ("cxidk.ai.mcp.server", "SERVER_INSTRUCTIONS"),
    "SecuredMcpHttpApp": ("cxidk.ai.mcp.http_app", "SecuredMcpHttpApp"),
    "build_http_app": ("cxidk.ai.mcp.http_app", "build_http_app"),
    "build_server": ("cxidk.ai.mcp.server", "build_server"),
}

__all__ = [
    "Policy",
    "SERVER_INSTRUCTIONS",
    "SecuredMcpHttpApp",
    "build_http_app",
    "build_server",
]


def __getattr__(attr_name: str) -> Any:
    """Lazily resolves `mcp`-dependent server symbols on first access."""
    target = _LAZY_EXPORTS.get(attr_name)
    if target is not None:
        mod_name, sym_name = target
        return getattr(importlib.import_module(mod_name), sym_name)
    raise AttributeError(f"module {__name__!r} has no attribute {attr_name!r}")
