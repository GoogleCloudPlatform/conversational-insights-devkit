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

"""Unit tests for the batch analysis and automated evaluation logic."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from cxidk.workflow.insight_refinements.analysis import (
    BigQueryOperator,
    run_batch_analysis,
)
from cxidk.workflow.insight_refinements.evaluation import (
    QuestionEvaluation,
    ConversationEvaluator,
    run_automated_evaluation,
)
from cxidk.workflow.insight_refinements.schemas.input import BatchAnalysisInput


@pytest.fixture
def mock_config():
    """Returns a minimal BatchAnalysisInput config for the analysis workflow."""
    return BatchAnalysisInput(
        **{
            "gcp": {
                "project_id": "test-project",
                "project_number": "12345",
                "location_id": "us-central1",
            },
            "ccai": {"scorecard_id": "12345"},
            "llm": {"model_name": "gemini-1.5-pro", "location_id": "us-central1"},
            "bigquery": {
                "dataset_id": "test_dataset",
                "staging_table_id": "staging",
                "main_table_id": "main",
            },
        }
    )


def test_question_evaluation_correctness():
    """Test the is_correct property of QuestionEvaluation."""
    qe_true = QuestionEvaluation(
        question_id="1",
        question_text="Test?",
        golden_answer="Meets",
        predicted_answer="Meets",
    )
    assert qe_true.is_correct is True

    qe_false = QuestionEvaluation(
        question_id="1",
        question_text="Test?",
        golden_answer="Meets",
        predicted_answer="Does Not Meet",
    )
    assert qe_false.is_correct is False

    # Test case insensitivity
    qe_case = QuestionEvaluation(
        question_id="1",
        question_text="Test?",
        golden_answer="meets",
        predicted_answer="MEETS ",
    )
    assert qe_case.is_correct is True


def test_conversation_evaluator_metrics():
    """Test metric calculation in ConversationEvaluator, including Cohen's Kappa."""
    evals = [
        QuestionEvaluation("1", "Q1", "yes", "yes"),
        QuestionEvaluation("2", "Q2", "yes", "no"),
        QuestionEvaluation("3", "Q3", "no", "no"),
        QuestionEvaluation("4", "Q4", "no", "yes"),
    ]
    # Matrix:
    # Gold: Yes, Yes, No, No
    # Pred: Yes, No, No, Yes
    # Agreement: 2/4 (50%)

    evaluator = ConversationEvaluator("conv_1", evals, valid_labels=["yes", "no"])
    metrics = evaluator.compute_metrics()

    assert metrics["accuracy"] == 0.5
    assert metrics["total_questions"] == 4
    # Kappa should be 0 because observed agreement (0.5) equals random chance agreement (0.5)
    # P(Yes) = 0.5, P(No) = 0.5 for both raters
    assert metrics["cohens_kappa"] == 0.0


def test_conversation_evaluator_perfect_agreement():
    """Test Cohen's Kappa for perfect agreement."""
    evals = [
        QuestionEvaluation("1", "Q1", "yes", "yes"),
        QuestionEvaluation("2", "Q2", "no", "no"),
    ]
    evaluator = ConversationEvaluator("conv_1", evals, valid_labels=["yes", "no"])
    metrics = evaluator.compute_metrics()

    assert metrics["accuracy"] == 1.0
    assert metrics["cohens_kappa"] == 1.0


def test_run_automated_evaluation_join():
    """Test the joining and processing logic of run_automated_evaluation."""
    results_df = pd.DataFrame(
        [
            {
                "resource_id": "c1",
                "question_id": "q1",
                "answer": "meets",
                "question_text": "Q1",
            },
            {
                "resource_id": "c1",
                "question_id": "q2",
                "answer": "meets",
                "question_text": "Q2",
            },
        ]
    )
    golden_df = pd.DataFrame(
        [
            {"resource_id": "c1", "question_id": "q1", "answer": "meets"},
            {"resource_id": "c1", "question_id": "q2", "answer": "does not meet"},
        ]
    )

    reporter = run_automated_evaluation(results_df, golden_df, join_key="resource_id")
    summary = reporter.get_summary_dataframe()

    assert len(summary) == 1
    assert summary.iloc[0]["accuracy"] == 0.5



@patch("cxidk.workflow.insight_refinements.analysis.get_bq_client")
# pylint: disable-next=redefined-outer-name  # pytest fixture injection
def test_bq_operator_load(mock_get_bq_client, mock_config):
    """Test BigQueryOperator load_dataframe_to_staging."""
    mock_client = mock_get_bq_client.return_value
    operator = BigQueryOperator(mock_config)
    df = pd.DataFrame({"col": [1, 2]})

    operator.load_dataframe_to_staging(df, "staging_table")

    # Verify the mock setup was called
    mock_client.load_table_from_dataframe.assert_called_once()
    # Verify job.result() was called
    mock_client.load_table_from_dataframe.return_value.result.assert_called_once()


