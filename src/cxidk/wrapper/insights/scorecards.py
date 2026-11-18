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

"""Typed, revision-aware QA scorecard views composed over the Insights REST collections.

The Insights API spreads one scorecard across three nested collections
(`qaScorecards`, `revisions`, `qaQuestions`) plus a sibling `qaQuestionTags`
collection. This module is the single place that stitches them together, so
Python SDK users, the MCP server, and ADK agents all observe identical data:
the same notion of "current revision", the same answer-choice flattening, and
the same derived weights.
"""

import dataclasses
import logging
from typing import Any, Dict, List, Optional

from cxidk.core import base
from cxidk.core import errors
from cxidk.wrapper.insights import config_resources

logger = logging.getLogger(__name__)

#: Built-in tag values are bare strings; custom tags are full resource names.
_CUSTOM_TAG_MARKER = "/"


@dataclasses.dataclass(frozen=True)
class AnswerChoice:
    """One selectable answer to a QA question.

    Attributes:
        key: Short identifier of the choice.
        value: Flattened `value` oneof: `str`, `float`, `bool`, or None for N/A.
        value_type: One of `'string'`, `'number'`, `'boolean'`, or `'na'`.
        score: Points awarded when this choice is selected.
    """

    key: str
    value: Any
    value_type: str
    score: float


@dataclasses.dataclass(frozen=True)
class QuestionInfo:  # pylint: disable=too-many-instance-attributes
    """Normalized `QaQuestion` definition.

    Attributes:
        question_id: Bare question ID.
        name: Full question resource name.
        order: Display order within the revision.
        abbreviation: Short question label.
        question_body: Question text evaluated by Quality AI.
        answer_instructions: Guidance describing how to pick an answer.
        question_type: `CUSTOMIZABLE`, `PREDEFINED`, or empty when unset.
        predefined_question_config: Predefined classifier config, if any.
        tags: Raw tags, mixing built-in names and `qaQuestionTags` names.
        tag_labels: Human-readable tags with custom tags resolved to names.
        answer_choices: Selectable answers with scores.
        max_score: Highest non-N/A choice score, i.e. the question's weight.
        weight_percent: `max_score` as a share of the revision total, or None.
        metrics: Tuned-model metrics when the revision has been tuned.
        tuning_metadata: Tuning metadata when the revision has been tuned.
        create_time: RFC 3339 creation timestamp.
        update_time: RFC 3339 last update timestamp.
    """

    question_id: str
    name: str
    order: int
    abbreviation: str
    question_body: str
    answer_instructions: str
    question_type: str
    predefined_question_config: Optional[Dict[str, Any]]
    tags: List[str]
    tag_labels: List[str]
    answer_choices: List[AnswerChoice]
    max_score: float
    weight_percent: Optional[float]
    metrics: Optional[Dict[str, Any]]
    tuning_metadata: Optional[Dict[str, Any]]
    create_time: str
    update_time: str


@dataclasses.dataclass(frozen=True)
class ScorecardInfo:
    """Identity and descriptive fields of a `QaScorecard`.

    Attributes:
        scorecard_id: Bare scorecard ID.
        name: Full scorecard resource name.
        display_name: User-specified display name.
        description: Scorecard intent description.
        is_default: Whether this is the project default scorecard.
        source: `QaScorecardSource` enum value when reported, else empty.
        create_time: RFC 3339 creation timestamp.
        update_time: RFC 3339 last update timestamp.
    """

    scorecard_id: str
    name: str
    display_name: str
    description: str
    is_default: bool
    source: str
    create_time: str
    update_time: str


@dataclasses.dataclass(frozen=True)
class ScorecardSummary(ScorecardInfo):
    """Scorecard list entry enriched with latest-revision facts.

    Attributes:
        revision_count: Number of revisions on the scorecard.
        latest_revision_id: Bare ID of the current revision, or empty.
        latest_revision_state: `State` of the current revision, or empty.
        question_count: Questions in the current revision, or None when
            counts were not requested.
    """

    revision_count: int
    latest_revision_id: str
    latest_revision_state: str
    question_count: Optional[int]


@dataclasses.dataclass(frozen=True)
class RevisionInfo:
    """Normalized `QaScorecardRevision`.

    Attributes:
        revision_id: Bare revision ID.
        name: Full revision resource name.
        state: Revision `State` (`EDITABLE`, `TRAINING`, `READY`, ...).
        alternate_ids: Aliases the API attaches, such as `latest`.
        is_latest: True for the current revision.
        create_time: RFC 3339 creation timestamp.
        snapshot_display_name: Scorecard display name captured in the snapshot.
    """

    revision_id: str
    name: str
    state: str
    alternate_ids: List[str]
    is_latest: bool
    create_time: str
    snapshot_display_name: str


