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

"""Shared fixtures and test doubles for the configuration workflow tests.

The doubles here deliberately expose no patch, update or delete method. An
importer that tries to mutate the destination therefore fails with
`AttributeError` rather than quietly passing a test, which is the point: the
create-only rule is the design, not an implementation detail.

Fixtures are declared with an explicit `name=` so the module-level function name
differs from the injected argument name. Test functions can then take a `gcs`
parameter without shadowing anything.
"""

import json
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from cxidk.workflow import ops
from cxidk.workflow.utils import ops_types

PROJECT = "src-proj"
LOCATION = "us-central1"
DEST_PROJECT = "dst-proj"
DEST_LOCATION = "europe-west1"
PARENT = f"projects/{PROJECT}/locations/{LOCATION}"
DEST_PARENT = f"projects/{DEST_PROJECT}/locations/{DEST_LOCATION}"
BUNDLE_URI = "gs://bundles/config.json"

SOURCE_NAME = ops_types.SOURCE_NAME_KEY
SOURCE_ENUM = ops_types.SOURCE_ENUM_KEY


class FakeCollection:
    """A stand-in for a `wrapper.insights` collection.

    Records every create call so tests can assert on what was written.

    Attributes:
        records: Resources the collection reports as existing.
        parent: Parent path used when minting created resource names.
        collection: Collection segment used in created resource names.
        created: Request bodies passed to `create`, in order.
        created_ids: Caller-supplied resource IDs passed to `create`, in order.
    """

    def __init__(
        self,
        records: Optional[List[Dict[str, Any]]] = None,
        parent: str = DEST_PARENT,
        collection: str = "things",
    ) -> None:
        """Initializes the fake.

        Args:
            records: Resources the collection should report as existing.
            parent: Parent path used when minting created resource names.
            collection: Collection segment used in created resource names.
        """
        self.records = records or []
        self.parent = parent
        self.collection = collection
        self.created: List[Dict[str, Any]] = []
        self.created_ids: List[Optional[str]] = []

    def list(self, params: Any = None, page_size: int = 100) -> List[Dict[str, Any]]:
        """Returns every record.

        Args:
            params: Ignored.
            page_size: Ignored.

        Returns:
            The configured records.
        """
        del params, page_size
        return self.records

    def list_active(self, params: Any = None) -> List[Dict[str, Any]]:
        """Returns records whose `active` flag is set.

        Args:
            params: Ignored.

        Returns:
            The active subset of the configured records.
        """
        del params
        return [r for r in self.records if r.get("active")]

    def list_deployed(self) -> List[Dict[str, Any]]:
        """Returns records whose state is DEPLOYED.

        Returns:
            The deployed subset of the configured records.
        """
        return [r for r in self.records if r.get("state") == "DEPLOYED"]

    def list_by_source(
        self, sources: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Returns records matching the requested scorecard sources.

        Args:
            sources: Sources to include, or None for all.

        Returns:
            The matching records.
        """
        if not sources:
            return self.records
        return [r for r in self.records if r.get("source", "") in sources]

    def create(
        self, body: Dict[str, Any], resource_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Records a create call and returns a synthetic resource.

        Args:
            body: The request body.
            resource_id: The caller-supplied ID, if any.

        Returns:
            The created resource, carrying a generated name.
        """
        self.created.append(body)
        self.created_ids.append(resource_id)
        assigned = resource_id or f"server-{len(self.created)}"
        return {**body, "name": f"{self.parent}/{self.collection}/{assigned}"}

    def get_latest(self) -> Optional[Dict[str, Any]]:
        """Returns the newest record.

        Returns:
            The record with the highest createTime, or None.
        """
        if not self.records:
            return None
        return max(self.records, key=lambda r: str(r.get("createTime", "")))


class FakeIssueModels(FakeCollection):
    """A topic-model collection, where every mutation is an operation.

    Attributes:
        imported: `(gcs_uri, create_new)` pairs passed to `import_model`.
        exported: `(model_id, gcs_uri)` pairs passed to `export_model`.
    """

    def __init__(self, records: Optional[List[Dict[str, Any]]] = None) -> None:
        """Initializes the fake.

        Args:
            records: Models the collection should report as existing.
        """
        super().__init__(records, collection="issueModels")
        self.imported: List[Tuple[str, bool]] = []
        self.exported: List[Tuple[str, str]] = []

    def export_model(self, model_id: str, gcs_uri: str) -> Dict[str, Any]:
        """Records a native export request.

        Args:
            model_id: Bare ID of the model being exported.
            gcs_uri: Destination object URI.

        Returns:
            A long-running operation payload.
        """
        self.exported.append((model_id, gcs_uri))
        return {"name": "operations/export"}

    def import_model(self, gcs_uri: str, create_new: bool = False) -> Dict[str, Any]:
        """Records a native import request.

        Args:
            gcs_uri: Source object URI.
            create_new: Whether a new model is created rather than replaced.

        Returns:
            A long-running operation payload.
        """
        self.imported.append((gcs_uri, create_new))
        return {"name": "operations/import"}

    def create(
        self, body: Dict[str, Any], resource_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Records a metadata-only create, which the API answers with an LRO.

        Args:
            body: The request body.
            resource_id: Ignored; this collection assigns its own IDs.

        Returns:
            A long-running operation payload.
        """
        super().create(body, resource_id)
        return {"name": "operations/create"}


class FakeSingleton:
    """The correlation configuration, which is get/update rather than create.

    Attributes:
        config: The configuration currently stored.
        updates: Bodies passed to `update`, in order.
    """

    def __init__(self, rules: Optional[List[Dict[str, Any]]] = None) -> None:
        """Initializes the fake.

        Args:
            rules: Correlation rules already present at this environment.
        """
        self.config: Dict[str, Any] = {
            "fullConversationConfig": {"correlationRules": list(rules or [])}
        }
        self.updates: List[Dict[str, Any]] = []

    def get(self) -> Dict[str, Any]:
        """Returns the current configuration.

        Returns:
            The configuration document.
        """
        return self.config

    def update(
        self, body: Dict[str, Any], update_mask: Optional[str] = None
    ) -> Dict[str, Any]:
        """Records an update call.

        Args:
            body: The new configuration.
            update_mask: Fields the caller intends to replace.

        Returns:
            The stored configuration.
        """
        del update_mask
        self.updates.append(body)
        self.config = body
        return body


def install(mocker: MockerFixture, name: str, fake: Any) -> Any:
    """Patches a wrapper collection class to yield a given fake.

    Args:
        mocker: The pytest-mock fixture.
        name: Attribute name on `wrapper.insights` to replace.
        fake: The fake instance every construction should return.

    Returns:
        The fake, for convenience.
    """
    mocker.patch(f"cxidk.wrapper.insights.{name}", side_effect=lambda **_kwargs: fake)
    return fake


@pytest.fixture(name="_no_auth", autouse=True)
def fixture_no_auth(mocker: MockerFixture) -> None:
    """Prevents any test from attempting real authentication.

    Args:
        mocker: The pytest-mock fixture.
    """
    mocker.patch("cxidk.core.base.Auth", autospec=True)


@pytest.fixture(name="gcs")
def fixture_gcs(mocker: MockerFixture) -> MagicMock:
    """Patches Cloud Storage and returns the fake bucket client.

    Args:
        mocker: The pytest-mock fixture.

    Returns:
        The mock `Gcs` instance shared by all constructions.
    """
    client = MagicMock()
    client.bucket_exists.return_value = True
    mocker.patch("cxidk.wrapper.storage.Gcs", return_value=client)
    return client


def written_bundle(gcs_client: MagicMock) -> Dict[str, Any]:
    """Extracts the document handed to Cloud Storage.

    Args:
        gcs_client: The mock `Gcs` instance.

    Returns:
        The parsed bundle document.
    """
    kwargs = gcs_client.upload_blob.call_args.kwargs
    parsed: Dict[str, Any] = json.loads(kwargs["data"])
    return parsed


def make_bundle(assets: Dict[str, Any], **manifest: Any) -> Dict[str, Any]:
    """Builds a syntactically valid bundle document.

    Args:
        assets: The asset payload.
        **manifest: Manifest overrides.

    Returns:
        A bundle document.
    """
    base_manifest: Dict[str, Any] = {
        "schema_version": ops.SCHEMA_VERSION,
        "exported_at": "2026-01-01T00:00:00+00:00",
        "source_project_id": PROJECT,
        "source_location": LOCATION,
        "assets": list(assets.keys()),
        "active_only": True,
        "scorecard_sources": list(ops.ALL_SCORECARD_SOURCES),
    }
    base_manifest.update(manifest)
    return {"manifest": base_manifest, "assets": assets}


def load_bundle(gcs_client: MagicMock, document: Dict[str, Any]) -> None:
    """Arranges for a read to return the given bundle.

    Args:
        gcs_client: The mock `Gcs` instance.
        document: The bundle document to serve.
    """
    gcs_client.download_blob.return_value = json.dumps(document)


def destination() -> ops.ConfigOps:
    """Builds a `ConfigOps` pointed at the destination environment.

    Returns:
        A configured client.
    """
    return ops.ConfigOps(DEST_PROJECT, DEST_LOCATION)


def phrase_matcher(source_id: str = "angry", **extra: Any) -> Dict[str, Any]:
    """Builds a phrase matcher bundle record.

    Args:
        source_id: Bare ID the record had at the source.
        **extra: Additional fields.

    Returns:
        A bundle record.
    """
    record: Dict[str, Any] = {
        SOURCE_NAME: f"{PARENT}/phraseMatchers/{source_id}",
        "displayName": "Angry customer",
        "active": True,
    }
    record.update(extra)
    return record
