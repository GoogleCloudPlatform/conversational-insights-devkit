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

"""Runner that generates synthetic human-to-human voice conversations."""

import datetime
import json
import logging
import os
import random
import re
from typing import Any, Dict, FrozenSet, Optional, Sequence, Set

from cxidk.core import base
from cxidk.workflow import audio
from cxidk.workflow import content_generator
from cxidk.wrapper import insights
from cxidk.wrapper import storage

_CONFIG_PATH = "insights-pipeline-producer-configs"
_CONFIG_FILES = ["projects.json", "demos.json"]
_PRODUCER_PROJECT = "insights-pipeline-producer"

_FILE_EXTENSION = ".json"
_AUDIO_EXTENSION = ".wav"
_MAX_CONVERSATIONS_CAP = 15

_PROJECT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
_BUCKET_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$")
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


def _validate_audio_profile(project: Dict[str, Any], project_id: str) -> None:
    """Validates `generation_profile` and non-negative audio cap."""
    gen_profile = project.get("generation_profile")
    if not isinstance(gen_profile, dict):
        raise ValueError(f"Missing generation_profile for project '{project_id}'.")
    max_per_run = gen_profile.get("max_conversations_per_run", {})
    if isinstance(max_per_run, dict) and "audio" in max_per_run:
        raw_audio = max_per_run["audio"]
        if isinstance(raw_audio, bool):
            raise ValueError("max_conversations_per_run.audio must be numeric.")
        if raw_audio is not None and str(raw_audio).strip() != "":
            if float(raw_audio) < 0:
                raise ValueError("max_conversations_per_run.audio must be >= 0.")


def _validate_project_buckets(
    project: Dict[str, Any],
    project_id: str,
    required_buckets: Sequence[str],
    gcs: Optional[storage.Gcs],
) -> None:
    """Validates GCS bucket names, allowlist membership, and project ownership."""
    allowed_buckets = _parse_csv_env("ALLOWED_BUCKETS")
    if not allowed_buckets:
        raise ValueError("ALLOWED_BUCKETS is not configured; refusing to run.")

    buckets = project.get("buckets")
    if not isinstance(buckets, dict):
        raise ValueError(f"Missing buckets map for project '{project_id}'.")

    for bucket_key in required_buckets:
        bucket_name = str(buckets.get(bucket_key, "")).strip()
        if not _is_valid_bucket_name(bucket_name):
            raise ValueError(
                f"Invalid bucket name for '{bucket_key}' in '{project_id}'."
            )
        if bucket_name not in allowed_buckets:
            raise ValueError(f"Bucket '{bucket_name}' is not in ALLOWED_BUCKETS.")

    allowed_numbers = _parse_csv_env("ALLOWED_PROJECT_NUMBERS")
    if allowed_numbers:
        proj_num = str(project.get("project_number", "")).strip()
        if proj_num and proj_num not in allowed_numbers:
            raise ValueError(
                f"project_number '{proj_num}' is not in ALLOWED_PROJECT_NUMBERS."
            )
        owner_gcs = gcs or storage.Gcs(
            project_id=_PRODUCER_PROJECT, bucket_name=_CONFIG_PATH
        )
        for bucket_key in required_buckets:
            bucket_name = str(buckets[bucket_key]).strip()
            bucket_meta = owner_gcs.client.get_bucket(bucket_name)
            if str(bucket_meta.project_number) not in allowed_numbers:
                raise ValueError(
                    f"Bucket '{bucket_name}' does not belong to an "
                    "allowlisted project number."
                )


def _validate_project(
    project: Dict[str, Any],
    required_buckets: Sequence[str] = ("audios", "transcripts", "metadata"),
    gcs: Optional[storage.Gcs] = None,
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

    location = str(project.get("location", "")).strip()
    if location not in _SUPPORTED_LOCATIONS:
        raise ValueError(
            f"Unsupported location '{location}' for project '{project_id}'."
        )

    environments = project.get("environments", [])
    if (
        not isinstance(environments, list)
        or not environments
        or any(env not in _SUPPORTED_ENVIRONMENTS for env in environments)
    ):
        raise ValueError(
            f"Invalid environments {environments!r} for project '{project_id}'."
        )

    _validate_audio_profile(project, project_id)
    if required_buckets:
        _validate_project_buckets(project, project_id, required_buckets, gcs)


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
        or not project["generation_profile"]["max_conversations_per_run"]["audio"]
    ):
        logging.error("Project (%s) not fully configured", project["project_id"])
        return False
    return True