@dataclasses.dataclass(frozen=True)
class ScorecardDefinition:
    """A scorecard plus the full question set of one resolved revision.

    Attributes:
        scorecard: Scorecard identity and description.
        revision: The resolved revision, or None when none exist.
        revision_count: Total revisions on the scorecard.
        latest_revision_id: Bare ID of the current revision, or empty.
        questions: Questions sorted by `(order, question_id)`.
        question_count: Number of questions in `questions`.
        total_max_score: Sum of `max_score` across `questions`.
    """

    scorecard: ScorecardInfo
    revision: Optional[RevisionInfo]
    revision_count: int
    latest_revision_id: str
    questions: List[QuestionInfo]
    question_count: int
    total_max_score: float


def _resource_id(resource_name: str) -> str:
    """Extracts the trailing bare ID from a full resource name.

    Args:
        resource_name: A full resource name, or an empty string.

    Returns:
        The final path segment, or an empty string.
    """
    return resource_name.rsplit("/", 1)[-1] if resource_name else ""


def _answer_choice(raw: Dict[str, Any]) -> AnswerChoice:
    """Flattens the `value` oneof of an API `AnswerChoice`.

    Args:
        raw: Answer choice dictionary as returned by the API.

    Returns:
        The normalized `AnswerChoice`.
    """
    value: Any
    if raw.get("naValue"):
        value, value_type = None, "na"
    elif "boolValue" in raw:
        value, value_type = bool(raw["boolValue"]), "boolean"
    elif "numValue" in raw:
        value, value_type = raw["numValue"], "number"
    else:
        value, value_type = raw.get("strValue", ""), "string"
    return AnswerChoice(
        key=str(raw.get("key", "")),
        value=value,
        value_type=value_type,
        score=float(raw.get("score") or 0.0),
    )


def _tag_label(tag: str, tag_names: Dict[str, str]) -> str:
    """Resolves one tag value to a human-readable label.

    Args:
        tag: A built-in tag name or a `qaQuestionTags` resource name.
        tag_names: Map of custom tag resource names to display names.

    Returns:
        Built-in tags unchanged; custom tags as their display name, falling
        back to the bare tag ID when unresolved.
    """
    if _CUSTOM_TAG_MARKER not in tag:
        return tag
    return tag_names.get(tag) or _resource_id(tag)


def _question(
    raw: Dict[str, Any],
    tag_names: Dict[str, str],
    weight_percent: Optional[float] = None,
) -> QuestionInfo:
    """Builds a `QuestionInfo` from an API `QaQuestion` dictionary.

    Args:
        raw: Question dictionary as returned by the API.
        tag_names: Map of custom tag resource names to display names.
        weight_percent: Pre-computed share of the revision total, if known.

    Returns:
        The normalized `QuestionInfo`.
    """
    choices = [_answer_choice(c) for c in raw.get("answerChoices") or []]
    scored = [c.score for c in choices if c.value_type != "na"]
    tags = [str(tag) for tag in raw.get("tags") or []]
    return QuestionInfo(
        question_id=_resource_id(raw.get("name", "")),
        name=raw.get("name", ""),
        order=int(raw.get("order") or 0),
        abbreviation=raw.get("abbreviation", ""),
        question_body=raw.get("questionBody", ""),
        answer_instructions=raw.get("answerInstructions", ""),
        question_type=raw.get("questionType", ""),
        predefined_question_config=raw.get("predefinedQuestionConfig"),
        tags=tags,
        tag_labels=[_tag_label(tag, tag_names) for tag in tags],
        answer_choices=choices,
        max_score=max(scored) if scored else 0.0,
        weight_percent=weight_percent,
        metrics=raw.get("metrics"),
        tuning_metadata=raw.get("tuningMetadata"),
        create_time=raw.get("createTime", ""),
        update_time=raw.get("updateTime", ""),
    )


def _build_questions(
    raw_questions: List[Dict[str, Any]], tag_names: Dict[str, str]
) -> List[QuestionInfo]:
    """Normalizes, orders, and weights the questions of one revision.

    Args:
        raw_questions: Question dictionaries as returned by the API.
        tag_names: Map of custom tag resource names to display names.

    Returns:
        Questions sorted by `(order, question_id)` with `weight_percent` set
        relative to the revision's total attainable score.
    """
    questions = sorted(
        (_question(raw, tag_names) for raw in raw_questions),
        key=lambda q: (q.order, q.question_id),
    )
    total = sum(q.max_score for q in questions)
    if not total:
        return questions
    return [
        dataclasses.replace(
            q, weight_percent=round(q.max_score / total * 100, 2)
        )
        for q in questions
    ]


