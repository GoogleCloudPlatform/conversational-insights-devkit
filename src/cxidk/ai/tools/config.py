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

"""CCAI Insights configuration inspection and guarded promotion tools."""

from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple, Type

from cxidk.core import context
from cxidk.core import errors
from cxidk.core import serialize
from cxidk.ai.tools import models
from cxidk.ai.tools import plan_tokens
from cxidk.ai.tools import registry
from cxidk.ai.tools import validation
from cxidk.workflow import ops
from cxidk.wrapper import insights

ResourceTypeLiteral = Literal[
    "phrase_matchers",
    "issue_models",
    "analysis_rules",
    "auto_labeling_rules",
    "assessment_rules",
    "qa_question_tags",
    "authorized_view_sets",
]

_COLLECTION_CLIENTS: Dict[str, Type[Any]] = {
    "phrase_matchers": insights.PhraseMatchers,
    "issue_models": insights.IssueModels,
    "analysis_rules": insights.AnalysisRules,
    "auto_labeling_rules": insights.AutoLabelingRules,
    "assessment_rules": insights.AssessmentRules,
    "qa_question_tags": insights.QaQuestionTags,
}


def _list_resource_collection(
    resource_type: str, target: context.CxContext
) -> List[Dict[str, Any]]:
    """Dispatches `resource_type` to the corresponding `wrapper.insights` list client."""
    client_cls = _COLLECTION_CLIENTS.get(resource_type)
    if client_cls is not None:
        client = client_cls(
            target.project_id,
            target.location,
            auth=target.auth,
            config=target.config,
        )
        return list(serialize.to_jsonable(client.list()))

    if resource_type == "authorized_view_sets":
        av_client = insights.AuthorizedViews(
            parent=target.parent,
            auth=target.auth,
            config=target.config,
        )
        resp = av_client.list_view_set() or {}
        return list(resp.get("authorizedViewSets", []))

    raise errors.InvalidArgumentError(
        f"Unsupported resource_type: {resource_type!r}",
        hint=(
            "Choose from: phrase_matchers, issue_models, analysis_rules, "
            "auto_labeling_rules, assessment_rules, qa_question_tags, "
            "authorized_view_sets."
        ),
    )


def _parse_assets(
    assets: Optional[Sequence[str]],
) -> Optional[List[ops.Asset]]:
    """Validates optional asset names into `ops.Asset` enum members."""
    if assets is None:
        return None
    parsed: List[ops.Asset] = []
    for raw in assets:
        try:
            parsed.append(ops.Asset(raw))
        except ValueError as exc:
            valid_names = [str(item) for item in ops.IMPORT_ORDER]
            raise errors.InvalidArgumentError(
                f"Unsupported configuration asset: {raw!r}",
                hint=f"Valid assets: {valid_names}",
            ) from exc
    return parsed


def _assets_claim(parsed_assets: Optional[List[ops.Asset]]) -> List[str]:
    """Produces a canonical asset claim list for `plan_token` binding."""
    if parsed_assets is None:
        return ["*"]
    return sorted(str(item) for item in parsed_assets)


def _make_config_ops(target: context.CxContext) -> ops.ConfigOps:
    """Constructs a regional `ConfigOps` client bound to `target`."""
    return ops.ConfigOps(
        project_id=target.project_id,
        location=target.location,
        auth=target.auth,
        config=target.config,
    )


def _prepare_bundle_import(
    bundle_uri: str,
    assets: Optional[Sequence[str]],
    cx: Optional[context.CxContext],
    project_id: Optional[str],
    location: Optional[str],
) -> Tuple[str, Optional[List[ops.Asset]], context.CxContext, ops.ConfigOps, str]:
    """Validates `bundle_uri`, builds `ConfigOps`, and computes the bundle SHA-256."""
    validation.validate_gcs_uri(bundle_uri, "bundle_uri")
    clean_uri = bundle_uri.strip()
    parsed_assets = _parse_assets(assets)
    target = context.CxContext.resolve(cx, project_id, location)
    ops_client = _make_config_ops(target)
    try:
        bundle_doc = ops_client.bundle_io.read_json(clean_uri)
    except ops.BundleError as exc:
        raise errors.InvalidArgumentError(
            str(exc),
            hint="Verify `bundle_uri` points to a valid cxidk schema_version=1 JSON bundle.",
        ) from exc
    digest = plan_tokens.compute_bundle_digest(bundle_doc)
    return clean_uri, parsed_assets, target, ops_client, digest


