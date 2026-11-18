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

"""Unit tests for the ScorecardOptimizer question refinement workflow."""

from unittest.mock import MagicMock, patch

from cxidk.workflow.insight_refinements.optimization import (
    ScorecardOptimizer,
    OptimizedScorecard,
    VerificationResult,
)


@patch("cxidk.workflow.insight_refinements.optimization.genai.Client")
def test_optimize_item_success(mock_client):
    """Test that optimize_question calls the LLM and returns parsed response."""
    # Mock LLM response
    mock_response = MagicMock()
    mock_response.parsed = OptimizedScorecard(
        refined_question="Refined Q",
        refined_instructions="Refined Inst",
        refined_answers=["Yes", "No"],
        reasoning_log="Thinking...",
        edge_cases=["Case 1"],
    )
    mock_client.return_value.models.generate_content.return_value = mock_response

    optimizer = ScorecardOptimizer("p", "l")
    result = optimizer.optimize_question(
        question="Old Q",
        instructions="Old Inst",
        answers=["Yes", "No"],
        disagreement_cases=[
            {"turn": "T1", "human": "Yes", "ai": "No", "reason": "Bad logic"}
        ],
    )

    assert result.refined_question == "Refined Q"
    mock_client.return_value.models.generate_content.assert_called_once()


@patch("cxidk.workflow.insight_refinements.optimization.genai.Client")
def test_verify_optimization_failure(mock_client):
    """Test verification logic identifying a failure."""
    # Mock LLM response for verification
    mock_response = MagicMock()
    # The verification model returns a score that DISAGREES with human
    mock_response.parsed = VerificationResult(score="No", reason="Because X")
    mock_client.return_value.models.generate_content.return_value = mock_response

    optimizer = ScorecardOptimizer("p", "l")
    scorecard = OptimizedScorecard(
        refined_question="Q",
        refined_instructions="I",
        refined_answers=["Yes", "No"],
        reasoning_log="L",
        edge_cases=[],
    )

    # Evidence says Human="Yes", but Mock LLM says "No" -> Failure
    failures = optimizer.verify_optimization(
        scorecard, [{"turn": "T1", "human": "Yes", "ai": "No"}]
    )

    assert len(failures) == 1
    assert failures[0]["expected"] == "Yes"
    assert failures[0]["actual"] == "No"


def test_format_evidence_validation():
    """Test that invalid evidence is handled gracefully."""
    optimizer = ScorecardOptimizer("p", "l")
    # Missing 'human' field
    # This private helper is the unit under test.
    xml = optimizer._format_evidence([{"turn": "T", "ai": "No"}])  # pylint: disable=protected-access
    assert "<error>Invalid Evidence Data</error>" in xml