def _scorecard_info(raw: Dict[str, Any]) -> ScorecardInfo:
    """Builds a `ScorecardInfo` from an API `QaScorecard` dictionary.

    Args:
        raw: Scorecard dictionary as returned by the API.

    Returns:
        The normalized `ScorecardInfo`.
    """
    return ScorecardInfo(
        scorecard_id=_resource_id(raw.get("name", "")),
        name=raw.get("name", ""),
        display_name=raw.get("displayName", ""),
        description=raw.get("description", ""),
        is_default=bool(raw.get("isDefault", False)),
        source=raw.get("source", ""),
        create_time=raw.get("createTime", ""),
        update_time=raw.get("updateTime", ""),
    )


def _revision_info(raw: Dict[str, Any], latest_name: str) -> RevisionInfo:
    """Builds a `RevisionInfo` from an API `QaScorecardRevision` dictionary.

    Args:
        raw: Revision dictionary as returned by the API.
        latest_name: Full resource name of the current revision, or empty.

    Returns:
        The normalized `RevisionInfo`.
    """
    name = raw.get("name", "")
    snapshot = raw.get("snapshot") or {}
    return RevisionInfo(
        revision_id=_resource_id(name),
        name=name,
        state=raw.get("state", ""),
        alternate_ids=[str(alias) for alias in raw.get("alternateIds") or []],
        is_latest=bool(name) and name == latest_name,
        create_time=raw.get("createTime", ""),
        snapshot_display_name=snapshot.get("displayName", ""),
    )


def _summary(
    raw: Dict[str, Any],
    revisions: List[Dict[str, Any]],
    latest: Optional[Dict[str, Any]],
    question_count: Optional[int],
) -> ScorecardSummary:
    """Builds a `ScorecardSummary` from a scorecard and its revisions.

    Args:
        raw: Scorecard dictionary as returned by the API.
        revisions: Every revision of the scorecard.
        latest: The current revision, or None.
        question_count: Question count of the current revision, or None.

    Returns:
        The enriched `ScorecardSummary`.
    """
    info = _scorecard_info(raw)
    return ScorecardSummary(
        **dataclasses.asdict(info),
        revision_count=len(revisions),
        latest_revision_id=_resource_id(latest.get("name", "")) if latest else "",
        latest_revision_state=latest.get("state", "") if latest else "",
        question_count=question_count,
    )


