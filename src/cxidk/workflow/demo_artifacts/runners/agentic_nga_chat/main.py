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

"""Runner that generates synthetic next-gen virtual-agent conversations."""

import datetime
import json
import logging
import os
import random
import re
import time
from typing import Any, Dict, FrozenSet, Sequence, Set

from cxidk.workflow import content_generator
from cxidk.wrapper import agents
from cxidk.wrapper import storage

_CONFIG_PATH = "insights-pipeline-producer-configs"
_CONFIG_FILES = ["projects.json", "demos.json"]
_PRODUCER_PROJECT = "insights-pipeline-producer"
_MAX_CONVERSATIONS_CAP = 15

_PROJECT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
_BUCKET_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$")
_SAFE_RESOURCE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
_SUPPORTED_LOCATIONS: FrozenSet[str] = frozenset({
    "global",
    "us",
    "us-central1",
    "us-east1",
    "us-west1",
    "northamerica-northeast1",
    "europe-west1",
    "europe-west2",
    "europe-west3",
    "europe-west4",
    "europe-west6",
    "asia-northeast1",
    "asia-northeast3",
    "asia-south1",
    "asia-southeast1",
    "asia-southeast2",
    "australia-southeast1",
})
_SUPPORTED_ENVIRONMENTS: FrozenSet[str] = frozenset({"prod", "stg"})
_SUPPORTED_VA_TYPES: FrozenSet[str] = frozenset({
    "deterministic",
    "generative",
    "next-gen",
    "agent-studio",
    "cxas",
})
_OPTIONAL_PROFILE_VA_TYPES: FrozenSet[str] = frozenset({
    "next-gen",
    "agent-studio",
    "cxas",
})


def _parse_csv_env(var_name: str) -> Set[str]:
    """Parses a comma-separated environment variable dynamically at call time."""
    raw = os.environ.get(var_name, "")
    return {item.strip() for item in raw.split(",") if item.strip()}


def _is_valid_bucket_name(name: str) -> bool:
    """Returns True when `name` is a safe GCS bucket identifier."""
    return (
        bool(name)
        and ".." not in name
        and "/" not in name
        and "\\" not in name
        and bool(_BUCKET_NAME_RE.match(name))
    )


def _validate_virtual_agent(va: Any, project_id: str) -> None:
    """Validates a single `virtual_agents` entry against path injection."""
    if not isinstance(va, dict):
        raise ValueError(f"virtual_agent entry in '{project_id}' must be an object.")
    agent_id = str(va.get("agent", "")).strip()
    if not _SAFE_RESOURCE_ID_RE.match(agent_id):
        raise ValueError(f"Invalid virtual_agent.agent in '{project_id}'.")

    va_type = str(va.get("type", "")).strip()
    if va_type not in _SUPPORTED_VA_TYPES:
        raise ValueError(f"Unsupported virtual_agent.type '{va_type}' in '{project_id}'.")

    conv_profile = str(va.get("conversation_profile", "")).strip()
    if conv_profile:
        if not _SAFE_RESOURCE_ID_RE.match(conv_profile):
            raise ValueError(
                f"Invalid virtual_agent.conversation_profile in '{project_id}'."
            )
    elif va_type not in _OPTIONAL_PROFILE_VA_TYPES:
        raise ValueError(
            f"virtual_agent.conversation_profile required for '{va_type}' in '{project_id}'."
        )

    va_location = str(va.get("location", "")).strip()
    if va_location not in _SUPPORTED_LOCATIONS:
        raise ValueError(
            f"Unsupported virtual_agent.location '{va_location}' in '{project_id}'."
        )

    va_env = str(va.get("environment", "")).strip()
    if va_env not in _SUPPORTED_ENVIRONMENTS:
        raise ValueError(
            f"Unsupported virtual_agent.environment '{va_env}' in '{project_id}'."
        )


