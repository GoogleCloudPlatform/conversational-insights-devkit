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

"""Unit tests for the scorecard `@cx_tool` adapters over `insights.Scorecards`."""

# pylint: disable=no-member  # pylint infers nested Pydantic model fields as FieldInfo

import inspect
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from cxidk import CxContext
from cxidk import errors
from cxidk.ai import tools
from cxidk.ai.mcp import server
from cxidk.ai.tools import models
from cxidk.ai.tools import scorecards as scorecard_tools
from cxidk.wrapper import insights

SC_NAME = "projects/demo-proj-01/locations/us-central1/qaScorecards/sc-1"
REV_NAME = f"{SC_NAME}/revisions/rev-2"

SCORECARD_INFO = insights.ScorecardInfo(
    scorecard_id="sc-1",
    name=SC_NAME,
    display_name="Support QA",
    description="Primary",
    is_default=True,
    source="",
    create_time="2025-01-01T00:00:00Z",
    update_time="2025-02-01T00:00:00Z",
)
SUMMARY = insights.ScorecardSummary(
    revision_count=2,
    latest_revision_id="rev-2",
    latest_revision_state="EDITABLE",
    question_count=1,
    **SCORECARD_INFO.__dict__,
)
REVISION = insights.RevisionInfo(
    revision_id="rev-2",
    name=REV_NAME,
    state="EDITABLE",
    alternate_ids=["latest"],
    is_latest=True,
    create_time="2025-02-01T00:00:00Z",
    snapshot_display_name="Support QA",
)
OLD_REVISION = insights.RevisionInfo(
    revision_id="rev-1",
    name=f"{SC_NAME}/revisions/rev-1",
    state="READY",
    alternate_ids=[],
    is_latest=False,
    create_time="2025-01-01T00:00:00Z",
    snapshot_display_name="Support QA v1",
)


def _question(question_id: str, body: str) -> insights.QuestionInfo:
    """Builds a `QuestionInfo` fixture with tuning data attached."""
    return insights.QuestionInfo(
        question_id=question_id,
        name=f"{REV_NAME}/qaQuestions/{question_id}",
        order=0,
        abbreviation="Q",
        question_body=body,
        answer_instructions="Pick yes when it happens.",
        question_type="CUSTOMIZABLE",
        predefined_question_config=None,
        tags=["BUSINESS"],
        tag_labels=["BUSINESS"],
        answer_choices=[
            insights.AnswerChoice(key="yes", value=True, value_type="boolean", score=2.0),
            insights.AnswerChoice(key="na", value=None, value_type="na", score=0.0),
        ],
        max_score=2.0,
        weight_percent=100.0,
        metrics={"accuracy": 0.9},
        tuning_metadata={"totalValidLabelCount": 5},
        create_time="2025-01-01T00:00:00Z",
        update_time="2025-01-01T00:00:00Z",
    )


def _definition(*questions: insights.QuestionInfo) -> insights.ScorecardDefinition:
    """Builds a `ScorecardDefinition` fixture for the latest revision."""
    return insights.ScorecardDefinition(
        scorecard=SCORECARD_INFO,
        revision=REVISION,
        revision_count=2,
        latest_revision_id="rev-2",
        questions=list(questions),
        question_count=len(questions),
        total_max_score=sum(q.max_score for q in questions),
    )


@pytest.fixture(name="wrapper")
def fixture_wrapper(mocker: MockerFixture) -> MagicMock:
    """Patches `insights.Scorecards` as seen by the tool module.

    Args:
        mocker: The pytest-mock fixture.

    Returns:
        The mocked `Scorecards` class (instance under `.return_value`).
    """
    return mocker.patch("cxidk.ai.tools.scorecards.insights.Scorecards", autospec=True)


def test_tools_are_registered_read_only() -> None:
    """All three scorecard tools are core, read-only, confirmation-free specs."""
    expected = {
        "insights_list_scorecards": models.ScorecardListOutput,
        "insights_get_scorecard": models.ScorecardDetailOutput,
        "insights_list_scorecard_revisions": models.ScorecardRevisionListOutput,
    }
    for name, output_model in expected.items():
        spec = tools.REGISTRY[name]
        assert spec.safety == tools.Safety.READ
        assert spec.toolset == "core"
        assert spec.confirm is False
        assert spec.idempotent is True
        assert spec.output_model is output_model
    read_only_names = {spec.name for spec in tools.list_specs(allow_writes=False)}
    assert set(expected) <= read_only_names


def test_tools_reject_traversal_ids_before_calling_wrapper(
    wrapper: MagicMock, demo_cx: CxContext
) -> None:
    """Malformed IDs are rejected before any wrapper client is constructed."""
    for bad_id in ("../settings", "sc/nested", "", " "):
        with pytest.raises(errors.InvalidArgumentError):
            tools.insights_get_scorecard(bad_id, cx=demo_cx)
        with pytest.raises(errors.InvalidArgumentError):
            tools.insights_list_scorecard_revisions(bad_id, cx=demo_cx)
    with pytest.raises(errors.InvalidArgumentError):
        tools.insights_get_scorecard("sc-1", revision_id="../latest", cx=demo_cx)
    wrapper.assert_not_called()


