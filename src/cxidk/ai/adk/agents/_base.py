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

"""Shared builder and declarative preset for reference ADK `LlmAgent` personas."""

from dataclasses import dataclass
import os
from typing import Any, List, Optional, Sequence, Tuple

from google.adk.agents import LlmAgent

from cxidk.ai import skills
from cxidk.ai.adk import toolset
from cxidk.core import context
from cxidk.ai.tools import validation


@dataclass(frozen=True)
class AgentPreset:
    """Declarative configuration for a bundled `cxidk` reference ADK agent.

    Attributes:
        name: ADK agent identifier.
        default_model: Default Gemini model when `CXIDK_GEMINI_MODEL` is unset.
        skill_name: Bundled `SKILL.md` directory name under `cxidk.ai.skills`.
        description: Concise agent summary used for multi-agent routing.
        role_preamble: Persona and safety instructions prepended to `SKILL.md`.
        toolsets: Enabled `cxidk.ai.tools` toolset names.
        allow_writes: Whether write tools (`toolset='writes'`) may be exposed.
        transcript_mode: Default transcript privacy mode (`full`, `redacted`, `omit`).
        principal: Audit and plan-token subject identifier for this agent.
    """

    name: str
    default_model: str
    skill_name: str
    description: str
    role_preamble: str
    toolsets: Tuple[str, ...]
    allow_writes: bool
    transcript_mode: validation.TranscriptMode
    principal: str


def build_skill_agent(
    preset: AgentPreset,
    *,
    cx: Optional[context.CxContext] = None,
    model: Optional[str] = None,
    allowed_projects: Optional[Sequence[str]] = None,
) -> LlmAgent:
    """Instantiates an ADK `LlmAgent` from a declarative `AgentPreset`.

    Args:
        preset: Declarative `AgentPreset` specifying skill, tools, and policy.
        cx: Optional base `CxContext` providing default project, location, and auth.
        model: Optional Gemini model name override.
        allowed_projects: Optional allowlist of GCP project IDs.

    Returns:
        Configured ADK `LlmAgent` instance.
    """
    resolved_model = (
        model or os.environ.get("CXIDK_GEMINI_MODEL") or preset.default_model
    )
    skill_text = skills.load_skill(preset.skill_name)
    instruction = f"{preset.role_preamble.strip()}\n\n{skill_text}"
    adk_tools: List[Any] = list(
        toolset.insights_tools(
            cx=cx,
            toolsets=preset.toolsets,
            allow_writes=preset.allow_writes,
            allowed_projects=allowed_projects,
            transcript_mode=preset.transcript_mode,
            principal=preset.principal,
        )
    )
    return LlmAgent(
        name=preset.name,
        model=resolved_model,
        description=preset.description,
        instruction=instruction,
        tools=adk_tools,
    )
