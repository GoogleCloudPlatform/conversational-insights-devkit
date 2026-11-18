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

"""Vocabulary shared by the configuration export and import workflow.

Holds the asset enumeration, the option and report dataclasses, the
Cloud Storage bundle reader/writer, the reference map, and the small helpers
for minting IDs and naming imported copies.

See `cxidk.workflow.ops` for the public entry point and for the reasoning
behind the create-only, GCS-only and active-only decisions encoded here.
"""

import copy
import datetime
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from cxidk.core import base
from cxidk.wrapper import storage


logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
GCS_PREFIX = "gs://"
DEFAULT_RENAME_TEMPLATE = "{name} (imported {date})"
DEFAULT_DATE_FORMAT = "%Y-%m-%d"

#: Fields that are output-only on every Insights resource.
COMMON_STRIPPED_FIELDS: Tuple[str, ...] = ("name", "createTime", "updateTime")

#: Scorecard sources exported by default. Discovery Engine and intent-taxonomy
#: scorecards are included deliberately, not merely tolerated.
ALL_SCORECARD_SOURCES: Tuple[str, ...] = (
    "QA_SCORECARD_SOURCE_CUSTOMER_DEFINED",
    "QA_SCORECARD_SOURCE_DISCOVERY_ENGINE",
    "QA_SCORECARD_SOURCE_INTENT_TAXONOMY",
)

_ID_SUFFIX_LENGTH = 6
_MAX_ID_STEM = 48


class Asset(StrEnum):
    """Selectable configuration asset types.

    Values double as the keys used in the bundle document. Deferred asset types
    are deliberately absent so that requesting one raises rather than silently
    exporting nothing.
    """

    QA_QUESTION_TAGS = "qa_question_tags"
    SCORECARDS = "scorecards"
    PHRASE_MATCHERS = "phrase_matchers"
    ISSUE_MODELS = "issue_models"
    ANALYSIS_RULES = "analysis_rules"
    AUTO_LABELING_RULES = "auto_labeling_rules"
    ASSESSMENT_RULES = "assessment_rules"
    CORRELATION_CONFIG = "correlation_config"


class NamingPolicy(StrEnum):
    """How an imported copy is named.

    Attributes:
        SUFFIX: Apply the rename template, labelling the copy.
        DUPLICATE: Keep the source display name byte-for-byte.
    """

    SUFFIX = "suffix"
    DUPLICATE = "duplicate"


class ReferenceResolution(StrEnum):
    """How to handle a reference that cannot be resolved at the destination.

    Attributes:
        STRICT: Refuse to create the record. The default.
        PRUNE: Drop the dangling reference and warn loudly.
        MANUAL: Consult the caller-supplied external reference map.
    """

    STRICT = "strict"
    PRUNE = "prune"
    MANUAL = "manual"


class BundleError(RuntimeError):
    """Raised when a bundle is malformed, unreadable, or of an unknown schema."""


class UnresolvedReferenceError(RuntimeError):
    """Raised under STRICT when a record points at something that is missing."""


@dataclass
class ExportOptions:
    """Options controlling an export.

    Attributes:
        active_only: Restrict the export to active resources. Topic models use
            their deployment state rather than an active flag.
        scorecard_sources: Scorecard sources to include. Defaults to every
            source.
        gcs_bucket: Bucket used to stage the native topic-model export. Required
            when topic models are selected and a trained copy is wanted.
    """

    active_only: bool = True
    scorecard_sources: Optional[Sequence[str]] = None
    gcs_bucket: Optional[str] = None


@dataclass
class ImportOptions:
    """Options controlling an import.

    Attributes:
        naming: Whether copies are suffixed or named identically to the source.
        rename_template: Template applied under `NamingPolicy.SUFFIX`. Supports
            `{name}`, `{date}` and `{source_project}`.
        date_format: `strftime` format used for `{date}`.
        activate_imported: Whether imported rules are created live. Defaults to
            False, because active-only export means every rule in a bundle was
            analysing production traffic at the source.
        preserve_default: Whether an imported scorecard may claim the
            destination's default slot.
        reference_resolution: Behaviour when a cross-resource reference cannot
            be resolved.
        external_reference_map: Explicit mapping for references this devkit
            cannot create, such as Dialogflow conversation profiles.
        dry_run: Perform no writes.
    """

    naming: NamingPolicy = NamingPolicy.SUFFIX
    rename_template: str = DEFAULT_RENAME_TEMPLATE
    date_format: str = DEFAULT_DATE_FORMAT
    activate_imported: bool = False
    preserve_default: bool = False
    reference_resolution: ReferenceResolution = ReferenceResolution.STRICT
    external_reference_map: Dict[str, str] = field(default_factory=dict)
    dry_run: bool = False


