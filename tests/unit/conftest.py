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

"""Shared pytest fixtures for `cxidk` unit tests."""

from unittest.mock import MagicMock

import pytest

from cxidk import CxContext
from cxidk.core import base


def _create_mock_auth() -> MagicMock:
    """Creates a mocked `base.Auth` instance without touching Google ADC."""
    auth_obj = MagicMock(spec=base.Auth)
    auth_obj.creds = MagicMock()
    return auth_obj


@pytest.fixture
def mock_auth() -> MagicMock:
    """Provides a mocked `base.Auth` instance for wrapper unit tests.

    Returns:
        Mocked `base.Auth` object with a non-null `creds` attribute.
    """
    return _create_mock_auth()


@pytest.fixture
def demo_cx() -> CxContext:
    """Provides a reusable `CxContext` bound to `demo-proj-01` / `us-central1`.

    Returns:
        Configured `CxContext` backed by mocked credentials.
    """
    return CxContext("demo-proj-01", "us-central1", auth=_create_mock_auth())
