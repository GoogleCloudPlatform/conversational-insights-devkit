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

"""Export and import of Contact Center Insights configuration.

`ConfigOps` moves configuration assets between Insights environments. Source and
destination may differ in project, in region, or in both.

Supported assets:
  * QA scorecards, including their latest revision and questions
  * Auto labeling rules
  * Analysis rules
  * Correlation rules
  * Smart highlighters, which the API calls phrase matchers
  * Topic models, which the API calls issue models
  * Assessment rules

Selection is modular: a caller may export or import a single asset type, an
arbitrary subset, or everything.

Three design rules run through this module and are worth stating up front,
because each one rules out code you might otherwise expect to find here.

1.  **This module never calls the Insights API directly.** Every request goes
    through `wrapper/insights/`, and every Cloud Storage operation goes
    through `wrapper/storage.py`.

2.  **Import is create-only.** No update, no merge, no overwrite, no delete. If
    a resource with the same name already exists at the destination, another one
    is created alongside it. Existing destination resources are never mutated.
    The single unavoidable exception is the correlation configuration, which is
    a singleton the API only exposes through an update method; there, rules are
    appended and pre-existing rules are left untouched.

    A direct consequence: resource IDs from the bundle are never reused.
    Re-using them would make the second import of any bundle fail with
    ALREADY_EXISTS, and falling back to an update is not permitted.

3.  **Export covers active resources only, and bundles are GCS-only.** Both are
    deliberate narrowings. Inactive drafts are noise when promoting config, and
    a single GCS object gives an atomic write that a directory of files cannot.

Scorecards carry their definition and conditional logic only. Example
conversations, feedback labels and fine-tuning state are all excluded, so an
imported scorecard arrives untuned.
"""

import datetime
import logging
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from cxidk.core import base
from cxidk.workflow.utils.ops_composite import (
    AnalysisRulesHandler,
    CorrelationConfigHandler,
    ScorecardsHandler,
)
from cxidk.workflow.utils.ops_handlers import (
    AssessmentRulesHandler,
    AssetHandler,
    AutoLabelingRulesHandler,
    Environment,
    IssueModelsHandler,
    PhraseMatchersHandler,
    QaQuestionTagsHandler,
)
from cxidk.workflow.utils.ops_types import (
    ALL_SCORECARD_SOURCES,
    SCHEMA_VERSION,
    Asset,
    AssetOutcome,
    BundleError,
    BundleIO,
    ExportOptions,
    ExportReport,
    ImportOptions,
    ImportReport,
    NameClash,
    NamingPolicy,
    PlanReport,
    ReferenceMap,
    ReferenceResolution,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ALL_SCORECARD_SOURCES",
    "SCHEMA_VERSION",
    "Asset",
    "AssetOutcome",
    "BundleError",
    "BundleIO",
    "ConfigOps",
    "Environment",
    "ExportOptions",
    "ExportReport",
    "ImportOptions",
    "ImportReport",
    "NameClash",
    "NamingPolicy",
    "PlanReport",
    "ReferenceMap",
    "ReferenceResolution",
]


#: Import order. Assets are created before anything that references them, so
#: the reference map is always populated by the time it is consulted.
IMPORT_ORDER: Tuple[Asset, ...] = (
    Asset.QA_QUESTION_TAGS,
    Asset.SCORECARDS,
    Asset.PHRASE_MATCHERS,
    Asset.ISSUE_MODELS,
    Asset.ANALYSIS_RULES,
    Asset.AUTO_LABELING_RULES,
    Asset.ASSESSMENT_RULES,
    Asset.CORRELATION_CONFIG,
)

_HANDLERS: Dict[Asset, Any] = {
    Asset.QA_QUESTION_TAGS: QaQuestionTagsHandler,
    Asset.SCORECARDS: ScorecardsHandler,
    Asset.PHRASE_MATCHERS: PhraseMatchersHandler,
    Asset.ISSUE_MODELS: IssueModelsHandler,
    Asset.ANALYSIS_RULES: AnalysisRulesHandler,
    Asset.AUTO_LABELING_RULES: AutoLabelingRulesHandler,
    Asset.ASSESSMENT_RULES: AssessmentRulesHandler,
    Asset.CORRELATION_CONFIG: CorrelationConfigHandler,
}