@dataclass
class NameClash:
    """A bundle record whose display name already exists at the destination.

    Advisory only. Create-only import proceeds regardless; this exists so that
    `plan()` can show what is about to be duplicated.

    Attributes:
        asset: The asset type involved.
        display_name: The display name shared by both resources.
        existing_names: Resource names of the destination matches.
    """

    asset: str
    display_name: str
    existing_names: List[str] = field(default_factory=list)


@dataclass
class AssetOutcome:
    """Per-asset result of an export or import.

    Attributes:
        asset: The asset type.
        count: Number of records exported, or created on import.
        skipped: Number of records deliberately not processed.
        warnings: Non-fatal messages worth surfacing.
        errors: Failures that prevented individual records being written.
        created_names: Destination resource names created, in creation order.
    """

    asset: str
    count: int = 0
    skipped: int = 0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    created_names: List[str] = field(default_factory=list)


@dataclass
class ExportReport:
    """Summary of an export.

    Attributes:
        uri: Destination bundle URI.
        source_project_id: Project the configuration was read from.
        source_location: Location the configuration was read from.
        assets: Per-asset outcomes keyed by asset value.
    """

    uri: str
    source_project_id: str
    source_location: str
    assets: Dict[str, AssetOutcome] = field(default_factory=dict)

    @property
    def total(self) -> int:
        """Total number of records exported across all assets.

        Returns:
            The summed record count.
        """
        return sum(outcome.count for outcome in self.assets.values())


@dataclass
class ImportReport:
    """Summary of an import.

    Attributes:
        uri: Source bundle URI.
        destination_project_id: Project written to.
        destination_location: Location written to.
        dry_run: Whether the run performed any writes.
        assets: Per-asset outcomes keyed by asset value.
        notes: Cross-cutting caveats, such as scorecards landing untuned.
    """

    uri: str
    destination_project_id: str
    destination_location: str
    dry_run: bool = False
    assets: Dict[str, AssetOutcome] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    @property
    def total_created(self) -> int:
        """Total number of resources created across all assets.

        Returns:
            The summed created count.
        """
        return sum(outcome.count for outcome in self.assets.values())

    @property
    def failed(self) -> bool:
        """Whether any asset reported an error.

        Returns:
            True if at least one error was recorded.
        """
        return any(outcome.errors for outcome in self.assets.values())


@dataclass
class PlanReport:
    """Read-only preview of what an import would do.

    Attributes:
        uri: Source bundle URI.
        source_project_id: Project recorded in the bundle manifest.
        source_location: Location recorded in the bundle manifest.
        destination_project_id: Project that would be written to.
        destination_location: Location that would be written to.
        will_create: Record counts per asset.
        name_clashes: Advisory display-name collisions.
        unresolved_references: Human-readable descriptions of dangling pointers.
        cost_notes: Warnings about billable side effects.
    """

    uri: str
    source_project_id: str
    source_location: str
    destination_project_id: str
    destination_location: str
    will_create: Dict[str, int] = field(default_factory=dict)
    name_clashes: List[NameClash] = field(default_factory=list)
    unresolved_references: List[str] = field(default_factory=list)
    cost_notes: List[str] = field(default_factory=list)

    def summary(self) -> str:
        """Renders the plan as readable multi-line text.

        Returns:
            A formatted plan summary suitable for printing.
        """
        lines = [
            f"source (from manifest)  {self.source_project_id} / "
            f"{self.source_location}",
            f"destination             {self.destination_project_id} / "
            f"{self.destination_location}",
            "",
            "will create",
        ]
        for asset, count in sorted(self.will_create.items()):
            lines.append(f"  {asset:<22}{count}")

        if self.name_clashes:
            lines += ["", "name already in use at destination (advisory)"]
            for clash in self.name_clashes:
                lines.append(
                    f"  {clash.asset:<22}{clash.display_name!r} "
                    f"({len(clash.existing_names)} existing)"
                )

        if self.unresolved_references:
            lines += ["", "unresolved references"]
            lines += [f"  {item}" for item in self.unresolved_references]

        if self.cost_notes:
            lines += ["", "cost"]
            lines += [f"  {note}" for note in self.cost_notes]

        return "\n".join(lines)


