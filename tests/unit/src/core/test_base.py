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

"""Unit tests for the Auth and Config classes."""
import pytest
from google import auth
from google.oauth2 import service_account
from src.core.base import Auth, Config

# Mocking API calls
@pytest.fixture(name="mock_request")
def fixture_mock_request(monkeypatch: pytest.MonkeyPatch):
    """Mock google.auth.transport.requests.Request."""
    class MockRequest:
        """Mock request object."""
        def __init__(self):
            pass  # No need for any attributes in this mock
    monkeypatch.setattr(auth.transport.requests, 'Request', MockRequest)

@pytest.fixture(name="mock_credentials")
def fixture_mock_credentials(monkeypatch: pytest.MonkeyPatch):
    """Mock google.oauth2.service_account.Credentials."""

    # Test only pylint: disable=unused-argument
    def mock_from_service_account_file(filename, scopes=None):
        return MockCredentials()

    # Test only pylint: disable=unused-argument
    def mock_from_service_account_info(info, scopes=None):
        return MockCredentials()

    monkeypatch.setattr(
        service_account.Credentials, 'from_service_account_file', mock_from_service_account_file
    )
    monkeypatch.setattr(
        service_account.Credentials, 'from_service_account_info', mock_from_service_account_info
    )

class MockCredentials:
    """Mock credentials object."""
    def __init__(self):
        self.token = 'mock_token'

    def refresh(self, request):
        """Mock refresh method."""


# Auth class tests
# Test only pylint: disable=unused-argument
def test_auth_with_creds(mock_request: None, mock_credentials: None):
    """Test Auth initialization with credentials."""
    creds = MockCredentials()
    creds_auth = Auth(creds=creds) #type: ignore
    assert creds_auth.token == 'mock_token'


# Test only pylint: disable=unused-argument
def test_auth_with_creds_path(mock_request: None, mock_credentials: None):
    """Test Auth initialization with credentials path."""
    path_auth = Auth(creds_path='path/to/creds.json')
    assert path_auth.token == 'mock_token'

# Test only pylint: disable=unused-argument
def test_auth_with_creds_dict(mock_request: None, mock_credentials: None):
    """Test Auth initialization with credentials dict."""
    dict_auth = Auth(creds_dict={'type': 'service_account'})
    assert dict_auth.token == 'mock_token'

# Test only pylint: disable=unused-argument
def test_auth_default(mock_request: None, mock_credentials: None, monkeypatch: pytest.MonkeyPatch):
    """Test Auth initialization with default credentials."""
    def mock_default():
        return MockCredentials(), 'mock_project_id'

    monkeypatch.setattr(auth, 'default', mock_default)
    defualt_auth = Auth()
    assert defualt_auth.token is not None

# Config class tests
def test_config_valid_region():
    """Test Config initialization with a valid region."""
    config = Config(region='us-central1')
    assert config.region == 'us-central1'

def test_config_invalid_region():
    """Test Config initialization with an invalid region."""
    with pytest.raises(ValueError):
        Config(region='invalid-region')

def test_config_valid_environment():
    """Test Config initialization with a valid environment."""
    config = Config(enviroment='prod')
    assert config.enviroment == 'prod'

def test_config_invalid_environment():
    """Test Config initialization with an invalid environment."""
    with pytest.raises(ValueError):
        Config(enviroment='invalid-env')

def test_config_endpoints():
    """Test Config endpoint methods."""
    config = Config()
    assert config.set_insights_endpoint().api_endpoint == 'contactcenterinsights.googleapis.com'
    assert config.set_speech_endpoint().api_endpoint == 'speech.googleapis.com'
    assert config.set_storage_endpoint().api_endpoint == 'https://storage.googleapis.com'
    assert config.set_dlp_endpoint().api_endpoint == 'https://dlp.googleapis.com'
    assert config.set_vertex_endpoint().api_endpoint == 'https://aiplatform.googleapis.com'
