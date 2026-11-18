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

"""Unit tests for the `insights.Scorecards` facade and its REST composition.

`base.Request.make` is replaced with an endpoint router so the real
`ConfigCollection` URL building is exercised end to end.
"""

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from cxidk.core import errors
from cxidk.wrapper import insights
from cxidk.wrapper.insights import config_resources

PROJECT = "demo-proj-01"
LOCATION = "us-central1"
PARENT = f"projects/{PROJECT}/locations/{LOCATION}"
SC_A_NAME = f"{PARENT}/qaScorecards/sc-a"
SC_B_NAME = f"{PARENT}/qaScorecards/sc-b"
REV_OLD_NAME = f"{SC_A_NAME}/revisions/rev-1"
REV_LATEST_NAME = f"{SC_A_NAME}/revisions/rev-2"
TAG_NAME = f"{PARENT}/qaQuestionTags/tag-empathy"

SC_A = {
    "name": SC_A_NAME,
    "displayName": "Support QA",
    "description": "Primary scorecard",
    "isDefault": True,
    "createTime": "2025-01-01T00:00:00Z",
    "updateTime": "2025-02-01T00:00:00Z",
}
SC_B = {"name": SC_B_NAME, "displayName": "Empty scorecard"}
REV_OLD = {
    "name": REV_OLD_NAME,
    "state": "READY",
    "createTime": "2025-01-01T00:00:00Z",
    "snapshot": {"displayName": "Support QA v1"},
}
REV_LATEST = {
    "name": REV_LATEST_NAME,
    "state": "EDITABLE",
    "alternateIds": ["latest"],
    "createTime": "2025-02-01T00:00:00Z",
    "snapshot": {"displayName": "Support QA"},
}
Q_GREETING = {
    "name": f"{REV_LATEST_NAME}/qaQuestions/q-greet",
    "order": 0,
    "abbreviation": "Greet",
    "questionBody": "Did the agent greet the customer?",
    "answerInstructions": "Yes when a greeting occurs in the first turn.",
    "questionType": "CUSTOMIZABLE",
    "tags": ["BUSINESS", TAG_NAME],
    "answerChoices": [
        {"key": "yes", "boolValue": True, "score": 2},
        {"key": "no", "boolValue": False, "score": 0},
        {"key": "na", "naValue": True, "score": 99},
    ],
    "metrics": {"accuracy": 0.9},
    "tuningMetadata": {"totalValidLabelCount": 12},
}
Q_RESOLUTION = {
    "name": f"{REV_LATEST_NAME}/qaQuestions/q-resolve",
    "order": 1,
    "questionBody": "Was the issue resolved?",
    "tags": ["CUSTOMER"],
    "answerChoices": [
        {"key": "full", "strValue": "Fully", "score": 6},
        {"key": "partial", "numValue": 0.5, "score": 3},
        {"key": "none", "strValue": "Not at all"},
    ],
}
Q_OLD = {
    "name": f"{REV_OLD_NAME}/qaQuestions/q-old",
    "order": 0,
    "questionBody": "Legacy question",
    "answerChoices": [{"key": "yes", "boolValue": True, "score": 1}],
}


def _routes() -> Dict[str, Any]:
    """Returns the default endpoint -> payload routing table."""
    return {
        f"{PARENT}/qaScorecards": {"qaScorecards": [SC_A, SC_B]},
        SC_A_NAME: SC_A,
        SC_B_NAME: SC_B,
        f"{SC_A_NAME}/revisions": {"qaScorecardRevisions": [REV_OLD, REV_LATEST]},
        f"{SC_B_NAME}/revisions": {},
        f"{REV_LATEST_NAME}/qaQuestions": {
            "qaQuestions": [Q_RESOLUTION, Q_GREETING]
        },
        f"{REV_OLD_NAME}/qaQuestions": {"qaQuestions": [Q_OLD]},
        f"{PARENT}/qaQuestionTags": {
            "qaQuestionTags": [{"name": TAG_NAME, "displayName": "Empathy"}]
        },
    }