class BundleIO:
    """Reads and writes bundle documents in Cloud Storage.

    Only `gs://` URIs are accepted. A local path is rejected rather than
    silently written to disk, so there is no ambiguity about where a bundle
    ended up.
    """

    def __init__(
        self,
        project_id: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ) -> None:
        """Initializes the bundle reader/writer.

        Args:
            project_id: Project used for Cloud Storage billing and quota. The
                bundle bucket often lives outside the Insights project.
            auth: An optional, pre-configured authentication object.
            config: An optional, pre-configured configuration object.
        """
        self.project_id = project_id
        self.auth = auth
        self.config = config

    @staticmethod
    def parse(uri: str) -> Tuple[str, str]:
        """Splits a GCS URI into bucket and object path.

        Args:
            uri: A URI of the form ``gs://bucket/path/to/object.json``.

        Returns:
            A ``(bucket, object_path)`` tuple.

        Raises:
            ValueError: If the URI is not a GCS URI or names no object.
        """
        if not uri.startswith(GCS_PREFIX):
            raise ValueError(
                f"Bundle paths must be Cloud Storage URIs starting with "
                f"{GCS_PREFIX!r}; got {uri!r}. Local filesystem paths are not "
                f"supported."
            )
        remainder = uri[len(GCS_PREFIX) :]
        bucket, _, object_path = remainder.partition("/")
        if not bucket or not object_path:
            raise ValueError(
                f"Bundle URI must include both a bucket and an object path; "
                f"got {uri!r}"
            )
        return bucket, object_path

    def _client(self, bucket: str) -> storage.Gcs:
        """Builds a Cloud Storage client for a bucket.

        Args:
            bucket: The bucket name, without the `gs://` prefix.

        Returns:
            A configured `storage.Gcs` instance.
        """
        return storage.Gcs(
            bucket_name=bucket,
            project_id=self.project_id,
            auth=self.auth,
            config=self.config,
        )

    def read_json(self, uri: str) -> Dict[str, Any]:
        """Reads and parses a JSON bundle.

        Args:
            uri: The `gs://` URI of the bundle.

        Returns:
            The parsed bundle document.

        Raises:
            BundleError: If the object cannot be parsed as a JSON object.
        """
        bucket, object_path = self.parse(uri)
        raw = self._client(bucket).download_blob(
            file_name=object_path, content_type=storage.ContentType.TEXT
        )
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        try:
            document = json.loads(text)
        except json.JSONDecodeError as error:
            raise BundleError(f"{uri} is not valid JSON: {error}") from error

        if not isinstance(document, dict):
            raise BundleError(f"{uri} does not contain a JSON object")
        return document

    def write_json(self, uri: str, document: Dict[str, Any]) -> None:
        """Serializes and uploads a bundle.

        Args:
            uri: The `gs://` URI to write.
            document: The bundle document.
        """
        bucket, object_path = self.parse(uri)
        self._client(bucket).upload_blob(
            file_name=object_path,
            data=json.dumps(document, indent=2, sort_keys=True),
            content_type=storage.ContentType.JSON,
        )

    def bucket_writable(self, uri: str) -> bool:
        """Checks that the bundle's bucket exists before doing real work.

        Args:
            uri: The `gs://` URI that will be written.

        Returns:
            True if the bucket exists and is visible to the caller.
        """
        bucket, _ = self.parse(uri)
        return self._client(bucket).bucket_exists()


class ReferenceMap:
    """Maps source resource names to the destination resources created for them.

    Under create-only import every destination ID is freshly minted, so a
    reference copied verbatim from the bundle always points at the wrong
    environment. This map is how the analysis-rule handler repairs them.
    """

    def __init__(self) -> None:
        """Initializes an empty map."""
        self._mapping: Dict[str, str] = {}

    def record(self, source_name: str, destination_name: str) -> None:
        """Records a source-to-destination correspondence.

        Args:
            source_name: Full resource name as it appeared at the source.
            destination_name: Full resource name created at the destination.
        """
        if source_name and destination_name:
            self._mapping[source_name] = destination_name

    def resolve(self, source_name: str) -> Optional[str]:
        """Looks up the destination equivalent of a source resource name.

        Args:
            source_name: Full resource name from the bundle.

        Returns:
            The destination resource name, or None when unknown.
        """
        return self._mapping.get(source_name)

    def __contains__(self, source_name: object) -> bool:
        """Reports whether a source name has been recorded.

        Args:
            source_name: The name to test.

        Returns:
            True if the name is present in the map.
        """
        return source_name in self._mapping

    def __len__(self) -> int:
        """Returns the number of recorded correspondences.

        Returns:
            The map size.
        """
        return len(self._mapping)


