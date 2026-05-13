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

"""Integration tests for the core module."""

import pytest

from cxidk.core import base

def test_different_envs():
    """Test different environments scenarios"""

    config = base.Config(
        environment = base.Environments.STAGING
    )
    assert config.environment == base.Environments.STAGING

    config = base.Config(
        environment = base.Environments.PRODUCTION
    )
    assert config.environment == base.Environments.PRODUCTION

    with pytest.raises(ValueError):
        base.Config(region='non-existing-region')

    with pytest.raises(ValueError):
        base.Config(environment='non-existing-environment')

def test_different_endpoints():
    """Test different endpoints scenarios"""

    config = base.Config()
    assert config.set_polysynth_endpoint() == "https://ces.googleapis.com/"
    assert config.set_insights_endpoint().api_endpoint == "contactcenterinsights.googleapis.com"
    assert config.set_speech_endpoint().api_endpoint == "speech.googleapis.com"
    assert config.set_storage_endpoint().api_endpoint == "https://storage.googleapis.com"
    assert config.set_dlp_endpoint().api_endpoint == "https://dlp.googleapis.com"
    assert config.set_vertex_endpoint().api_endpoint == "https://aiplatform.googleapis.com"

def test_different_regions():
    """Test different regions scenarios"""

    config = base.Config(
        region = 'europe-west1'
    )
    assert config.region == 'europe-west1'

    config = base.Config(
        region = 'europe-west2'
    )
    assert config.region == 'europe-west2'

    config = base.Config(
        region = 'global'
    )
    assert config.region == 'global'

    config = base.Config(
        region = 'us'
    )
    assert config.region == 'us'

    with pytest.raises(ValueError):
        base.Config(region='non-existing-region')