@pytest.fixture(name="router")
def fixture_router(mocker: MockerFixture) -> MagicMock:
    """Routes `base.Request.make` calls by endpoint and records them.

    Args:
        mocker: The pytest-mock fixture.

    Returns:
        The patched `make` mock; `routes` holds the editable routing table.
    """
    routes = _routes()

    def _make(
        _self: Any,
        endpoint: str,
        method: str,
        payload: Optional[Dict[str, Any]],
        **_kwargs: Any,
    ) -> Dict[str, Any]:
        del method, payload
        if endpoint not in routes:
            raise errors.NotFoundError(f"GET {endpoint} failed with HTTP 404")
        response = routes[endpoint]
        if isinstance(response, Exception):
            raise response
        return dict(response)

    make = mocker.patch("cxidk.core.base.Request.make", autospec=True)
    make.side_effect = _make
    make.routes = routes
    return make


def _client(mock_auth: MagicMock) -> insights.Scorecards:
    """Builds a `Scorecards` client with mocked credentials."""
    return insights.Scorecards(PROJECT, LOCATION, auth=mock_auth)


def _endpoints(router: MagicMock) -> List[str]:
    """Returns the endpoints requested so far, in order."""
    return [
        call.kwargs["endpoint"] if "endpoint" in call.kwargs else call.args[1]
        for call in router.call_args_list
    ]


def test_pick_latest_prefers_alias_then_create_time() -> None:
    """`pick_latest` honours the `latest` alias and falls back to `createTime`."""
    pick = config_resources.ScorecardRevisions.pick_latest
    assert pick([REV_OLD, REV_LATEST]) is REV_LATEST
    assert pick([REV_LATEST, REV_OLD]) is REV_LATEST

    newest_unaliased = {"name": "x/revisions/rev-9", "createTime": "2026-01-01T00:00:00Z"}
    assert pick([REV_OLD, newest_unaliased]) is newest_unaliased
    assert pick([]) is None


def test_list_enriches_counts_and_latest(
    router: MagicMock, mock_auth: MagicMock
) -> None:
    """`list()` reports revision facts and question counts per scorecard."""
    summaries = _client(mock_auth).list()

    assert [s.scorecard_id for s in summaries] == ["sc-a", "sc-b"]
    first = summaries[0]
    second = summaries[1]
    assert isinstance(first, insights.ScorecardSummary)
    assert first.display_name == "Support QA"
    assert first.is_default is True
    assert first.revision_count == 2
    assert first.latest_revision_id == "rev-2"
    assert first.latest_revision_state == "EDITABLE"
    assert first.question_count == 2
    assert second.revision_count == 0
    assert second.latest_revision_id == ""
    assert second.question_count == 0

    assert f"{REV_LATEST_NAME}/qaQuestions" in _endpoints(router)
    assert f"{REV_OLD_NAME}/qaQuestions" not in _endpoints(router)


def test_list_can_skip_question_counts(
    router: MagicMock, mock_auth: MagicMock
) -> None:
    """`include_question_counts=False` avoids every `qaQuestions` request."""
    summaries = _client(mock_auth).list(include_question_counts=False)

    assert all(s.question_count is None for s in summaries)
    assert not any(ep.endswith("/qaQuestions") for ep in _endpoints(router))
    assert summaries[0].latest_revision_id == "rev-2"


