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

"""Unit and confused-deputy security tests for the human_chat runner."""

import datetime
import json
from unittest.mock import MagicMock, patch

import pytest

from cxidk.workflow.demo_artifacts.runners.human_chat import main


def test_file_name_generator():
    """Tests that the file name generator returns the correct format."""
    file_name = main.file_name_generator()
    assert len(file_name) == 18
    assert datetime.datetime.strptime(file_name, "%y%m%d%H%M%S%f")


@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.import_config")
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.storage.Gcs")
@patch(
    "cxidk.workflow.demo_artifacts.runners.human_chat.main.content_generator.Generator"
)
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.insights.Ingestion")
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.random")
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.logging")
def test_runner_no_config(
    _mock_logging,
    _mock_random,
    _mock_ingestion,
    _mock_generator,
    _mock_gcs,
    mock_import_config,
):
    """Tests that the runner handles empty config lists gracefully."""
    mock_import_config.return_value = []
    result = main.runner(None)
    assert result == "0 conversations generated"


@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.import_config")
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.storage.Gcs")
@patch(
    "cxidk.workflow.demo_artifacts.runners.human_chat.main.content_generator.Generator"
)
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.insights.Ingestion")
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.random")
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.logging")
def test_runner_with_valid_config(
    _mock_logging,
    mock_random,
    _mock_ingestion,
    mock_generator,
    mock_gcs,
    mock_import_config,
    monkeypatch,
):
    """Tests the runner with an allowlisted valid configuration."""
    monkeypatch.setenv("ALLOWED_PROJECT_IDS", "test-project")
    monkeypatch.setenv(
        "ALLOWED_BUCKETS", "test-metadata-bucket,test-transcript-bucket"
    )
    mock_config = {
        "projects": [
            {
                "project_id": "test-project",
                "location": "us-central1",
                "buckets": {
                    "metadata": "test-metadata-bucket",
                    "transcripts": "test-transcript-bucket",
                },
                "generation_profile": {
                    "theme": "test-theme",
                    "max_conversations_per_run": {"chat": 2},
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
    assert mock_gcs.return_value.upload_blob.call_count == 4


@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.import_config")
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.storage.Gcs")
@patch(
    "cxidk.workflow.demo_artifacts.runners.human_chat.main.content_generator.Generator"
)
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.insights.Ingestion")
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.random")
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.logging")
def test_runner_partially_configured_project(
    mock_logging,
    mock_random,
    _mock_ingestion,
    _mock_generator,
    _mock_gcs,
    mock_import_config,
    monkeypatch,
):
    """Tests that the runner skips allowlisted but partially configured projects."""
    monkeypatch.setenv("ALLOWED_PROJECT_IDS", "test-project-partial")
    monkeypatch.setenv(
        "ALLOWED_BUCKETS", "test-metadata-bucket,test-transcript-bucket"
    )
    mock_config = {
        "projects": [
            {
                "project_id": "test-project-partial",
                "location": "us-central1",
                "buckets": {
                    "metadata": "test-metadata-bucket",
                    "transcripts": "test-transcript-bucket",
                },
                "generation_profile": {
                    "theme": [],
                    "max_conversations_per_run": {"chat": 0},
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


@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.import_config")
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.storage.Gcs")
@patch(
    "cxidk.workflow.demo_artifacts.runners.human_chat.main.content_generator.Generator"
)
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.insights.Ingestion")
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.random")
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.logging")
def test_runner_upload_exception(
    mock_logging,
    mock_random,
    mock_ingestion,
    _mock_generator,
    mock_gcs,
    mock_import_config,
    monkeypatch,
):
    """Tests that the runner handles exceptions during file upload."""
    monkeypatch.setenv("ALLOWED_PROJECT_IDS", "test-project-exception")
    monkeypatch.setenv(
        "ALLOWED_BUCKETS", "test-metadata-bucket,test-transcript-bucket"
    )
    mock_config = {
        "projects": [
            {
                "project_id": "test-project-exception",
                "location": "us-central1",
                "buckets": {
                    "metadata": "test-metadata-bucket",
                    "transcripts": "test-transcript-bucket",
                },
                "generation_profile": {
                    "theme": "test-theme",
                    "max_conversations_per_run": {"chat": 1},
                },
                "environments": ["stg"],
            }
        ]
    }
    mock_import_config.return_value = [json.dumps(mock_config)]
    mock_random.randint.return_value = 1
    mock_gcs.return_value.upload_blob.side_effect = Exception("Upload failed")

    result = main.runner(None)

    assert result == "0 conversations generated"
    mock_logging.error.assert_called_with(
        "An unexpected error (%s) occurred during file upload for project %s",
        mock_gcs.return_value.upload_blob.side_effect,
        "test-project-exception",
    )
    mock_ingestion.assert_not_called()


@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.import_config")
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.storage.Gcs")
@patch(
    "cxidk.workflow.demo_artifacts.runners.human_chat.main.content_generator.Generator"
)
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.insights.Ingestion")
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.random")
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.logging")
def test_runner_ingestion_exception(
    mock_logging,
    mock_random,
    mock_ingestion,
    mock_generator,
    mock_gcs,
    mock_import_config,
    monkeypatch,
):
    """Tests that the runner handles exceptions during ingestion."""
    monkeypatch.setenv("ALLOWED_PROJECT_IDS", "test-project-ingest-err")
    monkeypatch.setenv(
        "ALLOWED_BUCKETS", "test-metadata-bucket,test-transcript-bucket"
    )
    mock_config = {
        "projects": [
            {
                "project_id": "test-project-ingest-err",
                "location": "us-central1",
                "buckets": {
                    "metadata": "test-metadata-bucket",
                    "transcripts": "test-transcript-bucket",
                },
                "generation_profile": {
                    "theme": "test-theme",
                    "max_conversations_per_run": {"chat": 1},
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
    mock_ingestion.side_effect = Exception("Ingestion failed")

    result = main.runner(None)

    assert result == "0 conversations generated"
    mock_logging.error.assert_called_with(
        "An unexpected error (%s) occurred during file upload on %s %s",
        mock_ingestion.side_effect,
        "stg",
        "test-project-ingest-err",
    )
    assert mock_gcs.return_value.upload_blob.call_count == 2


@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.import_config")
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.storage.Gcs")
@patch(
    "cxidk.workflow.demo_artifacts.runners.human_chat.main.content_generator.Generator"
)
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.insights.Ingestion")
def test_runner_fails_closed_when_allowlists_unset(
    mock_ingestion,
    mock_generator,
    mock_gcs,
    mock_import_config,
    monkeypatch,
):
    """Unset or empty allowlists fail closed with zero outbound API calls."""
    monkeypatch.delenv("ALLOWED_PROJECT_IDS", raising=False)
    monkeypatch.delenv("ALLOWED_BUCKETS", raising=False)
    mock_config = {
        "projects": [
            {
                "project_id": "test-project",
                "location": "us-central1",
                "buckets": {
                    "metadata": "test-metadata-bucket",
                    "transcripts": "test-transcript-bucket",
                },
                "generation_profile": {
                    "theme": "test-theme",
                    "max_conversations_per_run": {"chat": 2},
                },
                "environments": ["prod"],
            }
        ]
    }
    mock_import_config.return_value = [json.dumps(mock_config)]

    assert main.runner(None) == "0 conversations generated"
    mock_gcs.assert_not_called()
    mock_generator.assert_not_called()
    mock_ingestion.assert_not_called()


@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.import_config")
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.storage.Gcs")
@patch(
    "cxidk.workflow.demo_artifacts.runners.human_chat.main.content_generator.Generator"
)
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.insights.Ingestion")
@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.random")
def test_runner_skips_unallowlisted_project_and_runs_valid_sibling(
    mock_random,
    mock_ingestion,
    mock_generator,
    mock_gcs,
    mock_import_config,
    monkeypatch,
):
    """Unallowlisted project is skipped while allowlisted sibling executes."""
    monkeypatch.setenv("ALLOWED_PROJECT_IDS", "valid-project")
    monkeypatch.setenv("ALLOWED_BUCKETS", "valid-meta-bkt,valid-trans-bkt")
    mock_config = {
        "projects": [
            {
                "project_id": "attacker-owned-project",
                "location": "us-central1",
                "buckets": {
                    "metadata": "valid-meta-bkt",
                    "transcripts": "valid-trans-bkt",
                },
                "generation_profile": {
                    "theme": "test-theme",
                    "max_conversations_per_run": {"chat": 2},
                },
                "environments": ["prod"],
            },
            {
                "project_id": "valid-project",
                "location": "us-central1",
                "buckets": {
                    "metadata": "valid-meta-bkt",
                    "transcripts": "valid-trans-bkt",
                },
                "generation_profile": {
                    "theme": "test-theme",
                    "max_conversations_per_run": {"chat": 1},
                },
                "environments": ["prod"],
            },
        ]
    }
    mock_import_config.return_value = [json.dumps(mock_config)]
    mock_random.randint.return_value = 1
    mock_generator.return_value.create_parameters.return_value = {}
    mock_generator.return_value.create_metadata.return_value = {
        "agent_info": [
            {"agent_name": "a", "agent_id": "1", "agent_team": "t"}
        ],
        "labels": {},
        "customer_satisfaction_rating": 5,
    }
    mock_generator.return_value.create_conversation.return_value = "{}"

    assert main.runner(None) == "1 conversations generated"
    assert mock_gcs.return_value.upload_blob.call_count == 2
    mock_ingestion.assert_called_once()


@patch("cxidk.workflow.demo_artifacts.runners.human_chat.main.storage.Gcs")
@patch(
    "cxidk.workflow.demo_artifacts.runners.human_chat.main.content_generator.Generator"
)
def test_validate_project_rejects_squatted_bucket_and_project_number_mismatch(
    mock_generator,
    mock_gcs,
    monkeypatch,
):
    """Prefix-squatted buckets and external project numbers are rejected."""
    monkeypatch.setenv("ALLOWED_PROJECT_IDS", "valid-project")
    monkeypatch.setenv("ALLOWED_BUCKETS", "valid-meta-bkt,valid-trans-bkt")

    squatted = {
        "project_id": "valid-project",
        "location": "us-central1",
        "buckets": {
            "metadata": "valid-project-attacker-bucket",
            "transcripts": "valid-trans-bkt",
        },
        "generation_profile": {
            "theme": "test-theme",
            "max_conversations_per_run": {"chat": 1},
        },
        "environments": ["prod"],
    }
    with pytest.raises(ValueError, match="ALLOWED_BUCKETS"):
        main._process_project(squatted)  # pylint: disable=protected-access
    mock_generator.assert_not_called()

    monkeypatch.setenv("ALLOWED_PROJECT_NUMBERS", "111111111111")
    fake_bucket_meta = MagicMock()
    fake_bucket_meta.project_number = 999999999999
    mock_gcs.return_value.client.get_bucket.return_value = fake_bucket_meta

    wrong_owner = {
        "project_id": "valid-project",
        "project_number": "111111111111",
        "location": "us-central1",
        "buckets": {
            "metadata": "valid-meta-bkt",
            "transcripts": "valid-trans-bkt",
        },
        "generation_profile": {
            "theme": "test-theme",
            "max_conversations_per_run": {"chat": 1},
        },
        "environments": ["prod"],
    }
    with pytest.raises(ValueError, match="allowlisted project number"):
        main._process_project(wrong_owner)  # pylint: disable=protected-access
    mock_gcs.return_value.upload_blob.assert_not_called()


@pytest.mark.parametrize(
    "bad_location,bad_bucket",
    [
        ("../other", "valid-trans-bkt"),
        ("us-central1?x=1", "valid-trans-bkt"),
        ("us-central1", "bucket/../evil"),
    ],
)
def test_validate_project_rejects_traversal_payloads(
    bad_location, bad_bucket, monkeypatch
):
    """Path traversal or query payloads in location or bucket raise ValueError."""
    monkeypatch.setenv("ALLOWED_PROJECT_IDS", "valid-project")
    monkeypatch.setenv("ALLOWED_BUCKETS", f"valid-meta-bkt,{bad_bucket}")
    project = {
        "project_id": "valid-project",
        "location": bad_location,
        "buckets": {"metadata": "valid-meta-bkt", "transcripts": bad_bucket},
        "generation_profile": {
            "theme": "test-theme",
            "max_conversations_per_run": {"chat": 1},
        },
        "environments": ["prod"],
    }
    with pytest.raises(ValueError):
        main._validate_project(project)  # pylint: disable=protected-access
