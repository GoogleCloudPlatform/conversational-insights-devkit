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

"""Configuration resource collections and QA scorecard clients for CCAI Insights."""

import logging
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from google.cloud import contact_center_insights_v1
from google.cloud.contact_center_insights_v1 import types

from cxidk.core import base
from cxidk.wrapper.insights._enums import _ISSUE_MODEL_DEPLOYED
from cxidk.wrapper.insights._enums import _RETRY_ATTEMPTS


class LegacyScorecards:
    """Proto-based QA scorecard client retained for `workflow.config_copier`.

    This class provides methods to create, list, get, and delete QA scorecards
    using native Python SDK methods and returns proto messages. It is superseded
    by `cxidk.wrapper.insights.Scorecards`, which composes the REST collections
    and returns typed, revision-aware views.

    Attributes:
        project_id: The Google Cloud project ID.
        location: The Google Cloud location.
        parent: The parent resource name.
        client: The ContactCenterInsightsClient instance.
    """

    def __init__(
        self,
        project_id: str,
        location: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ) -> None:
        """Initializes the LegacyScorecards client.

        Args:
            project_id: The Google Cloud project ID.
            location: The Google Cloud location where the operations are running.
            auth: An optional, pre-configured authentication object.
            config: An optional, pre-configured configuration object.
        """
        self.project_id = project_id
        self.location = location
        self.auth = auth or base.Auth()
        self.config = config or base.Config()
        self.parent = f"projects/{self.project_id}/locations/{self.location}"

        self.client = contact_center_insights_v1.ContactCenterInsightsClient(
            credentials=self.auth.creds,
            client_options=self.config.set_insights_endpoint(),
        )

    def create_scorecard(
        self,
        qa_scorecard: types.QaScorecard,
        qa_scorecard_id: Optional[str] = None,
    ) -> types.QaScorecard:
        """Creates a new QA scorecard using the native SDK.

        Args:
            qa_scorecard: A populated types.QaScorecard object.
            qa_scorecard_id: Optional user-specified ID for the scorecard.

        Returns:
            The created types.QaScorecard resource.
        """
        return self.client.create_qa_scorecard(
            parent=self.parent,
            qa_scorecard=qa_scorecard,
            qa_scorecard_id=qa_scorecard_id,
        )

    def list_scorecards(self) -> Any:
        """Lists all QA scorecards in the project/location using the native SDK.

        Returns:
            An iterable Pager containing types.QaScorecard resources.
        """
        return self.client.list_qa_scorecards(parent=self.parent)

    def get_scorecard(self, scorecard_id: str) -> types.QaScorecard:
        """Retrieves a specific QA scorecard by its ID using the native SDK.

        Args:
            scorecard_id: The ID of the scorecard.

        Returns:
            The requested types.QaScorecard resource.
        """
        name = f"{self.parent}/qaScorecards/{scorecard_id}"
        return self.client.get_qa_scorecard(name=name)

    def delete_scorecard(self, scorecard_id: str) -> None:
        """Deletes a specific QA scorecard using the native SDK.

        Args:
            scorecard_id: The ID of the scorecard to delete.
        """
        name = f"{self.parent}/qaScorecards/{scorecard_id}"
        self.client.delete_qa_scorecard(name=name)


