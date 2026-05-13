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

"""Unit tests for the base module."""

from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
from google.api_core.client_options import ClientOptions

from cxidk.core.base import Auth, Config, Environments, Methods, Request


class TestAuth:
    """Tests for the Auth class."""

    @patch("google.auth.transport.requests.Request")
    def test_init_with_creds(self, _: MagicMock) -> None:
        """Test Auth initialization with creds."""
        mock_creds = MagicMock()
        Auth(creds=mock_creds)
        mock_creds.refresh.assert_called_once()

    @patch("google.auth.transport.requests.Request")
    @patch("cxidk.core.base.service_account")
    def test_init_with_creds_path(
        self, mock_service_account: MagicMock, _: MagicMock
    ) -> None:
        """Test Auth initialization with creds_path."""
        Auth(creds_path="/path/to/creds.json")
        mock_service_account.Credentials.from_service_account_file.assert_called_once()

    @patch("google.auth.transport.requests.Request")
    @patch("cxidk.core.base.service_account")
    def test_init_with_creds_dict(
        self, mock_service_account: MagicMock, _: MagicMock
    ) -> None:
        """Test Auth initialization with creds_dict."""
        Auth(creds_dict={})
        mock_service_account.Credentials.from_service_account_info.assert_called_once()

    @patch("google.auth.transport.requests.Request")
    @patch("cxidk.core.base.default")
    def test_init_with_default(self, mock_default: MagicMock, _: MagicMock) -> None:
        """Test Auth initialization with default."""
        mock_creds = MagicMock()
        mock_creds.requires_scopes = False
        mock_default.return_value = (mock_creds, "test-project")
        Auth()
        mock_default.assert_called_once()


class TestConfig:
    """Tests for the Config class."""

    def test_init_valid(self) -> None:
        """Test Config initialization with valid parameters."""
        config = Config(
            region="us-central1",
            environment=Environments.PRODUCTION # type: ignore[arg-type]
        )
        assert config.region == "us-central1"
        assert config.environment == Environments.PRODUCTION

    def test_init_invalid_region(self) -> None:
        """Test Config initialization with an invalid region."""
        with pytest.raises(ValueError):
            Config(region="invalid-region")

    def test_init_invalid_environment(self) -> None:
        """Test Config initialization with an invalid environment."""
        with pytest.raises(ValueError):
            Config(environment="invalid-env")  # type: ignore[arg-type]

    def test_set_insights_endpoint(self) -> None:
        """Test set_insights_endpoint."""
        config = Config(region="us-central1")
        options = config.set_insights_endpoint()
        assert isinstance(options, ClientOptions)
        assert (
            options.api_endpoint == "us-central1-contactcenterinsights.googleapis.com"
        )

    def test_set_speech_endpoint(self) -> None:
        """Test set_speech_endpoint."""
        config = Config(region="us-central1")
        options = config.set_speech_endpoint()
        assert isinstance(options, ClientOptions)
        assert options.api_endpoint == "us-central1-speech.googleapis.com"

    def test_set_storage_endpoint(self) -> None:
        """Test set_storage_endpoint."""
        config = Config(region="us-central1")
        options = config.set_storage_endpoint()
        assert isinstance(options, ClientOptions)
        assert options.api_endpoint == "us-central1-storage.googleapis.com"

    def test_set_dlp_endpoint(self) -> None:
        """Test set_dlp_endpoint."""
        config = Config(region="us-central1")
        options = config.set_dlp_endpoint()
        assert isinstance(options, ClientOptions)
        assert options.api_endpoint == "us-central1-dlp.googleapis.com"

    def test_set_vertex_endpoint(self) -> None:
        """Test set_vertex_endpoint."""
        config = Config(region="us-central1")
        options = config.set_vertex_endpoint()
        assert isinstance(options, ClientOptions)
        assert options.api_endpoint == "us-central1-aiplatform.googleapis.com"

    def test_set_polysynth_endpoint(self) -> None:
        """Test set_polysynth_endpoint."""
        config = Config(environment=Environments.STAGING)  # type: ignore[arg-type]
        endpoint = config.set_polysynth_endpoint()
        assert endpoint == "https://staging-ces-googleapis.sandbox.google.com/"


class TestRequest:
    """Tests for the Request class."""

    PROJECT_ID = "test-project"
    LOCATION = "us-central1"

    @pytest.fixture
    def mock_auth(self) -> MagicMock:
        """Fixture for a mocked Auth object."""
        mock = MagicMock(spec=Auth)
        # When using a spec, nested mocks must be explicitly created.
        mock.creds = MagicMock()
        mock.creds.token = "fake-token"
        return mock

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Fixture for a mocked Config object."""
        return MagicMock(spec=Config)

    @patch("cxidk.core.base.Auth")
    @patch("cxidk.core.base.Config")
    def test_init_defaults(self, mock_config_cls: MagicMock, mock_auth_cls: MagicMock) -> None:
        """Test Request initialization with default auth and config."""
        req = Request(project_id=self.PROJECT_ID, location=self.LOCATION)
        mock_auth_cls.assert_called_once()
        mock_config_cls.assert_called_once()
        assert req.auth is not None
        assert req.config is not None

    def test_init_provided(self, mock_auth: MagicMock, mock_config: MagicMock) -> None:
        """Test Request initialization with provided auth and config."""
        req = Request(
            project_id=self.PROJECT_ID,
            location=self.LOCATION,
            auth=mock_auth,
            config=mock_config,
        )
        assert req.auth == mock_auth
        assert req.config == mock_config

    @patch("cxidk.core.base.requests")
    def test_make_get_request(self, mock_requests: MagicMock, mock_auth: MagicMock) -> None:
        """Test a successful GET request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"key": "value"}'
        mock_response.json.return_value = {"key": "value"}
        mock_requests.get.return_value = mock_response

        req = Request(project_id=self.PROJECT_ID, location=self.LOCATION, auth=mock_auth)
        payload = {"param1": "value1", "param2": None}
        response = req.make("test/endpoint", Methods.GET, payload) # type: ignore[arg-type]

        mock_requests.get.assert_called_once_with(
            "test/endpoint",
            params={"param1": "value1"},
            headers={"Authorization": "Bearer fake-token"},
            timeout=60,
        )
        assert response == {"key": "value"}

    @patch("cxidk.core.base.requests")
    def test_make_post_request(self, mock_requests: MagicMock, mock_auth: MagicMock) -> None:
        """Test a successful POST request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"status": "created"}'
        mock_response.json.return_value = {"status": "created"}
        mock_requests.post.return_value = mock_response

        req = Request(project_id=self.PROJECT_ID, location=self.LOCATION, auth=mock_auth)
        payload: Dict[str, Any] = {"data": "some_data"}
        response = req.make("another/endpoint", Methods.POST, payload)

        mock_requests.post.assert_called_once_with(
            "another/endpoint",
            json=payload,
            headers={"Authorization": "Bearer fake-token"},
            timeout=60,
        )
        assert response == {"status": "created"}
