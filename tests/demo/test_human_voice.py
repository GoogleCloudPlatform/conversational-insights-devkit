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

"""Unit tests for the human_voice runner main.py."""

from unittest.mock import patch
import datetime
import json
from cxidk.workflow.demo_artifacts.runners.human_voice import main

def test_file_name_generator():
    """Tests that the file name generator returns the correct format."""
    file_name = main.file_name_generator()
    assert len(file_name) == 18
    assert datetime.datetime.strptime(file_name, "%y%m%d%H%M%S%f")

@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.import_config")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.storage.Gcs")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.content_generator.Generator")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.audio.GenerateAudio")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.insights.Ingestion")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.random")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.logging")
def test_runner_no_config(
    _mock_logging,
    _mock_random,
    _mock_ingestion,
    _mock_audio_generator,
    _mock_generator,
    _mock_gcs,
    mock_import_config,
):
    """Tests that the runner handles no configs gracefully."""
    mock_import_config.return_value = []
    result = main.runner(None)
    assert result == "0 conversations generated"


@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.import_config")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.storage.Gcs")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.content_generator.Generator")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.audio.GenerateAudio")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.insights.Ingestion")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.random")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.logging")
def test_runner_with_valid_config(
    _mock_logging,
    mock_random,
    mock_ingestion,
    mock_audio_generator,
    mock_generator,
    mock_gcs,
    mock_import_config,
):
    """Tests the runner with a valid configuration."""
    mock_config = {
        "projects": [
            {
                "project_id": "test-project",
                "location": "us-central1",
                "buckets": {
                    "metadata": "test-metadata-bucket",
                    "transcripts": "test-transcript-bucket",
                    "audios": "test-audio-bucket",
                },
                "generation_profile": {
                    "theme": "test-theme",
                    "max_conversations_per_run": {"audio": 2},
                },
                "environments": ["stg", "prod"],
            }
        ]
    }
    mock_import_config.return_value = [json.dumps(mock_config)]
    mock_random.randint.return_value = 2
    mock_generator.return_value.create_parameters.return_value = {}
    mock_generator.return_value.create_metadata.return_value = {
        "agent_info": [
            {"agent_name": "test-agent", "agent_id": "123", "agent_team": "test-team"}
        ],
        "labels": {},
        "customer_satisfaction_rating": 5,
    }
    mock_generator.return_value.create_conversation.return_value = "{}"

    result = main.runner(None)

    assert result == "4 conversations generated"
    assert mock_audio_generator.return_value.single.call_count == 2
    assert mock_gcs.return_value.upload_blob.call_count == 4
    assert mock_ingestion.call_count == 4


@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.import_config")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.storage.Gcs")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.content_generator.Generator")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.audio.GenerateAudio")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.insights.Ingestion")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.random")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.logging")
def test_runner_partially_configured_project(
    mock_logging,
    mock_random,
    _mock_ingestion,
    _mock_audio_generator,
    _mock_generator,
    _mock_gcs,
    mock_import_config,
):
    """Tests that the runner handles partially configured projects."""
    mock_config = {
        "projects": [
            {
                "project_id": "test-project-partial",
                "location": "us-central1",
                "buckets": {
                    "metadata": "test-metadata-bucket",
                    "transcripts": "test-transcript-bucket",
                    "audios": "test-audio-bucket",
                },
                "generation_profile": {"theme": [], "max_conversations_per_run": {"audio": 0}},
                "environments": ["stg", "prod"],
            }
        ]
    }
    mock_import_config.return_value = [json.dumps(mock_config)]

    result = main.runner(None)

    assert result == "0 conversations generated"
    mock_logging.error.assert_called_with(
        "Project (%s) not fully configured", "test-project-partial"
    )
    mock_random.randint.assert_not_called()


