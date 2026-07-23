# Copyright 2026 Google LLC
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

"""Unit tests for the ScorecardCopier workflow class."""

from unittest.mock import MagicMock
import pytest
from google.cloud.contact_center_insights_v1 import types
from pytest_mock import MockerFixture
from cxidk.workflow.config_copier import ScorecardCopier


@pytest.fixture
def mock_wrappers(mocker: MockerFixture) -> MagicMock:
    """Mocks insights.Scorecards and insights.ScorecardQuestions wrappers."""
    mock_scorecards_cls = mocker.patch(
        "cxidk.workflow.config_copier.insights.Scorecards", autospec=True
    )
    mock_questions_cls = mocker.patch(
        "cxidk.workflow.config_copier.insights.ScorecardQuestions", autospec=True
    )

    # Setup source scorecard return
    mock_source_scorecard = types.QaScorecard(
        name="projects/src-proj/locations/us/qaScorecards/sc-src",
        display_name="Original Name",
        description="Original Description",
    )
    mock_scorecards_cls.return_value.get_scorecard.return_value = mock_source_scorecard

    # Setup dest scorecard creation return
    mock_dest_scorecard = types.QaScorecard(
        name="projects/dest-proj/locations/us/qaScorecards/sc-dest",
        display_name="Copied Name",
        description="Original Description",
    )
    mock_scorecards_cls.return_value.create_scorecard.return_value = mock_dest_scorecard

    # Setup source questions pager return
    mock_question_1 = types.QaQuestion(
        name="projects/src-proj/locations/us/qaScorecards/sc-src/qaQuestions/q1",
        display_name="Q1",
        question_body="Body 1",
    )
    mock_question_2 = types.QaQuestion(
        name="projects/src-proj/locations/us/qaScorecards/sc-src/qaQuestions/q2",
        display_name="Q2",
        question_body="Body 2",
    )
    mock_questions_cls.return_value.list_questions.return_value = [
        mock_question_1,
        mock_question_2,
    ]

    return {
        "Scorecards": mock_scorecards_cls,
        "ScorecardQuestions": mock_questions_cls,
    }


def test_copier_init(mock_wrappers: MagicMock) -> None:
    """Test ScorecardCopier client initialization."""
    copier = ScorecardCopier(
        source_project_id="src-proj",
        source_location="us",
        dest_project_id="dest-proj",
        dest_location="us",
    )
    assert copier.source_project_id == "src-proj"
    assert copier.dest_project_id == "dest-proj"
    assert mock_wrappers["Scorecards"].call_count == 2


def test_copy_scorecard(mock_wrappers: MagicMock) -> None:
    """Test copying a full scorecard and its questions."""
    copier = ScorecardCopier(
        source_project_id="src-proj",
        source_location="us",
        dest_project_id="dest-proj",
        dest_location="us",
    )

    result = copier.copy_scorecard(
        scorecard_id="sc-src", new_display_name="Copied Name"
    )

    assert result["dest_scorecard_id"] == "sc-dest"
    assert result["copied_questions_count"] == 2

    # Verify clean scorecard payload creation
    mock_scorecards = mock_wrappers["Scorecards"].return_value
    mock_scorecards.get_scorecard.assert_called_once_with(scorecard_id="sc-src")
    create_call_args = mock_scorecards.create_scorecard.call_args[1]["qa_scorecard"]
    assert create_call_args.display_name == "Copied Name"
    assert create_call_args.description == "Original Description"
    assert not create_call_args.name  # Clean system property

    # Verify clean question payload creations
    mock_questions = mock_wrappers["ScorecardQuestions"].return_value
    mock_questions.list_questions.assert_called_once()
    assert mock_questions.create_question.call_count == 2