@registry.cx_tool(
    name="insights_get_settings",
    title="Get CCAI Insights Settings",
    description=(
        "Retrieves project/location CCAI Insights settings including conversation "
        "TTL, default language, Pub/Sub notifications, Speech recognizer, DLP "
        "redaction templates, and automatic analysis percentages."
    ),
    safety=registry.Safety.READ,
    idempotent=True,
    open_world=True,
    toolset="core",
    confirm=False,
    output_model=models.SettingsOutput,
)
def insights_get_settings(
    project_id: Optional[str] = None,
    location: Optional[str] = None,
    *,
    cx: Optional[context.CxContext] = None,
) -> models.SettingsOutput:
    """Fetches project/location CCAI Insights global settings.

    Args:
        project_id: Optional target GCP project ID override.
        location: Optional target GCP location override.
        cx: Optional execution `CxContext`.

    Returns:
        `SettingsOutput` containing serialized project/location settings.

    Raises:
        errors.CxidkError: If the Insights API call fails.
    """
    target = context.CxContext.resolve(cx, project_id, location)
    with errors.translate_google_api_error():
        client = insights.Settings(
            project_id=target.project_id,
            parent=target.parent,
            auth=target.auth,
            config=target.config,
        )
        settings_proto = client.get()

    return models.SettingsOutput(
        project_id=target.project_id,
        location=target.location,
        settings=serialize.to_jsonable(settings_proto),
    )


@registry.cx_tool(
    name="insights_list_resources",
    title="List CCAI Insights Configuration Resources",
    description=(
        "Lists CCAI Insights configuration resources of a given `resource_type`: "
        "`phrase_matchers` (smart highlighters), `issue_models` (topic models), "
        "`analysis_rules`, `auto_labeling_rules`, `assessment_rules`, "
        "`qa_question_tags`, or `authorized_view_sets`."
    ),
    safety=registry.Safety.READ,
    idempotent=True,
    open_world=True,
    toolset="core",
    confirm=False,
    output_model=models.ResourceListOutput,
)
def insights_list_resources(
    resource_type: ResourceTypeLiteral,
    project_id: Optional[str] = None,
    location: Optional[str] = None,
    *,
    cx: Optional[context.CxContext] = None,
) -> models.ResourceListOutput:
    """Lists configuration resources for the requested collection.

    Args:
        resource_type: Collection name (`phrase_matchers`, `issue_models`,
            `analysis_rules`, `auto_labeling_rules`, `assessment_rules`,
            `qa_question_tags`, or `authorized_view_sets`).
        project_id: Optional target GCP project ID override.
        location: Optional target GCP location override.
        cx: Optional execution `CxContext`.

    Returns:
        `ResourceListOutput` containing the collection items and count.

    Raises:
        errors.InvalidArgumentError: If `resource_type` is unsupported.
        errors.CxidkError: If the Insights API call fails.
    """
    target = context.CxContext.resolve(cx, project_id, location)
    with errors.translate_google_api_error():
        items = _list_resource_collection(resource_type, target)

    return models.ResourceListOutput(
        project_id=target.project_id,
        location=target.location,
        resource_type=resource_type,
        items=items,
        count=len(items),
    )


