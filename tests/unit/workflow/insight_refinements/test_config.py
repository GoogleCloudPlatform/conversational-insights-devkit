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

"""Unit tests for the BatchAnalysisInput configuration schema."""

import pytest

from cxidk.workflow.insight_refinements.schemas.input import BatchAnalysisInput


def test_config_with_new_fields():
    """Test that the updated config schema correctly parses new fields."""
    config_data = {
        "gcp": {
            "project_id": "test-project",
            "project_number": "123456789",
            "location_id": "us-central1",
            "staging_bucket": "my-bucket",
        },
        "ccai": {
            "scorecard_id": "scorecard-123",
            "feedback_regionalization": True,
        },
        "llm": {
            "model_name": "gemini-3.0-flash",
            "location_id": "us-central1",
        },
        "bigquery": {
            "project_id": "analytics-project",
            "dataset_id": "test_dataset",
            "staging_table_id": "staging",
            "main_table_id": "main",
        },
        "topic_refinement": {
            "issue_model_id": "model-abc",
            "prompt_gcs_uri": "gs://bucket/prompt.txt",
        },
    }

    config = BatchAnalysisInput(**config_data)

    # pylint infers the pydantic Field() default (FieldInfo) instead of the
    # nested model type, so attribute access on sub-models is a false positive.
    # pylint: disable-next=no-member
    assert config.gcp.project_number == "123456789"
    # pylint: disable-next=no-member
    assert config.gcp.staging_bucket == "my-bucket"
    # pylint: disable-next=no-member
    assert config.ccai.feedback_regionalization is True
    # pylint: disable-next=no-member
    assert config.bigquery.project_id == "analytics-project"
    # pylint: disable-next=no-member
    assert config.topic_refinement.issue_model_id == "model-abc"
    # pylint: disable-next=no-member
    assert config.topic_refinement.prompt_gcs_uri == "gs://bucket/prompt.txt"
    # Verify defaults
    # pylint: disable-next=no-member
    assert config.topic_refinement.l1_definitions_table == "l1_topic_definitions"


def test_config_missing_required_fields():
    """Test that missing required fields raises validation error."""
    invalid_data = {
        "gcp": {"project_id": "p", "location_id": "l"},  # Missing project_number
        "ccai": {"scorecard_id": "s"},
        "llm": {"model_name": "m", "location_id": "l"},
        "bigquery": {"dataset_id": "d", "staging_table_id": "s", "main_table_id": "m"},
    }

    with pytest.raises(ValueError):
        BatchAnalysisInput(**invalid_data)