@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.import_config")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.storage.Gcs")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.content_generator.Generator")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.audio.GenerateAudio")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.insights.Ingestion")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.random")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.logging")
def test_runner_audio_generation_exception(
    mock_logging,
    mock_random,
    mock_ingestion,
    mock_audio_generator,
    mock_generator,
    mock_gcs,
    mock_import_config,
):
    """Tests that the runner handles exceptions during audio generation."""
    mock_config = {
        "projects": [
            {
                "project_id": "test-project-audio-exception",
                "location": "us-central1",
                "buckets": {
                    "metadata": "test-metadata-bucket",
                    "transcripts": "test-transcript-bucket",
                    "audios": "test-audio-bucket",
                },
                "generation_profile": {
                    "theme": "test-theme",
                    "max_conversations_per_run": {"audio": 1},
                },
                "environments": ["stg"],
            }
        ]
    }
    mock_import_config.return_value = [json.dumps(mock_config)]
    mock_random.randint.return_value = 1
    mock_generator.return_value.create_parameters.return_value = {}
    mock_generator.return_value.create_metadata.return_value = {
        "agent_info": [
            {"agent_name": "test-agent", "agent_id": "123", "agent_team": "test-team"}
        ],
        "labels": {},
        "customer_satisfaction_rating": 5,
    }
    mock_generator.return_value.create_conversation.return_value = "{}"
    mock_audio_generator.return_value.single.side_effect = Exception("Audio generation failed")

    result = main.runner(None)

    assert result == "0 conversations generated"
    mock_logging.error.assert_called_with(
        "An unexpected error (%s) occurred during audio generation on %s",
        mock_audio_generator.return_value.single.side_effect,
        "test-project-audio-exception",
    )
    mock_gcs.return_value.upload_blob.assert_not_called()
    mock_ingestion.return_value.single.assert_not_called()


@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.import_config")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.storage.Gcs")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.content_generator.Generator")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.audio.GenerateAudio")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.insights.Ingestion")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.random")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.logging")
def test_runner_upload_exception(
    mock_logging,
    mock_random,
    mock_ingestion,
    mock_audio_generator,
    mock_generator,
    mock_gcs,
    mock_import_config,
):
    """Tests that the runner handles exceptions during file upload."""
    mock_config = {
        "projects": [
            {
                "project_id": "test-project-upload-exception",
                "location": "us-central1",
                "buckets": {
                    "metadata": "test-metadata-bucket",
                    "transcripts": "test-transcript-bucket",
                    "audios": "test-audio-bucket",
                },
                "generation_profile": {
                    "theme": "test-theme",
                    "max_conversations_per_run": {"audio": 1},
                },
                "environments": ["stg"],
            }
        ]
    }
    mock_import_config.return_value = [json.dumps(mock_config)]
    mock_random.randint.return_value = 1
    mock_generator.return_value.create_parameters.return_value = {}
    mock_generator.return_value.create_metadata.return_value = {
        "agent_info": [
            {"agent_name": "test-agent", "agent_id": "123", "agent_team": "test-team"}
        ],
        "labels": {},
        "customer_satisfaction_rating": 5,
    }
    mock_generator.return_value.create_conversation.return_value = "{}"
    mock_gcs.return_value.upload_blob.side_effect = Exception("Upload failed")

    result = main.runner(None)

    assert result == "0 conversations generated"
    mock_audio_generator.return_value.single.assert_called_once()
    mock_logging.error.assert_called_with(
        "An unexpected error (%s) occurred during file upload for project %s",
        mock_gcs.return_value.upload_blob.side_effect,
        "test-project-upload-exception",
    )
    mock_ingestion.return_value.single.assert_not_called()


@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.import_config")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.storage.Gcs")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.content_generator.Generator")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.audio.GenerateAudio")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.insights.Ingestion")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.random")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.logging")
def test_runner_ingestion_exception(
    mock_logging,
    mock_random,
    mock_ingestion,
    mock_audio_generator,
    mock_generator,
    mock_gcs,
    mock_import_config,
):
    """Tests that the runner handles exceptions during ingestion."""
    mock_config = {
        "projects": [
            {
                "project_id": "test-project-ingestion-exception",
                "location": "us-central1",
                "buckets": {
                    "metadata": "test-metadata-bucket",
                    "transcripts": "test-transcript-bucket",
                    "audios": "test-audio-bucket",
                },
                "generation_profile": {
                    "theme": "test-theme",
                    "max_conversations_per_run": {"audio": 1},
                },
                "environments": ["stg"],
            }
        ]
    }
    mock_import_config.return_value = [json.dumps(mock_config)]
    mock_random.randint.return_value = 1
    mock_generator.return_value.create_metadata.return_value = {
        "agent_info": [
            {"agent_name": "test-agent", "agent_id": "123", "agent_team": "test-team"}
        ],
        "labels": {},
        "customer_satisfaction_rating": 5,
    }
    mock_generator.return_value.create_conversation.return_value = "{}"
    mock_ingestion.side_effect = Exception("Ingestion failed")

    result = main.runner(None)

    assert result == "0 conversations generated"
    mock_audio_generator.return_value.single.assert_called_once()
    assert mock_gcs.return_value.upload_blob.call_count == 2
    mock_logging.error.assert_called_with(
        "An unexpected error (%s) occurred during file upload on %s %s",
        mock_ingestion.side_effect,
        "stg",
        "test-project-ingestion-exception",
    )