class ScorecardQuestions:
    """Manages QA scorecard questions in Contact Center AI Insights.

    This class provides methods to create, list, get, and delete QA questions
    within a specific scorecard using native Python SDK methods.

    Attributes:
        project_id: The Google Cloud project ID.
        location: The Google Cloud location.
        scorecard_id: The parent scorecard ID.
        parent: The parent scorecard resource name.
        client: The ContactCenterInsightsClient instance.
    """

    def __init__(
        self,
        project_id: str,
        location: str,
        scorecard_id: str,
        revision_id: Optional[str] = None,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ) -> None:
        """Initializes the ScorecardQuestions client.

        Args:
            project_id: The Google Cloud project ID.
            location: The Google Cloud location.
            scorecard_id: The parent scorecard ID.
            revision_id: The parent scorecard revision ID. The API nests
                questions under a revision, so this is required for calls to
                succeed. It is optional only to preserve the original
                signature; omitting it logs a warning and builds the legacy,
                incorrect parent path.
            auth: An optional, pre-configured authentication object.
            config: An optional, pre-configured configuration object.
        """
        self.project_id = project_id
        self.location = location
        self.scorecard_id = scorecard_id
        self.revision_id = revision_id
        self.auth = auth or base.Auth()
        self.config = config or base.Config()
        self.parent = (
            f"projects/{self.project_id}/locations/{self.location}"
            f"/qaScorecards/{self.scorecard_id}"
        )
        if revision_id:
            self.parent = f"{self.parent}/revisions/{revision_id}"
        else:
            logging.warning(
                "ScorecardQuestions was created without a revision_id. The "
                "Insights API nests questions under "
                "qaScorecards/{id}/revisions/{revision_id}/qaQuestions, so "
                "requests built from this parent will not resolve. Pass "
                "revision_id, or use RevisionQuestions."
            )

        self.client = contact_center_insights_v1.ContactCenterInsightsClient(
            credentials=self.auth.creds,
            client_options=self.config.set_insights_endpoint(),
        )

    def create_question(
        self,
        qa_question: types.QaQuestion,
        qa_question_id: Optional[str] = None,
    ) -> types.QaQuestion:
        """Creates a new QA question using the native SDK.

        Args:
            qa_question: A populated types.QaQuestion object.
            qa_question_id: Optional user-specified ID for the question.

        Returns:
            The created types.QaQuestion resource.
        """
        return self.client.create_qa_question(
            parent=self.parent,
            qa_question=qa_question,
            qa_question_id=qa_question_id,
        )

    def list_questions(self) -> Any:
        """Lists all QA questions within the scorecard using the native SDK.

        Returns:
            An iterable Pager containing types.QaQuestion resources.
        """
        return self.client.list_qa_questions(parent=self.parent)

    def get_question(self, question_id: str) -> types.QaQuestion:
        """Retrieves a specific QA question by its ID using the native SDK.

        Args:
            question_id: The ID of the question.

        Returns:
            The requested types.QaQuestion resource.
        """
        name = f"{self.parent}/qaQuestions/{question_id}"
        return self.client.get_qa_question(name=name)

    def delete_question(self, question_id: str) -> None:
        """Deletes a specific QA question using the native SDK.

        Args:
            question_id: The ID of the question to delete.
        """
        name = f"{self.parent}/qaQuestions/{question_id}"
        self.client.delete_qa_question(name=name)