def new_resource_id(source_id: str) -> str:
    """Mints a fresh resource ID that will not collide at the destination.

    The source ID is kept as a readable stem so that a created resource can be
    traced back to its origin, but a random suffix guarantees that importing the
    same bundle twice does not fail with ALREADY_EXISTS.

    Args:
        source_id: The bare ID the resource had at the source, used as a stem.

    Returns:
        A new resource ID.
    """
    stem = re.sub(r"[^a-zA-Z0-9-]", "-", source_id or "imported")[:_MAX_ID_STEM]
    stem = stem.strip("-") or "imported"
    return f"{stem}-{uuid.uuid4().hex[:_ID_SUFFIX_LENGTH]}"


def resource_id_from_name(resource_name: str) -> str:
    """Extracts the trailing bare ID from a full resource name.

    Args:
        resource_name: A full resource name, or an empty string.

    Returns:
        The final path segment, or an empty string.
    """
    return resource_name.rsplit("/", 1)[-1] if resource_name else ""


def strip_fields(
    record: Dict[str, Any], extra: Iterable[str] = ()
) -> Dict[str, Any]:
    """Removes output-only fields so a record can be replayed as a create.

    Args:
        record: The resource dictionary read from the API.
        extra: Additional field names to remove beyond the common set.

    Returns:
        A copy of the record without server-owned fields.
    """
    cleaned = copy.deepcopy(record)
    for key in (*COMMON_STRIPPED_FIELDS, *extra):
        cleaned.pop(key, None)
    return cleaned


def apply_naming(
    display_name: str,
    options: ImportOptions,
    source_project: str,
    now: Optional[datetime.datetime] = None,
) -> str:
    """Computes the display name an imported copy should carry.

    Any suffix previously produced by the same template is removed before a new
    one is applied, so repeated round-trips cannot accrete a chain of markers.

    Args:
        display_name: The source display name.
        options: Import options carrying the policy and template.
        source_project: Project the bundle came from, for `{source_project}`.
        now: Timestamp used for `{date}`. Defaults to the current time.

    Returns:
        The display name to use at the destination.
    """
    if options.naming == NamingPolicy.DUPLICATE:
        return display_name

    stamp = (now or datetime.datetime.now()).strftime(options.date_format)
    stripped = _strip_existing_suffix(display_name, options)
    return options.rename_template.format(
        name=stripped, date=stamp, source_project=source_project
    )


def _strip_existing_suffix(display_name: str, options: ImportOptions) -> str:
    """Removes a previously applied rename marker from a display name.

    Args:
        display_name: The display name to clean.
        options: Import options carrying the template.

    Returns:
        The display name with any prior marker removed.
    """
    pattern = re.escape(options.rename_template)
    pattern = pattern.replace(re.escape("{name}"), "(?P<name>.*?)")
    pattern = pattern.replace(re.escape("{date}"), r"\d{2,4}[-/]\d{1,2}[-/]\d{1,4}")
    pattern = pattern.replace(re.escape("{source_project}"), r"[^\s]+")

    match = re.fullmatch(pattern, display_name)
    if match and match.groupdict().get("name"):
        return _strip_existing_suffix(match.group("name"), options)
    return display_name


#: Key used inside a bundle to remember the resource name a record had at the
#: source. Stripped before any create call. Present so that references between
#: assets can be repaired after every ID has been regenerated.
SOURCE_NAME_KEY = "_sourceName"

#: Key recording a scorecard's original `source` enum, which is output-only and
#: therefore cannot be restored at the destination.
SOURCE_ENUM_KEY = "_sourceEnum"

_INTERNAL_KEY_PREFIX = "_"


def payload_of(record: Dict[str, Any]) -> Dict[str, Any]:
    """Strips bundle-internal bookkeeping keys from a record.

    Args:
        record: A bundle record, possibly carrying underscore-prefixed keys.

    Returns:
        A copy safe to send as an API request body.
    """
    return {
        key: value
        for key, value in record.items()
        if not key.startswith(_INTERNAL_KEY_PREFIX)
    }
