"""Conversational Insights DevKit (`cxidk`) — AI-native toolkit for CCAI Insights.

Public package architecture for Python developers and AI coding agents:
- `cxidk.CxContext`: Explicit regional execution context (`project_id`, `location`, `auth`).
- `cxidk.wrapper`: Service clients (`insights`, `speech`, `sensitive_data_protection`,
  `storage`, `vertex`, `agents`, `iam`, `sheets`).
- `cxidk.workflow`: Domain pipelines (`ops.ConfigOps` config promotion, `format.Insights`
  AWS/Genesys transcript conversion, `role_recognizer.RoleRecognizer`, `views_manager`,
  `insight_refinements`).
- `cxidk.ai`: Agentic surfaces (`tools` `@cx_tool` registry, `mcp` `cxidk-mcp` server,
  `adk` Google ADK `FunctionTool` & agents, `skills` portable `SKILL.md` playbooks).
- `cxidk.get_llms_txt()`: Returns the bundled `llms.txt` machine-readable API & tool index.
"""

import importlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cxidk.core import errors
from cxidk.core.context import CxContext

if TYPE_CHECKING:
    from cxidk import ai
    from cxidk import core
    from cxidk import workflow
    from cxidk import wrapper

__version__ = "2.0.0"

_SUBPACKAGES = frozenset({"ai", "core", "workflow", "wrapper"})

__all__ = [
    "CxContext",
    "__version__",
    "ai",
    "core",
    "errors",
    "get_llms_txt",
    "workflow",
    "wrapper",
]


def get_llms_txt() -> str:
    """Returns the bundled `llms.txt` Markdown index for AI/LLM discovery.

    Returns:
        UTF-8 Markdown string indexing public SDK modules, MCP/ADK tools,
        resources, prompts, and bundled Agent Skills.

    Raises:
        NotFoundError: If `llms.txt` cannot be found in package data or repo root.
    """
    pkg_dir = Path(__file__).resolve().parent
    bundled = pkg_dir / "llms.txt"
    if bundled.is_file():
        return bundled.read_text(encoding="utf-8")
    repo_fallback = pkg_dir.parents[1] / "llms.txt"
    if repo_fallback.is_file():
        return repo_fallback.read_text(encoding="utf-8")
    raise errors.NotFoundError(
        "Bundled llms.txt not found.",
        hint="Run `python .github/scripts/gen_llms_txt.py` or reinstall `cxidk`.",
    )


def __getattr__(subpackage_name: str) -> Any:
    """Lazily imports top-level `cxidk` subpackages on first attribute access."""
    if subpackage_name in _SUBPACKAGES:
        return importlib.import_module(f"cxidk.{subpackage_name}")
    raise AttributeError(
        f"module {__name__!r} has no attribute {subpackage_name!r}"
    )
