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

"""Unit tests for the Insights class."""

from unittest.mock import MagicMock, patch

from google.cloud import contact_center_insights_v1
from google.api_core import exceptions
from google.cloud.contact_center_insights_v1 import types

import pytest

from src.wrapper.insights import Settings, Ingestion, Analysis, Export, Annotators
from src.core import base



@pytest.fixture(name="mock_insights_client")
def fixture_mock_insights_client():
    """Mocks the Contact Center Insights Client."""
    mock_client = MagicMock(spec=contact_center_insights_v1.ContactCenterInsightsClient)
    with patch(
        "src.wrapper.insights.contact_center_insights_v1.ContactCenterInsightsClient",
        return_value=mock_client,
    ):
        yield mock_client


# Settings Tests
@pytest.fixture(name="settings_instance")
def fixture_settings_instance(mock_insights_client: MagicMock):
    """Creates an instance of the Settings class with mocks."""
    # For test only, if removed all tests fails
    # pylint: disable=pointless-statement
    mock_insights_client
    mock_auth = MagicMock(spec=base.Auth)
    mock_config = MagicMock(spec=base.Config)
    mock_config.set_insights_endpoint.return_value = None
    return Settings(
        parent="projects/test-project/locations/test-location/settings",
        project_id="test-project",
        auth=mock_auth,
        config=mock_config,
    )


def test_settings_update_global_auto_analysis(
    settings_instance: Settings, mock_insights_client: MagicMock
):
    """Tests updating global auto analysis settings."""
    mock_update_settings = MagicMock()
    mock_insights_client.update_settings = mock_update_settings
    settings_instance.update_global_auto_analysis(
        runtime_percentage=80.5,
        upload_percentage=20.3,
        analysis_annotators=[Annotators.INSIGHTS],
    )
    mock_update_settings.assert_called_once()


def test_settings_update_ttl(
    settings_instance: Settings, mock_insights_client: MagicMock
):
    """Tests updating conversation TTL settings."""
    mock_update_settings = MagicMock()
    mock_insights_client.update_settings = mock_update_settings
    settings_instance.update_ttl(ttl_in_days=365)
    mock_update_settings.assert_called_once()


def test_settings_update_pubsub(
    settings_instance: Settings, mock_insights_client: MagicMock
):
    """Tests updating Pub/Sub notification settings."""
    mock_update_settings = MagicMock()
    mock_insights_client.update_settings = mock_update_settings

    pub_sub_map = {"key1": "value1", "key2": "value2"}

    settings_instance.update_pubsub(pub_sub_map=pub_sub_map)
    mock_update_settings.assert_called_once()


def test_settings_update_global_language(
    settings_instance: Settings, mock_insights_client: MagicMock
):
    """Tests updating the global language setting."""
    mock_update_settings = MagicMock()
    mock_insights_client.update_settings = mock_update_settings
    settings_instance.update_global_language(language_code="es-ES")
    mock_update_settings.assert_called_once()


def test_settings_update_global_speech(
    settings_instance: Settings, mock_insights_client: MagicMock
):
    """Tests updating the global speech recognizer setting."""
    mock_update_settings = MagicMock()
    mock_insights_client.update_settings = mock_update_settings
    settings_instance.update_global_speech(
        speech_recognizer_path="projects/test/locations/us/recognizers/test"
    )
    mock_update_settings.assert_called_once()


def test_settings_update_global_dlp(
    settings_instance: Settings, mock_insights_client: MagicMock
):
    """Tests updating the global DLP settings."""
    mock_update_settings = MagicMock()
    mock_insights_client.update_settings = mock_update_settings
    settings_instance.update_global_dlp(
        inspect_template="test-inspect", deidentify_template="test-deidentify"
    )
    mock_update_settings.assert_called_once()


def test_settings_get(settings_instance: Settings, mock_insights_client: MagicMock):
    """Tests getting the current settings."""
    mock_get_settings = MagicMock(return_value=types.resources.Settings())
    mock_insights_client.get_settings = mock_get_settings
    settings_instance.get()
    mock_get_settings.assert_called_once()


# Ingestion Tests


@pytest.fixture(name="ingestion_instance")
def fixture_ingestion_instance(mock_insights_client: MagicMock):
    """Creates an instance of the Ingestion class with mocks."""
    # For test only, if removed all tests fails
    # pylint: disable=pointless-statement
    mock_insights_client
    mock_auth = MagicMock(spec=base.Auth)
    mock_config = MagicMock(spec=base.Config)
    mock_config.set_insights_endpoint.return_value = None
    return Ingestion(
        parent="projects/test-project/locations/test-location",
        auth=mock_auth,
        config=mock_config,
    )


