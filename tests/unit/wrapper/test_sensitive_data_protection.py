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

"""Unit tests for the DLP wrapper."""

# pylint: disable=redefined-outer-name, protected-access, line-too-long, no-member, unused-argument

from typing import Dict
from unittest.mock import MagicMock, patch

import pytest
from pytest_mock import MockerFixture

from cxidk.wrapper.sensitive_data_protection import DLP

# --- Constants for Testing ---
PROJECT_ID = "test-project"
LOCATION = "us-central1"
PARENT = f"projects/{PROJECT_ID}/locations/{LOCATION}"


# --- Fixtures ---


@pytest.fixture
def mock_dlp_client(mocker: MockerFixture) -> MagicMock:
    """Mocks the DlpServiceClient."""
    return mocker.patch("cxidk.wrapper.sensitive_data_protection.dlp_v2.DlpServiceClient")


@pytest.fixture
def mock_base(mocker: MockerFixture) -> Dict[str, MagicMock]:
    """Mocks cxidk.core.base.Auth and cxidk.core.base.Config."""
    mock_auth_cls = mocker.patch(
        "cxidk.wrapper.sensitive_data_protection.base.Auth", autospec=True
    )
    mock_config_cls = mocker.patch(
        "cxidk.wrapper.sensitive_data_protection.base.Config", autospec=True
    )
    return {"Auth": mock_auth_cls, "Config": mock_config_cls}


@pytest.fixture
def dlp_wrapper(mock_dlp_client: MagicMock, mock_base: Dict[str, MagicMock]) -> DLP:
    """Returns an initialized DLP wrapper."""
    return DLP(project_id=PROJECT_ID, location=LOCATION)


# --- Test Class for DLP ---


