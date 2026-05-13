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
"""
Docstring for tests.integration.test_bulk_authorized_views
"""

import os
import pandas as pd
from cxidk.workflow import views_manager as authorized_views


_PROBER_PROJECT_ID = "insights-python-tooling-prober"
_LOCATION = "us-central1"


def test_ingest_from_sheets():
    """Test ingest from sheets"""
    view_manager = authorized_views.Manager(
        project_id=_PROBER_PROJECT_ID,
        location=_LOCATION,
    )

    view_manager.bulk_create_agent_views(
        source_type=authorized_views.SourceType.SHEETS,
        source_path="1z6sVu4yCo_UxNnzUsTTkCPRiqphK",
    )


def test_ingest_from_csv():
    """Test ingest from a CSV file."""
    csv_path = "temp_agent_data.csv"
    data = {
        "agent_id": ["test-agent-1", "test-agent-2"],
        "agent_name": ["Test Agent One", "Test Agent Two"],
        "agent_type": ["agent", "agent"],
        "agent_ldap": ["test-user1@example.com", "test-user2@example.com"],
    }
    df = pd.DataFrame(data)
    df.to_csv(csv_path, index=False)

    try:
        view_manager = authorized_views.Manager(
            project_id=_PROBER_PROJECT_ID,
            location=_LOCATION,
        )
        view_manager.bulk_create_agent_views(
            source_type=authorized_views.SourceType.CSV,
            source_path=csv_path,
        )
    finally:
        os.remove(csv_path)
