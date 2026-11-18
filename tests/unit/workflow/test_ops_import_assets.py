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

"""Unit tests for per-asset import behaviour.

Split from `test_ops_import.py` only because the two halves together exceed the
module length this project lints for. The assets gathered here are the ones
with behaviour of their own: composite scorecards, reference-carrying analysis
rules, the correlation singleton, and long-running topic models.
"""

from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

from pytest_mock import MockerFixture

# The fixtures are used by injection, not by reference; pylint cannot see that.
from ops_testing import (  # pylint: disable=unused-import
    BUNDLE_URI,
    DEST_LOCATION,
    DEST_PARENT,
    DEST_PROJECT,
    LOCATION,
    PARENT,
    PROJECT,
    SOURCE_ENUM,
    SOURCE_NAME,
    FakeCollection,
    FakeIssueModels,
    FakeSingleton,
    destination,
    fixture_gcs,
    fixture_no_auth,
    install,
    load_bundle,
    make_bundle,
    phrase_matcher,
    written_bundle,
)

from cxidk.workflow import ops



class TestScorecardImport:
    """Scorecards, their single revision, and question tag remapping."""

    @staticmethod
    def _install(
        mocker: MockerFixture,
    ) -> Tuple[FakeCollection, FakeCollection, FakeCollection, FakeCollection]:
        """Wires up the four collections a scorecard import touches.

        Args:
            mocker: The pytest-mock fixture.

        Returns:
            A ``(tags, scorecards, revisions, questions)`` tuple of fakes.
        """
        tags = install(
            mocker,
            "QaQuestionTags",
            FakeCollection([], collection="qaQuestionTags"),
        )
        scorecards = install(
            mocker,
            "QaScorecards",
            FakeCollection([], collection="qaScorecards"),
        )
        revisions = install(
            mocker,
            "ScorecardRevisions",
            FakeCollection(
                [],
                parent=f"{DEST_PARENT}/qaScorecards/sc",
                collection="revisions",
            ),
        )
        questions = install(
            mocker,
            "RevisionQuestions",
            FakeCollection(
                [],
                parent=f"{DEST_PARENT}/qaScorecards/sc/revisions/r",
                collection="qaQuestions",
            ),
        )
        return tags, scorecards, revisions, questions

    @staticmethod
    def _record(
        tags: Optional[List[str]] = None,
        source_enum: str = "QA_SCORECARD_SOURCE_CUSTOMER_DEFINED",
    ) -> Dict[str, Any]:
        """Builds a scorecard bundle record with one question.

        Args:
            tags: Tag values the question should carry.
            source_enum: The scorecard's original, output-only source.

        Returns:
            A bundle record.
        """
        return {
            SOURCE_NAME: f"{PARENT}/qaScorecards/sc1",
            SOURCE_ENUM: source_enum,
            "displayName": "Quality",
            "isDefault": True,
            "_revision": {
                SOURCE_NAME: f"{PARENT}/qaScorecards/sc1/revisions/rev1"
            },
            "_questions": [
                {
                    SOURCE_NAME: (
                        f"{PARENT}/qaScorecards/sc1/revisions/rev1"
                        f"/qaQuestions/q1"
                    ),
                    "abbreviation": "Greeting",
                    "tags": list(tags or []),
                }
            ],
        }

    def test_creates_one_revision_and_its_questions(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """A scorecard without a revision has no questions and does nothing."""
        _, scorecards, revisions, questions = self._install(mocker)
        load_bundle(gcs, make_bundle({"scorecards": [self._record()]}))

        destination().import_(uri=BUNDLE_URI, assets=[ops.Asset.SCORECARDS])

        assert len(scorecards.created) == 1
        assert len(revisions.created) == 1
        assert len(questions.created) == 1

    def test_does_not_claim_the_destination_default_slot(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """`isDefault` would demote whatever the destination shows first."""
        _, scorecards, _, _ = self._install(mocker)
        load_bundle(gcs, make_bundle({"scorecards": [self._record()]}))

        destination().import_(uri=BUNDLE_URI, assets=[ops.Asset.SCORECARDS])

        assert "isDefault" not in scorecards.created[0]

    def test_preserve_default_is_available(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Promoting a whole environment may legitimately want the flag."""
        _, scorecards, _, _ = self._install(mocker)
        load_bundle(gcs, make_bundle({"scorecards": [self._record()]}))

        destination().import_(
            uri=BUNDLE_URI,
            assets=[ops.Asset.SCORECARDS],
            options=ops.ImportOptions(preserve_default=True),
        )

        assert scorecards.created[0]["isDefault"] is True

    def test_records_the_original_source_in_the_description(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """`source` is output-only, so the description is the only place left."""
        _, scorecards, _, _ = self._install(mocker)
        record = self._record(source_enum="QA_SCORECARD_SOURCE_DISCOVERY_ENGINE")
        load_bundle(gcs, make_bundle({"scorecards": [record]}))

        report = destination().import_(
            uri=BUNDLE_URI, assets=[ops.Asset.SCORECARDS]
        )

        assert "[source: QA_SCORECARD_SOURCE_DISCOVERY_ENGINE]" in (
            scorecards.created[0]["description"]
        )
        assert any(
            "output-only" in warning
            for warning in report.assets["scorecards"].warnings
        )

    def test_warns_that_copies_are_untuned(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Tuning depends on conversations the destination does not have."""
        self._install(mocker)
        load_bundle(gcs, make_bundle({"scorecards": [self._record()]}))

        report = destination().import_(
            uri=BUNDLE_URI, assets=[ops.Asset.SCORECARDS]
        )

        assert any(
            "untuned" in warning
            for warning in report.assets["scorecards"].warnings
        )

    def test_repoints_custom_question_tags(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Custom tags are resources, so their names change on import."""
        tags, _, _, questions = self._install(mocker)
        record = self._record(tags=["BUSINESS", f"{PARENT}/qaQuestionTags/t1"])
        load_bundle(
            gcs,
            make_bundle(
                {
                    "qa_question_tags": [
                        {
                            SOURCE_NAME: f"{PARENT}/qaQuestionTags/t1",
                            "displayName": "Compliance",
                        }
                    ],
                    "scorecards": [record],
                }
            ),
        )

        destination().import_(uri=BUNDLE_URI)

        created_tag = f"{DEST_PARENT}/qaQuestionTags/{tags.created_ids[0]}"
        assert questions.created[0]["tags"] == ["BUSINESS", created_tag]

    def test_leaves_built_in_tags_alone(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """'BUSINESS' is a category, not a resource; it needs no remapping."""
        _, _, _, questions = self._install(mocker)
        record = self._record(tags=["BUSINESS", "COMPLIANCE"])
        load_bundle(gcs, make_bundle({"scorecards": [record]}))

        destination().import_(uri=BUNDLE_URI, assets=[ops.Asset.SCORECARDS])

        assert questions.created[0]["tags"] == ["BUSINESS", "COMPLIANCE"]

    def test_drops_an_unmappable_custom_tag_and_says_so(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """A dangling tag reference would point at the source project."""
        _, _, _, questions = self._install(mocker)
        record = self._record(tags=[f"{PARENT}/qaQuestionTags/t1"])
        load_bundle(gcs, make_bundle({"scorecards": [record]}))

        report = destination().import_(
            uri=BUNDLE_URI, assets=[ops.Asset.SCORECARDS]
        )

        assert questions.created[0]["tags"] == []
        assert any(
            "Dropped custom question tag" in warning
            for warning in report.assets["scorecards"].warnings
        )


class TestAnalysisRuleReferences:
    """Analysis rules are the only asset carrying cross-resource pointers."""

    @staticmethod
    def _rule(selector: Dict[str, Any]) -> Dict[str, Any]:
        """Builds an analysis rule bundle record.

        Args:
            selector: The `annotatorSelector` payload.

        Returns:
            A bundle record.
        """
        return {
            SOURCE_NAME: f"{PARENT}/analysisRules/ar1",
            "displayName": "Analyse everything",
            "active": True,
            "analysisPercentage": 0.5,
            "annotatorSelector": selector,
        }

    @staticmethod
    def _install(mocker: MockerFixture) -> FakeCollection:
        """Installs the analysis rule collection.

        Args:
            mocker: The pytest-mock fixture.

        Returns:
            The analysis rule fake.
        """
        return install(
            mocker,
            "AnalysisRules",
            FakeCollection([], collection="analysisRules"),
        )

    def test_repoints_references_at_the_imported_copies(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """A verbatim reference would aim the rule at the source project."""
        matchers = install(
            mocker,
            "PhraseMatchers",
            FakeCollection([], collection="phraseMatchers"),
        )
        rules = self._install(mocker)
        load_bundle(
            gcs,
            make_bundle(
                {
                    "phrase_matchers": [phrase_matcher("pm1")],
                    "analysis_rules": [
                        self._rule(
                            {"phraseMatchers": [f"{PARENT}/phraseMatchers/pm1"]}
                        )
                    ],
                }
            ),
        )

        destination().import_(uri=BUNDLE_URI)

        created = f"{DEST_PARENT}/phraseMatchers/{matchers.created_ids[0]}"
        assert rules.created[0]["annotatorSelector"]["phraseMatchers"] == [created]

    def test_strict_refuses_rather_than_prunes(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Pruning widens the rule, so the default must not do it silently."""
        rules = self._install(mocker)
        load_bundle(
            gcs,
            make_bundle(
                {
                    "analysis_rules": [
                        self._rule(
                            {"phraseMatchers": [f"{PARENT}/phraseMatchers/pm1"]}
                        )
                    ]
                }
            ),
        )

        report = destination().import_(uri=BUNDLE_URI)

        assert not rules.created
        assert report.assets["analysis_rules"].skipped == 1
        assert report.failed is True

    def test_prune_policy_empties_the_list(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Callers can opt into pruning once they know what it means."""
        rules = self._install(mocker)
        load_bundle(
            gcs,
            make_bundle(
                {
                    "analysis_rules": [
                        self._rule(
                            {"phraseMatchers": [f"{PARENT}/phraseMatchers/pm1"]}
                        )
                    ]
                }
            ),
        )

        destination().import_(
            uri=BUNDLE_URI,
            options=ops.ImportOptions(
                reference_resolution=ops.ReferenceResolution.PRUNE
            ),
        )

        assert rules.created[0]["annotatorSelector"]["phraseMatchers"] == []

    def test_uses_the_external_map_for_dialogflow_references(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Conversation profiles live in Dialogflow and cannot be created here."""
        rules = self._install(mocker)
        source_profile = f"{PARENT}/conversationProfiles/cp1"
        target_profile = f"{DEST_PARENT}/conversationProfiles/cp9"
        load_bundle(
            gcs,
            make_bundle(
                {
                    "analysis_rules": [
                        self._rule(
                            {
                                "summarizationConfig": {
                                    "conversationProfile": source_profile
                                }
                            }
                        )
                    ]
                }
            ),
        )

        destination().import_(
            uri=BUNDLE_URI,
            options=ops.ImportOptions(
                external_reference_map={source_profile: target_profile}
            ),
        )

        selector = rules.created[0]["annotatorSelector"]
        assert selector["summarizationConfig"]["conversationProfile"] == (
            target_profile
        )

    def test_strict_refuses_an_unmapped_dialogflow_reference(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Summarization pointing at another project is a real misconfiguration."""
        rules = self._install(mocker)
        load_bundle(
            gcs,
            make_bundle(
                {
                    "analysis_rules": [
                        self._rule(
                            {
                                "summarizationConfig": {
                                    "generator": f"{PARENT}/generators/g1"
                                }
                            }
                        )
                    ]
                }
            ),
        )

        report = destination().import_(uri=BUNDLE_URI)

        assert not rules.created
        assert any(
            "external_reference_map" in error
            for error in report.assets["analysis_rules"].errors
        )

    def test_notes_when_referenced_assets_are_not_in_the_selection(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Importing rules alone cannot possibly resolve their references."""
        self._install(mocker)
        load_bundle(gcs, make_bundle({"analysis_rules": []}))

        report = destination().import_(uri=BUNDLE_URI)

        assert any("phrase_matchers" in note for note in report.notes)


class TestCorrelationConfig:
    """The singleton exception, where append is the closest thing to create."""

    @staticmethod
    def _bundle(rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Builds a correlation configuration bundle.

        Args:
            rules: Correlation rules to carry.

        Returns:
            A bundle document.
        """
        return make_bundle(
            {
                "correlation_config": {
                    "fullConversationConfig": {"correlationRules": rules}
                }
            }
        )

    def test_export_keeps_only_active_rules(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Active-only export reaches inside the singleton too."""
        install(
            mocker,
            "CorrelationConfig",
            FakeSingleton(
                [
                    {"ruleId": "r1", "active": True},
                    {"ruleId": "r2", "active": False},
                ]
            ),
        )

        ops.ConfigOps(PROJECT, LOCATION).export(
            uri=BUNDLE_URI, assets=[ops.Asset.CORRELATION_CONFIG]
        )

        document = written_bundle(gcs)
        rules = document["assets"]["correlation_config"][
            "fullConversationConfig"
        ]["correlationRules"]
        assert [rule["ruleId"] for rule in rules] == ["r1"]

    def test_import_appends_without_touching_existing_rules(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Read-modify-write must not drop what the destination already had."""
        existing = {"ruleId": "keep-me", "active": True}
        fake = install(mocker, "CorrelationConfig", FakeSingleton([existing]))
        load_bundle(gcs, self._bundle([{"ruleId": "r1", "active": True}]))

        destination().import_(uri=BUNDLE_URI)

        written = fake.updates[0]["fullConversationConfig"]["correlationRules"]
        assert written[0] == existing
        assert len(written) == 2

    def test_import_mints_fresh_rule_ids(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """`ruleId` is caller-supplied, so a reused one would clash."""
        fake = install(mocker, "CorrelationConfig", FakeSingleton([]))
        load_bundle(gcs, self._bundle([{"ruleId": "r1", "active": True}]))

        destination().import_(uri=BUNDLE_URI)

        written = fake.updates[0]["fullConversationConfig"]["correlationRules"]
        assert written[0]["ruleId"].startswith("r1-")
        assert written[0]["ruleId"] != "r1"
        assert written[0]["active"] is False

    def test_dry_run_does_not_update(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """The singleton is the easiest asset to damage by accident."""
        fake = install(mocker, "CorrelationConfig", FakeSingleton([]))
        load_bundle(gcs, self._bundle([{"ruleId": "r1", "active": True}]))

        report = destination().import_(
            uri=BUNDLE_URI, options=ops.ImportOptions(dry_run=True)
        )

        assert not fake.updates
        assert report.assets["correlation_config"].count == 1


class TestTopicModels:
    """Topic models are long-running, billable, and useless when untrained."""

    @staticmethod
    def _lro(mocker: MockerFixture, name: str) -> None:
        """Patches the long-running operation helper to return a resource.

        Args:
            mocker: The pytest-mock fixture.
            name: Resource name the completed operation should yield.
        """
        lro = mocker.patch("cxidk.wrapper.insights.LongRunningOperation")
        lro.from_operation.return_value.result.return_value = {"name": name}

    def test_export_stages_a_trained_model_when_given_a_bucket(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """The native round-trip is the only way to carry training across."""
        fake = install(
            mocker,
            "IssueModels",
            FakeIssueModels(
                [{"name": f"{PARENT}/issueModels/m1", "state": "DEPLOYED"}]
            ),
        )
        self._lro(mocker, f"{PARENT}/operations/1")
        del gcs  # Requested so Cloud Storage is patched; unused directly.

        ops.ConfigOps(PROJECT, LOCATION).export(
            uri=BUNDLE_URI,
            assets=[ops.Asset.ISSUE_MODELS],
            options=ops.ExportOptions(gcs_bucket="staging"),
        )

        assert fake.exported == [("m1", "gs://staging/issue-models/m1.pb")]

    def test_import_uses_the_native_path_when_a_model_is_staged(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """A metadata-only create would throw the training away."""
        fake = install(mocker, "IssueModels", FakeIssueModels([]))
        self._lro(mocker, f"{DEST_PARENT}/issueModels/new")
        load_bundle(
            gcs,
            make_bundle(
                {
                    "issue_models": [
                        {
                            SOURCE_NAME: f"{PARENT}/issueModels/m1",
                            "displayName": "Topics",
                            "_gcsModelUri": "gs://staging/issue-models/m1.pb",
                        }
                    ]
                }
            ),
        )

        destination().import_(uri=BUNDLE_URI)

        assert fake.imported == [("gs://staging/issue-models/m1.pb", True)]
        assert not fake.created

    def test_import_warns_when_only_metadata_is_available(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """An untrained model looks fine and produces nothing."""
        fake = install(mocker, "IssueModels", FakeIssueModels([]))
        self._lro(mocker, f"{DEST_PARENT}/issueModels/new")
        load_bundle(
            gcs,
            make_bundle(
                {
                    "issue_models": [
                        {
                            SOURCE_NAME: f"{PARENT}/issueModels/m1",
                            "displayName": "Topics",
                        }
                    ]
                }
            ),
        )

        report = destination().import_(uri=BUNDLE_URI)

        assert len(fake.created) == 1
        assert any(
            "untrained" in warning
            for warning in report.assets["issue_models"].warnings
        )

    def test_import_never_deploys(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Deployment is billable, so it stays an explicit follow-up action."""
        install(mocker, "IssueModels", FakeIssueModels([]))
        self._lro(mocker, f"{DEST_PARENT}/issueModels/new")
        load_bundle(
            gcs,
            make_bundle(
                {
                    "issue_models": [
                        {
                            SOURCE_NAME: f"{PARENT}/issueModels/m1",
                            "displayName": "Topics",
                            "_gcsModelUri": "gs://staging/issue-models/m1.pb",
                        }
                    ]
                }
            ),
        )

        report = destination().import_(uri=BUNDLE_URI)

        assert any(
            "undeployed" in warning
            for warning in report.assets["issue_models"].warnings
        )