class ConfigOps:
    """Exports and imports Contact Center Insights configuration.

    One instance addresses one environment. Moving configuration between
    environments therefore uses two instances, which is also how differing
    credentials are supplied when the source and destination projects are owned
    by different service accounts.

    Example:
        Promote phrase matchers from a sandbox to production, across regions::

            src = ConfigOps("dev-proj", "us-central1", auth=dev_auth)
            src.export(uri="gs://bundles/config.json")

            dst = ConfigOps("prod-proj", "europe-west1", auth=prod_auth)
            print(dst.plan(uri="gs://bundles/config.json").summary())
            dst.import_(
                uri="gs://bundles/config.json",
                assets=[Asset.PHRASE_MATCHERS],
            )

    Attributes:
        environment: The project, location and credentials in use.
    """

    def __init__(
        self,
        project_id: str,
        location: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
        bundle_project_id: Optional[str] = None,
    ) -> None:
        """Initializes the configuration operations client.

        Args:
            project_id: The Google Cloud project ID holding the Insights
                resources.
            location: The Insights location. This drives both the resource
                parent path and the regional endpoint.
            auth: An optional, pre-configured authentication object.
            config: An optional, pre-configured configuration object whose
                region must match `location`.
            bundle_project_id: Project used for Cloud Storage access, when the
                bundle bucket lives outside `project_id`.

        Raises:
            ValueError: If a supplied config targets a different region.
        """
        self.environment = Environment(
            project_id=project_id, location=location, auth=auth, config=config
        )
        self.bundle_io = BundleIO(
            project_id=bundle_project_id or project_id,
            auth=self.environment.auth,
            config=self.environment.config,
        )
        self._handler_cache: Dict[Asset, AssetHandler] = {}

    @property
    def project_id(self) -> str:
        """The Insights project ID.

        Returns:
            The configured project ID.
        """
        return self.environment.project_id

    @property
    def location(self) -> str:
        """The Insights location.

        Returns:
            The configured location.
        """
        return self.environment.location

    def handler(self, asset: Asset) -> AssetHandler:
        """Returns the handler for an asset, constructing it on first use.

        Lazy construction matters: exporting only scorecards should not build
        clients for the seven assets that were not requested.

        Args:
            asset: The asset type.

        Returns:
            The handler instance.

        Raises:
            ValueError: If the asset has no registered handler.
        """
        if asset not in _HANDLERS:
            raise ValueError(
                f"Unsupported asset {asset!r}. Supported assets: "
                f"{[str(a) for a in IMPORT_ORDER]}"
            )
        if asset not in self._handler_cache:
            self._handler_cache[asset] = _HANDLERS[asset](self.environment)
        return self._handler_cache[asset]

    @staticmethod
    def _normalize(assets: Optional[Iterable[Asset]]) -> List[Asset]:
        """Resolves an asset selection into a dependency-ordered list.

        Args:
            assets: The requested assets, or None for everything.

        Returns:
            The selection ordered so dependencies come first.

        Raises:
            ValueError: If an unsupported asset is requested.
        """
        if assets is None:
            return list(IMPORT_ORDER)

        requested = [Asset(asset) for asset in assets]
        unknown = [a for a in requested if a not in _HANDLERS]
        if unknown:
            raise ValueError(f"Unsupported assets: {[str(a) for a in unknown]}")
        return [asset for asset in IMPORT_ORDER if asset in set(requested)]

    def export(
        self,
        uri: str,
        assets: Optional[Iterable[Asset]] = None,
        options: Optional[ExportOptions] = None,
    ) -> ExportReport:
        """Exports configuration to a single JSON bundle in Cloud Storage.

        Args:
            uri: Destination `gs://` URI for the bundle.
            assets: Assets to export. Defaults to everything.
            options: Export options. Defaults to active resources only, all
                scorecard sources, and no topic-model staging bucket.

        Returns:
            A report describing what was exported.

        Raises:
            BundleError: If the destination bucket is not reachable.
            ValueError: If the URI is not a GCS URI.
        """
        options = options or ExportOptions()
        selection = self._normalize(assets)

        if not self.bundle_io.bucket_writable(uri):
            raise BundleError(
                f"Cannot reach the bucket for {uri!r}. Checked before reading "
                f"any configuration so the export does not fail at the end."
            )

        report = ExportReport(
            uri=uri,
            source_project_id=self.project_id,
            source_location=self.location,
        )
        payload: Dict[str, Any] = {}

        for asset in selection:
            handler = self.handler(asset)
            records = handler.export(options)
            payload[str(asset)] = records
            report.assets[str(asset)] = AssetOutcome(
                asset=str(asset),
                count=len(records) if isinstance(records, list) else 1,
            )

        document = {
            "manifest": self._manifest(selection, options),
            "assets": payload,
        }
        self.bundle_io.write_json(uri, document)

        logger.info(
            "Exported %d records across %d assets to %s",
            report.total,
            len(selection),
            uri,
        )
        return report

    def _manifest(
        self, selection: List[Asset], options: ExportOptions
    ) -> Dict[str, Any]:
        """Builds the bundle manifest.

        Args:
            selection: Assets included in the bundle.
            options: Export options, recorded so the bundle is self-describing.

        Returns:
            The manifest dictionary.
        """
        return {
            "schema_version": SCHEMA_VERSION,
            "exported_at": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
            "source_project_id": self.project_id,
            "source_location": self.location,
            "assets": [str(asset) for asset in selection],
            "active_only": options.active_only,
            "scorecard_sources": list(
                options.scorecard_sources or ALL_SCORECARD_SOURCES
            ),
        }

    def _load(
        self, uri: str, assets: Optional[Iterable[Asset]]
    ) -> Tuple[Dict[str, Any], Dict[str, Any], List[Asset]]:
        """Reads a bundle and validates the requested selection against it.

        Args:
            uri: Source `gs://` URI.
            assets: Requested assets, or None for everything in the bundle.

        Returns:
            A ``(manifest, assets_payload, selection)`` tuple.

        Raises:
            BundleError: If the bundle is malformed, of an unknown schema
                version, or missing a requested asset.
        """
        document = self.bundle_io.read_json(uri)

        manifest = document.get("manifest")
        if not isinstance(manifest, dict):
            raise BundleError(f"{uri} has no manifest")

        version = manifest.get("schema_version")
        if version != SCHEMA_VERSION:
            raise BundleError(
                f"{uri} has schema_version {version!r}; this devkit "
                f"understands {SCHEMA_VERSION}."
            )

        payload = document.get("assets")
        if not isinstance(payload, dict):
            raise BundleError(f"{uri} has no assets section")

        available = self._available(uri, manifest)

        # An unspecified selection means "everything this bundle holds", not
        # "all eight asset types". Exporting a subset and then importing it
        # without repeating the subset is the common case.
        selection = (
            [asset for asset in IMPORT_ORDER if asset in available]
            if assets is None
            else self._normalize(assets)
        )

        missing = [a for a in selection if a not in available]
        if missing:
            raise BundleError(
                f"{uri} does not contain {[str(a) for a in missing]}. It "
                f"contains {[str(a) for a in sorted(available, key=str)]}."
            )

        return manifest, payload, selection

    @staticmethod
    def _available(uri: str, manifest: Dict[str, Any]) -> Set[Asset]:
        """Reads the manifest's asset list, tolerating unfamiliar entries.

        A bundle written by a later devkit may name assets this one does not
        implement. Ignoring them lets a caller still import the assets both
        versions understand, rather than being blocked by an asset they did not
        ask for.

        Args:
            uri: Source URI, for the warning message.
            manifest: The bundle manifest.

        Returns:
            The set of assets in the bundle that this devkit can handle.
        """
        available: Set[Asset] = set()
        unrecognized: List[str] = []

        for name in manifest.get("assets", []):
            try:
                available.add(Asset(name))
            except ValueError:
                unrecognized.append(str(name))

        if unrecognized:
            logger.warning(
                "%s names assets this devkit does not support: %s. They will "
                "be ignored.",
                uri,
                unrecognized,
            )
        return available

    def plan(
        self,
        uri: str,
        assets: Optional[Iterable[Asset]] = None,
        options: Optional[ImportOptions] = None,
    ) -> PlanReport:
        """Previews an import without writing anything.

        Under create-only semantics this is advisory: nothing it reports changes
        what `import_` does. It exists so that duplicate creation and dangling
        references are visible decisions rather than discoveries.

        Args:
            uri: Source `gs://` URI.
            assets: Assets to consider. Defaults to everything in the bundle.
            options: Import options that would be used.

        Returns:
            A plan report.
        """
        options = options or ImportOptions()
        manifest, payload, selection = self._load(uri, assets)

        report = PlanReport(
            uri=uri,
            source_project_id=manifest.get("source_project_id", "?"),
            source_location=manifest.get("source_location", "?"),
            destination_project_id=self.project_id,
            destination_location=self.location,
        )

        if (
            report.source_project_id == self.project_id
            and report.source_location == self.location
        ):
            report.cost_notes.append(
                "Destination is the same project and location as the source. "
                "Create-only import will duplicate every selected resource."
            )

        for asset in selection:
            records = payload.get(str(asset))
            handler = self.handler(asset)

            if asset == Asset.CORRELATION_CONFIG:
                rules = (
                    (records or {}).get("fullConversationConfig") or {}
                ).get("correlationRules") or []
                report.will_create[str(asset)] = len(rules)
                continue

            records = records or []
            report.will_create[str(asset)] = len(records)
            report.name_clashes.extend(handler.scan_names(records))

            if asset == Asset.ANALYSIS_RULES:
                report.cost_notes.extend(self._analysis_cost_notes(records, options))

        if Asset.ISSUE_MODELS in selection:
            report.cost_notes.append(
                "0 topic models will be deployed; deployment is billable and "
                "is never performed by import."
            )

        return report

    @staticmethod
    def _analysis_cost_notes(
        records: List[Dict[str, Any]], options: ImportOptions
    ) -> List[str]:
        """Describes the billing impact of importing analysis rules.

        `analysisPercentage` is a fraction in [0, 1], not a percentage out of
        100, so a rule exported from a sandbox at 1.0 analyses every
        conversation at the destination.

        Args:
            records: Analysis rule records.
            options: Import options, which decide whether rules arrive live.

        Returns:
            Human-readable cost notes.
        """
        if not records:
            return []

        if not options.activate_imported:
            return [
                f"{len(records)} analysis rules will be created INACTIVE; no "
                f"analysis will run until they are activated."
            ]

        notes = [
            f"{len(records)} analysis rules will be created ACTIVE and will "
            f"begin analysing conversations immediately:"
        ]
        for record in records:
            fraction = record.get("analysisPercentage", 0) or 0
            notes.append(
                f"  {record.get('displayName')!r}: "
                f"{float(fraction) * 100:.1f}% of conversations"
            )
        return notes

    def import_(
        self,
        uri: str,
        assets: Optional[Iterable[Asset]] = None,
        options: Optional[ImportOptions] = None,
    ) -> ImportReport:
        """Creates configuration at the destination from a bundle.

        Import is create-only. Existing destination resources are never updated
        or deleted, and re-running an import creates a further set of copies.

        Args:
            uri: Source `gs://` URI.
            assets: Assets to import. Defaults to everything in the bundle.
            options: Import options.

        Returns:
            A report describing what was created.

        Raises:
            BundleError: If the bundle is malformed or missing a requested
                asset.
        """
        options = options or ImportOptions()
        manifest, payload, selection = self._load(uri, assets)
        source_project = manifest.get("source_project_id", "")

        report = ImportReport(
            uri=uri,
            destination_project_id=self.project_id,
            destination_location=self.location,
            dry_run=options.dry_run,
        )
        reference_map = ReferenceMap()

        self._warn_missing_dependencies(selection, report)

        for asset in selection:
            handler = self.handler(asset)

            if asset == Asset.CORRELATION_CONFIG:
                correlation = handler
                assert isinstance(correlation, CorrelationConfigHandler)
                report.assets[str(asset)] = correlation.import_rules(
                    payload.get(str(asset)) or {}, options
                )
                continue

            report.assets[str(asset)] = handler.import_(
                records=payload.get(str(asset)) or [],
                options=options,
                reference_map=reference_map,
                source_project=source_project,
            )

        if not options.activate_imported:
            report.notes.append(
                "Imported rules were created inactive. Activate them "
                "deliberately once reviewed."
            )
        report.notes.append(
            "Import is create-only: nothing at the destination was modified or "
            "deleted, and re-running this import will create further copies."
        )

        logger.info(
            "Created %d resources across %d assets in %s/%s",
            report.total_created,
            len(selection),
            self.project_id,
            self.location,
        )
        return report

    def _warn_missing_dependencies(
        self, selection: List[Asset], report: ImportReport
    ) -> None:
        """Notes when a selected asset's referents were not also selected.

        Args:
            selection: The assets about to be imported.
            report: Report collecting the notes.
        """
        chosen = set(selection)
        for asset in selection:
            handler_cls = _HANDLERS[asset]
            missing = [
                str(dependency)
                for dependency in getattr(handler_cls, "depends_on", ())
                if dependency not in chosen
            ]
            if missing:
                report.notes.append(
                    f"{asset} references {missing}, which are not part of this "
                    f"import. Those references cannot be resolved."
                )