def test_list_maps_summaries_and_forwards_flag(
    wrapper: MagicMock, demo_cx: CxContext
) -> None:
    """`insights_list_scorecards` maps summaries 1:1 and forwards the counts flag."""
    wrapper.return_value.list.return_value = [SUMMARY]

    out = tools.insights_list_scorecards(include_question_counts=False, cx=demo_cx)

    wrapper.assert_called_once_with(
        project_id="demo-proj-01",
        location="us-central1",
        auth=demo_cx.auth,
        config=demo_cx.config,
    )
    wrapper.return_value.list.assert_called_once_with(include_question_counts=False)
    assert out.project_id == "demo-proj-01"
    assert out.count == 1
    assert out.truncated is False
    item = out.scorecards[0]
    assert isinstance(item, models.ScorecardListItem)
    assert item.model_dump() == SUMMARY.__dict__


def test_get_maps_definition_and_gates_tuning_metadata(
    wrapper: MagicMock, demo_cx: CxContext
) -> None:
    """`insights_get_scorecard` maps the definition and hides tuning data by default."""
    wrapper.return_value.get.return_value = _definition(_question("q-1", "Greeted?"))

    out = tools.insights_get_scorecard("sc-1", cx=demo_cx)

    wrapper.return_value.get.assert_called_once_with("sc-1", revision_id=None)
    assert out.scorecard.scorecard_id == "sc-1"
    assert out.revision is not None
    assert out.revision.is_latest is True
    assert out.revision_count == 2
    assert out.latest_revision_id == "rev-2"
    assert out.question_count == 1
    assert out.total_max_score == 2.0
    question = out.questions[0]
    assert question.question_body == "Greeted?"
    assert question.max_score == 2.0
    assert question.weight_percent == 100.0
    assert question.answer_choices[1].value_type == "na"
    assert question.metrics is None
    assert question.tuning_metadata is None

    detailed = tools.insights_get_scorecard(
        "sc-1", revision_id="rev-1", include_tuning_metadata=True, cx=demo_cx
    )
    wrapper.return_value.get.assert_called_with("sc-1", revision_id="rev-1")
    assert detailed.questions[0].metrics == {"accuracy": 0.9}
    assert detailed.questions[0].tuning_metadata == {"totalValidLabelCount": 5}


def test_get_handles_scorecard_without_revisions(
    wrapper: MagicMock, demo_cx: CxContext
) -> None:
    """A definition without a revision maps to `revision=None` and no questions."""
    wrapper.return_value.get.return_value = insights.ScorecardDefinition(
        scorecard=SCORECARD_INFO,
        revision=None,
        revision_count=0,
        latest_revision_id="",
        questions=[],
        question_count=0,
        total_max_score=0.0,
    )

    out = tools.insights_get_scorecard("sc-1", cx=demo_cx)

    assert out.revision is None
    assert out.questions == []
    assert out.question_count == 0


def test_list_revisions_maps_items_and_latest(
    wrapper: MagicMock, demo_cx: CxContext
) -> None:
    """`insights_list_scorecard_revisions` maps items and derives `latest_revision_id`."""
    wrapper.return_value.list_revisions.return_value = [REVISION, OLD_REVISION]

    out = tools.insights_list_scorecard_revisions("sc-1", cx=demo_cx)

    wrapper.return_value.list_revisions.assert_called_once_with("sc-1")
    assert out.scorecard_id == "sc-1"
    assert out.count == 2
    assert out.latest_revision_id == "rev-2"
    assert [r.revision_id for r in out.revisions] == ["rev-2", "rev-1"]
    assert [r.is_latest for r in out.revisions] == [True, False]


def test_result_budget_truncates_questions_and_flags() -> None:
    """The MCP result budget trims `questions` and sets `truncated`, keeping the true count."""
    questions = [_question(f"q-{i}", "x" * 400) for i in range(20)]
    definition = _definition(*questions)
    out = models.ScorecardDetailOutput(
        project_id="demo-proj-01",
        location="us-central1",
        scorecard=models.ScorecardItem.model_validate(SCORECARD_INFO.__dict__),
        revision=models.RevisionItem.model_validate(REVISION.__dict__),
        revision_count=2,
        latest_revision_id="rev-2",
        questions=[
            scorecard_tools._question_item(q, True)  # pylint: disable=protected-access
            for q in definition.questions
        ],
        question_count=definition.question_count,
        total_max_score=definition.total_max_score,
    )

    bounded = server._enforce_result_budget(out, 4000)  # pylint: disable=protected-access

    assert isinstance(bounded, models.ScorecardDetailOutput)
    assert bounded.truncated is True
    assert 1 <= len(bounded.questions) < 20
    assert bounded.question_count == 20
    assert len(bounded.model_dump_json()) <= 4000

    untouched = server._enforce_result_budget(out, 10**7)  # pylint: disable=protected-access
    assert untouched is out


def test_tool_layer_has_no_direct_rest_clients() -> None:
    """Guards the layering rule: tools only talk to `insights.Scorecards`."""
    source = inspect.getsource(scorecard_tools)
    for forbidden in (
        "QaScorecards",
        "ScorecardRevisions",
        "RevisionQuestions",
        "QaQuestionTags",
        "LegacyScorecards",
        "base.Request",
    ):
        assert forbidden not in source, f"{forbidden} must not be used by the tool layer"
    assert "insights.Scorecards(" in source
