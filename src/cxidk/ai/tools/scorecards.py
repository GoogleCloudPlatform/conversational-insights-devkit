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

"""Read-only QA scorecard inspection tools.

These tools are thin adapters over `cxidk.wrapper.insights.Scorecards`: they
validate caller input, resolve the execution context, delegate every API
interaction to the wrapper, and map its dataclasses onto the Pydantic output
schemas. No REST collection is touched from this module.
"""

import dataclasses
from typing import Any, Dict, Optional

from cxidk.core import context
from cxidk.core import errors
from cxidk.ai.tools import models
from cxidk.ai.tools import registry
from cxidk.ai.tools import validation
from cxidk.wrapper import insights


def _client(target: context.CxContext) -> insights.Scorecards:
    """Builds a regional `Scorecards` wrapper bound to `target`.

    Args:
        target: Resolved execution context.

    Returns:
        A `Scorecards` client sharing the context's credentials and config.
    """
    return insights.Scorecards(
        project_id=target.project_id,
        location=target.location,
        auth=target.auth,
        config=target.config,
    )


def _question_item(
    question: insights.QuestionInfo, include_tuning_metadata: bool
) -> models.QuestionItem:
    """Maps a wrapper `QuestionInfo` onto the `QuestionItem` schema.

    Args:
        question: Normalized question from the wrapper.
        include_tuning_metadata: Whether to keep `metrics` and
            `tuning_metadata` in the output.

    Returns:
        The validated `QuestionItem`.
    """
    data: Dict[str, Any] = dataclasses.asdict(question)
    if not include_tuning_metadata:
        data["metrics"] = None
        data["tuning_metadata"] = None
    return models.QuestionItem.model_validate(data)


@registry.cx_tool(
    name="insights_list_scorecards",
    title="List QA Scorecards",
    description=(
        "Lists QA scorecards in the target CCAI Insights project and location with "
        "display name, default flag, revision count, latest revision ID and state, "
        "and the number of questions in the latest revision. Set "
        "`include_question_counts=False` to skip per-scorecard question lookups on "
        "large inventories. Use `insights_get_scorecard` to read the questions."
    ),
    safety=registry.Safety.READ,
    idempotent=True,
    open_world=True,
    toolset="core",
    confirm=False,
    output_model=models.ScorecardListOutput,
)
def insights_list_scorecards(
    include_question_counts: bool = True,
    project_id: Optional[str] = None,
    location: Optional[str] = None,
    *,
    cx: Optional[context.CxContext] = None,
) -> models.ScorecardListOutput:
    """Lists QA scorecards with latest-revision summaries.

    Args:
        include_question_counts: Whether to count questions in each scorecard's
            latest revision (one extra API request per scorecard).
        project_id: Optional target GCP project ID override.
        location: Optional target GCP location override.
        cx: Optional execution `CxContext`.

    Returns:
        `ScorecardListOutput` with one `ScorecardListItem` per scorecard.

    Raises:
        errors.CxidkError: If the Insights API call fails.
    """
    target = context.CxContext.resolve(cx, project_id, location)
    with errors.translate_google_api_error():
        summaries = _client(target).list(
            include_question_counts=include_question_counts
        )

    items = [
        models.ScorecardListItem.model_validate(dataclasses.asdict(summary))
        for summary in summaries
    ]
    return models.ScorecardListOutput(
        project_id=target.project_id,
        location=target.location,
        scorecards=items,
        count=len(items),
    )


