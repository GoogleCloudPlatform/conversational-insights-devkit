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

"""Aggregate statistics and time-series metric tools for CCAI Insights."""

from typing import List, Optional

from cxidk.core import context
from cxidk.core import errors
from cxidk.core import serialize
from cxidk.ai.tools import models
from cxidk.ai.tools import registry
from cxidk.ai.tools import validation
from cxidk.wrapper import insights


def _make_stats_client(target: context.CxContext) -> insights.Stats:
    """Constructs a regional `insights.Stats` client from `target`."""
    return insights.Stats(
        project_id=target.project_id,
        location=target.location,
        auth=target.auth,
        config=target.config,
    )


@registry.cx_tool(
    name="insights_calculate_stats",
    title="Calculate CCAI Insights Statistics",
    description=(
        "Computes aggregate statistics across matching conversations—including "
        "conversation count, average duration, average turn count, and top issue "
        "distribution. Always call this before paging through hundreds of "
        "conversations or launching `insights_bulk_analyze`."
    ),
    safety=registry.Safety.READ,
    idempotent=True,
    open_world=True,
    toolset="core",
    confirm=False,
    output_model=models.StatsSummaryOutput,
)
def insights_calculate_stats(
    filter: str = "",  # pylint: disable=redefined-builtin
    project_id: Optional[str] = None,
    location: Optional[str] = None,
    *,
    cx: Optional[context.CxContext] = None,
) -> models.StatsSummaryOutput:
    """Calculates aggregate conversation statistics.

    Args:
        filter: Optional CCAI Insights filter expression.
        project_id: Optional target GCP project ID override.
        location: Optional target GCP location override.
        cx: Optional execution `CxContext`.

    Returns:
        `StatsSummaryOutput` containing serialized `CalculateStatsResponse` fields.

    Raises:
        errors.CxidkError: If filter validation or the Insights API call fails.
    """
    clean_filter = validation.validate_filter(filter)
    target = context.CxContext.resolve(cx, project_id, location)

    with errors.translate_google_api_error():
        response = _make_stats_client(target).calculate(
            filter_str=clean_filter or None
        )

    return models.StatsSummaryOutput(
        project_id=target.project_id,
        location=target.location,
        filter=clean_filter,
        stats=serialize.to_jsonable(response),
    )


@registry.cx_tool(
    name="insights_query_metrics",
    title="Query CCAI Insights Time-Series Metrics",
    description=(
        "Queries CCAI Insights time-series metrics at `NONE`, `HOURLY`, `DAILY`, "
        "or `MONTHLY` granularity, optionally sliced by dimensions (`ISSUE`, "
        "`AGENT`, `AGENT_TEAM`, `QA_QUESTION_ID`, `QA_QUESTION_ANSWER_VALUE`, "
        "`CONVERSATION_PROFILE_ID`)."
    ),
    safety=registry.Safety.READ,
    idempotent=True,
    open_world=True,
    toolset="core",
    confirm=False,
    output_model=models.MetricsQueryOutput,
)
def insights_query_metrics(
    filter: str = "",  # pylint: disable=redefined-builtin
    time_granularity: str = "DAILY",
    dimensions: Optional[List[str]] = None,
    project_id: Optional[str] = None,
    location: Optional[str] = None,
    *,
    cx: Optional[context.CxContext] = None,
) -> models.MetricsQueryOutput:
    """Queries Insights time-series metrics.

    Args:
        filter: Optional CCAI Insights filter expression.
        time_granularity: Bucket granularity (`NONE`, `HOURLY`, `DAILY`, `MONTHLY`).
        dimensions: Optional list of dimension keys (`ISSUE`, `AGENT`, etc.).
        project_id: Optional target GCP project ID override.
        location: Optional target GCP location override.
        cx: Optional execution `CxContext`.

    Returns:
        `MetricsQueryOutput` containing the serialized operation or metric slices.

    Raises:
        errors.InvalidArgumentError: If `time_granularity` or `dimensions` is invalid.
        errors.CxidkError: If the Insights API call fails.
    """
    clean_filter = validation.validate_filter(filter)
    target = context.CxContext.resolve(cx, project_id, location)
    dim_list = [str(d).strip().upper() for d in (dimensions or [])]

    with errors.translate_google_api_error():
        try:
            result = _make_stats_client(target).query_metrics(
                filter_str=clean_filter,
                time_granularity=time_granularity,
                dimensions=dim_list,
            )
        except ValueError as exc:
            raise errors.InvalidArgumentError(
                str(exc),
                hint=(
                    "Valid granularities: NONE, HOURLY, DAILY, MONTHLY. "
                    "Valid dimensions: ISSUE, AGENT, AGENT_TEAM, QA_QUESTION_ID, "
                    "QA_QUESTION_ANSWER_VALUE, CONVERSATION_PROFILE_ID."
                ),
            ) from exc

    return models.MetricsQueryOutput(
        project_id=target.project_id,
        location=target.location,
        time_granularity=time_granularity.strip().upper(),
        dimensions=dim_list,
        result=serialize.to_jsonable(result),
    )
