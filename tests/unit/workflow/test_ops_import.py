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

"""Unit tests for the import half of the configuration workflow.

The invariant under test here is that import creates and only creates: no
update, no merge, no overwrite, no reuse of source IDs. Per-asset behaviour
lives in `test_ops_import_assets.py`; this file covers the shared machinery and
the read-only preview.
"""

from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest
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
)

from cxidk.workflow import ops



class TestImportIsCreateOnly:
    """The central invariant: import creates, and only creates."""

    @staticmethod
    def _run(
        mocker: MockerFixture,
        gcs_client: MagicMock,
        records: List[Dict[str, Any]],
        options: Optional[ops.ImportOptions] = None,
    ) -> Tuple[FakeCollection, ops.ImportReport]:
        """Imports phrase matchers from a one-asset bundle.

        Args:
            mocker: The pytest-mock fixture.
            gcs_client: The mock `Gcs` instance.
            records: Bundle records to import.
            options: Import options.

        Returns:
            A ``(fake collection, report)`` tuple.
        """
        fake = install(
            mocker,
            "PhraseMatchers",
            FakeCollection([], collection="phraseMatchers"),
        )
        load_bundle(gcs_client, make_bundle({"phrase_matchers": records}))
        report = destination().import_(uri=BUNDLE_URI, options=options)
        return fake, report

    def test_never_reuses_a_source_resource_id(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Reusing IDs would make the second import fail with ALREADY_EXISTS."""
        fake, _ = self._run(mocker, gcs, [phrase_matcher()])

        assigned = fake.created_ids[0]
        assert assigned != "angry"
        assert assigned is not None and assigned.startswith("angry-")

    def test_repeating_an_import_creates_further_copies(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Create-only means a second run duplicates rather than updates."""
        fake = install(
            mocker,
            "PhraseMatchers",
            FakeCollection([], collection="phraseMatchers"),
        )
        load_bundle(gcs, make_bundle({"phrase_matchers": [phrase_matcher()]}))

        client = destination()
        client.import_(uri=BUNDLE_URI)
        client.import_(uri=BUNDLE_URI)

        assert len(fake.created) == 2
        assert fake.created_ids[0] != fake.created_ids[1]

    def test_labels_the_copy_by_default(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """A suffix is what makes two same-named resources tellable apart."""
        fake, _ = self._run(mocker, gcs, [phrase_matcher()])

        assert fake.created[0]["displayName"].startswith("Angry customer (imported ")

    def test_duplicate_policy_keeps_the_source_name(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Some customers want byte-identical names across environments."""
        fake, _ = self._run(
            mocker,
            gcs,
            [phrase_matcher()],
            ops.ImportOptions(naming=ops.NamingPolicy.DUPLICATE),
        )

        assert fake.created[0]["displayName"] == "Angry customer"

    def test_copies_arrive_inactive(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Active-only export means every record was live at the source."""
        fake, report = self._run(mocker, gcs, [phrase_matcher()])

        assert fake.created[0]["active"] is False
        assert any("created inactive" in note for note in report.notes)

    def test_activation_is_opt_in(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Callers who want live copies must say so."""
        fake, _ = self._run(
            mocker,
            gcs,
            [phrase_matcher()],
            ops.ImportOptions(activate_imported=True),
        )

        assert fake.created[0]["active"] is True

    def test_dry_run_writes_nothing_but_still_counts(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """A dry run has to be useful without being destructive."""
        fake, report = self._run(
            mocker, gcs, [phrase_matcher()], ops.ImportOptions(dry_run=True)
        )

        assert not fake.created
        assert report.assets["phrase_matchers"].count == 1
        assert report.dry_run is True

    def test_dry_run_resolves_cross_asset_references_within_bundle(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """A dry run must not falsely fail STRICT references included in the bundle."""
        matchers = install(
            mocker,
            "PhraseMatchers",
            FakeCollection([], collection="phraseMatchers"),
        )
        rules = install(
            mocker,
            "AnalysisRules",
            FakeCollection([], collection="analysisRules"),
        )
        load_bundle(
            gcs,
            make_bundle(
                {
                    "phrase_matchers": [phrase_matcher("pm1")],
                    "analysis_rules": [
                        {
                            SOURCE_NAME: f"{PARENT}/analysisRules/ar1",
                            "displayName": "Rule 1",
                            "annotatorSelector": {
                                "phraseMatchers": [
                                    f"{PARENT}/phraseMatchers/pm1"
                                ]
                            },
                        }
                    ],
                }
            ),
        )

        report = destination().import_(
            uri=BUNDLE_URI, options=ops.ImportOptions(dry_run=True)
        )

        assert not matchers.created
        assert not rules.created
        assert report.failed is False
        assert report.total_created == 2

    def test_strips_bundle_internal_keys(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Bookkeeping keys are ours; the API would reject them."""
        fake, _ = self._run(mocker, gcs, [phrase_matcher()])

        assert not [key for key in fake.created[0] if key.startswith("_")]

    def test_stamps_provenance_into_version_tag(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Manual cleanup needs a way to find a previous import's copies."""
        fake, _ = self._run(mocker, gcs, [phrase_matcher()])

        assert fake.created[0]["versionTag"] == "imported:angry"

    def test_report_states_the_semantics(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """The report is where a surprised operator looks first."""
        _, report = self._run(mocker, gcs, [phrase_matcher()])

        assert any("create-only" in note for note in report.notes)
        assert report.total_created == 1
        assert report.failed is False


class TestBundleValidation:
    """Bundles are rejected loudly rather than partially applied."""

    def test_rejects_an_unknown_schema_version(self, gcs: MagicMock) -> None:
        """A newer bundle may mean something different by the same keys."""
        load_bundle(gcs, make_bundle({"phrase_matchers": []}, schema_version=99))

        with pytest.raises(ops.BundleError, match="schema_version"):
            destination().import_(uri=BUNDLE_URI)

    def test_rejects_a_bundle_without_a_manifest(self, gcs: MagicMock) -> None:
        """Without a manifest there is no way to know what a bundle holds."""
        load_bundle(gcs, {"assets": {}})

        with pytest.raises(ops.BundleError, match="no manifest"):
            destination().import_(uri=BUNDLE_URI)

    def test_rejects_a_bundle_without_an_assets_section(
        self, gcs: MagicMock
    ) -> None:
        """A manifest alone describes an import that cannot happen."""
        document = make_bundle({"phrase_matchers": []})
        del document["assets"]
        load_bundle(gcs, document)

        with pytest.raises(ops.BundleError, match="no assets section"):
            destination().import_(uri=BUNDLE_URI)

    def test_rejects_a_request_for_an_absent_asset(self, gcs: MagicMock) -> None:
        """Silently importing nothing would look like success."""
        load_bundle(gcs, make_bundle({"phrase_matchers": []}))

        with pytest.raises(ops.BundleError, match="does not contain"):
            destination().import_(uri=BUNDLE_URI, assets=[ops.Asset.SCORECARDS])


class TestPlan:
    """The preview exists so surprises happen before the writes, not after."""

    def test_counts_without_writing_anything(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """A plan that wrote would defeat its own purpose."""
        fake = install(
            mocker,
            "PhraseMatchers",
            FakeCollection([], collection="phraseMatchers"),
        )
        load_bundle(gcs, make_bundle({"phrase_matchers": [phrase_matcher()]}))

        report = destination().plan(uri=BUNDLE_URI)

        assert report.will_create == {"phrase_matchers": 1}
        assert not fake.created

    def test_reports_display_names_already_in_use(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Advisory, but it is the moment to choose a naming policy."""
        install(
            mocker,
            "PhraseMatchers",
            FakeCollection(
                [
                    {
                        "name": f"{DEST_PARENT}/phraseMatchers/existing",
                        "displayName": "Angry customer",
                    }
                ],
                collection="phraseMatchers",
            ),
        )
        load_bundle(gcs, make_bundle({"phrase_matchers": [phrase_matcher()]}))

        report = destination().plan(uri=BUNDLE_URI)

        assert len(report.name_clashes) == 1
        assert report.name_clashes[0].display_name == "Angry customer"
        assert "advisory" in report.summary()

    def test_flags_importing_into_the_source_environment(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Same project and region means a plain duplication of everything."""
        install(
            mocker,
            "PhraseMatchers",
            FakeCollection([], collection="phraseMatchers"),
        )
        load_bundle(gcs, make_bundle({"phrase_matchers": [phrase_matcher()]}))

        report = ops.ConfigOps(PROJECT, LOCATION).plan(uri=BUNDLE_URI)

        assert any("duplicate" in note for note in report.cost_notes)

    def test_translates_the_analysis_fraction_into_a_percentage(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """`analysisPercentage` is a fraction in [0, 1] and reads as a trap."""
        install(
            mocker,
            "AnalysisRules",
            FakeCollection([], collection="analysisRules"),
        )
        load_bundle(
            gcs,
            make_bundle(
                {
                    "analysis_rules": [
                        {
                            SOURCE_NAME: f"{PARENT}/analysisRules/ar1",
                            "displayName": "Everything",
                            "analysisPercentage": 1.0,
                        }
                    ]
                }
            ),
        )

        report = destination().plan(
            uri=BUNDLE_URI, options=ops.ImportOptions(activate_imported=True)
        )

        assert any("100.0% of conversations" in note for note in report.cost_notes)

    def test_says_when_nothing_will_run(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Inactive imports are safe, and that is worth stating too."""
        install(
            mocker,
            "AnalysisRules",
            FakeCollection([], collection="analysisRules"),
        )
        load_bundle(
            gcs,
            make_bundle(
                {
                    "analysis_rules": [
                        {
                            SOURCE_NAME: f"{PARENT}/analysisRules/ar1",
                            "displayName": "Everything",
                            "analysisPercentage": 1.0,
                        }
                    ]
                }
            ),
        )

        report = destination().plan(uri=BUNDLE_URI)

        assert any("INACTIVE" in note for note in report.cost_notes)

    def test_notes_that_topic_models_arrive_undeployed(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """The absence of a bill is as surprising as its presence."""
        install(mocker, "IssueModels", FakeIssueModels([]))
        load_bundle(gcs, make_bundle({"issue_models": []}))

        report = destination().plan(uri=BUNDLE_URI)

        assert any("deployed" in note for note in report.cost_notes)

    def test_summary_names_both_environments(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Cross-project promotion is easy to get backwards."""
        install(
            mocker,
            "PhraseMatchers",
            FakeCollection([], collection="phraseMatchers"),
        )
        load_bundle(gcs, make_bundle({"phrase_matchers": [phrase_matcher()]}))

        summary = destination().plan(uri=BUNDLE_URI).summary()

        assert f"{PROJECT} / {LOCATION}" in summary
        assert f"{DEST_PROJECT} / {DEST_LOCATION}" in summary