@patch("cxidk.workflow.insight_refinements.analysis.get_bq_client")
# pylint: disable-next=redefined-outer-name  # pytest fixture injection
def test_bq_operator_merge(mock_get_bq_client, mock_config):
    """Test BigQueryOperator merge_staging_to_main."""
    mock_client = mock_get_bq_client.return_value
    operator = BigQueryOperator(mock_config)

    # Configure the mock to return an integer for num_dml_affected_rows
    mock_query_job = mock_client.query.return_value
    mock_query_job.num_dml_affected_rows = 10

    operator.merge_staging_to_main(
        staging_table="staging",
        main_table="main",
        merge_keys=["id"],
        update_columns=["val"],
    )

    mock_client.query.assert_called_once()
    mock_query_job.result.assert_called_once()

    # Check that the SQL contains the MERGE statement
    args, _ = mock_client.query.call_args
    assert "MERGE" in args[0]
    assert "test-project.test_dataset.main" in args[0]


@patch("cxidk.workflow.insight_refinements.schemas.input.BatchAnalysisInput.get_auth")
@patch("cxidk.workflow.insight_refinements.analysis.Analysis")
# pylint: disable-next=redefined-outer-name  # pytest fixture injection
def test_run_batch_analysis_bulk(mock_analysis_cls, mock_get_auth, mock_config):
    """run_batch_analysis triggers a bulk LRO and reports success.

    Upstream replaced the hand-rolled REST client (ConversationAnalyzer) with the
    devkit's Analysis wrapper, which returns a google.api_core Operation. That
    object exposes the LRO resource name via `.operation.name`, not `.name`.
    """
    mock_get_auth.return_value = MagicMock()
    mock_config.analysis.enable_bulk_analysis = True
    mock_config.analysis.filter = "test-filter"
    mock_config.analysis.analysis_percentage = 50

    mock_operation = MagicMock()
    mock_operation.operation.name = "projects/p/locations/l/operations/op123"
    mock_analysis_cls.return_value.bulk.return_value = mock_operation

    results = run_batch_analysis(mock_config)

    assert results == [
        {"status": "success", "operation_metadata": "Completed successfully"}
    ]

    mock_analysis_cls.return_value.bulk.assert_called_once()
    _, bulk_kwargs = mock_analysis_cls.return_value.bulk.call_args
    assert bulk_kwargs["analysis_percentage"] == 50.0
    assert bulk_kwargs["analysis_filter"] == "test-filter"

    # The LRO must be awaited before the run is reported as successful.
    mock_operation.result.assert_called_once_with(timeout=3600)


@patch("cxidk.workflow.insight_refinements.analysis.get_bq_client")
# pylint: disable-next=redefined-outer-name  # pytest fixture injection
def test_bq_operator_rejects_unsafe_identifiers(mock_get_bq_client, mock_config):
    """BigQueryOperator rejects SQL-injection characters in table and column names."""
    operator = BigQueryOperator(mock_config)
    df = pd.DataFrame({"col": [1]})

    with pytest.raises(ValueError, match="Unsafe BigQuery"):
        operator.load_dataframe_to_staging(df, "staging`; DROP TABLE main; --")

    with pytest.raises(ValueError, match="Unsafe BigQuery"):
        operator.merge_staging_to_main(
            staging_table="staging",
            main_table="main",
            merge_keys=["id = 1 OR 1=1 --"],
            update_columns=["val"],
        )
    mock_get_bq_client.return_value.query.assert_not_called()


# pylint: disable-next=redefined-outer-name  # pytest fixture injection
def test_topic_model_exporter_rejects_ssrf_and_traversal(mock_config):
    """TopicModelExporter blocks untrusted hosts, buckets, and LRO path traversal."""
    # pylint: disable-next=import-outside-toplevel
    from cxidk.workflow.insight_refinements.schemas.input import TopicRefinementConfig
    # pylint: disable-next=import-outside-toplevel
    from cxidk.workflow.insight_refinements.scripts.export_topic_model import (
        TopicModelExporter,
    )

    mock_config.topic_refinement = TopicRefinementConfig(issue_model_id="model-123")

    with (
        patch(
            "cxidk.workflow.insight_refinements.scripts.export_topic_model._get_oauth_token",
            return_value="tok",
        ) as mock_tok,
        patch("cxidk.workflow.insight_refinements.analysis.get_bq_client"),
        patch(
            "cxidk.workflow.insight_refinements.scripts.export_topic_model.get_storage_client"
        ),
        patch(
            "cxidk.workflow.insight_refinements.scripts.export_topic_model.requests"
        ) as mock_req,
    ):
        # Bypass Pydantic validator via attribute mutation to test defense-in-depth
        mock_config.ccai.insights_endpoint = "evil.example.com"
        with pytest.raises(ValueError, match="Untrusted insights_endpoint"):
            TopicModelExporter(mock_config, "valid-staging-bucket")
        mock_tok.assert_not_called()

        mock_config.ccai.insights_endpoint = None
        with pytest.raises(ValueError, match="Unsafe GCS bucket"):
            TopicModelExporter(mock_config, "../traversal-bucket")

        exporter = TopicModelExporter(mock_config, "valid-staging-bucket")
        with pytest.raises(ValueError, match="Unsafe operation"):
            # pylint: disable-next=protected-access
            exporter._wait_for_operation(
                {"name": "projects/p/locations/l/operations/../../evil"}
            )
        mock_req.get.assert_not_called()
        mock_req.post.assert_not_called()
