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

"""Unit tests for the configuration export/import workflow.

The tests are organised around the invariants the design commits to, because
those are the things that would quietly regress: import is create-only, IDs are
never reused, bundles live only in Cloud Storage, export covers active resources
only, and scorecards never carry training data.
"""

from typing import Any, Dict, cast
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

# The fixtures are used by injection, not by reference; pylint cannot see that.
from ops_testing import (  # pylint: disable=unused-import
    BUNDLE_URI,
    LOCATION,
    PARENT,
    PROJECT,
    FakeCollection,
    fixture_gcs,
    fixture_no_auth,
    install,
    written_bundle,
)

from cxidk.workflow import ops
from cxidk.workflow.utils import ops_types



class TestBundleIo:
    """GCS-only path handling."""

    def test_parses_gcs_uri(self) -> None:
        """A well-formed gs:// URI splits into bucket and object."""
        assert ops.BundleIO.parse("gs://b/a/c.json") == ("b", "a/c.json")

    @pytest.mark.parametrize(
        "uri", ["/tmp/config.json", "./config.json", "config.json", "s3://b/o"]
    )
    def test_rejects_non_gcs_paths(self, uri: str) -> None:
        """Local and foreign paths are refused rather than silently accepted."""
        with pytest.raises(ValueError, match="Cloud Storage"):
            ops.BundleIO.parse(uri)

    def test_rejects_bucket_without_object(self) -> None:
        """A bucket alone is not a bundle location."""
        with pytest.raises(ValueError, match="bucket and an object"):
            ops.BundleIO.parse("gs://bucket-only")


class TestIdentityAndNaming:
    """ID minting and display-name policy."""

    def test_new_id_never_reuses_the_source(self) -> None:
        """Reusing a bundle ID would make the second import fail."""
        assert ops_types.new_resource_id("angry-customer") != "angry-customer"

    def test_new_id_keeps_a_readable_stem(self) -> None:
        """The origin stays traceable from the generated ID."""
        assert ops_types.new_resource_id("angry-customer").startswith(
            "angry-customer-"
        )

    def test_new_ids_are_unique(self) -> None:
        """Two imports of one record must not collide."""
        generated = {ops_types.new_resource_id("x") for _ in range(50)}
        assert len(generated) == 50

    def test_new_id_sanitizes_and_survives_empty_input(self) -> None:
        """Unusual source IDs still yield a usable identifier."""
        assert ops_types.new_resource_id("").startswith("imported-")
        assert " " not in ops_types.new_resource_id("has spaces/and~punct")

    def test_suffix_policy_labels_the_copy(self) -> None:
        """SUFFIX appends the template."""
        options = ops.ImportOptions(naming=ops.NamingPolicy.SUFFIX)
        assert ops_types.apply_naming("Angry", options, PROJECT).startswith("Angry (")

    def test_duplicate_policy_leaves_the_name_alone(self) -> None:
        """DUPLICATE produces a byte-identical display name."""
        options = ops.ImportOptions(naming=ops.NamingPolicy.DUPLICATE)
        assert ops_types.apply_naming("Angry", options, PROJECT) == "Angry"

    def test_suffixes_do_not_accrete(self) -> None:
        """Round-tripping must not stack markers on a name."""
        options = ops.ImportOptions()
        once = ops_types.apply_naming("Angry", options, PROJECT)
        twice = ops_types.apply_naming(once, options, PROJECT)
        assert twice.count("imported") == 1

    def test_custom_prefix_template_is_supported(self) -> None:
        """A prefix-style template works as well as a suffix."""
        options = ops.ImportOptions(rename_template="[imported {date}] {name}")
        assert ops_types.apply_naming("Angry", options, PROJECT).endswith("Angry")


class TestEnvironment:
    """Region and endpoint consistency."""

    def test_rejects_config_disagreeing_with_location(self) -> None:
        """A parent path and an endpoint for different regions cannot mix."""
        import cxidk.core.base as core_base  # pylint: disable=C0415

        with pytest.raises(ValueError, match="disagrees"):
            ops.Environment(
                project_id=PROJECT,
                location="us-central1",
                config=core_base.Config(region="europe-west1"),
            )

    def test_derives_config_from_location(self) -> None:
        """Without an explicit config, the location selects the endpoint."""
        environment = ops.Environment(project_id=PROJECT, location=LOCATION)
        assert environment.config.region == LOCATION
        assert environment.parent == PARENT