class Scorecards:
    """QA scorecards, revisions, and questions as typed, revision-aware views.

    Composes the REST collections (`QaScorecards`, `ScorecardRevisions`,
    `RevisionQuestions`, `QaQuestionTags`) behind one client. Read operations
    ship first; write operations (create, new revision, deploy, tune) are
    intended to land on this same class. Raw API dictionaries remain reachable
    through `collection` for callers that need API-shaped payloads.

    Attributes:
        project_id: The Google Cloud project ID.
        location: The Google Cloud location.
        auth: The authentication object shared by every child collection.
        config: The configuration object shared by every child collection.
        collection: The underlying `QaScorecards` REST collection.
    """

    def __init__(
        self,
        project_id: str,
        location: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ) -> None:
        """Initializes the scorecards client.

        Args:
            project_id: The Google Cloud project ID.
            location: The Google Cloud location. This drives both the resource
                parent path and the regional endpoint, so the two cannot drift.
            auth: An optional, pre-configured authentication object.
            config: An optional, pre-configured configuration object.
        """
        self.project_id = project_id
        self.location = location
        self.auth = auth or base.Auth()
        self.config = config or base.Config(region=location)
        self.collection = config_resources.QaScorecards(
            project_id, location, auth=self.auth, config=self.config
        )

    def _revisions(self, scorecard_id: str) -> config_resources.ScorecardRevisions:
        """Builds the revisions collection for one scorecard.

        Args:
            scorecard_id: The bare ID of the parent scorecard.

        Returns:
            A `ScorecardRevisions` client sharing this client's credentials.
        """
        return config_resources.ScorecardRevisions(
            self.project_id,
            self.location,
            scorecard_id,
            auth=self.auth,
            config=self.config,
        )

    def _questions(
        self, scorecard_id: str, revision_id: str
    ) -> config_resources.RevisionQuestions:
        """Builds the questions collection for one scorecard revision.

        Args:
            scorecard_id: The bare ID of the parent scorecard.
            revision_id: The bare ID of the parent revision.

        Returns:
            A `RevisionQuestions` client sharing this client's credentials.
        """
        return config_resources.RevisionQuestions(
            self.project_id,
            self.location,
            scorecard_id,
            revision_id,
            auth=self.auth,
            config=self.config,
        )

    def _tags(self) -> config_resources.QaQuestionTags:
        """Builds the custom question tags collection.

        Returns:
            A `QaQuestionTags` client sharing this client's credentials.
        """
        return config_resources.QaQuestionTags(
            self.project_id, self.location, auth=self.auth, config=self.config
        )

    def list(self, include_question_counts: bool = True) -> List[ScorecardSummary]:
        """Lists scorecards with revision and question facts.

        Each scorecard costs one `revisions` list request, plus one
        `qaQuestions` list request when `include_question_counts` is True.

        Args:
            include_question_counts: Whether to count the questions of each
                scorecard's current revision.

        Returns:
            One `ScorecardSummary` per scorecard, in API order.
        """
        summaries: List[ScorecardSummary] = []
        for raw in self.collection.list_by_source():
            scorecard_id = _resource_id(raw.get("name", ""))
            revisions = self._revisions(scorecard_id).list()
            latest = config_resources.ScorecardRevisions.pick_latest(revisions)
            question_count: Optional[int] = None
            if include_question_counts:
                question_count = 0
                if latest:
                    revision_id = _resource_id(latest.get("name", ""))
                    question_count = len(
                        self._questions(scorecard_id, revision_id).list()
                    )
            summaries.append(_summary(raw, revisions, latest, question_count))
        return summaries

    def list_revisions(self, scorecard_id: str) -> List[RevisionInfo]:
        """Lists the revisions of one scorecard, newest first.

        Args:
            scorecard_id: The bare ID of the scorecard.

        Returns:
            `RevisionInfo` items sorted by `create_time` descending, with the
            current revision flagged through `is_latest`.
        """
        revisions = self._revisions(scorecard_id).list()
        latest = config_resources.ScorecardRevisions.pick_latest(revisions)
        latest_name = latest.get("name", "") if latest else ""
        return sorted(
            (_revision_info(raw, latest_name) for raw in revisions),
            key=lambda item: item.create_time,
            reverse=True,
        )

    def get(
        self,
        scorecard_id: str,
        revision_id: Optional[str] = None,
        resolve_tags: bool = True,
    ) -> ScorecardDefinition:
        """Fetches a scorecard and the questions of one of its revisions.

        Args:
            scorecard_id: The bare ID of the scorecard.
            revision_id: The bare ID of the revision to inspect. None or
                `'latest'` resolves the current revision.
            resolve_tags: Whether to look up display names for custom tags.
                Resolution is best-effort and never fails the read.

        Returns:
            The `ScorecardDefinition` for the resolved revision. When the
            scorecard has no revisions, `revision` is None and `questions` is
            empty.

        Raises:
            errors.NotFoundError: If the scorecard or the explicit revision
                does not exist.
        """
        raw_scorecard = self.collection.get(scorecard_id)
        revisions_client = self._revisions(scorecard_id)
        revisions = revisions_client.list()
        latest = config_resources.ScorecardRevisions.pick_latest(revisions)
        latest_name = latest.get("name", "") if latest else ""

        wants_latest = revision_id in (
            None,
            config_resources.ScorecardRevisions.LATEST_ALIAS,
        )
        if wants_latest:
            revision = latest
        else:
            revision = next(
                (
                    raw
                    for raw in revisions
                    if _resource_id(raw.get("name", "")) == revision_id
                ),
                None,
            ) or revisions_client.get(str(revision_id))

        raw_questions: List[Dict[str, Any]] = []
        if revision:
            raw_questions = self._questions(
                scorecard_id, _resource_id(revision.get("name", ""))
            ).list()

        tag_names = self._tag_names(raw_questions) if resolve_tags else {}
        questions = _build_questions(raw_questions, tag_names)
        return ScorecardDefinition(
            scorecard=_scorecard_info(raw_scorecard),
            revision=_revision_info(revision, latest_name) if revision else None,
            revision_count=len(revisions),
            latest_revision_id=_resource_id(latest_name),
            questions=questions,
            question_count=len(questions),
            total_max_score=sum(q.max_score for q in questions),
        )

    def _tag_names(self, raw_questions: List[Dict[str, Any]]) -> Dict[str, str]:
        """Maps custom tag resource names to display names, best-effort.

        The lookup is skipped entirely when no question references a custom
        tag, and a failed lookup degrades to bare tag IDs rather than failing
        a read that is otherwise complete.

        Args:
            raw_questions: Question dictionaries as returned by the API.

        Returns:
            Map of `qaQuestionTags` resource names to display names.
        """
        if not any(
            _CUSTOM_TAG_MARKER in str(tag)
            for raw in raw_questions
            for tag in raw.get("tags") or []
        ):
            return {}
        try:
            tags = self._tags().list()
        except errors.CxidkError as exc:
            logger.warning(
                "Could not resolve custom QA question tags (%s); "
                "falling back to bare tag IDs.",
                exc.code,
            )
            return {}
        return {
            str(tag["name"]): str(tag.get("displayName", ""))
            for tag in tags
            if tag.get("name")
        }
