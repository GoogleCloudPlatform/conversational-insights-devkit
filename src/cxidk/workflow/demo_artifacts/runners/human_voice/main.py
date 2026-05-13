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

"""Runner that generates the human to human conversations"""

import json
import random
import datetime
import logging

from cxidk.core import base
from cxidk.wrapper import storage
from cxidk.wrapper import insights
from cxidk.workflow import content_generator
from cxidk.workflow import audio

logging.basicConfig(level=logging.INFO)


_CONFIG_PATH = "insights-pipeline-producer-configs"
_CONFIG_FILES = ["projects.json","demos.json"]
_PRODUCER_PROJECT = "insights-pipeline-producer"

_FILE_EXTENSION = ".json"
_AUDIO_EXTENSION = ".wav"


def import_config():
    """Import config"""
    gcs = storage.Gcs(project_id=_PRODUCER_PROJECT, bucket_name=_CONFIG_PATH)
    configs = []
    for config_file in _CONFIG_FILES:
        configs.append(
            gcs.download_blob(config_file).decode("utf-8")
        )
    return configs


def file_name_generator():
    """Generates a file name based on the current time.
    The format is YYMMDDHHMM.
    Returns:
        str: The formatted file name string.
    """
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


def _generate_audio(audio_generator, conversation, audio_bucket, file_name, project_id):
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


def _upload_artifacts(gcs, project_id, transcript_bucket, metadata_bucket, file_name, conversation, metadata): # pylint: disable=C0301
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


def _process_project(project, gcs):
    """Processes a single project to generate and ingest conversations."""
    if not _is_project_fully_configured(project):
        return 0

    project_id = project["project_id"]
    ranger = random.randint(0, int(project["generation_profile"]["max_conversations_per_run"]["audio"])) # pylint: disable=C0301
    logging.info("Generating %s conversations for %s", ranger, project_id)

    generator = content_generator.Generator(project_id=_PRODUCER_PROJECT, location="us-central1")
    audio_generator = audio.GenerateAudio(project_id=_PRODUCER_PROJECT)
    parameters = generator.create_parameters(generation_profile=project["generation_profile"])

    conversations_generated = 0
    for _ in range(ranger):
        metadata = generator.create_metadata(parameters=parameters)
        conversation = generator.create_conversation(parameters=parameters)
        file_name = file_name_generator()

        audio_path = _generate_audio(audio_generator, conversation, project["buckets"]["audios"], file_name, project_id) # pylint: disable=C0301
        if not audio_path:
            continue

        if _upload_artifacts(gcs, project_id, project["buckets"]["transcripts"], project["buckets"]["metadata"], file_name, conversation, metadata): # pylint: disable=C0301
            conversations_generated += _ingest_to_environments(project, audio_path, file_name, metadata) # pylint: disable=C0301

    return conversations_generated

#Args is reqd for the cloud function to properly run
def runner(args): # pylint: disable=unused-argument
    """Runner: The code that will run in the cloud function"""

    conversations_generated = 0
    configs = import_config()

    for config_str in configs:
        config = json.loads(config_str)
        for project in config["projects"]:
            gcs = storage.Gcs(project_id=_PRODUCER_PROJECT, bucket_name=_CONFIG_PATH)
            conversations_generated += _process_project(project, gcs)

    return f"{conversations_generated} conversations generated"
