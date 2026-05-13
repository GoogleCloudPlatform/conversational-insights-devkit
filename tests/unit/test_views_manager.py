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

"""Unit tests for the Authorized Views Manager workflow."""

# pylint: disable=redefined-outer-name, protected-access, unused-argument, line-too-long

from typing import Dict
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from google.api_core import exceptions
from pytest_mock import MockerFixture

from cxidk.workflow.views_manager import Manager, SourceType

# --- Constants ---
PROJECT_ID = "test-project"
LOCATION = "us-central1"
PARENT = f"projects/{PROJECT_ID}/locations/{LOCATION}"
VIEW_SET_ID = "test-view-set-123"
CUSTOM_ROLE_ID = "test_custom_role"


# --- Fixtures ---


@pytest.fixture
def mock_insights_wrapper(mocker: MockerFixture) -> MagicMock:
    """Mocks the insights.AuthorizedViews wrapper."""
    return mocker.patch("cxidk.workflow.views_manager.insights.AuthorizedViews")


@pytest.fixture
def mock_iam_wrapper(mocker: MockerFixture) -> MagicMock:
    """Mocks the iam.Policy wrapper."""
    return mocker.patch("cxidk.workflow.views_manager.iam.Policy")


@pytest.fixture
def mock_sheets_wrapper(mocker: MockerFixture) -> MagicMock:
    """Mocks the sheets.Sheets wrapper."""
    return mocker.patch("cxidk.workflow.views_manager.sheets.Sheets")


@pytest.fixture
def mock_pandas_read_csv(mocker: MockerFixture) -> MagicMock:
    """Mocks pandas.read_csv."""
    return mocker.patch("cxidk.workflow.views_manager.pd.read_csv")


@pytest.fixture
def mock_logging(mocker: MockerFixture) -> Dict[str, MagicMock]:
    """Mocks logging methods."""
    return {
        "info": mocker.patch("cxidk.workflow.views_manager.logging.info"),
        "error": mocker.patch("cxidk.workflow.views_manager.logging.error"),
        "warning": mocker.patch("cxidk.workflow.views_manager.logging.warning"),
    }


@pytest.fixture
def views_manager(
    mock_insights_wrapper: MagicMock, mock_iam_wrapper: MagicMock
) -> Manager:
    """Returns an initialized Manager instance."""
    return Manager(
        project_id=PROJECT_ID,
        location=LOCATION,
        view_set_id=VIEW_SET_ID,
        custom_role_id=CUSTOM_ROLE_ID,
    )


# --- Test Class ---