def _validate_agentic_profile(project: Dict[str, Any], project_id: str) -> None:
    """Validates `generation_profile` and non-negative agentic cap."""
    gen_profile = project.get("generation_profile")
    if not isinstance(gen_profile, dict):
        raise ValueError(f"Missing generation_profile for project '{project_id}'.")
    max_per_run = gen_profile.get("max_conversations_per_run", {})
    if isinstance(max_per_run, dict) and "agentic" in max_per_run:
        raw_agentic = max_per_run["agentic"]
        if isinstance(raw_agentic, bool):
            raise ValueError("max_conversations_per_run.agentic must be numeric.")
        if raw_agentic is not None and str(raw_agentic).strip() != "":
            if float(raw_agentic) < 0:
                raise ValueError("max_conversations_per_run.agentic must be >= 0.")


def _validate_optional_buckets(
    project: Dict[str, Any], project_id: str, required_buckets: Sequence[str]
) -> None:
    """Validates optional or required GCS buckets when present."""
    buckets = project.get("buckets")
    allowed_buckets = _parse_csv_env("ALLOWED_BUCKETS")
    if required_buckets and not allowed_buckets:
        raise ValueError("ALLOWED_BUCKETS is not configured; refusing to run.")
    if not isinstance(buckets, dict):
        return
    keys_to_check = required_buckets or [
        k for k, v in buckets.items() if str(v).strip()
    ]
    for bucket_key in keys_to_check:
        bucket_name = str(buckets.get(bucket_key, "")).strip()
        if not _is_valid_bucket_name(bucket_name):
            raise ValueError(
                f"Invalid bucket name for '{bucket_key}' in '{project_id}'."
            )
        if allowed_buckets and bucket_name not in allowed_buckets:
            raise ValueError(f"Bucket '{bucket_name}' is not in ALLOWED_BUCKETS.")


def _validate_project(
    project: Dict[str, Any],
    required_buckets: Sequence[str] = (),
) -> None:
    """Validates `project` against fail-closed resource allowlists."""
    if not isinstance(project, dict):
        raise ValueError("Project configuration entry must be a JSON object.")

    allowed_projects = _parse_csv_env("ALLOWED_PROJECT_IDS")
    if not allowed_projects:
        raise ValueError("ALLOWED_PROJECT_IDS is not configured; refusing to run.")

    project_id = str(project.get("project_id", "")).strip()
    if not _PROJECT_ID_RE.match(project_id) or project_id not in allowed_projects:
        raise ValueError(
            f"Project '{project_id}' is invalid or not in ALLOWED_PROJECT_IDS."
        )

    loc = str(project.get("location", "")).strip()
    if loc and loc not in _SUPPORTED_LOCATIONS:
        raise ValueError(
            f"Unsupported location '{loc}' for project '{project_id}'."
        )

    if "environments" in project:
        environments = project["environments"]
        if not isinstance(environments, list) or any(
            env not in _SUPPORTED_ENVIRONMENTS for env in environments
        ):
            raise ValueError(
                f"Invalid environments {environments!r} for project '{project_id}'."
            )

    _validate_agentic_profile(project, project_id)
    _validate_optional_buckets(project, project_id, required_buckets)

    virtual_agents = project.get("virtual_agents", [])
    if not isinstance(virtual_agents, list):
        raise ValueError(f"virtual_agents must be a list in '{project_id}'.")
    for va in virtual_agents:
        _validate_virtual_agent(va, project_id)


def import_config():
    """Imports pipeline configuration files from GCS."""
    gcs = storage.Gcs(project_id=_PRODUCER_PROJECT, bucket_name=_CONFIG_PATH)
    configs = []
    for config_file in _CONFIG_FILES:
        configs.append(gcs.download_blob(config_file))
    return configs


def file_name_generator():
    """Generates a timestamp-based file name (`YYMMDDHHMMSSffffff`)."""
    return datetime.datetime.now().strftime("%y%m%d%H%M%S%f")


def _is_project_fully_configured(project):
    """Checks if a project has a theme and max conversations configured."""
    if (
        not project["generation_profile"]["theme"]
        or not project["generation_profile"]["max_conversations_per_run"]["agentic"]
    ):
        logging.error("Project (%s) not fully configured", project["project_id"])
        return False
    return True