@registry.cx_tool(
    name="insights_get_scorecard",
    title="Get QA Scorecard Definition",
    description=(
        "Fetches one QA scorecard and the full question set of a revision: question "
        "body, answer instructions, tags, answer choices with scores, derived "
        "`max_score` and `weight_percent`, question type, and order. Omit "
        "`revision_id` (or pass 'latest') for the current revision; pass a bare "
        "revision ID from `insights_list_scorecard_revisions` to inspect an older one."
    ),
    safety=registry.Safety.READ,
    idempotent=True,
    open_world=True,
    toolset="core",
    confirm=False,
    output_model=models.ScorecardDetailOutput,
)
def insights_get_scorecard(
    scorecard_id: str,
    revision_id: Optional[str] = None,
    include_tuning_metadata: bool = False,
    project_id: Optional[str] = None,
    location: Optional[str] = None,
    *,
    cx: Optional[context.CxContext] = None,
) -> models.ScorecardDetailOutput:
    """Fetches a scorecard definition for its latest or an explicit revision.

    Args:
        scorecard_id: Bare QA scorecard ID.
        revision_id: Optional bare revision ID; None or `'latest'` resolves the
            current revision.
        include_tuning_metadata: Whether to include per-question tuning
            `metrics` and `tuning_metadata`.
        project_id: Optional target GCP project ID override.
        location: Optional target GCP location override.
        cx: Optional execution `CxContext`.

    Returns:
        `ScorecardDetailOutput` with the resolved revision and its questions.

    Raises:
        errors.InvalidArgumentError: If `scorecard_id` or `revision_id` is invalid.
        errors.NotFoundError: If the scorecard or explicit revision does not exist.
        errors.CxidkError: If the Insights API call fails.
    """
    clean_id = validation.validate_resource_id(scorecard_id, "scorecard_id")
    clean_revision = (
        validation.validate_resource_id(revision_id, "revision_id")
        if revision_id
        else None
    )
    target = context.CxContext.resolve(cx, project_id, location)
    with errors.translate_google_api_error():
        definition = _client(target).get(clean_id, revision_id=clean_revision)

    revision_item = (
        models.RevisionItem.model_validate(dataclasses.asdict(definition.revision))
        if definition.revision is not None
        else None
    )
    return models.ScorecardDetailOutput(
        project_id=target.project_id,
        location=target.location,
        scorecard=models.ScorecardItem.model_validate(
            dataclasses.asdict(definition.scorecard)
        ),
        revision=revision_item,
        revision_count=definition.revision_count,
        latest_revision_id=definition.latest_revision_id,
        questions=[
            _question_item(question, include_tuning_metadata)
            for question in definition.questions
        ],
        question_count=definition.question_count,
        total_max_score=definition.total_max_score,
    )


@registry.cx_tool(
    name="insights_list_scorecard_revisions",
    title="List QA Scorecard Revisions",
    description=(
        "Lists all revisions of a QA scorecard, newest first, with revision ID, full "
        "resource name, state (EDITABLE, TRAINING, READY, ...), aliases, and which "
        "revision is current. Pass a returned `revision_id` to "
        "`insights_get_scorecard` to inspect that revision's questions."
    ),
    safety=registry.Safety.READ,
    idempotent=True,
    open_world=True,
    toolset="core",
    confirm=False,
    output_model=models.ScorecardRevisionListOutput,
)
def insights_list_scorecard_revisions(
    scorecard_id: str,
    project_id: Optional[str] = None,
    location: Optional[str] = None,
    *,
    cx: Optional[context.CxContext] = None,
) -> models.ScorecardRevisionListOutput:
    """Lists the revisions of a QA scorecard, newest first.

    Args:
        scorecard_id: Bare QA scorecard ID.
        project_id: Optional target GCP project ID override.
        location: Optional target GCP location override.
        cx: Optional execution `CxContext`.

    Returns:
        `ScorecardRevisionListOutput` with `RevisionItem` entries.

    Raises:
        errors.InvalidArgumentError: If `scorecard_id` is invalid.
        errors.CxidkError: If the Insights API call fails.
    """
    clean_id = validation.validate_resource_id(scorecard_id, "scorecard_id")
    target = context.CxContext.resolve(cx, project_id, location)
    with errors.translate_google_api_error():
        revisions = _client(target).list_revisions(clean_id)

    items = [
        models.RevisionItem.model_validate(dataclasses.asdict(revision))
        for revision in revisions
    ]
    return models.ScorecardRevisionListOutput(
        project_id=target.project_id,
        location=target.location,
        scorecard_id=clean_id,
        revisions=items,
        count=len(items),
        latest_revision_id=next(
            (item.revision_id for item in items if item.is_latest), ""
        ),
    )
