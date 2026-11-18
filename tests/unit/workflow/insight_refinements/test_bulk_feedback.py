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

"""Unit tests for the BulkFeedbackManager CSV to CCAI feedback pipeline."""

from unittest.mock import MagicMock, mock_open, patch

import pytest

from cxidk.workflow.insight_refinements.bulk_feedback import BulkFeedbackManager
from cxidk.workflow.insight_refinements.schemas.input import BatchAnalysisInput


@pytest.fixture(autouse=True)
def mock_ccai():
    """Stub the Contact Center Insights client used by BulkFeedbackManager.

    Scoped to this module's tests: patching the attribute on the module under
    test avoids mutating sys.modules, which would leak a MagicMock into
    'google.cloud' and break unrelated test modules collected afterwards.

    qai_logger is stubbed too: it binds a real Cloud Logging client at import
    time when application default credentials are present, which would make
    these tests depend on the developer's environment.
    """
    with patch(
        "cxidk.workflow.insight_refinements.bulk_feedback.contact_center_insights_v1",
        new=MagicMock(),
    ) as mocked, patch(
        "cxidk.workflow.insight_refinements.bulk_feedback.qai_logger",
        new=MagicMock(),
    ):
        yield mocked



@pytest.fixture
def mock_config():
    """Returns a minimal BatchAnalysisInput config for the feedback manager."""
    return BatchAnalysisInput(
        **{
            "gcp": {
                "project_id": "test-p",
                "project_number": "12345",
                "location_id": "us-central1",
            },
            "ccai": {"scorecard_id": "123"},
            "llm": {"model_name": "gemini", "location_id": "us"},
            "bigquery": {
                "dataset_id": "d",
                "staging_table_id": "s",
                "main_table_id": "m",
            },
        }
    )


@patch("cxidk.workflow.insight_refinements.utils.get_storage_client")
# pylint: disable-next=redefined-outer-name  # pytest fixture injection
def test_csv_row_to_json_label(_mock_storage, mock_config):
    """Test the mapping from CSV row to FeedbackLabel JSON structure."""
    # We don't need to patch CCAI client again because we mocked the module
    manager = BulkFeedbackManager(mock_config)

    # Test Case 1: Yes/No + Rationale
    row = {
        "conversation_id": "123",
        "question_id": "q1",
        "answer_value": "Yes",
        "rationale": "Good greeting",
        "score": "1.0",
    }

    # This private helper is the unit under test.
    label = manager._csv_row_to_json_label(row)  # pylint: disable=protected-access

    assert (
        "projects/test-p/locations/us-central1/conversations/123"
        in label["labeled_resource"]
    )
    assert label["qa_answer_label"]["key"] == "q1"
    assert label["qa_answer_label"]["bool_value"] is True
    # pylint sees the None branch of the conditional 'qa_answer_rationale' value;
    # the row above always provides a rationale, so the dict is populated here.
    assert (  # pylint: disable=unsubscriptable-object
        label["qa_answer_label"]["qa_answer_rationale"]["rationale"] == "Good greeting"
    )
    assert label["qa_answer_label"]["score"] == 1.0


@patch("cxidk.workflow.insight_refinements.utils.get_storage_client")
# pylint: disable-next=redefined-outer-name  # pytest fixture injection
def test_upload_from_local_csv(mock_storage, mock_config):
    """Test the orchestration of reading CSV and uploading to GCS."""
    manager = BulkFeedbackManager(mock_config)

    # Mock CSV content
    csv_content = """conversation_id,question_id,answer_value,rationale,score
123,q1,Yes,reason,1.0"""

    # Mock Storage
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_storage.return_value.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob

    # Mock Bulk Upload API call on the manager's client (which is a mock from sys.modules)
    mock_operation = MagicMock()
    mock_operation.result.return_value.upload_stats.success_count = 1
    manager.client.bulk_upload_feedback_labels.return_value = mock_operation

    with patch("builtins.open", mock_open(read_data=csv_content)):
        result = manager.upload_from_local_csv("dummy.csv", "my-bucket")

    assert result["status"] == "success"
    mock_blob.upload_from_string.assert_called_once()

    # Verify content
    uploaded_jsonl = mock_blob.upload_from_string.call_args[0][0]
    assert "qa_answer_rationale" in uploaded_jsonl
