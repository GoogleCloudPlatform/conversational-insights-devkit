"""Domain workflows for CCAI Insights promotion, formatting, and QAI tuning."""

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cxidk.workflow import audio
    from cxidk.workflow import config_copier
    from cxidk.workflow import content_generator
    from cxidk.workflow import format  # pylint: disable=redefined-builtin
    from cxidk.workflow import insight_refinements
    from cxidk.workflow import ops
    from cxidk.workflow import role_recognizer
    from cxidk.workflow import views_manager

_WORKFLOW_MODULES = frozenset(
    {
        "audio",
        "config_copier",
        "content_generator",
        "format",
        "insight_refinements",
        "ops",
        "role_recognizer",
        "views_manager",
    }
)

__all__ = [
    "audio",
    "config_copier",
    "content_generator",
    "format",
    "insight_refinements",
    "ops",
    "role_recognizer",
    "views_manager",
]


def __getattr__(workflow_name: str) -> Any:
    """Lazily imports `cxidk.workflow` submodules on first attribute access."""
    if workflow_name in _WORKFLOW_MODULES:
        return importlib.import_module(f"cxidk.workflow.{workflow_name}")
    raise AttributeError(
        f"module {__name__!r} has no attribute {workflow_name!r}"
    )
