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

"""Read clients for CCAI Insights conversations, analyses, and statistics."""

from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from google.cloud import contact_center_insights_v1
from google.cloud.contact_center_insights_v1 import types

from cxidk.core import base


def _resolve_conversation_view(view: str) -> Any:
    """Resolves `'BASIC'` or `'FULL'` into `types.ConversationView`."""
    normalized = view.strip().upper()
    mapping: Dict[str, Any] = {
        "BASIC": types.ConversationView.BASIC,
        "FULL": types.ConversationView.FULL,
    }
    if normalized not in mapping:
        raise ValueError(
            f"Unsupported conversation view {view!r}. Choose 'BASIC' or 'FULL'."
        )
    return mapping[normalized]


class Conversations:
    """Read client for listing and fetching CCAI Insights conversations.

    Defaults `list()` to `ConversationView.BASIC` (metadata and summary without
    full turn-by-turn transcripts) to protect context budgets and minimize PII
    exposure, while `get()` defaults to `FULL` for single-conversation drill-down.
    """

    def __init__(
        self,
        project_id: str,
        location: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ) -> None:
        """Initializes the Conversations client."""
        self.project_id = project_id
        self.location = location
        self.auth = auth or base.Auth()
        self.config = config or base.Config(region=location)
        self.parent = f"projects/{self.project_id}/locations/{self.location}"
        self.client = contact_center_insights_v1.ContactCenterInsightsClient(
            credentials=self.auth.creds,
            client_options=self.config.set_insights_endpoint(),
        )

    def list(
        self,
        filter_str: Optional[str] = None,
        page_size: int = 25,
        page_token: Optional[str] = None,
        order_by: Optional[str] = None,
        view: str = "BASIC",
    ) -> Tuple[List[types.Conversation], str]:
        """Lists a single page of conversations.

        Args:
            filter_str: Optional CCAI Insights filter expression.
            page_size: Maximum conversations to return (1-100).
            page_token: Optional pagination token from a prior call.
            order_by: Optional sort specification (for example `create_time desc`).
            view: Conversation view level (`BASIC` or `FULL`).

        Returns:
            A `(conversations, next_page_token)` tuple.

        Raises:
            ValueError: If `page_size` is outside `[1, 100]` or `view` is invalid.
        """
        if page_size < 1 or page_size > 100:
            raise ValueError("page_size must be between 1 and 100.")
        view_enum = _resolve_conversation_view(view)
        req = types.ListConversationsRequest(
            parent=self.parent,
            filter=filter_str or "",
            page_size=page_size,
            page_token=page_token or "",
            order_by=order_by or "",
            view=view_enum,
        )
        pager = self.client.list_conversations(request=req)
        pages = getattr(pager, "pages", None)
        if pages is not None:
            first_page = next(iter(pages), None)
            if first_page is not None:
                return (
                    list(first_page.conversations),
                    str(first_page.next_page_token or ""),
                )
        return list(pager), str(getattr(pager, "next_page_token", "") or "")

    def get(
        self,
        conversation_id: str,
        view: str = "FULL",
    ) -> types.Conversation:
        """Fetches a single conversation by ID or full resource name.

        Args:
            conversation_id: Bare conversation ID or full `projects/...` name.
            view: Conversation view level (`FULL` or `BASIC`).

        Returns:
            The `types.Conversation` resource.

        Raises:
            ValueError: If `view` is unrecognized.
        """
        view_enum = _resolve_conversation_view(view)
        name = (
            conversation_id
            if conversation_id.startswith("projects/")
            else f"{self.parent}/conversations/{conversation_id}"
        )
        req = types.GetConversationRequest(name=name, view=view_enum)
        return self.client.get_conversation(request=req)


class Analyses:
    """Read client for listing and fetching conversation analyses."""

    def __init__(
        self,
        project_id: str,
        location: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ) -> None:
        """Initializes the Analyses client.

        Args:
            project_id: Google Cloud project ID.
            location: Google Cloud region (for example `us-central1`).
            auth: Optional `base.Auth` instance.
            config: Optional `base.Config` instance.
        """
        self.project_id = project_id
        self.location = location
        self.auth = auth or base.Auth()
        self.config = config or base.Config(region=location)
        self.parent = f"projects/{self.project_id}/locations/{self.location}"
        self.client = contact_center_insights_v1.ContactCenterInsightsClient(
            credentials=self.auth.creds,
            client_options=self.config.set_insights_endpoint(),
        )

    def _conversation_name(self, conversation_id: str) -> str:
        if conversation_id.startswith("projects/"):
            return conversation_id
        return f"{self.parent}/conversations/{conversation_id}"

    def list(
        self,
        conversation_id: str,
        page_size: int = 25,
        page_token: Optional[str] = None,
        filter_str: Optional[str] = None,
    ) -> Tuple[List[types.Analysis], str]:
        """Lists analyses for a conversation.

        Args:
            conversation_id: Bare conversation ID or full `projects/...` name.
            page_size: Maximum analyses to return (1-100).
            page_token: Optional pagination token from a prior call.
            filter_str: Optional CCAI Insights analysis filter expression.

        Returns:
            A `(analyses, next_page_token)` tuple.

        Raises:
            ValueError: If `page_size` is outside `[1, 100]`.
        """
        if page_size < 1 or page_size > 100:
            raise ValueError("page_size must be between 1 and 100.")
        req = types.ListAnalysesRequest(
            parent=self._conversation_name(conversation_id),
            page_size=page_size,
            page_token=page_token or "",
            filter=filter_str or "",
        )
        pager = self.client.list_analyses(request=req)
        pages = getattr(pager, "pages", None)
        if pages is not None:
            first_page = next(iter(pages), None)
            if first_page is not None:
                return (
                    list(first_page.analyses),
                    str(first_page.next_page_token or ""),
                )
        return list(pager), str(getattr(pager, "next_page_token", "") or "")

    def get(
        self,
        conversation_id: str,
        analysis_id: str,
    ) -> types.Analysis:
        """Fetches a specific analysis resource.

        Args:
            conversation_id: Bare conversation ID or full `projects/...` name.
            analysis_id: Bare analysis ID or full `projects/.../analyses/...` name.

        Returns:
            The `types.Analysis` resource.
        """
        conv_name = self._conversation_name(conversation_id)
        name = (
            analysis_id
            if analysis_id.startswith("projects/")
            else f"{conv_name}/analyses/{analysis_id}"
        )
        return self.client.get_analysis(
            request=types.GetAnalysisRequest(name=name)
        )