@registry.cx_tool(
    name="config_export_bundle",
    title="Export CCAI Insights Configuration Bundle",
    description=(
        "Exports active CCAI Insights configuration assets from the source "
        "project/location to an atomic JSON bundle in Google Cloud Storage "
        "(`gs://bucket/path.json`). Requires write enablement and confirmation."
    ),
    safety=registry.Safety.WRITE,
    idempotent=False,
    open_world=True,
    toolset="writes",
    confirm=True,
    output_model=models.ConfigExportOutput,
    summary_fn=lambda args: (
        f"Export CCAI Insights configuration to {args.get('bundle_uri')!r} "
        f"(assets={args.get('assets') or 'ALL'})."
    ),
)
def config_export_bundle(
    bundle_uri: str,
    assets: Optional[List[str]] = None,
    active_only: bool = True,
    gcs_staging_bucket: Optional[str] = None,
    project_id: Optional[str] = None,
    location: Optional[str] = None,
    *,
    cx: Optional[context.CxContext] = None,
) -> models.ConfigExportOutput:
    """Exports CCAI Insights configuration to a GCS bundle.

    Args:
        bundle_uri: Destination `gs://<bucket>/<object>.json` URI.
        assets: Optional subset of asset category names to export.
        active_only: When True, exports only active configuration resources.
        gcs_staging_bucket: Optional GCS bucket used to stage issue models.
        project_id: Optional source GCP project ID override.
        location: Optional source GCP location override.
        cx: Optional execution `CxContext`.

    Returns:
        `ConfigExportOutput` summarizing exported asset counts.

    Raises:
        errors.InvalidArgumentError: If `bundle_uri` or `assets` is invalid.
        errors.OperationFailedError: If writing the bundle to GCS fails.
    """
    validation.validate_gcs_uri(bundle_uri, "bundle_uri")
    parsed_assets = _parse_assets(assets)
    target = context.CxContext.resolve(cx, project_id, location)
    export_opts = ops.ExportOptions(
        active_only=active_only,
        gcs_bucket=gcs_staging_bucket,
    )

    with errors.translate_google_api_error():
        try:
            report = _make_config_ops(target).export(
                uri=bundle_uri.strip(),
                assets=parsed_assets,
                options=export_opts,
            )
        except ops.BundleError as exc:
            raise errors.OperationFailedError(
                str(exc),
                hint=(
                    "Verify the destination GCS bucket exists and the caller "
                    "has storage write access."
                ),
            ) from exc

    return models.ConfigExportOutput(
        bundle_uri=report.uri,
        source_project_id=report.source_project_id,
        source_location=report.source_location,
        total_exported=report.total,
        assets={key: val.count for key, val in report.assets.items()},
    )


@registry.cx_tool(
    name="config_plan_import",
    title="Plan CCAI Insights Configuration Import",
    description=(
        "Performs a read-only dry-run preview of importing a GCS configuration "
        "bundle into the destination project/location, reporting resource counts, "
        "display-name clashes, and billing impact notes, and returns a signed "
        "short-lived `plan_token` required by `config_apply_import`."
    ),
    safety=registry.Safety.READ,
    idempotent=True,
    open_world=True,
    toolset="writes",
    confirm=False,
    output_model=models.ConfigPlanOutput,
)
def config_plan_import(
    bundle_uri: str,
    assets: Optional[List[str]] = None,
    activate_imported: bool = False,
    project_id: Optional[str] = None,
    location: Optional[str] = None,
    *,
    cx: Optional[context.CxContext] = None,
    principal: str = "local-stdio",
    signing_key: Optional[bytes] = None,
    allow_ephemeral_key: bool = True,
) -> models.ConfigPlanOutput:
    """Previews a configuration import and mints a signed `plan_token`.

    Args:
        bundle_uri: Source `gs://<bucket>/<object>.json` bundle URI.
        assets: Optional subset of asset category names to plan.
        activate_imported: Planned activation flag for imported rules.
        project_id: Optional destination GCP project ID override.
        location: Optional destination GCP location override.
        cx: Optional execution `CxContext`.
        principal: Authenticated caller identity bound into `plan_token`.
        signing_key: Optional explicit HMAC signing secret.
        allow_ephemeral_key: Whether ephemeral keys are allowed in local mode.

    Returns:
        `ConfigPlanOutput` with resource counts, clashes, and signed `plan_token`.

    Raises:
        errors.InvalidArgumentError: If `bundle_uri` or bundle schema is invalid.
        errors.PolicyViolationError: If signing key policy is not satisfied.
    """
    clean_uri, parsed_assets, target, ops_client, digest = (
        _prepare_bundle_import(bundle_uri, assets, cx, project_id, location)
    )
    import_opts = ops.ImportOptions(activate_imported=activate_imported)

    with errors.translate_google_api_error():
        try:
            plan_report = ops_client.plan(
                uri=clean_uri,
                assets=parsed_assets,
                options=import_opts,
            )
        except ops.BundleError as exc:
            raise errors.InvalidArgumentError(
                str(exc),
                hint="Verify `bundle_uri` points to a valid cxidk schema_version=1 JSON bundle.",
            ) from exc

    token = plan_tokens.issue_plan_token(
        destination_project_id=target.project_id,
        destination_location=target.location,
        bundle_uri=clean_uri,
        bundle_sha256=digest,
        assets=_assets_claim(parsed_assets),
        activate_imported=activate_imported,
        principal=principal,
        signing_key=signing_key,
        allow_ephemeral=allow_ephemeral_key,
    )

    return models.ConfigPlanOutput(
        bundle_uri=clean_uri,
        bundle_sha256=digest,
        destination_project_id=target.project_id,
        destination_location=target.location,
        will_create=dict(plan_report.will_create),
        name_clashes=serialize.to_jsonable(plan_report.name_clashes),
        cost_notes=list(plan_report.cost_notes),
        summary=plan_report.summary(),
        plan_token=token,
    )