@pytest.mark.usefixtures("router")
def test_get_latest_normalizes_questions(mock_auth: MagicMock) -> None:
    """`get()` resolves the latest revision and normalizes question data."""
    definition = _client(mock_auth).get("sc-a")

    assert definition.scorecard.scorecard_id == "sc-a"
    assert definition.scorecard.is_default is True
    assert definition.revision is not None
    assert definition.revision.revision_id == "rev-2"
    assert definition.revision.is_latest is True
    assert definition.revision.alternate_ids == ["latest"]
    assert definition.revision.snapshot_display_name == "Support QA"
    assert definition.revision_count == 2
    assert definition.latest_revision_id == "rev-2"
    assert definition.question_count == 2
    assert definition.total_max_score == 8.0

    assert [q.question_id for q in definition.questions] == ["q-greet", "q-resolve"]
    greet = definition.questions[0]
    resolve = definition.questions[1]
    assert greet.max_score == 2.0  # N/A score of 99 must be ignored
    assert greet.weight_percent == 25.0
    assert resolve.max_score == 6.0
    assert resolve.weight_percent == 75.0
    assert greet.tags == ["BUSINESS", TAG_NAME]
    assert greet.tag_labels == ["BUSINESS", "Empathy"]
    assert greet.metrics == {"accuracy": 0.9}
    assert greet.tuning_metadata == {"totalValidLabelCount": 12}

    choices = {c.key: c for c in greet.answer_choices}
    assert (choices["yes"].value, choices["yes"].value_type) == (True, "boolean")
    assert (choices["na"].value, choices["na"].value_type) == (None, "na")
    resolve_choices = {c.key: c for c in resolve.answer_choices}
    assert resolve_choices["full"].value_type == "string"
    assert (resolve_choices["partial"].value, resolve_choices["partial"].value_type) == (
        0.5,
        "number",
    )
    assert resolve_choices["none"].score == 0.0


def test_get_explicit_and_alias_revision(
    router: MagicMock, mock_auth: MagicMock
) -> None:
    """Explicit revision IDs resolve historical questions; `latest` is the default."""
    client = _client(mock_auth)

    old = client.get("sc-a", revision_id="rev-1")
    assert old.revision is not None
    assert old.revision.revision_id == "rev-1"
    assert old.revision.is_latest is False
    assert old.latest_revision_id == "rev-2"
    assert [q.question_id for q in old.questions] == ["q-old"]
    assert old.total_max_score == 1.0
    assert old.questions[0].weight_percent == 100.0

    aliased = client.get("sc-a", revision_id="latest")
    assert aliased.revision is not None
    assert aliased.revision.revision_id == "rev-2"
    assert REV_OLD_NAME not in _endpoints(router)  # no stray single-revision GET


def test_get_unknown_revision_raises_not_found(
    router: MagicMock, mock_auth: MagicMock
) -> None:
    """A revision absent from the list falls through to a GET that 404s."""
    with pytest.raises(errors.NotFoundError):
        _client(mock_auth).get("sc-a", revision_id="nope")
    assert f"{SC_A_NAME}/revisions/nope" in _endpoints(router)


def test_get_without_revisions(router: MagicMock, mock_auth: MagicMock) -> None:
    """A scorecard with no revisions yields an empty definition."""
    definition = _client(mock_auth).get("sc-b")

    assert definition.revision is None
    assert definition.revision_count == 0
    assert definition.latest_revision_id == ""
    assert not definition.questions
    assert definition.question_count == 0
    assert definition.total_max_score == 0.0
    assert not any(ep.endswith("/qaQuestions") for ep in _endpoints(router))


def test_tag_resolution_is_best_effort(
    router: MagicMock, mock_auth: MagicMock
) -> None:
    """Tag lookups are skipped without custom tags and never fail the read."""
    client = _client(mock_auth)

    client.get("sc-a", revision_id="rev-1")  # Q_OLD has no tags at all
    assert f"{PARENT}/qaQuestionTags" not in _endpoints(router)

    router.routes[f"{PARENT}/qaQuestionTags"] = errors.PermissionDeniedError("denied")
    definition = client.get("sc-a")
    assert definition.questions[0].tag_labels == ["BUSINESS", "tag-empathy"]

    unresolved = client.get("sc-a", resolve_tags=False)
    assert unresolved.questions[0].tag_labels == ["BUSINESS", "tag-empathy"]


@pytest.mark.usefixtures("router")
def test_list_revisions_newest_first_with_is_latest(mock_auth: MagicMock) -> None:
    """`list_revisions()` orders newest first and flags the current revision."""
    revisions = _client(mock_auth).list_revisions("sc-a")

    assert [r.revision_id for r in revisions] == ["rev-2", "rev-1"]
    assert [r.is_latest for r in revisions] == [True, False]
    assert revisions[0].state == "EDITABLE"
    assert revisions[1].snapshot_display_name == "Support QA v1"
    assert revisions[0].name == REV_LATEST_NAME

    assert _client(mock_auth).list_revisions("sc-b") == []
