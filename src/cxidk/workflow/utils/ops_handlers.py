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

"""Environment binding and handlers for flat configuration collections.

Contains the `Environment` that pins a project, location and credential
together, the `AssetHandler` base class, and the handlers for assets that are
ordinary flat collections: phrase matchers, auto labeling rules, assessment
rules, question tags and topic models.

Assets that are composite or carry cross-resource references live in
`ops_composite` instead.
"""

import datetime
import logging
from typing import Any, Dict, List, Optional, Tuple

from cxidk.core import base
from cxidk.wrapper import insights
from cxidk.workflow.utils.ops_types import (
    GCS_PREFIX,
    SOURCE_NAME_KEY,
    Asset,
    AssetOutcome,
    ExportOptions,
    ImportOptions,
    NameClash,
    ReferenceMap,
    UnresolvedReferenceError,
    apply_naming,
    new_resource_id,
    payload_of,
    resource_id_from_name,
    strip_fields,
)

logger = logging.getLogger(__name__)


class Environment:
    """A project, location and credential triple addressing one Insights setup.

    The location drives both the resource parent path and the regional API
    endpoint. Keeping them in one object is what prevents the classic failure of
    sending a `europe-west1` parent path to a `us-central1` endpoint.

    Attributes:
        project_id: The Google Cloud project ID.
        location: The Google Cloud location.
        auth: The authentication object used for every call.
        config: The configuration object, always agreeing with `location`.
    """

    def __init__(
        self,
        project_id: str,
        location: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ) -> None:
        """Initializes the environment.

        Args:
            project_id: The Google Cloud project ID.
            location: The Google Cloud location.
            auth: An optional, pre-configured authentication object. Supply
                distinct objects for source and destination when promoting
                between projects owned by different service accounts.
            config: An optional, pre-configured configuration object. Its region
                must match `location`.

        Raises:
            ValueError: If a supplied config targets a different region.
        """
        if config is not None and config.region not in (None, location):
            raise ValueError(
                f"config.region ({config.region!r}) disagrees with location "
                f"({location!r}). The region selects the API endpoint while the "
                f"location builds the resource path; they must match."
            )

        self.project_id = project_id
        self.location = location
        self.auth = auth or base.Auth()
        self.config = config or base.Config(region=location)

    @property
    def parent(self) -> str:
        """The resource parent path for this environment.

        Returns:
            A string of the form ``projects/{project}/locations/{location}``.
        """
        return f"projects/{self.project_id}/locations/{self.location}"

    def collection(self, cls: Any, **kwargs: Any) -> Any:
        """Instantiates a wrapper collection bound to this environment.

        Args:
            cls: A `wrapper.insights` collection class.
            **kwargs: Extra constructor arguments, such as a parent ID.

        Returns:
            The constructed wrapper instance.
        """
        return cls(
            project_id=self.project_id,
            location=self.location,
            auth=self.auth,
            config=self.config,
            **kwargs,
        )


