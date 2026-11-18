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

"""Unit and confused-deputy security tests for the human_voice runner."""

import datetime
import json
from unittest.mock import MagicMock, patch

import pytest

from cxidk.workflow.demo_artifacts.runners.human_voice import main


def test_file_name_generator():
    """Tests that the file name generator returns the correct format."""
    file_name = main.file_name_generator()
    assert len(file_name) == 18
    assert datetime.datetime.strptime(file_name, "%y%m%d%H%M%S%f")


@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.import_config")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.storage.Gcs")
@patch(
    "cxidk.workflow.demo_artifacts.runners.human_voice.main.content_generator.Generator"
)
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
@patch(
    "cxidk.workflow.demo_artifacts.runners.human_voice.main.content_generator.Generator"
)
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
    monkeypatch,
):
    """Tests the runner with an allowlisted valid configuration."""
    monkeypatch.setenv("ALLOWED_PROJECT_IDS", "test-project")
    monkeypatch.setenv(
        "ALLOWED_BUCKETS",
        "test-metadata-bucket,test-transcript-bucket,test-audio-bucket",
    )
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
@patch(
    "cxidk.workflow.demo_artifacts.runners.human_voice.main.content_generator.Generator"
)
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
    monkeypatch,
):
    """Tests that the runner handles partially configured projects."""
    monkeypatch.setenv("ALLOWED_PROJECT_IDS", "test-project-partial")
    monkeypatch.setenv(
        "ALLOWED_BUCKETS",
        "test-metadata-bucket,test-transcript-bucket,test-audio-bucket",
    )
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
                "generation_profile": {
                    "theme": [],
                    "max_conversations_per_run": {"audio": 0},
                },
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
@patch(
    "cxidk.workflow.demo_artifacts.runners.human_voice.main.content_generator.Generator"
)
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
    monkeypatch,
):
    """Tests that the runner handles exceptions during audio generation."""
    monkeypatch.setenv("ALLOWED_PROJECT_IDS", "test-project-audio-exception")
    monkeypatch.setenv(
        "ALLOWED_BUCKETS",
        "test-metadata-bucket,test-transcript-bucket,test-audio-bucket",
    )
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
    mock_audio_generator.return_value.single.side_effect = Exception(
        "Audio generation failed"
    )

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
@patch(
    "cxidk.workflow.demo_artifacts.runners.human_voice.main.content_generator.Generator"
)
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
    monkeypatch,
):
    """Tests that the runner handles exceptions during file upload."""
    monkeypatch.setenv("ALLOWED_PROJECT_IDS", "test-project-upload-exception")
    monkeypatch.setenv(
        "ALLOWED_BUCKETS",
        "test-metadata-bucket,test-transcript-bucket,test-audio-bucket",
    )
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
@patch(
    "cxidk.workflow.demo_artifacts.runners.human_voice.main.content_generator.Generator"
)
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
    monkeypatch,
):
    """Tests that the runner handles exceptions during ingestion."""
    monkeypatch.setenv("ALLOWED_PROJECT_IDS", "test-project-ingest-err")
    monkeypatch.setenv(
        "ALLOWED_BUCKETS",
        "test-metadata-bucket,test-transcript-bucket,test-audio-bucket",
    )
    mock_config = {
        "projects": [
            {
                "project_id": "test-project-ingest-err",
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
        "test-project-ingest-err",
    )


@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.import_config")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.storage.Gcs")
@patch(
    "cxidk.workflow.demo_artifacts.runners.human_voice.main.content_generator.Generator"
)
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.audio.GenerateAudio")
@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.insights.Ingestion")
def test_runner_fails_closed_and_blocks_squatted_buckets(
    mock_ingestion,
    mock_audio_generator,
    mock_generator,
    mock_gcs,
    mock_import_config,
    monkeypatch,
):
    """Unset allowlists or unallowlisted audio buckets block TTS and GCS calls."""
    monkeypatch.delenv("ALLOWED_PROJECT_IDS", raising=False)
    monkeypatch.delenv("ALLOWED_BUCKETS", raising=False)
    base_project = {
        "project_id": "test-project",
        "location": "us-central1",
        "buckets": {
            "metadata": "test-metadata-bucket",
            "transcripts": "test-transcript-bucket",
            "audios": "test-project-attacker-audio",
        },
        "generation_profile": {
            "theme": "test-theme",
            "max_conversations_per_run": {"audio": 2},
        },
        "environments": ["prod"],
    }
    mock_import_config.return_value = [json.dumps({"projects": [base_project]})]

    assert main.runner(None) == "0 conversations generated"
    mock_audio_generator.assert_not_called()
    mock_gcs.assert_not_called()
    mock_generator.assert_not_called()
    mock_ingestion.assert_not_called()

    monkeypatch.setenv("ALLOWED_PROJECT_IDS", "test-project")
    monkeypatch.setenv(
        "ALLOWED_BUCKETS", "test-metadata-bucket,test-transcript-bucket"
    )
    assert main.runner(None) == "0 conversations generated"
    mock_audio_generator.assert_not_called()
    mock_gcs.assert_not_called()


@patch("cxidk.workflow.demo_artifacts.runners.human_voice.main.storage.Gcs")
def test_validate_project_rejects_traversal_and_wrong_bucket_owner(
    mock_gcs, monkeypatch
):
    """Path traversal in location or bucket ownership mismatch raises ValueError."""
    monkeypatch.setenv("ALLOWED_PROJECT_IDS", "test-project")
    monkeypatch.setenv(
        "ALLOWED_BUCKETS",
        "test-metadata-bucket,test-transcript-bucket,test-audio-bucket",
    )
    bad_project = {
        "project_id": "test-project",
        "location": "us-central1/../evil",
        "buckets": {
            "metadata": "test-metadata-bucket",
            "transcripts": "test-transcript-bucket",
            "audios": "test-audio-bucket",
        },
        "generation_profile": {
            "theme": "test-theme",
            "max_conversations_per_run": {"audio": 1},
        },
        "environments": ["prod"],
    }
    with pytest.raises(ValueError):
        main._validate_project(bad_project)  # pylint: disable=protected-access

    monkeypatch.setenv("ALLOWED_PROJECT_NUMBERS", "12345678")
    fake_meta = MagicMock()
    fake_meta.project_number = 87654321
    mock_gcs.return_value.client.get_bucket.return_value = fake_meta
    bad_project["location"] = "us-central1"
    with pytest.raises(ValueError, match="allowlisted project number"):
        main._validate_project(bad_project)  # pylint: disable=protected-access
