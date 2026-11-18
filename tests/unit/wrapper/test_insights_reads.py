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

"""Unit tests for Phase 1 CCAI Insights read APIs and EvaluationReporter.format_report."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from google.cloud.contact_center_insights_v1 import types
import pytest

from cxidk.workflow.insight_refinements import evaluation
from cxidk.wrapper import insights


def test_conversations_list_and_get(
    mocker: MagicMock, mock_auth: MagicMock
) -> None:
    """Verifies `Conversations.list` (BASIC default) and `Conversations.get` (FULL default)."""
    mock_cls = mocker.patch(
        "cxidk.wrapper.insights.contact_center_insights_v1.ContactCenterInsightsClient"
    )
    sdk_client = mock_cls.return_value

    convo_proto = types.Conversation(name="projects/p1/locations/us-central1/conversations/c1")
    first_page = SimpleNamespace(
        conversations=[convo_proto],
        next_page_token="tok-2",
    )
    sdk_client.list_conversations.return_value = SimpleNamespace(pages=[first_page])
    sdk_client.get_conversation.return_value = convo_proto

    client = insights.Conversations("p1", "us-central1", auth=mock_auth)
    items, next_tok = client.list(filter_str='medium="CHAT"', page_size=10)
    assert len(items) == 1
    assert next_tok == "tok-2"

    sent_req = sdk_client.list_conversations.call_args.kwargs["request"]
    assert sent_req.view == types.ConversationView.BASIC
    assert sent_req.page_size == 10

    fetched = client.get("c1")
    assert fetched.name.endswith("/c1")
    get_req = sdk_client.get_conversation.call_args.kwargs["request"]
    assert get_req.view == types.ConversationView.FULL

    with pytest.raises(ValueError, match="page_size"):
        client.list(page_size=0)
    with pytest.raises(ValueError, match="Unsupported conversation view"):
        client.get("c1", view="UNKNOWN")


def test_analyses_list_and_get(
    mocker: MagicMock, mock_auth: MagicMock
) -> None:
    """Verifies `Analyses.list` and `Analyses.get` parent resolution."""
    mock_cls = mocker.patch(
        "cxidk.wrapper.insights.contact_center_insights_v1.ContactCenterInsightsClient"
    )
    sdk_client = mock_cls.return_value
    analysis_proto = types.Analysis(
        name="projects/p1/locations/us-central1/conversations/c1/analyses/a1"
    )
    first_page = SimpleNamespace(analyses=[analysis_proto], next_page_token="")
    sdk_client.list_analyses.return_value = SimpleNamespace(pages=[first_page])
    sdk_client.get_analysis.return_value = analysis_proto

    client = insights.Analyses("p1", "us-central1", auth=mock_auth)
    items, tok = client.list("c1", page_size=5)
    assert len(items) == 1
    assert tok == ""

    single = client.get("c1", "a1")
    assert single.name.endswith("/a1")

    with pytest.raises(ValueError, match="page_size"):
        client.list("c1", page_size=101)


def test_stats_calculate_and_query_metrics(
    mocker: MagicMock, mock_auth: MagicMock
) -> None:
    """Verifies `Stats.calculate` and `Stats.query_metrics` validation."""
    mock_cls = mocker.patch(
        "cxidk.wrapper.insights.contact_center_insights_v1.ContactCenterInsightsClient"
    )
    sdk_client = mock_cls.return_value
    sdk_client.calculate_stats.return_value = types.CalculateStatsResponse(
        conversation_count=42
    )
    sdk_client.query_metrics.return_value = {"name": "op-metrics"}

    client = insights.Stats("p1", "us-central1", auth=mock_auth)
    stats_resp = client.calculate(filter_str="latest_analysis:*")
    assert stats_resp.conversation_count == 42

    metrics_resp = client.query_metrics(
        filter_str="",
        time_granularity="DAILY",
        dimensions=["ISSUE", "AGENT_TEAM"],
    )
    assert metrics_resp == {"name": "op-metrics"}

    with pytest.raises(ValueError, match="Unsupported time_granularity"):
        client.query_metrics(time_granularity="YEARLY")
    with pytest.raises(ValueError, match="Unsupported dimension"):
        client.query_metrics(dimensions=["BOGUS_DIM"])


def test_evaluation_reporter_format_report() -> None:
    """Verifies `EvaluationReporter.format_report` returns a table string cleanly."""
    eval_items = [
        evaluation.QuestionEvaluation(
            question_id="q-1",
            question_text="Did the agent greet the caller?",
            golden_answer="yes",
            predicted_answer="yes",
        ),
        evaluation.QuestionEvaluation(
            question_id="q-1",
            question_text="Did the agent greet the caller?",
            golden_answer="no",
            predicted_answer="no",
        ),
    ]
    reporter = evaluation.EvaluationReporter({"conv-1": eval_items})
    report_text = reporter.format_report()
    assert "EVALUATION REPORT SUMMARY" in report_text
    assert "Did the agent greet the caller?" in report_text
    assert "100.00%" in report_text