class AssetHandler:
    """Base class for per-asset export and import logic.

    Attributes:
        asset: The asset type this handler owns.
        depends_on: Assets that must be imported before this one, because this
            one references them.
        stripped_fields: Output-only fields removed in addition to the common
            set.
        wrapper_name: Name of the `wrapper.insights` collection class backing
            the asset. Resolved by name at call time rather than bound at import
            time, so that tests can patch the wrapper module the same way the
            rest of this package's tests do.
        active_field: Name of the boolean field marking a resource active, or
            None when the asset has no such concept.
    """

    asset: Asset
    depends_on: Tuple[Asset, ...] = ()
    stripped_fields: Tuple[str, ...] = ()
    wrapper_name: str = ""
    active_field: Optional[str] = "active"

    def __init__(self, environment: Environment) -> None:
        """Initializes the handler.

        Args:
            environment: The environment this handler reads from or writes to.
        """
        self.environment = environment

    @property
    def wrapper_cls(self) -> Any:
        """The wrapper collection class backing this asset.

        Returns:
            The class object looked up from `wrapper.insights`.
        """
        return getattr(insights, self.wrapper_name)

    @property
    def client(self) -> Any:
        """The wrapper collection client for this asset.

        Returns:
            A configured wrapper instance.
        """
        return self.environment.collection(self.wrapper_cls)

    def export(self, options: ExportOptions) -> Any:
        """Reads the asset from the source environment.

        Args:
            options: Export options, notably `active_only`.

        Returns:
            A list of sanitized bundle records for collection assets. The
            correlation configuration is a singleton and returns a single
            dictionary instead, which is why this is not narrowed to a list.
        """
        raw = (
            self.client.list_active()
            if options.active_only
            else self.client.list()
        )
        return [self._to_record(item) for item in raw]

    def _to_record(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Converts an API resource into a bundle record.

        Args:
            item: The resource as returned by the API.

        Returns:
            A sanitized record carrying its source resource name.
        """
        record = strip_fields(item, self.stripped_fields)
        record[SOURCE_NAME_KEY] = item.get("name", "")
        return record

    def scan_names(self, records: List[Dict[str, Any]]) -> List[NameClash]:
        """Reports display names already present at the destination.

        Advisory only: create-only import proceeds regardless.

        Args:
            records: The bundle records about to be imported.

        Returns:
            A list of clashes, one per colliding display name.
        """
        wanted = {r.get("displayName") for r in records if r.get("displayName")}
        if not wanted:
            return []

        clashes: Dict[str, NameClash] = {}
        for existing in self.client.list():
            name = existing.get("displayName")
            if name in wanted:
                clash = clashes.setdefault(
                    name, NameClash(asset=str(self.asset), display_name=name)
                )
                clash.existing_names.append(existing.get("name", ""))
        return list(clashes.values())

    def import_(
        self,
        records: List[Dict[str, Any]],
        options: ImportOptions,
        reference_map: ReferenceMap,
        source_project: str,
    ) -> AssetOutcome:
        """Creates the asset's records at the destination.

        Args:
            records: Bundle records for this asset.
            options: Import options.
            reference_map: Map updated with each created resource.
            source_project: Project the bundle came from.

        Returns:
            The outcome for this asset.
        """
        outcome = AssetOutcome(asset=str(self.asset))
        client = self.client

        for record in records:
            try:
                body = self._prepare(record, options, reference_map, source_project)
            except UnresolvedReferenceError as error:
                outcome.errors.append(str(error))
                outcome.skipped += 1
                continue

            assigned_id = new_resource_id(
                resource_id_from_name(record.get(SOURCE_NAME_KEY, ""))
            )
            if options.dry_run:
                outcome.count += 1
                reference_map.record(
                    record.get(SOURCE_NAME_KEY, ""),
                    f"{self.environment.parent}/dryRun/{assigned_id}",
                )
                continue

            created = client.create(
                body=body,
                resource_id=assigned_id,
            )
            self._record_created(record, created, outcome, reference_map)

        return outcome

    def _prepare(
        self,
        record: Dict[str, Any],
        options: ImportOptions,
        reference_map: ReferenceMap,
        source_project: str,
    ) -> Dict[str, Any]:
        """Builds the create body for one record.

        Args:
            record: The bundle record.
            options: Import options.
            reference_map: Map of already-created resources.
            source_project: Project the bundle came from.

        Returns:
            The request body.
        """
        del reference_map  # Only the analysis-rule handler needs it.
        body = payload_of(record)

        if body.get("displayName"):
            body["displayName"] = apply_naming(
                body["displayName"], options, source_project
            )

        if self.active_field and self.active_field in body:
            body[self.active_field] = options.activate_imported

        return body

    def _record_created(
        self,
        record: Dict[str, Any],
        created: Dict[str, Any],
        outcome: AssetOutcome,
        reference_map: ReferenceMap,
    ) -> None:
        """Registers a freshly created resource in the outcome and map.

        Args:
            record: The originating bundle record.
            created: The API response for the create call.
            outcome: The outcome being accumulated.
            reference_map: Map updated with the correspondence.
        """
        destination_name = created.get("name", "")
        outcome.count += 1
        outcome.created_names.append(destination_name)
        reference_map.record(record.get(SOURCE_NAME_KEY, ""), destination_name)


class PhraseMatchersHandler(AssetHandler):
    """Smart highlighters."""

    asset = Asset.PHRASE_MATCHERS
    wrapper_name = "PhraseMatchers"
    stripped_fields = ("revisionId", "revisionCreateTime", "activationUpdateTime")

    def _prepare(
        self,
        record: Dict[str, Any],
        options: ImportOptions,
        reference_map: ReferenceMap,
        source_project: str,
    ) -> Dict[str, Any]:
        """Builds the create body, stamping provenance into `versionTag`.

        `versionTag` is free text, so using it to record the source resource
        makes a previous import's copies easy to find later. Under create-only
        semantics cleanup is manual, which makes that marker worth having.

        Args:
            record: The bundle record.
            options: Import options.
            reference_map: Map of already-created resources.
            source_project: Project the bundle came from.

        Returns:
            The request body.
        """
        body = super()._prepare(record, options, reference_map, source_project)
        source_name = record.get(SOURCE_NAME_KEY, "")
        if source_name:
            body["versionTag"] = f"imported:{resource_id_from_name(source_name)}"
        return body


class AutoLabelingRulesHandler(AssetHandler):
    """Auto labeling rules. Conditions are CEL and carry no resource names."""

    asset = Asset.AUTO_LABELING_RULES
    wrapper_name = "AutoLabelingRules"


class AssessmentRulesHandler(AssetHandler):
    """Assessment rules driving scheduled QA sampling."""

    asset = Asset.ASSESSMENT_RULES
    wrapper_name = "AssessmentRules"

    def export(self, options: ExportOptions) -> List[Dict[str, Any]]:
        """Exports assessment rules, warning about elapsed schedule windows.

        A rule whose `scheduleInfo.endTime` is already in the past imports
        successfully and then never fires, which is a confusing failure mode.

        Args:
            options: Export options.

        Returns:
            A list of sanitized bundle records.
        """
        records = super().export(options)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        for record in records:
            end_time = (record.get("scheduleInfo") or {}).get("endTime")
            if end_time and str(end_time) < now:
                logger.warning(
                    "Assessment rule %r has an endTime of %s, which has "
                    "already elapsed. Imported copies will never fire.",
                    record.get("displayName"),
                    end_time,
                )
        return records


class QaQuestionTagsHandler(AssetHandler):
    """Custom question tags.

    Only custom tags are resources. Scorecard questions may also carry built-in
    category strings such as 'BUSINESS', which are not resources and need no
    handling here.
    """

    asset = Asset.QA_QUESTION_TAGS
    wrapper_name = "QaQuestionTags"
    active_field = None


class IssueModelsHandler(AssetHandler):
    """Topic models.

    Every mutation on this collection is a long-running operation, and a model
    recreated from metadata alone is untrained and therefore useless. The native
    GCS export and import round-trip is used whenever a bucket is available.
    """

    asset = Asset.ISSUE_MODELS
    wrapper_name = "IssueModels"
    active_field = None
    stripped_fields = ("state", "issueCount", "trainingStats", "modelType")

    _GCS_URI_KEY = "_gcsModelUri"

    def export(self, options: ExportOptions) -> List[Dict[str, Any]]:
        """Exports topic models, natively when a staging bucket is available.

        Args:
            options: Export options. `gcs_bucket` enables the native, trained
                export; without it only metadata is captured.

        Returns:
            A list of bundle records.
        """
        client = self.client
        raw = client.list_deployed() if options.active_only else client.list()

        records = []
        for item in raw:
            record = self._to_record(item)
            if options.gcs_bucket:
                record[self._GCS_URI_KEY] = self._export_native(
                    client, item, options.gcs_bucket
                )
            else:
                logger.warning(
                    "Topic model %r exported as metadata only; no gcs_bucket "
                    "was supplied. The imported copy will be untrained.",
                    item.get("displayName"),
                )
            records.append(record)
        return records

    def _export_native(
        self, client: Any, item: Dict[str, Any], bucket: str
    ) -> str:
        """Runs the native model export and waits for it to finish.

        Args:
            client: The topic model wrapper.
            item: The model resource being exported.
            bucket: Destination bucket name, without a `gs://` prefix.

        Returns:
            The GCS URI the trained model was written to.
        """
        model_id = resource_id_from_name(item.get("name", ""))
        uri = f"{GCS_PREFIX}{bucket}/issue-models/{model_id}.pb"
        operation = client.export_model(model_id=model_id, gcs_uri=uri)
        self._await(operation)
        return uri

    def _await(self, operation: Dict[str, Any]) -> Dict[str, Any]:
        """Waits for a long-running operation to complete.

        Args:
            operation: The operation payload returned by the API.

        Returns:
            The operation's response payload.
        """
        lro = insights.LongRunningOperation.from_operation(
            operation=operation,
            project_id=self.environment.project_id,
            location=self.environment.location,
            auth=self.environment.auth,
            config=self.environment.config,
        )
        return lro.result()

    def import_(
        self,
        records: List[Dict[str, Any]],
        options: ImportOptions,
        reference_map: ReferenceMap,
        source_project: str,
    ) -> AssetOutcome:
        """Creates topic models at the destination.

        Models are never deployed here. Deployment is billable and is left as a
        deliberate follow-up action.

        Args:
            records: Bundle records for topic models.
            options: Import options.
            reference_map: Map updated with each created model.
            source_project: Project the bundle came from.

        Returns:
            The outcome for topic models.
        """
        outcome = AssetOutcome(asset=str(self.asset))
        client = self.client

        for record in records:
            gcs_uri = record.get(self._GCS_URI_KEY)
            if options.dry_run:
                outcome.count += 1
                assigned_id = new_resource_id(
                    resource_id_from_name(record.get(SOURCE_NAME_KEY, ""))
                )
                reference_map.record(
                    record.get(SOURCE_NAME_KEY, ""),
                    f"{self.environment.parent}/issueModels/{assigned_id}",
                )
                continue

            if gcs_uri:
                operation = client.import_model(gcs_uri=gcs_uri, create_new=True)
                created = self._await(operation)
            else:
                body = self._prepare(
                    record, options, reference_map, source_project
                )
                operation = client.create(body=body)
                created = self._await(operation)
                outcome.warnings.append(
                    f"{record.get('displayName')!r} was recreated from metadata "
                    f"only and is untrained."
                )

            self._record_created(record, created, outcome, reference_map)
            outcome.warnings.append(
                f"{record.get('displayName')!r} was created undeployed; "
                f"deploying it is billable and must be done explicitly."
            )

        return outcome