class ConfigCollection:
    """Base class for REST-backed Insights configuration collections.

    Every configuration asset that `workflow/ops.py` exports and imports is
    reached through a subclass of this class.

    Note on the REST choice: several of these collections (`autoLabelingRules`,
    `assessmentRules`, `qaQuestionTags`, `correlationConfig`) are absent from
    the pinned GAPIC SDK, so a REST path is required regardless. Routing the
    remaining collections the same way keeps every asset on one mechanism and,
    more importantly, keeps every payload as a camelCase dictionary in the exact
    shape the API documents. Export bundles are therefore byte-comparable with
    the API's own JSON, and a single sanitizer and reference-rewriter can serve
    all assets rather than one per representation.

    Attributes:
        collection: The REST collection segment, e.g. 'phraseMatchers'.
        items_key: The key holding the array in a list response.
        id_param: The query parameter used to supply a caller-chosen ID on
            create, or None when the server always assigns the ID.
        supports_paging: Whether the list method accepts pageSize/pageToken.
        active_field: Name of the boolean field marking a resource active, or
            None when the concept does not apply.
    """

    collection: str = ""
    items_key: str = ""
    id_param: Optional[str] = None
    supports_paging: bool = True
    active_field: Optional[str] = "active"

    def __init__(
        self,
        project_id: str,
        location: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ) -> None:
        """Initializes the collection client.

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
        self.parent = f"projects/{project_id}/locations/{location}"

        self.request = base.Request(
            project_id=project_id,
            location=location,
            auth=self.auth,
            config=self.config,
            base_url=self.config.insights_base_url(location),
        )

    def _collection_url(self) -> str:
        """Builds the endpoint for the collection itself.

        Returns:
            The endpoint relative to the versioned API base URL.
        """
        return f"{self.parent}/{self.collection}"

    def _resource_url(self, resource_id: str) -> str:
        """Builds the endpoint for a single resource.

        Args:
            resource_id: The bare resource ID, not a full resource name.

        Returns:
            The endpoint relative to the versioned API base URL.
        """
        return f"{self._collection_url()}/{resource_id}"

    def list(
        self,
        params: Optional[Dict[str, Any]] = None,
        page_size: int = 100,
    ) -> List[Dict[str, Any]]:
        """Lists every resource in the collection, exhausting pagination.

        Args:
            params: Extra query parameters, such as a `filter`.
            page_size: Page size requested when the collection supports paging.

        Returns:
            A list of resource dictionaries. Empty when none exist.
        """
        results: List[Dict[str, Any]] = []
        query: Dict[str, Any] = dict(params or {})
        if self.supports_paging:
            query["pageSize"] = page_size

        while True:
            response = (
                self.request.make(
                    endpoint=self._collection_url(),
                    method=base.Methods.GET,
                    payload=None,
                    params=query,
                    raise_on_error=True,
                    max_attempts=_RETRY_ATTEMPTS,
                )
                or {}
            )
            results.extend(response.get(self.items_key, []))

            token = response.get("nextPageToken")
            if not token or not self.supports_paging:
                return results
            query["pageToken"] = token

    def list_active(
        self, params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Lists only resources whose active flag is set.

        Filtering is performed client-side. Of the collections involved, only
        `phraseMatchers` and `qaQuestionTags` expose a server-side `filter`
        parameter, so a uniform client-side pass is both simpler and correct
        everywhere.

        Args:
            params: Extra query parameters passed through to `list`.

        Returns:
            A list of active resource dictionaries. When the collection has no
            notion of active, every resource is returned.
        """
        records = self.list(params=params)
        if self.active_field is None:
            return records
        return [r for r in records if r.get(self.active_field)]

    def get(self, resource_id: str) -> Dict[str, Any]:
        """Retrieves a single resource.

        Args:
            resource_id: The bare resource ID.

        Returns:
            The resource as a dictionary.
        """
        return (
            self.request.make(
                endpoint=self._resource_url(resource_id),
                method=base.Methods.GET,
                payload=None,
                raise_on_error=True,
                max_attempts=_RETRY_ATTEMPTS,
            )
            or {}
        )

    def create(
        self,
        body: Dict[str, Any],
        resource_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates a resource.

        Args:
            body: The resource body, already sanitized of output-only fields.
            resource_id: An optional caller-chosen ID. Ignored when the
                collection does not accept one.

        Returns:
            The created resource, or the long-running operation describing its
            creation for collections that create asynchronously.
        """
        params: Dict[str, Any] = {}
        if resource_id and self.id_param:
            params[self.id_param] = resource_id

        return (
            self.request.make(
                endpoint=self._collection_url(),
                method=base.Methods.POST,
                payload=body,
                params=params or None,
                raise_on_error=True,
                max_attempts=_RETRY_ATTEMPTS,
            )
            or {}
        )

    def patch(
        self,
        resource_id: str,
        body: Dict[str, Any],
        update_mask: str,
    ) -> Dict[str, Any]:
        """Updates a resource in place.

        Not used by the configuration import path, which is create-only. It
        exists for the correlation-config singleton and for callers managing
        resources outside that workflow.

        Args:
            resource_id: The bare resource ID.
            body: The fields to update.
            update_mask: A comma-separated FieldMask.

        Returns:
            The updated resource.
        """
        return (
            self.request.make(
                endpoint=self._resource_url(resource_id),
                method=base.Methods.PATCH,
                payload=body,
                params={"updateMask": update_mask},
                raise_on_error=True,
                max_attempts=_RETRY_ATTEMPTS,
            )
            or {}
        )

    def delete(self, resource_id: str) -> Dict[str, Any]:
        """Deletes a resource.

        Args:
            resource_id: The bare resource ID.

        Returns:
            An empty dictionary, or a long-running operation for collections
            that delete asynchronously.
        """
        return (
            self.request.make(
                endpoint=self._resource_url(resource_id),
                method=base.Methods.DELETE,
                payload=None,
                raise_on_error=True,
                max_attempts=_RETRY_ATTEMPTS,
            )
            or {}
        )


class PhraseMatchers(ConfigCollection):
    """Smart highlighters, exposed by the API as phrase matchers."""

    collection = "phraseMatchers"
    items_key = "phraseMatchers"
    id_param = None


class AnalysisRules(ConfigCollection):
    """Analysis rules controlling automatic conversation analysis."""

    collection = "analysisRules"
    items_key = "analysisRules"
    id_param = None


class AutoLabelingRules(ConfigCollection):
    """Auto labeling rules. Absent from the pinned GAPIC SDK."""

    collection = "autoLabelingRules"
    items_key = "autoLabelingRules"
    id_param = "autoLabelingRuleId"


class AssessmentRules(ConfigCollection):
    """Assessment rules driving scheduled QA sampling."""

    collection = "assessmentRules"
    items_key = "assessmentRules"
    id_param = "assessmentRuleId"


class QaQuestionTags(ConfigCollection):
    """Custom question tags referenced by scorecard questions.

    Note that `QaQuestion.tags` mixes two kinds of value: bare strings naming
    built-in categories such as 'BUSINESS', and full resource names pointing at
    members of this collection. Only the latter are resources.
    """

    collection = "qaQuestionTags"
    items_key = "qaQuestionTags"
    id_param = "qaQuestionTagId"
    supports_paging = False
    active_field = None


class IssueModels(ConfigCollection):
    """Topic models. Every mutation here is a long-running operation."""

    collection = "issueModels"
    items_key = "issueModels"
    id_param = None
    supports_paging = False
    active_field = None

    def list_deployed(self) -> List[Dict[str, Any]]:
        """Lists only topic models that are currently deployed.

        Topic models express availability through a read-only `state` enum
        rather than an `active` boolean, so this replaces `list_active`.

        Returns:
            A list of deployed topic model dictionaries.
        """
        return [m for m in self.list() if m.get("state") == _ISSUE_MODEL_DEPLOYED]

    def export_model(
        self, model_id: str, gcs_uri: str
    ) -> Dict[str, Any]:
        """Starts a native export of a trained topic model to GCS.

        Args:
            model_id: The bare topic model ID.
            gcs_uri: The destination object URI, including the `gs://` prefix.

        Returns:
            The long-running operation describing the export.
        """
        return (
            self.request.make(
                endpoint=f"{self._resource_url(model_id)}:export",
                method=base.Methods.POST,
                payload={"gcsDestination": {"objectUri": gcs_uri}},
                raise_on_error=True,
                max_attempts=_RETRY_ATTEMPTS,
            )
            or {}
        )

    def import_model(self, gcs_uri: str, create_new: bool = True) -> Dict[str, Any]:
        """Starts a native import of a trained topic model from GCS.

        Args:
            gcs_uri: The source object URI, including the `gs://` prefix.
            create_new: Whether to create a new model rather than replacing an
                existing one. Always True under create-only import semantics.

        Returns:
            The long-running operation describing the import.
        """
        return (
            self.request.make(
                endpoint=f"{self._collection_url()}:import",
                method=base.Methods.POST,
                payload={
                    "gcsSource": {"objectUri": gcs_uri},
                    "createNewModel": create_new,
                },
                raise_on_error=True,
                max_attempts=_RETRY_ATTEMPTS,
            )
            or {}
        )

    def deploy(self, model_id: str) -> Dict[str, Any]:
        """Deploys a topic model.

        This is a billable operation and is never invoked automatically by the
        configuration import path.

        Args:
            model_id: The bare topic model ID.

        Returns:
            The long-running operation describing the deployment.
        """
        return (
            self.request.make(
                endpoint=f"{self._resource_url(model_id)}:deploy",
                method=base.Methods.POST,
                payload={},
                raise_on_error=True,
                max_attempts=_RETRY_ATTEMPTS,
            )
            or {}
        )

    def undeploy(self, model_id: str) -> Dict[str, Any]:
        """Undeploys a topic model.

        Args:
            model_id: The bare topic model ID.

        Returns:
            The long-running operation describing the undeployment.
        """
        return (
            self.request.make(
                endpoint=f"{self._resource_url(model_id)}:undeploy",
                method=base.Methods.POST,
                payload={},
                raise_on_error=True,
                max_attempts=_RETRY_ATTEMPTS,
            )
            or {}
        )


class IssueModelIssues(ConfigCollection):
    """Issues nested beneath a topic model."""

    collection = "issues"
    items_key = "issues"
    id_param = None
    supports_paging = False
    active_field = None

    def __init__(
        self,
        project_id: str,
        location: str,
        issue_model_id: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ) -> None:
        """Initializes the issues client for one topic model.

        Args:
            project_id: The Google Cloud project ID.
            location: The Google Cloud location.
            issue_model_id: The bare ID of the parent topic model.
            auth: An optional, pre-configured authentication object.
            config: An optional, pre-configured configuration object.
        """
        super().__init__(project_id, location, auth=auth, config=config)
        self.issue_model_id = issue_model_id
        self.parent = f"{self.parent}/issueModels/{issue_model_id}"


class QaScorecards(ConfigCollection):
    """QA scorecards, reached over REST for the configuration workflow.

    The `LegacyScorecards` class covers the same collection through the
    GAPIC SDK and returns proto messages. This class exists alongside it
    because the export bundle is API JSON, and round-tripping through protos
    would both lose unknown fields and force a second representation on the
    sanitizer.
    """

    collection = "qaScorecards"
    items_key = "qaScorecards"
    id_param = "qaScorecardId"
    active_field = None

    def list_by_source(
        self, sources: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Lists scorecards, optionally narrowed to particular sources.

        Args:
            sources: `QaScorecardSource` enum values to include. Defaults to
                every source, which deliberately includes Discovery Engine and
                intent-taxonomy scorecards as well as customer-defined ones.

        Returns:
            A list of scorecard dictionaries.
        """
        params = {"qaScorecardSources": sources} if sources else None
        return self.list(params=params)


class ScorecardRevisions(ConfigCollection):
    """Revisions nested beneath a QA scorecard."""

    collection = "revisions"
    items_key = "qaScorecardRevisions"
    id_param = "qaScorecardRevisionId"
    active_field = None

    #: Alias the API attaches to the current revision via `alternateIds`.
    LATEST_ALIAS = "latest"

    def __init__(
        self,
        project_id: str,
        location: str,
        scorecard_id: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ) -> None:
        """Initializes the revisions client for one scorecard.

        Args:
            project_id: The Google Cloud project ID.
            location: The Google Cloud location.
            scorecard_id: The bare ID of the parent scorecard.
            auth: An optional, pre-configured authentication object.
            config: An optional, pre-configured configuration object.
        """
        super().__init__(project_id, location, auth=auth, config=config)
        self.scorecard_id = scorecard_id
        self.parent = f"{self.parent}/qaScorecards/{scorecard_id}"

    @classmethod
    def pick_latest(
        cls, revisions: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Selects the current revision from an already-fetched list.

        Prefers the revision the API aliases as `latest` through
        `alternateIds`, and falls back to the newest `createTime` for payloads
        that omit the alias. Keeping the rule here means export and the
        `Scorecards` facade can never disagree about which revision is current.

        Args:
            revisions: Revision dictionaries as returned by `list`.

        Returns:
            The current revision dictionary, or None when `revisions` is empty.
        """
        for revision in revisions:
            if cls.LATEST_ALIAS in (revision.get("alternateIds") or []):
                return revision
        if not revisions:
            return None
        return max(revisions, key=lambda r: str(r.get("createTime", "")))

    def get_latest(self) -> Optional[Dict[str, Any]]:
        """Retrieves the most recent revision of the parent scorecard.

        Export carries the latest revision only, so this keeps the "latest"
        rule in one place instead of duplicating sort logic per caller.

        Returns:
            The newest revision dictionary, or None when the scorecard has no
            revisions.
        """
        return self.pick_latest(self.list())


class RevisionQuestions(ConfigCollection):
    """QA questions nested beneath a scorecard revision.

    The questions collection is nested under a revision, not directly under the
    scorecard. The older `ScorecardQuestions` class builds the shorter,
    incorrect parent path; this class uses the path the API actually documents.
    """

    collection = "qaQuestions"
    items_key = "qaQuestions"
    id_param = "qaQuestionId"
    supports_paging = True
    active_field = None

    def __init__(
        self,
        project_id: str,
        location: str,
        scorecard_id: str,
        revision_id: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ) -> None:
        """Initializes the questions client for one scorecard revision.

        Args:
            project_id: The Google Cloud project ID.
            location: The Google Cloud location.
            scorecard_id: The bare ID of the parent scorecard.
            revision_id: The bare ID of the parent revision.
            auth: An optional, pre-configured authentication object.
            config: An optional, pre-configured configuration object.
        """
        super().__init__(project_id, location, auth=auth, config=config)
        self.scorecard_id = scorecard_id
        self.revision_id = revision_id
        self.parent = (
            f"{self.parent}/qaScorecards/{scorecard_id}/revisions/{revision_id}"
        )