def test_ingestion_single(
    ingestion_instance: Ingestion, mock_insights_client: MagicMock
):
    """Tests ingesting a single conversation."""
    mock_upload_conversation = MagicMock()
    mock_insights_client.upload_conversation = mock_upload_conversation
    ingestion_instance.single(conversation_id="test-conversation-id")
    mock_upload_conversation.assert_called_once()


def test_ingestion_bulk(ingestion_instance: Ingestion, mock_insights_client: MagicMock):
    """Tests ingesting multiple conversations."""
    mock_ingest_conversations = MagicMock()
    mock_insights_client.ingest_conversations = mock_ingest_conversations
    ingestion_instance.bulk(metadata_path="gs://test-bucket/metadata.json")
    mock_ingest_conversations.assert_called_once()


# Analysis Tests
@pytest.fixture(name="analysis_instance")
def fixture_analysis_instance(mock_insights_client: MagicMock):
    """Creates an instance of the Analysis class with mocks."""
    # For test only, if removed all tests fails
    # pylint: disable=pointless-statement
    mock_insights_client
    mock_auth = MagicMock(spec=base.Auth)
    mock_config = MagicMock(spec=base.Config)
    mock_config.set_insights_endpoint.return_value = None
    return Analysis(
        parent="projects/test-project/locations/test-location/conversations/test-id",
        auth=mock_auth,
        config=mock_config,
    )


def test_analysis_single(analysis_instance: Analysis, mock_insights_client: MagicMock):
    """Tests creating an analysis for a single conversation."""
    mock_create_analysis = MagicMock()
    mock_insights_client.create_analysis = mock_create_analysis
    analysis_instance.single(annotators=[Annotators.INSIGHTS])
    mock_create_analysis.assert_called_once()


def test_analysis_bulk(analysis_instance: Analysis, mock_insights_client: MagicMock):
    """Tests creating analyses for multiple conversations."""
    mock_bulk_analyze_conversations = MagicMock()
    mock_insights_client.bulk_analyze_conversations = mock_bulk_analyze_conversations

    analysis_instance.bulk(
        annotators=[Annotators.INSIGHTS], analysis_percentage=50, analysis_filter="filter"
    )
    mock_bulk_analyze_conversations.assert_called_once()


def test_set_annotators_none(analysis_instance: Analysis):
    """Tests invalid annotators"""
    with pytest.raises(ValueError) as ve:
        # Test only pylint: disable=protected-access
        # Purposefully passing the wrong type
        analysis_instance._set_annotators(annotators=None) # type: ignore
    assert "Invalid annotator" in str(ve.value)


def test_set_annotators_empty(analysis_instance: Analysis):
    """Tests invalid annotators"""
    with pytest.raises(ValueError) as ve:
        # Test only pylint: disable=protected-access
        analysis_instance._set_annotators(annotators=[])
    assert "Invalid annotator" in str(ve.value)


# Export Tests
@pytest.fixture(name="export_instance")
def fixture_export_instance(mock_insights_client: MagicMock):
    """Creates an instance of the Export class with mocks."""
    # For test only, if removed all tests fails
    # pylint: disable=pointless-statement
    mock_insights_client
    mock_auth = MagicMock(spec=base.Auth)
    mock_config = MagicMock(spec=base.Config)
    mock_config.set_insights_endpoint.return_value = None
    return Export(
        parent="projects/test/locations/test", auth=mock_auth, config=mock_config
    )


def test_export_to_bq(export_instance: Export, mock_insights_client: MagicMock):
    """Tests exporting insights data to BigQuery."""
    mock_export_insights_data = MagicMock()
    mock_insights_client.export_insights_data = mock_export_insights_data
    export_instance.to_bq(
        project_id="test-project",
        dataset="test_dataset",
        table="test_table",
        insights_filter="test_filter",
    )
    mock_export_insights_data.assert_called_once()


def test_settings_set_annotators_invalid_type(settings_instance: Settings):
    """Tests invalid annotators"""
    with pytest.raises(TypeError):
        # Test only pylint: disable=protected-access
        # Purposefully passing the wrong type
        settings_instance._set_annotators("test") # type: ignore


def test_settings_set_annotators_invalid_annotator(settings_instance: Settings):
    """Tests invalid annotators"""
    with pytest.raises(TypeError):
        # Test only pylint: disable=protected-access
        settings_instance._set_annotators(["test"])


def test_send_update_settings_invalid_argument(
    settings_instance: Settings, mock_insights_client: MagicMock
):
    """"Tests invalid argument"""
    mock_insights_client.update_settings.side_effect = exceptions.InvalidArgument(
        "Invalid argument"
    )
    with pytest.raises(ValueError) as ve:
        # Test only pylint: disable=protected-access
        settings_instance._send_update_settings(request="test")

    assert "Invalid argument" in str(ve.value)