def _handle_conversation_turn(generator, parameters, context):
    """Handles a single turn in a conversation."""
    conversation_history = "\n".join(
        [f"{turn['role']}: {turn['message']}" for turn in context]
    )
    generated_input = json.loads(
        generator.create_turn(
            parameters=parameters,
            conversation_history=conversation_history,
        )
    )
    generated_input["role"] = "customer"
    context.append(generated_input)
    time.sleep(random.uniform(5, 40))
    return generated_input


def _run_conversation(project_id, virtual_agent, generator, parameters):
    """Runs a single conversation with a PolySynth agent."""
    context = [
        {
            "role": "system",
            "message": (
                f"Remember that this agent can only help you with {virtual_agent['topics']}"
            ),
        },
        {
            "role": "system",
            "message": (
                "Always start the conversations with greetings and stating "
                "what do you need help with"
            ),
        },
    ]

    polysynth = agents.PolySynth(
        project_id=project_id,
        location=virtual_agent["location"],
        env=virtual_agent["environment"],
    )
    session = polysynth.create_session(agent_id=virtual_agent["agent"])

    while True:
        generated_input = _handle_conversation_turn(generator, parameters, context)

        if generated_input["message"].lower() == "quit":
            break

        try:
            response = polysynth.send_message(
                session_id=session, text=generated_input["message"].lower()
            )
            if not response:
                break
            context.append({"message": response, "role": "AGENT"})
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.info(e)
            break
    return 1


def _process_virtual_agent(project, virtual_agent, generator):
    """Processes a virtual agent to generate conversations."""
    _validate_project(project)
    conversations_generated = 0
    if virtual_agent["type"] != "next-gen":
        return conversations_generated

    project_id = project["project_id"]
    logging.info(
        "------> Configuration found for %s project and %s virtual agent found",
        project_id,
        virtual_agent["agent"],
    )

    parameters = generator.create_parameters(
        generation_profile=project["generation_profile"]
    )
    max_agentic = min(
        max(
            1,
            int(
                float(
                    project["generation_profile"]["max_conversations_per_run"]["agentic"]
                )
            ),
        ),
        _MAX_CONVERSATIONS_CAP,
    )
    ranger = random.randint(0, max_agentic)

    logging.info(
        "------> Generating %s conversations for agent %s with the %s type on %s",
        ranger,
        virtual_agent["agent"],
        virtual_agent["type"],
        project_id,
    )

    for index in range(ranger):
        logging.info(
            "------> Generating conversation %s of %s for agent %s %s %s",
            index + 1,
            ranger,
            project_id,
            project.get("environments", []),
            virtual_agent["agent"],
        )
        conversations_generated += _run_conversation(
            project_id, virtual_agent, generator, parameters
        )
    return conversations_generated


def _process_project(project, generator=None):
    """Processes a single project's configuration to generate conversations."""
    _validate_project(project)
    if not _is_project_fully_configured(project):
        return 0

    if not project.get("virtual_agents"):
        logging.info(
            "No virtual agents found in the project %s configuration.",
            project["project_id"],
        )
        return 0

    if generator is None:
        generator = content_generator.Generator(
            project_id=_PRODUCER_PROJECT,
            location="us-central1",
        )

    conversations_generated = 0
    for virtual_agent in project["virtual_agents"]:
        conversations_generated += _process_virtual_agent(
            project, virtual_agent, generator
        )
    return conversations_generated


def runner(args):  # pylint: disable=unused-argument
    """Cloud Function entry point for synthetic next-gen agent conversations."""
    conversations_generated = 0
    configs = import_config()
    for config_str in configs:
        config = json.loads(config_str)
        for project in config.get("projects", []):
            try:
                _validate_project(project)
            except ValueError as exc:
                logging.error("Skipping invalid project entry: %s", exc)
                continue
            conversations_generated += _process_project(project)

    return f"{conversations_generated} conversations generated"
