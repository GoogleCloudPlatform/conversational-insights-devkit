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

"""Unit tests for the insight refinement pydantic schemas."""

import pytest

from cxidk.workflow.insight_refinements.schemas.input import (
    BatchAnalysisInput,
    FeedbackCSVRow,
)
from cxidk.workflow.insight_refinements.schemas.output import (
    EvaluationMetrics,
    EvaluationResult,
)
from cxidk.workflow.insight_refinements.schemas.topic import (
    L1TopicDefinition,
    L2TaxonomyResult,
    TopicAuditLog,
)


def test_batch_analysis_input_validation():
    """Test validation logic in BatchAnalysisInput."""
    # Valid config
    config_data = {
        "gcp": {
            "project_id": "p",
            "project_number": "123",
            "location_id": "l",
        },
        "ccai": {"scorecard_id": "123"},
        "llm": {"model_name": "gemini", "location_id": "us"},
        "bigquery": {"dataset_id": "d", "staging_table_id": "s", "main_table_id": "m"},
    }
    input_model = BatchAnalysisInput(**config_data)
    # pylint infers the pydantic Field() default (FieldInfo) for `gcp`.
    assert input_model.gcp.project_id == "p"  # pylint: disable=no-member

    # Invalid and suffix-spoofed endpoints must be rejected
    for bad_host in (
        "invalid.com",
        "evil-googleapis.com",
        "attacker.com/x?.googleapis.com",
        "attacker.com@.googleapis.com",
    ):
        config_data["ccai"]["insights_endpoint"] = bad_host
        with pytest.raises(ValueError):
            BatchAnalysisInput(**config_data)


def test_evaluation_metrics_validation():
    """Test validation logic in EvaluationMetrics."""
    metrics = EvaluationMetrics(
        accuracy=0.9,
        precision=0.8,
        recall=0.7,
        f1_score=0.75,
        cohens_kappa=0.6,
        total_samples=100,
    )
    assert metrics.accuracy == 0.9


def test_feedback_csv_row_validation():
    """Test validation for FeedbackCSVRow."""
    # Valid row
    row = FeedbackCSVRow(
        conversation_id="conv1",
        question_id="q1",
        answer_value="Yes",
        rationale="Agent greeted clearly.",
        score=1.0,
    )
    assert row.conversation_id == "conv1"
    assert row.rationale == "Agent greeted clearly."

    # Missing required field
    with pytest.raises(ValueError):
        FeedbackCSVRow(conversation_id="conv1")  # Missing question_id, answer_value


def test_evaluation_result_rationale():
    """Test that EvaluationResult accepts rationale."""
    result = EvaluationResult(
        resource_id="r1",
        question_id="q1",
        predicted_answer="Yes",
        golden_answer="No",
        is_correct=False,
        rationale="LLM missed the nuance.",
    )
    assert result.rationale == "LLM missed the nuance."


def test_l1_topic_definition_validation():
    """Test validation for L1TopicDefinition."""
    topic = L1TopicDefinition(
        issue_model_id="model-123",
        issue_id="issue-123",
        display_name="Greeting",
        description="Agent greets the customer.",
        exported_at="2026-03-18T12:00:00Z",
    )
    assert topic.issue_model_id == "model-123"
    assert topic.issue_id == "issue-123"


def test_l2_taxonomy_result_validation():
    """Test validation for L2TaxonomyResult."""
    result = L2TaxonomyResult(
        conversation_id="conv-1",
        l1_issue_id="issue-123",
        l2_category="Polite Greeting",
        reasoning="The agent used a very polite tone.",
    )
    assert result.l2_category == "Polite Greeting"


def test_topic_audit_log_validation():
    """Test validation for TopicAuditLog."""
    log = TopicAuditLog(
        run_id="run-789",
        conversation_id="conv-1",
        status="success",
        latency_ms=150.5,
        input_tokens=100,
        output_tokens=50,
    )
    assert log.status == "success"
    assert log.latency_ms == 150.5