_GRANULARITY_MAP: Dict[str, Any] = {
    "NONE": types.QueryMetricsRequest.TimeGranularity.NONE,
    "DAILY": types.QueryMetricsRequest.TimeGranularity.DAILY,
    "DAY": types.QueryMetricsRequest.TimeGranularity.DAILY,
    "HOURLY": types.QueryMetricsRequest.TimeGranularity.HOURLY,
    "HOUR": types.QueryMetricsRequest.TimeGranularity.HOURLY,
    "PER_MINUTE": types.QueryMetricsRequest.TimeGranularity.PER_MINUTE,
    "PER_5_MINUTES": types.QueryMetricsRequest.TimeGranularity.PER_5_MINUTES,
    "MONTHLY": types.QueryMetricsRequest.TimeGranularity.MONTHLY,
    "MONTH": types.QueryMetricsRequest.TimeGranularity.MONTHLY,
}

_DIMENSION_MAP: Dict[str, Any] = {
    "ISSUE": types.Dimension.DimensionKey.ISSUE,
    "AGENT": types.Dimension.DimensionKey.AGENT,
    "AGENT_TEAM": types.Dimension.DimensionKey.AGENT_TEAM,
    "QA_QUESTION_ID": types.Dimension.DimensionKey.QA_QUESTION_ID,
    "QA_QUESTION_ANSWER_VALUE": types.Dimension.DimensionKey.QA_QUESTION_ANSWER_VALUE,
    "CONVERSATION_PROFILE_ID": types.Dimension.DimensionKey.CONVERSATION_PROFILE_ID,
}


class Stats:
    """Read client for aggregated CCAI Insights statistics and time-series metrics."""

    def __init__(
        self,
        project_id: str,
        location: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ) -> None:
        """Initializes the Stats client.

        Args:
            project_id: Google Cloud project ID.
            location: Google Cloud region (for example `us-central1`).
            auth: Optional `base.Auth` instance.
            config: Optional `base.Config` instance.
        """
        self.project_id = project_id
        self.location = location
        self.auth = auth or base.Auth()
        self.config = config or base.Config(region=location)
        self.parent = f"projects/{self.project_id}/locations/{self.location}"
        self.client = contact_center_insights_v1.ContactCenterInsightsClient(
            credentials=self.auth.creds,
            client_options=self.config.set_insights_endpoint(),
        )

    def calculate(
        self, filter_str: Optional[str] = None
    ) -> types.CalculateStatsResponse:
        """Calculates aggregate conversation counts, durations, and top issues.

        Args:
            filter_str: Optional CCAI Insights filter expression.

        Returns:
            `types.CalculateStatsResponse` containing aggregated statistics.
        """
        req = types.CalculateStatsRequest(
            location=self.parent,
            filter=filter_str or "",
        )
        return self.client.calculate_stats(request=req)

    def query_metrics(
        self,
        filter_str: str = "",
        time_granularity: str = "DAILY",
        dimensions: Optional[List[str]] = None,
    ) -> Any:
        """Queries time-series metrics sliced by optional dimensions.

        Args:
            filter_str: CCAI Insights filter expression (commonly time-bounded).
            time_granularity: Bucket size (`NONE`, `DAILY`, `HOURLY`,
                `PER_MINUTE`, `PER_5_MINUTES`, or `MONTHLY`).
            dimensions: Optional slice dimensions (`ISSUE`, `AGENT`,
                `AGENT_TEAM`, `QA_QUESTION_ID`, `QA_QUESTION_ANSWER_VALUE`,
                `CONVERSATION_PROFILE_ID`).

        Returns:
            Long-running operation or `QueryMetricsResponse` from the SDK.

        Raises:
            ValueError: If `time_granularity` or any `dimensions` entry is invalid.
        """
        gran_key = time_granularity.strip().upper()
        if gran_key not in _GRANULARITY_MAP:
            raise ValueError(
                f"Unsupported time_granularity {time_granularity!r}. "
                f"Choose from: {sorted(_GRANULARITY_MAP)}"
            )

        dim_objs: List[types.Dimension] = []
        for raw_dim in dimensions or []:
            dim_key = raw_dim.strip().upper()
            if dim_key not in _DIMENSION_MAP:
                raise ValueError(
                    f"Unsupported dimension {raw_dim!r}. "
                    f"Choose from: {sorted(_DIMENSION_MAP)}"
                )
            dim_objs.append(
                types.Dimension(dimension_key=_DIMENSION_MAP[dim_key])
            )

        req = types.QueryMetricsRequest(
            location=self.parent,
            filter=filter_str,
            time_granularity=_GRANULARITY_MAP[gran_key],
            dimensions=dim_objs,
        )
        return self.client.query_metrics(request=req)