class TestDLP:
    """Tests for the DLP class."""

    def test_init(
        self,
        mock_dlp_client: MagicMock,
        mock_base: Dict[str, MagicMock],
    ) -> None:
        """Test DLP initialization."""
        dlp = DLP(project_id=PROJECT_ID, location=LOCATION)
        mock_base["Auth"].assert_called_once()
        mock_base["Config"].assert_called_once()
        mock_dlp_client.assert_called_once()
        assert dlp.project_id == PROJECT_ID
        assert dlp.location == LOCATION
        assert dlp.parent == PARENT

    def test_create_inspect_template_defaults(self, dlp_wrapper: DLP) -> None:
        """Test create_inspect_template with default values."""
        mock_response = MagicMock()
        mock_response.name = f"{PARENT}/inspectTemplates/default_insights_template"
        dlp_wrapper.client.create_inspect_template.return_value = mock_response # type: ignore[attr-defined]

        result = dlp_wrapper.create_inspect_template()

        dlp_wrapper.client.create_inspect_template.assert_called_once() # type: ignore[attr-defined]
        request = dlp_wrapper.client.create_inspect_template.call_args[1]["request"] # type: ignore[attr-defined]
        assert request.parent == PARENT
        assert request.template_id == "default_insights_template"
        assert request.inspect_template.inspect_config.info_types[0].name == "PERSON_NAME"
        assert result == mock_response.name

    def test_create_inspect_template_custom(self, dlp_wrapper: DLP) -> None:
        """Test create_inspect_template with custom values."""
        dlp_wrapper.client.create_inspect_template.return_value.name = "test-name" # type: ignore[attr-defined]
        info_types = ["CREDIT_CARD_NUMBER"]

        dlp_wrapper.create_inspect_template(
            template_id="custom-id",
            display_name="Custom Template",
            description="A custom description",
            info_types=info_types,
        )

        request = dlp_wrapper.client.create_inspect_template.call_args[1]["request"] # type: ignore[attr-defined]
        assert request.template_id == "custom-id"
        assert request.inspect_template.display_name == "Custom Template"
        assert request.inspect_template.inspect_config.info_types[0].name == "CREDIT_CARD_NUMBER"

    def test_get_inspect_template(self, dlp_wrapper: DLP) -> None:
        """Test get_inspect_template."""
        template_id = "my-template"
        expected_name = f"{PARENT}/inspectTemplates/{template_id}"

        dlp_wrapper.get_inspect_template(template_id=template_id)

        dlp_wrapper.client.get_inspect_template.assert_called_once() # type: ignore[attr-defined]
        request = dlp_wrapper.client.get_inspect_template.call_args[1]["request"] # type: ignore[attr-defined]
        assert request.name == expected_name

    def test_create_deidentify_template_defaults(self, dlp_wrapper: DLP) -> None:
        """Test create_deidentify_template with default values."""
        mock_response = MagicMock()
        mock_response.name = f"{PARENT}/deidentifyTemplates/default_deidentify_template"
        dlp_wrapper.client.create_deidentify_template.return_value = mock_response # type: ignore[attr-defined]

        result = dlp_wrapper.create_deidentify_template()

        dlp_wrapper.client.create_deidentify_template.assert_called_once() # type: ignore[attr-defined]
        request = dlp_wrapper.client.create_deidentify_template.call_args[1]["request"] # type: ignore[attr-defined]
        assert request.parent == PARENT
        assert request.template_id == "default_deidentify_template"
        transformation = request.deidentify_template.deidentify_config.info_type_transformations.transformations[0]
        assert "replace_with_info_type_config" in transformation.primitive_transformation
        assert transformation.info_types[0].name == "PERSON_NAME"
        assert result == mock_response.name

    def test_create_deidentify_template_custom(self, dlp_wrapper: DLP) -> None:
        """Test create_deidentify_template with custom values."""
        dlp_wrapper.client.create_deidentify_template.return_value.name = "test-name" # type: ignore[attr-defined]
        info_types = ["PHONE_NUMBER"]

        dlp_wrapper.create_deidentify_template(
            template_id="custom-deid",
            display_name="Custom De-id",
            description="Custom de-id description",
            info_types=info_types,
        )

        request = dlp_wrapper.client.create_deidentify_template.call_args[1]["request"] # type: ignore[attr-defined]
        assert request.template_id == "custom-deid"
        assert request.deidentify_template.display_name == "Custom De-id"
        transformation = request.deidentify_template.deidentify_config.info_type_transformations.transformations[0]
        assert transformation.info_types[0].name == "PHONE_NUMBER"

    def test_get_deidentify_template(self, dlp_wrapper: DLP) -> None:
        """Test get_deidentify_template."""
        template_id = "my-deid-template"
        expected_name = f"{PARENT}/deidentifyTemplates/{template_id}"

        dlp_wrapper.get_deidentify_template(template_id=template_id)

        dlp_wrapper.client.get_deidentify_template.assert_called_once() # type: ignore[attr-defined]
        request = dlp_wrapper.client.get_deidentify_template.call_args[1]["request"] # type: ignore[attr-defined]
        assert request.name == expected_name


    @patch.object(DLP, "create_inspect_template", return_value="inspect-tmpl-name")
    @patch.object(DLP, "create_deidentify_template", return_value="deid-tmpl-name")
    def test_redact_creates_templates(
        self, mock_create_deid: MagicMock, mock_create_insp: MagicMock, dlp_wrapper: DLP
    ) -> None:
        """Test that redact creates templates if they are not provided."""
        data = {"transcript_header": [], "transcript": []} # type: ignore[var-annotated]
        dlp_wrapper.redact(data=data)

        mock_create_insp.assert_called_once()
        mock_create_deid.assert_called_once()

        request = dlp_wrapper.client.deidentify_content.call_args[1]["request"] # type: ignore[attr-defined]
        assert request.inspect_template_name == "inspect-tmpl-name"
        assert request.deidentify_template_name == "deid-tmpl-name"

    def test_redact_with_provided_templates(self, dlp_wrapper: DLP) -> None:
        """Test redact with provided template names."""
        data = {
            "transcript_header": [{"name": "col1"}],
            "transcript": [{"string_value": "some data"}],
        }
        inspect_template = "my-inspect-template"
        deidentify_template = "my-deidentify-template"

        dlp_wrapper.redact(
            data=data,
            inspect_template=inspect_template,
            deidentify_template=deidentify_template,
        )

        dlp_wrapper.client.deidentify_content.assert_called_once() # type: ignore[attr-defined]
        request = dlp_wrapper.client.deidentify_content.call_args[1]["request"] # type: ignore[attr-defined]

        assert request.parent == PARENT
        assert request.inspect_template_name == inspect_template
        assert request.deidentify_template_name == deidentify_template

        # Verify table structure
        table = request.item.table
        assert table.headers[0].name == "col1"
        assert table.rows[0].values[0].string_value == "some data"