class TestExport:
    """Export scope, filtering and manifest."""

    def test_selective_export_includes_only_requested_assets(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Asking for one asset must not export the other seven."""
        install(
            mocker,
            "PhraseMatchers",
            FakeCollection([{"name": f"{PARENT}/phraseMatchers/1", "active": True}]),
        )
        config_ops = ops.ConfigOps(PROJECT, LOCATION)
        config_ops.export(uri=BUNDLE_URI, assets=[ops.Asset.PHRASE_MATCHERS])

        bundle = written_bundle(gcs)
        assert list(bundle["assets"]) == ["phrase_matchers"]
        assert bundle["manifest"]["assets"] == ["phrase_matchers"]

    def test_active_only_skips_inactive_resources(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Inactive drafts are noise when promoting configuration."""
        install(
            mocker,
            "PhraseMatchers",
            FakeCollection(
                [
                    {"name": f"{PARENT}/phraseMatchers/1", "active": True},
                    {"name": f"{PARENT}/phraseMatchers/2", "active": False},
                ]
            ),
        )
        config_ops = ops.ConfigOps(PROJECT, LOCATION)
        config_ops.export(uri=BUNDLE_URI, assets=[ops.Asset.PHRASE_MATCHERS])

        assert len(written_bundle(gcs)["assets"]["phrase_matchers"]) == 1

    def test_active_only_false_keeps_everything(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """The escape hatch exports drafts too."""
        install(
            mocker,
            "PhraseMatchers",
            FakeCollection(
                [
                    {"name": f"{PARENT}/phraseMatchers/1", "active": True},
                    {"name": f"{PARENT}/phraseMatchers/2", "active": False},
                ]
            ),
        )
        config_ops = ops.ConfigOps(PROJECT, LOCATION)
        config_ops.export(
            uri=BUNDLE_URI,
            assets=[ops.Asset.PHRASE_MATCHERS],
            options=ops.ExportOptions(active_only=False),
        )

        assert len(written_bundle(gcs)["assets"]["phrase_matchers"]) == 2

    def test_issue_models_use_deployment_state_not_active(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Topic models express availability through `state`, not `active`."""
        install(
            mocker,
            "IssueModels",
            FakeCollection(
                [
                    {"name": f"{PARENT}/issueModels/1", "state": "DEPLOYED"},
                    {"name": f"{PARENT}/issueModels/2", "state": "UNDEPLOYED"},
                ]
            ),
        )
        config_ops = ops.ConfigOps(PROJECT, LOCATION)
        config_ops.export(uri=BUNDLE_URI, assets=[ops.Asset.ISSUE_MODELS])

        assert len(written_bundle(gcs)["assets"]["issue_models"]) == 1

    def test_manifest_records_export_filters(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """A filtered bundle must describe itself as filtered."""
        install(mocker, "PhraseMatchers", FakeCollection([]))
        config_ops = ops.ConfigOps(PROJECT, LOCATION)
        config_ops.export(uri=BUNDLE_URI, assets=[ops.Asset.PHRASE_MATCHERS])

        manifest = written_bundle(gcs)["manifest"]
        assert manifest["active_only"] is True
        assert manifest["source_project_id"] == PROJECT
        assert manifest["source_location"] == LOCATION
        assert manifest["schema_version"] == ops.SCHEMA_VERSION

    def test_strips_output_only_fields(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Server-owned fields cannot be replayed into a create call."""
        install(
            mocker,
            "PhraseMatchers",
            FakeCollection(
                [
                    {
                        "name": f"{PARENT}/phraseMatchers/1",
                        "active": True,
                        "createTime": "2026-01-01T00:00:00Z",
                        "updateTime": "2026-01-02T00:00:00Z",
                        "revisionId": "r1",
                        "displayName": "Angry",
                    }
                ]
            ),
        )
        config_ops = ops.ConfigOps(PROJECT, LOCATION)
        config_ops.export(uri=BUNDLE_URI, assets=[ops.Asset.PHRASE_MATCHERS])

        record = written_bundle(gcs)["assets"]["phrase_matchers"][0]
        for stripped in ("name", "createTime", "updateTime", "revisionId"):
            assert stripped not in record
        assert record[ops_types.SOURCE_NAME_KEY] == f"{PARENT}/phraseMatchers/1"

    def test_fails_fast_when_bucket_is_unreachable(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Checking the bucket first avoids failing after all the reads."""
        gcs.bucket_exists.return_value = False
        install(mocker, "PhraseMatchers", FakeCollection([]))
        config_ops = ops.ConfigOps(PROJECT, LOCATION)

        with pytest.raises(ops.BundleError, match="Cannot reach the bucket"):
            config_ops.export(uri=BUNDLE_URI, assets=[ops.Asset.PHRASE_MATCHERS])

    def test_rejects_unknown_asset(self) -> None:
        """Deferred assets have no handler and must not silently no-op.

        The cast mimics a caller who is not running a type checker, which is
        the only way this value reaches the library.
        """
        config_ops = ops.ConfigOps(PROJECT, LOCATION)
        deferred = cast(ops.Asset, "discoveries")
        with pytest.raises(ValueError):
            config_ops.export(uri=BUNDLE_URI, assets=[deferred])


class TestScorecardExport:
    """Scorecard scope boundary and source handling."""

    @staticmethod
    def _install(mocker: MockerFixture, question: Dict[str, Any]) -> None:
        """Wires up a one-scorecard, one-revision, one-question environment.

        Args:
            mocker: The pytest-mock fixture.
            question: The question the revision should contain.
        """
        install(
            mocker,
            "QaScorecards",
            FakeCollection(
                [
                    {
                        "name": f"{PARENT}/qaScorecards/sc1",
                        "displayName": "Quality",
                        "isDefault": True,
                        "source": "QA_SCORECARD_SOURCE_DISCOVERY_ENGINE",
                    }
                ]
            ),
        )
        install(
            mocker,
            "ScorecardRevisions",
            FakeCollection(
                [
                    {
                        "name": f"{PARENT}/qaScorecards/sc1/revisions/old",
                        "createTime": "2026-01-01T00:00:00Z",
                    },
                    {
                        "name": f"{PARENT}/qaScorecards/sc1/revisions/new",
                        "createTime": "2026-06-01T00:00:00Z",
                    },
                ]
            ),
        )
        install(mocker, "RevisionQuestions", FakeCollection([question]))

    def test_excludes_training_data_and_trained_artifacts(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Example conversations and tuning state are out of scope by design."""
        self._install(
            mocker,
            {
                "name": f"{PARENT}/qaScorecards/sc1/revisions/new/qaQuestions/q1",
                "abbreviation": "Greeting",
                "tuningMetadata": {"totalValidLabelCount": 12},
                "metrics": {"accuracy": 0.9},
                "qaQuestionDataOptions": {"conversationDataOptions": {}},
            },
        )
        config_ops = ops.ConfigOps(PROJECT, LOCATION)
        config_ops.export(uri=BUNDLE_URI, assets=[ops.Asset.SCORECARDS])

        question = written_bundle(gcs)["assets"]["scorecards"][0]["_questions"][0]
        assert "tuningMetadata" not in question
        assert "metrics" not in question
        assert "qaQuestionDataOptions" not in question

    def test_exports_only_the_latest_revision(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Revision history is deliberately not carried across."""
        self._install(mocker, {"name": "q", "abbreviation": "G"})
        config_ops = ops.ConfigOps(PROJECT, LOCATION)
        config_ops.export(uri=BUNDLE_URI, assets=[ops.Asset.SCORECARDS])

        revision = written_bundle(gcs)["assets"]["scorecards"][0]["_revision"]
        assert revision[ops_types.SOURCE_NAME_KEY].endswith("/new")

    def test_preserves_non_customer_source_for_provenance(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """`source` is output-only, so the bundle is the only place to keep it."""
        self._install(mocker, {"name": "q", "abbreviation": "G"})
        config_ops = ops.ConfigOps(PROJECT, LOCATION)
        config_ops.export(uri=BUNDLE_URI, assets=[ops.Asset.SCORECARDS])

        record = written_bundle(gcs)["assets"]["scorecards"][0]
        assert record[ops_types.SOURCE_ENUM_KEY] == (
            "QA_SCORECARD_SOURCE_DISCOVERY_ENGINE"
        )
        assert "source" not in record

    def test_requests_every_scorecard_source_by_default(
        self, mocker: MockerFixture, gcs: MagicMock
    ) -> None:
        """Discovery Engine and intent-taxonomy scorecards are in scope."""
        self._install(mocker, {"name": "q", "abbreviation": "G"})
        config_ops = ops.ConfigOps(PROJECT, LOCATION)
        config_ops.export(uri=BUNDLE_URI, assets=[ops.Asset.SCORECARDS])

        sources = written_bundle(gcs)["manifest"]["scorecard_sources"]
        assert "QA_SCORECARD_SOURCE_DISCOVERY_ENGINE" in sources
        assert "QA_SCORECARD_SOURCE_INTENT_TAXONOMY" in sources