def _generate_audio(
    audio_generator, conversation, audio_bucket, file_name, project_id
):
    """Generates audio for a conversation and returns the audio path."""
    try:
        audio_path = f"gs://{audio_bucket}/{file_name}{_AUDIO_EXTENSION}"
        audio_generator.single(
            transcript=json.loads(conversation),
            audio_file_path=audio_path,
        )
        return audio_path
    except Exception as e:  # pylint: disable=broad-exception-caught
        logging.error(
            "An unexpected error (%s) occurred during audio generation on %s",
            e,
            project_id,
        )
        return None


def _upload_artifacts(
    gcs,
    project_id,
    transcript_bucket,
    metadata_bucket,
    file_name,
    conversation,
    metadata,
):
    """Uploads conversation transcript and metadata to GCS."""
    try:
        gcs.project_id = project_id
        gcs.bucket_name = transcript_bucket
        gcs.upload_blob(file_name=file_name + _FILE_EXTENSION, data=conversation)

        gcs.bucket_name = metadata_bucket
        gcs.upload_blob(
            file_name=file_name + _FILE_EXTENSION,
            data=json.dumps(metadata, indent=2),
        )
        return True
    except Exception as e:  # pylint: disable=broad-exception-caught
        logging.error(
            "An unexpected error (%s) occurred during file upload for project %s",
            e,
            project_id,
        )
        return False


def _ingest_to_environments(project, audio_path, file_name, metadata):
    """Ingests the conversation into all configured environments."""
    ingested_count = 0
    project_id = project["project_id"]
    project_location = project["location"]

    for env in project["environments"]:
        try:
            ingestion = insights.Ingestion(
                parent=f"projects/{project_id}/locations/{project_location}",
                audio_path=audio_path,
                config=base.Config(
                    region=project_location,
                    environment=base.Environments(env),
                ),
            )
            ingestion.single(
                agent=[
                    {
                        "name": metadata["agent_info"][0]["agent_name"],
                        "id": metadata["agent_info"][0]["agent_id"],
                        "team": metadata["agent_info"][0]["agent_team"],
                    }
                ],
                labels=metadata["labels"],
                customer_satisfaction=metadata["customer_satisfaction_rating"],
                conversation_id=file_name,
            )
            logging.info(
                "-----> Conversation %s uploaded to %s %s insights instance",
                file_name,
                env,
                project_id,
            )
            ingested_count += 1
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error(
                "An unexpected error (%s) occurred during file upload on %s %s",
                e,
                env,
                project_id,
            )
    return ingested_count


def _process_project(project, gcs=None):
    """Processes a single project to generate and ingest conversations."""
    _validate_project(
        project, required_buckets=("audios", "transcripts", "metadata"), gcs=gcs
    )
    if not _is_project_fully_configured(project):
        return 0

    if gcs is None:
        gcs = storage.Gcs(project_id=_PRODUCER_PROJECT, bucket_name=_CONFIG_PATH)

    project_id = project["project_id"]
    max_audio = min(
        max(
            1,
            int(float(project["generation_profile"]["max_conversations_per_run"]["audio"])),
        ),
        _MAX_CONVERSATIONS_CAP,
    )
    ranger = random.randint(0, max_audio)
    logging.info("Generating %s conversations for %s", ranger, project_id)

    generator = content_generator.Generator(
        project_id=_PRODUCER_PROJECT, location="us-central1"
    )
    audio_generator = audio.GenerateAudio(project_id=_PRODUCER_PROJECT)
    parameters = generator.create_parameters(
        generation_profile=project["generation_profile"]
    )

    conversations_generated = 0
    for _ in range(ranger):
        metadata = generator.create_metadata(parameters=parameters)
        conversation = generator.create_conversation(parameters=parameters)
        file_name = file_name_generator()

        audio_path = _generate_audio(
            audio_generator,
            conversation,
            project["buckets"]["audios"],
            file_name,
            project_id,
        )
        if not audio_path:
            continue

        if _upload_artifacts(
            gcs,
            project_id,
            project["buckets"]["transcripts"],
            project["buckets"]["metadata"],
            file_name,
            conversation,
            metadata,
        ):
            conversations_generated += _ingest_to_environments(
                project, audio_path, file_name, metadata
            )

    return conversations_generated


def runner(args):  # pylint: disable=unused-argument
    """Cloud Function entry point for synthetic human voice generation."""
    conversations_generated = 0
    configs = import_config()

    for config_str in configs:
        config = json.loads(config_str)
        for project in config.get("projects", []):
            try:
                _validate_project(
                    project,
                    required_buckets=("audios", "transcripts", "metadata"),
                )
            except ValueError as exc:
                logging.error("Skipping invalid project entry: %s", exc)
                continue
            conversations_generated += _process_project(project)

    return f"{conversations_generated} conversations generated"
