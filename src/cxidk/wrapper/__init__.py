"""Google Cloud service client wrappers for CCAI Insights and adjacent APIs."""

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cxidk.wrapper import agents
    from cxidk.wrapper import iam
    from cxidk.wrapper import insights
    from cxidk.wrapper import sensitive_data_protection
    from cxidk.wrapper import sheets
    from cxidk.wrapper import speech
    from cxidk.wrapper import storage
    from cxidk.wrapper import vertex

_WRAPPER_MODULES = frozenset(
    {
        "agents",
        "iam",
        "insights",
        "sensitive_data_protection",
        "sheets",
        "speech",
        "storage",
        "vertex",
    }
)

__all__ = [
    "agents",
    "iam",
    "insights",
    "sensitive_data_protection",
    "sheets",
    "speech",
    "storage",
    "vertex",
]


def __getattr__(module_name: str) -> Any:
    """Lazily imports `cxidk.wrapper` submodules on first attribute access."""
    if module_name in _WRAPPER_MODULES:
        return importlib.import_module(f"cxidk.wrapper.{module_name}")
    raise AttributeError(f"module {__name__!r} has no attribute {module_name!r}")
