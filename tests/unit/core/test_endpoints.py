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

"""SSRF and endpoint validation regression tests for cxidk.core.base."""

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from cxidk.core import base
from cxidk.core import errors


@pytest.mark.parametrize(
    "bad_location",
    [
        "",
        "   ",
        "attacker.example/x?",
        "us-central1@evil.com",
        "../etc/passwd",
        "mars-north9",
        "https://evil.example",
    ],
)
def test_insights_host_rejects_malicious_or_unknown_locations(
    bad_location: str,
) -> None:
    """Ensures explicit `location` arguments cannot smuggle arbitrary hosts."""
    cfg = base.Config(region="us-central1")
    with pytest.raises(errors.InvalidArgumentError):
        cfg.insights_host(bad_location)
    with pytest.raises(errors.InvalidArgumentError):
        cfg.insights_base_url(bad_location)


def test_insights_host_resolves_regional_and_global_endpoints() -> None:
    """Validates canonical regional and global hostnames."""
    cfg = base.Config(region="europe-west1")
    assert cfg.insights_host() == "europe-west1-contactcenterinsights.googleapis.com"
    assert cfg.insights_host("global") == "contactcenterinsights.googleapis.com"
    assert (
        cfg.insights_base_url("us-central1")
        == "https://us-central1-contactcenterinsights.googleapis.com/v1/"
    )


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "test/relative/endpoint",
        "http://us-central1-contactcenterinsights.googleapis.com/v1/projects/p",
        "https://attacker.example/v1/projects/p",
        "https://googleapis.com.attacker.example/v1/projects/p",
        "https://user:pass@contactcenterinsights.googleapis.com/v1/projects/p",
        "file:///etc/passwd",
    ],
)
@patch("cxidk.core.base.requests")
def test_request_refuses_to_send_bearer_token_to_untrusted_url(
    mock_requests: MagicMock,
    unsafe_url: str,
) -> None:
    """Regression test: credentials are never attached to non-Google/non-HTTPS URLs."""
    mock_auth = MagicMock(spec=base.Auth)
    mock_auth.creds = MagicMock()
    mock_auth.creds.token = "secret-bearer-token"

    req = base.Request(
        project_id="test-proj",
        location="us-central1",
        base_url="",
        auth=mock_auth,
    )
    with pytest.raises(errors.UnsafeEndpointError):
        req.make(unsafe_url, base.Methods.GET, None)

    mock_requests.get.assert_not_called()
