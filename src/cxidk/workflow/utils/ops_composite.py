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

"""Handlers for configuration assets that are not flat collections.

Three assets need more than create-one-resource-per-record:

  * Scorecards are composite. Each one owns a revision, which in turn owns a
    set of questions, so importing one scorecard means three levels of
    creates and a tag remapping pass.
  * Analysis rules carry references to other resources by full resource name,
    which must be repointed at whatever this run created.
  * The correlation configuration is a singleton with no create method, so it
    is appended to rather than created.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from cxidk.wrapper import insights
from cxidk.workflow.utils.ops_handlers import AssetHandler
from cxidk.workflow.utils.ops_types import (
    ALL_SCORECARD_SOURCES,
    SOURCE_ENUM_KEY,
    SOURCE_NAME_KEY,
    Asset,
    AssetOutcome,
    ExportOptions,
    ImportOptions,
    NameClash,
    ReferenceMap,
    ReferenceResolution,
    UnresolvedReferenceError,
    apply_naming,
    new_resource_id,
    payload_of,
    resource_id_from_name,
    strip_fields,
)

logger = logging.getLogger(__name__)


class ScorecardsHandler(AssetHandler):
    """QA scorecards, their latest revision, and that revision's questions.

    Scope is the portable definition only. Example-conversation configuration,
    fine-tuning metadata and trained metrics are all stripped, so an imported
    scorecard arrives untuned. That is the intended outcome: tuning depends on
    conversations that do not exist in the destination project.

    All four scorecard sources are exported, including Discovery Engine and
    intent-taxonomy scorecards. Note that `QaScorecard.source` is output-only,
    so those copies necessarily land as customer-defined; the original value is
    preserved in the bundle and stamped into the description.
    """

    asset = Asset.SCORECARDS
    depends_on = (Asset.QA_QUESTION_TAGS,)
    wrapper_name = "QaScorecards"
    active_field = None
    stripped_fields = ("source",)

    #: Question fields that would drag training data or trained artifacts into
    #: the bundle. Removing them is a scope boundary, not mere hygiene.
    QUESTION_STRIPPED_FIELDS: Tuple[str, ...] = (
        "tuningMetadata",
        "metrics",
        "qaQuestionDataOptions",
    )

    _REVISION_KEY = "_revision"
    _QUESTIONS_KEY = "_questions"

    def export(self, options: ExportOptions) -> List[Dict[str, Any]]:
        """Exports scorecards with their latest revision and questions.

        Args:
            options: Export options. `scorecard_sources` narrows the selection;
                `active_only` does not apply, as scorecards have no active flag.

        Returns:
            A list of scorecard bundle records.
        """
        sources = list(options.scorecard_sources or ALL_SCORECARD_SOURCES)
        client = self.client

        records = []
        for scorecard in client.list_by_source(sources=sources):
            record = self._to_record(scorecard)
            record[SOURCE_ENUM_KEY] = scorecard.get("source", "")

            scorecard_id = resource_id_from_name(scorecard.get("name", ""))
            revision = self.environment.collection(
                insights.ScorecardRevisions, scorecard_id=scorecard_id
            ).get_latest()

            if not revision:
                logger.warning(
                    "Scorecard %r has no revisions; exporting definition only.",
                    scorecard.get("displayName"),
                )
                record[self._REVISION_KEY] = {}
                record[self._QUESTIONS_KEY] = []
                records.append(record)
                continue

            record[self._REVISION_KEY] = {
                SOURCE_NAME_KEY: revision.get("name", "")
            }
            record[self._QUESTIONS_KEY] = self._export_questions(
                scorecard_id, resource_id_from_name(revision.get("name", ""))
            )
            records.append(record)

        return records

    def _export_questions(
        self, scorecard_id: str, revision_id: str
    ) -> List[Dict[str, Any]]:
        """Exports the questions belonging to one scorecard revision.

        Args:
            scorecard_id: Bare ID of the parent scorecard.
            revision_id: Bare ID of the parent revision.

        Returns:
            A list of sanitized question records.
        """
        questions = self.environment.collection(
            insights.RevisionQuestions,
            scorecard_id=scorecard_id,
            revision_id=revision_id,
        ).list()

        exported = []
        for question in questions:
            record = strip_fields(question, self.QUESTION_STRIPPED_FIELDS)
            record[SOURCE_NAME_KEY] = question.get("name", "")
            exported.append(record)
        return exported

    def import_(
        self,
        records: List[Dict[str, Any]],
        options: ImportOptions,
        reference_map: ReferenceMap,
        source_project: str,
    ) -> AssetOutcome:
        """Creates scorecards, one revision each, and their questions.

        Args:
            records: Scorecard bundle records.
            options: Import options.
            reference_map: Map updated with scorecard and revision names.
            source_project: Project the bundle came from.

        Returns:
            The outcome for scorecards.
        """
        outcome = AssetOutcome(asset=str(self.asset))
        client = self.client

        for record in records:
            body = self._scorecard_body(record, options, source_project)

            assigned_id = new_resource_id(
                resource_id_from_name(record.get(SOURCE_NAME_KEY, ""))
            )
            if options.dry_run:
                outcome.count += 1
                synthetic_sc = f"{self.environment.parent}/qaScorecards/{assigned_id}"
                reference_map.record(record.get(SOURCE_NAME_KEY, ""), synthetic_sc)
                revision_source = (record.get(self._REVISION_KEY) or {}).get(
                    SOURCE_NAME_KEY, ""
                )
                if revision_source:
                    rev_id = new_resource_id(resource_id_from_name(revision_source))
                    reference_map.record(
                        revision_source, f"{synthetic_sc}/revisions/{rev_id}"
                    )
                for question in record.get(self._QUESTIONS_KEY) or []:
                    self._remap_tags(
                        question.get("tags") or [], reference_map, outcome
                    )
                continue

            created = client.create(
                body=body,
                resource_id=assigned_id,
            )
            self._record_created(record, created, outcome, reference_map)
            self._import_revision(record, created, outcome, reference_map)

            if record.get(SOURCE_ENUM_KEY) not in (
                "",
                "QA_SCORECARD_SOURCE_CUSTOMER_DEFINED",
                "QA_SCORECARD_SOURCE_UNSPECIFIED",
            ):
                outcome.warnings.append(
                    f"{record.get('displayName')!r} originated from "
                    f"{record[SOURCE_ENUM_KEY]} but `source` is output-only, so "
                    f"the copy is customer-defined."
                )
            outcome.warnings.append(
                f"{record.get('displayName')!r} was created untuned; tuning is "
                f"environment-specific and out of scope."
            )

        return outcome

    def _scorecard_body(
        self,
        record: Dict[str, Any],
        options: ImportOptions,
        source_project: str,
    ) -> Dict[str, Any]:
        """Builds the scorecard create body.

        Args:
            record: The scorecard bundle record.
            options: Import options.
            source_project: Project the bundle came from.

        Returns:
            The request body.
        """
        body = payload_of(record)

        if body.get("displayName"):
            body["displayName"] = apply_naming(
                body["displayName"], options, source_project
            )

        # `isDefault` would otherwise demote whatever scorecard the destination
        # currently presents first.
        if not options.preserve_default:
            body.pop("isDefault", None)

        original_source = record.get(SOURCE_ENUM_KEY)
        if original_source and original_source != (
            "QA_SCORECARD_SOURCE_CUSTOMER_DEFINED"
        ):
            marker = f"[source: {original_source}]"
            description = body.get("description", "")
            if marker not in description:
                body["description"] = f"{description} {marker}".strip()

        return body

    def _import_revision(
        self,
        record: Dict[str, Any],
        created_scorecard: Dict[str, Any],
        outcome: AssetOutcome,
        reference_map: ReferenceMap,
    ) -> None:
        """Creates one revision under a new scorecard and populates questions.

        Args:
            record: The scorecard bundle record.
            created_scorecard: API response for the scorecard create.
            outcome: Outcome accumulating warnings.
            reference_map: Map updated with the revision correspondence.
        """
        revision_record = record.get(self._REVISION_KEY) or {}
        scorecard_id = resource_id_from_name(created_scorecard.get("name", ""))

        revisions = self.environment.collection(
            insights.ScorecardRevisions, scorecard_id=scorecard_id
        )
        created_revision = revisions.create(
            body={},
            resource_id=new_resource_id(
                resource_id_from_name(revision_record.get(SOURCE_NAME_KEY, ""))
            ),
        )

        reference_map.record(
            revision_record.get(SOURCE_NAME_KEY, ""),
            created_revision.get("name", ""),
        )

        revision_id = resource_id_from_name(created_revision.get("name", ""))
        questions = self.environment.collection(
            insights.RevisionQuestions,
            scorecard_id=scorecard_id,
            revision_id=revision_id,
        )

        for question in record.get(self._QUESTIONS_KEY) or []:
            body = payload_of(question)
            body["tags"] = self._remap_tags(
                body.get("tags") or [], reference_map, outcome
            )
            questions.create(
                body=body,
                resource_id=new_resource_id(
                    resource_id_from_name(question.get(SOURCE_NAME_KEY, ""))
                ),
            )

    @staticmethod
    def _remap_tags(
        tags: List[str],
        reference_map: ReferenceMap,
        outcome: AssetOutcome,
    ) -> List[str]:
        """Rewrites custom tag references, leaving built-in tags untouched.

        `QaQuestion.tags` mixes two kinds of value. Built-in categories are bare
        strings such as 'BUSINESS' and mean the same thing in every project.
        Custom tags are full resource names and must be repointed at the copies
        created in this run. The discriminator is simply the presence of a '/'.

        Args:
            tags: The tag values from the source question.
            reference_map: Map of created question tags.
            outcome: Outcome collecting a warning for each dropped tag.

        Returns:
            The rewritten tag list, preserving order.
        """
        remapped = []
        for tag in tags:
            if "/" not in tag:
                remapped.append(tag)
                continue
            resolved = reference_map.resolve(tag)
            if resolved:
                remapped.append(resolved)
            else:
                message = (
                    f"Dropped custom question tag {tag!r}: no destination "
                    f"equivalent was created. Include "
                    f"Asset.QA_QUESTION_TAGS in the import to keep it."
                )
                logger.warning(message)
                outcome.warnings.append(message)
        return remapped


class AnalysisRulesHandler(AssetHandler):
    """Analysis rules, the only asset carrying cross-resource references.

    `annotatorSelector` points at phrase matchers, topic models and scorecard
    revisions by full resource name. Those names embed the source project and a
    source-assigned ID, so replaying them verbatim aims the rule at the origin
    environment.

    One subtlety makes silent pruning dangerous. Per the API, an empty
    `phraseMatchers` list means "use every active phrase matcher", and an empty
    `issueModels` list means "use the most recently deployed topic model".
    Dropping a dangling reference therefore *widens* a rule rather than
    narrowing it, which is why STRICT refuses rather than prunes by default.
    """

    asset = Asset.ANALYSIS_RULES
    depends_on = (
        Asset.PHRASE_MATCHERS,
        Asset.ISSUE_MODELS,
        Asset.SCORECARDS,
    )
    wrapper_name = "AnalysisRules"

    #: Reference fields holding a list of resource names, and the empty-list
    #: meaning that makes pruning them hazardous.
    _LIST_REFERENCES: Tuple[Tuple[Tuple[str, ...], str], ...] = (
        (
            ("phraseMatchers",),
            "an empty list means ALL active phrase matchers",
        ),
        (
            ("issueModels",),
            "an empty list means the most recently deployed topic model",
        ),
        (
            ("qaConfig", "scorecardList", "qaScorecardRevisions"),
            "an empty list changes which scorecards are applied",
        ),
    )

    #: Dialogflow references this devkit cannot create.
    _EXTERNAL_REFERENCES: Tuple[Tuple[str, ...], ...] = (
        ("summarizationConfig", "conversationProfile"),
        ("summarizationConfig", "generator"),
    )

    def _prepare(
        self,
        record: Dict[str, Any],
        options: ImportOptions,
        reference_map: ReferenceMap,
        source_project: str,
    ) -> Dict[str, Any]:
        """Builds the create body with every reference repointed.

        Args:
            record: The analysis rule bundle record.
            options: Import options, including reference resolution policy.
            reference_map: Map of resources created earlier in this run.
            source_project: Project the bundle came from.

        Returns:
            The request body.

        Raises:
            UnresolvedReferenceError: Under STRICT, when a reference cannot be
                resolved.
        """
        body = super()._prepare(record, options, reference_map, source_project)
        selector = body.get("annotatorSelector")
        if not selector:
            return body

        for path, empty_meaning in self._LIST_REFERENCES:
            self._rewrite_list(
                selector, path, empty_meaning, options, reference_map, record
            )

        for path in self._EXTERNAL_REFERENCES:
            self._rewrite_external(selector, path, options, record)

        return body

    def _rewrite_list(
        self,
        selector: Dict[str, Any],
        path: Tuple[str, ...],
        empty_meaning: str,
        options: ImportOptions,
        reference_map: ReferenceMap,
        record: Dict[str, Any],
    ) -> None:
        """Rewrites one list-valued reference field in place.

        Args:
            selector: The `annotatorSelector` dictionary.
            path: Key path to the list within the selector.
            empty_meaning: What an empty list means to the API, used in
                warnings.
            options: Import options.
            reference_map: Map of created resources.
            record: The originating record, for error messages.

        Raises:
            UnresolvedReferenceError: Under STRICT, when a name is unresolved.
        """
        container = self._descend(selector, path[:-1])
        if container is None:
            return

        names = container.get(path[-1])
        if not names:
            return

        resolved_names = []
        for name in names:
            resolved = reference_map.resolve(name)
            if resolved:
                resolved_names.append(resolved)
                continue

            location = ".".join(path)
            message = (
                f"Analysis rule {record.get('displayName')!r} references "
                f"{name!r} in {location}, which was not created by this import."
            )
            if options.reference_resolution == ReferenceResolution.STRICT:
                raise UnresolvedReferenceError(message)
            logger.warning(
                "%s Pruning it, but note that %s, so the rule becomes BROADER "
                "rather than narrower.",
                message,
                empty_meaning,
            )

        container[path[-1]] = resolved_names

    def _rewrite_external(
        self,
        selector: Dict[str, Any],
        path: Tuple[str, ...],
        options: ImportOptions,
        record: Dict[str, Any],
    ) -> None:
        """Rewrites a Dialogflow reference from the external mapping.

        Args:
            selector: The `annotatorSelector` dictionary.
            path: Key path to the scalar reference.
            options: Import options carrying `external_reference_map`.
            record: The originating record, for error messages.

        Raises:
            UnresolvedReferenceError: Under STRICT, when no mapping exists.
        """
        container = self._descend(selector, path[:-1])
        if container is None:
            return

        value = container.get(path[-1])
        if not value:
            return

        mapped = options.external_reference_map.get(value)
        if mapped:
            container[path[-1]] = mapped
            return

        message = (
            f"Analysis rule {record.get('displayName')!r} references Dialogflow "
            f"resource {value!r} in {'.'.join(path)}. This devkit cannot create "
            f"it; supply a mapping via external_reference_map."
        )
        if options.reference_resolution == ReferenceResolution.STRICT:
            raise UnresolvedReferenceError(message)
        logger.warning("%s Removing the reference.", message)
        container.pop(path[-1], None)

    @staticmethod
    def _descend(
        root: Dict[str, Any], path: Tuple[str, ...]
    ) -> Optional[Dict[str, Any]]:
        """Walks a nested dictionary, returning None if the path is absent.

        Args:
            root: The dictionary to walk.
            path: Successive keys to follow.

        Returns:
            The nested dictionary, or None when any key is missing.
        """
        node: Any = root
        for key in path:
            if not isinstance(node, dict) or key not in node:
                return None
            node = node[key]
        return node if isinstance(node, dict) else None


class CorrelationConfigHandler(AssetHandler):
    """The correlation configuration singleton.

    This is the one asset that cannot be literally create-only: the API exposes
    no create method, only get and update. The closest faithful behaviour is to
    append rules under freshly minted IDs and leave every pre-existing rule
    exactly as it was.
    """

    asset = Asset.CORRELATION_CONFIG
    wrapper_name = "CorrelationConfig"
    active_field = None

    _RULES_PATH = "fullConversationConfig"

    def export(self, options: ExportOptions) -> Dict[str, Any]:
        """Reads the correlation configuration.

        Args:
            options: Export options; `active_only` filters the nested rules.

        Returns:
            A record holding the correlation rules, empty when unconfigured.
        """
        config = self.client.get()
        rules = (config.get(self._RULES_PATH) or {}).get("correlationRules") or []

        if options.active_only:
            rules = [rule for rule in rules if rule.get("active")]

        return {self._RULES_PATH: {"correlationRules": rules}}

    def scan_names(self, records: List[Dict[str, Any]]) -> List[NameClash]:
        """Correlation rules have no display name, so nothing can clash.

        Args:
            records: Unused.

        Returns:
            An empty list.
        """
        del records
        return []

    def import_rules(
        self,
        record: Dict[str, Any],
        options: ImportOptions,
    ) -> AssetOutcome:
        """Appends the bundle's correlation rules to the destination config.

        Args:
            record: The correlation config bundle record.
            options: Import options.

        Returns:
            The outcome for the correlation configuration.
        """
        outcome = AssetOutcome(asset=str(self.asset))
        incoming = (record.get(self._RULES_PATH) or {}).get(
            "correlationRules"
        ) or []
        if not incoming:
            return outcome

        client = self.client
        existing_config = client.get()
        existing_rules = (
            existing_config.get(self._RULES_PATH) or {}
        ).get("correlationRules") or []

        appended = list(existing_rules)
        for rule in incoming:
            new_rule = payload_of(rule)
            new_rule["ruleId"] = new_resource_id(rule.get("ruleId", "rule"))
            new_rule["active"] = options.activate_imported
            appended.append(new_rule)
            outcome.count += 1

        if options.dry_run:
            return outcome

        client.update(
            body={self._RULES_PATH: {"correlationRules": appended}},
            update_mask=self._RULES_PATH,
        )
        outcome.warnings.append(
            f"{len(existing_rules)} pre-existing correlation rules were left "
            f"untouched. This asset is a singleton updated read-modify-write, "
            f"so concurrent imports can lose rules."
        )
        return outcome