class TestManager:
    """Tests for the views manager."""

    def test_init(
        self, mock_insights_wrapper: MagicMock, mock_iam_wrapper: MagicMock
    ) -> None:
        """Test Manager initialization."""
        manager = Manager(
            project_id=PROJECT_ID,
            location=LOCATION,
            view_set_id=VIEW_SET_ID,
            custom_role_id=CUSTOM_ROLE_ID,
        )

        assert manager.project_id == PROJECT_ID
        assert manager.location == LOCATION
        assert manager.parent == PARENT
        assert manager.view_set_id == VIEW_SET_ID
        assert manager.custom_role_id == CUSTOM_ROLE_ID

        mock_insights_wrapper.assert_called_once_with(parent=PARENT)
        mock_iam_wrapper.assert_called_once_with(project_id=PROJECT_ID)

    def test_create_view_exists(self, views_manager: Manager) -> None:
        """Test _create_view when the view already exists."""
        views_manager.insights.list_view.return_value = { # type: ignore[attr-defined]
            "authorizedViews": [
                {
                    "name": f"{PARENT}/authorizedViewSets/{VIEW_SET_ID}/authorizedViews/existing-view-123",
                    "displayName": "agent-john-doe-12345",
                }
            ]
        }

        result = views_manager._create_view(
            view_set_id=VIEW_SET_ID, agent_id="12345", agent_name="John Doe"
        )

        assert result == "existing-view-123"
        views_manager.insights.create_view.assert_not_called() # type: ignore[attr-defined]

    def test_create_view_new(self, views_manager: Manager) -> None:
        """Test _create_view for a new view."""
        views_manager.insights.list_view.return_value = {"authorizedViews": []} # type: ignore[attr-defined]
        views_manager.insights.create_view.return_value = { # type: ignore[attr-defined]
            "name": f"{PARENT}/authorizedViewSets/{VIEW_SET_ID}/authorizedViews/new-view-456"
        }

        result = views_manager._create_view(
            view_set_id=VIEW_SET_ID, agent_id="54321", agent_name="Jane Smith"
        )

        assert result == "new-view-456"
        views_manager.insights.create_view.assert_called_once_with( # type: ignore[attr-defined]
            authorized_view_set_id=VIEW_SET_ID,
            display_name="agent-jane-smith-54321",
            conversation_filter='agent_id = "54321"',
        )

    def test_create_view_creation_fails(
        self, views_manager: Manager, mock_logging: Dict[str, MagicMock]
    ) -> None:
        """Test _create_view when view creation fails."""
        views_manager.insights.list_view.return_value = {} # type: ignore[attr-defined]
        views_manager.insights.create_view.return_value = None # type: ignore[attr-defined]

        result = views_manager._create_view(
            view_set_id=VIEW_SET_ID, agent_id="123", agent_name="Fail"
        )

        assert result is None
        mock_logging["error"].assert_called_once_with(
            "Failed to create view for agent_id: %s", "123"
        )

    def test_create_default_view_set_exists(self, views_manager: Manager) -> None:
        """Test _create_default_view_set when the view set already exists."""
        views_manager.insights.get_view_set.return_value = { # type: ignore[attr-defined]
            "name": f"{PARENT}/authorizedViewSets/{VIEW_SET_ID}"
        }

        result = views_manager._create_default_view_set()

        assert result == VIEW_SET_ID
        views_manager.insights.create_view_set.assert_not_called() # type: ignore[attr-defined]

    def test_create_default_view_set_new(self, views_manager: Manager) -> None:
        """Test _create_default_view_set for a new view set."""
        manager = Manager(project_id=PROJECT_ID, location=LOCATION)  # No view_set_id
        manager.insights.create_view_set.return_value = { # type: ignore[attr-defined]
            "name": f"{PARENT}/authorizedViewSets/new-view-set"
        }

        result = manager._create_default_view_set()

        assert result == "new-view-set"
        manager.insights.create_view_set.assert_called_once_with( # type: ignore[attr-defined] # pylint: disable=no-member
            authorized_view_set_name="default-viewer"
        )

    def test_create_default_role(self, views_manager: Manager) -> None:
        """Test _create_deafult_role."""
        result = views_manager._create_deafult_role(role_id="my_role")

        assert result == "my_role"
        views_manager.iam.create_custom_role.assert_called_once() # type: ignore[attr-defined]
        call_args = views_manager.iam.create_custom_role.call_args[1] # type: ignore[attr-defined]
        assert call_args["role_id"] == "my_role"
        assert "contactcenterinsights.authorizedConversations.get" in call_args["permissions"]

    def test_create_default_role_already_exists(
        self, views_manager: Manager, mock_logging: Dict[str, MagicMock]
    ) -> None:
        """Test _create_deafult_role when the role already exists."""
        views_manager.iam.create_custom_role.side_effect = exceptions.AlreadyExists( # type: ignore[attr-defined]
            "Role exists"
        )

        views_manager._create_deafult_role(role_id="existing_role")

        mock_logging["info"].assert_called_once_with(
            "Role '%s' already exists.", "existing_role"
        )

    def test_add_iam_policy(self, views_manager: Manager) -> None:
        """Test _add_iam_policy."""
        mock_policy = MagicMock()
        mock_policy.bindings = []
        views_manager.iam.get.return_value = mock_policy # type: ignore[attr-defined]

        views_manager._add_iam_policy(role="roles/test.role")

        expected_member = (
            "principalSet://contactcenterinsights.googleapis.com/projects/"
            f"{PROJECT_ID}/type/AuthorizedView/ancestor.name/"
            f"authorizedViewSets/{VIEW_SET_ID}"
        )
        views_manager.iam.add.assert_called_once_with( # type: ignore[attr-defined]
            member=expected_member, role="roles/test.role"
        )

    def test_add_agent_custom_role(self, views_manager: Manager) -> None:
        """Test _add_agent_custom_role."""
        views_manager._add_agent_custom_role(
            agent_ldap="test.user@example.com", custom_role="my_custom_role"
        )

        views_manager.iam.add.assert_called_once_with( # type: ignore[attr-defined]
            member="test.user@example.com",
            role=f"projects/{PROJECT_ID}/roles/my_custom_role",
        )

    @patch.object(Manager, "_create_default_view_set", return_value="created-view-set")
    @patch.object(Manager, "_create_deafult_role", return_value="created-role")
    @patch.object(Manager, "_add_iam_policy")
    @patch.object(Manager, "_add_agent_custom_role")
    @patch.object(Manager, "_create_view", return_value="created-view")
    def test_bulk_create_agent_views_csv(
        self,
        mock_create_view: MagicMock,
        mock_add_agent_role: MagicMock,
        mock_add_policy: MagicMock,
        mock_create_role: MagicMock,
        mock_create_view_set: MagicMock,
        views_manager: Manager,
        mock_pandas_read_csv: MagicMock,
    ) -> None:
        """Test bulk_create_agent_views with a CSV source."""
        # Instantiate a new manager without custom_role_id to ensure _create_deafult_role is called
        manager = Manager(
            project_id=PROJECT_ID,
            location=LOCATION,
        )

        # Setup mock DataFrame
        mock_df = pd.DataFrame(
            {
                "agent_id": ["111", "222"],
                "agent_name": ["Agent One", "Agent Two"],
                "agent_ldap": ["one@test.com", "two@test.com"],
                "agent_type": ["agent", "agent"],
            }
        )
        mock_pandas_read_csv.return_value = mock_df

        manager.bulk_create_agent_views(
            source_type=SourceType.CSV, source_path="path/to/file.csv"
        )

        mock_pandas_read_csv.assert_called_once_with("path/to/file.csv")

        # Verify orchestration methods were called
        assert mock_create_view_set.called
        assert mock_create_role.called
        assert mock_add_policy.called

        # Verify calls per agent
        assert mock_add_agent_role.call_count == 2
        assert mock_create_view.call_count == 2

        # Check calls for the first agent
        mock_add_agent_role.assert_any_call(
            agent_ldap="user:one@test.com", custom_role=manager.custom_role_id
        )
        mock_create_view.assert_any_call(
            view_set_id=manager.view_set_id,
            agent_id="111",
            agent_name="Agent One",
        )