@registry.cx_tool(
    name="config_apply_import",
    title="Apply CCAI Insights Configuration Import",
    description=(
        "Executes a create-only configuration import from `bundle_uri` into the "
        "destination project/location after verifying a valid, unexpired "
        "`plan_token` from `config_plan_import`. Imported rules are created "
        "INACTIVE by default (`activate_imported=False`) and topic models are "
        "never auto-deployed."
    ),
    safety=registry.Safety.WRITE,
    idempotent=False,
    open_world=True,
    toolset="writes",
    confirm=True,
    output_model=models.ConfigApplyOutput,
    summary_fn=lambda args: (
        f"Create-only import from {args.get('bundle_uri')!r} into "
        f"{args.get('project_id') or 'default-project'}/"
        f"{args.get('location') or 'default-location'} "
        f"(assets={args.get('assets') or 'ALL'}, "
        f"activate_imported={bool(args.get('activate_imported', False))})."
    ),
)
def config_apply_import(
    bundle_uri: str,
    plan_token: str,
    assets: Optional[List[str]] = None,
    activate_imported: bool = False,
    naming_policy: Literal["suffix", "duplicate"] = "suffix",
    reference_resolution: Literal["strict", "prune"] = "strict",
    project_id: Optional[str] = None,
    location: Optional[str] = None,
    *,
    cx: Optional[context.CxContext] = None,
    principal: str = "local-stdio",
    signing_key: Optional[bytes] = None,
    allow_ephemeral_key: bool = True,
) -> models.ConfigApplyOutput:
    """Verifies `plan_token` and applies a create-only configuration import.

    Args:
        bundle_uri: Source `gs://<bucket>/<object>.json` bundle URI.
        plan_token: Signed HS256 token returned by `config_plan_import`.
        assets: Optional subset of asset category names matching the plan.
        activate_imported: Activation flag matching the approved plan.
        naming_policy: Display-name collision strategy (`'suffix'` or `'duplicate'`).
        reference_resolution: Cross-asset reference handling (`'strict'` or `'prune'`).
        project_id: Optional destination GCP project ID override.
        location: Optional destination GCP location override.
        cx: Optional execution `CxContext`.
        principal: Authenticated caller identity verified against `plan_token`.
        signing_key: Optional explicit HMAC verification secret.
        allow_ephemeral_key: Whether ephemeral keys are allowed in local mode.

    Returns:
        `ConfigApplyOutput` reporting created resource counts and notes.

    Raises:
        errors.PolicyViolationError: If `plan_token` verification fails.
        errors.CxidkError: If reading the bundle or creating resources fails.
    """
    clean_uri, parsed_assets, target, ops_client, digest = (
        _prepare_bundle_import(bundle_uri, assets, cx, project_id, location)
    )
    plan_tokens.verify_plan_token(
        plan_token,
        destination_project_id=target.project_id,
        destination_location=target.location,
        bundle_uri=clean_uri,
        bundle_sha256=digest,
        assets=_assets_claim(parsed_assets),
        activate_imported=activate_imported,
        principal=principal,
        signing_key=signing_key,
        allow_ephemeral=allow_ephemeral_key,
    )

    import_opts = ops.ImportOptions(
        naming=ops.NamingPolicy(naming_policy),
        activate_imported=activate_imported,
        reference_resolution=ops.ReferenceResolution(reference_resolution),
    )
    with errors.translate_google_api_error():
        try:
            report = ops_client.import_(
                uri=clean_uri,
                assets=parsed_assets,
                options=import_opts,
            )
        except ops.BundleError as exc:
            raise errors.OperationFailedError(
                str(exc),
                hint="Check bundle contents and destination permissions.",
            ) from exc

    return models.ConfigApplyOutput(
        bundle_uri=report.uri,
        destination_project_id=report.destination_project_id,
        destination_location=report.destination_location,
        total_created=report.total_created,
        assets=serialize.to_jsonable(report.assets),
        notes=list(report.notes),
    )
