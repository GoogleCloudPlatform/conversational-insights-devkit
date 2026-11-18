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

"""Unit tests for the IAM Policy wrapper."""

# pylint: disable=redefined-outer-name, protected-access, unused-argument, line-too-long

from typing import Any, Dict, Generator
from unittest.mock import MagicMock

import pytest
from google.iam.v1 import policy_pb2
from google.protobuf.json_format import ParseDict
from pytest_mock import MockerFixture

from cxidk.wrapper.iam import Policy

# --- Constants ---
PROJECT_ID = "test-project"
PROJECT_NAME = f"projects/{PROJECT_ID}"


# --- Fixtures ---


@pytest.fixture
def mock_projects_client(mocker: MockerFixture) -> MagicMock:
    """Mocks the resourcemanager_v3.ProjectsClient."""
    return mocker.patch("cxidk.wrapper.iam.resourcemanager_v3.ProjectsClient")


@pytest.fixture
def mock_iam_admin_client(mocker: MockerFixture) -> MagicMock:
    """Mocks the iam_admin_v1.IAMClient."""
    return mocker.patch("cxidk.wrapper.iam.iam_admin_v1.IAMClient")


@pytest.fixture(autouse=True)
def mock_auth_config(mocker: MockerFixture) -> Generator[None, None, None]:
    """Mocks Auth and Config to prevent external calls."""
    mocker.patch("cxidk.wrapper.iam.base.Auth")
    mocker.patch("cxidk.wrapper.iam.base.Config")
    yield


@pytest.fixture
def iam_policy_manager(
    mock_projects_client: MagicMock, mock_iam_admin_client: MagicMock
) -> Policy:
    """Returns an initialized Policy instance with mocked clients."""
    return Policy(project_id=PROJECT_ID)


# --- Test Class ---


class TestPolicy:
    """Tests for the IAM Policy wrapper."""

    def test_init(
        self, mock_projects_client: MagicMock, mock_iam_admin_client: MagicMock
    ) -> None:
        """Test Policy initialization."""
        manager = Policy(project_id=PROJECT_ID)

        assert manager.project_id == PROJECT_ID
        assert manager.project_name == PROJECT_NAME
        mock_projects_client.assert_called_once()
        mock_iam_admin_client.assert_called_once()

    def test_set(self, iam_policy_manager: Policy) -> None:
        """Test setting an IAM policy."""
        policy_dict = {"bindings": [{"role": "roles/viewer", "members": ["user:test@test.com"]}]}
        iam_policy_manager.set(policy_dict)

        expected_request = {"resource": PROJECT_NAME, "policy": policy_dict}
        iam_policy_manager.client.set_iam_policy.assert_called_once_with( # type: ignore[attr-defined]
            request=expected_request
        )

    def test_get(self, iam_policy_manager: Policy) -> None:
        """Test getting an IAM policy."""
        iam_policy_manager.get()

        expected_request = {"resource": PROJECT_NAME}
        iam_policy_manager.client.get_iam_policy.assert_called_once_with( # type: ignore[attr-defined]
            request=expected_request
        )

    def test_add_new_binding(self, iam_policy_manager: Policy) -> None:
        """Test adding a member to a new role binding."""
        initial_policy_dict: Dict[str, Any] = {"bindings": []}
        initial_policy = ParseDict(initial_policy_dict, policy_pb2.Policy()) # pylint: disable= no-member
        iam_policy_manager.client.get_iam_policy.return_value = initial_policy # type: ignore[attr-defined]

        iam_policy_manager.add(member="user:new@test.com", role="roles/editor")

        # Check that set_iam_policy was called
        iam_policy_manager.client.set_iam_policy.assert_called_once() # type: ignore[attr-defined]
        call_kwargs = iam_policy_manager.client.set_iam_policy.call_args.kwargs # type: ignore[attr-defined]

        # Verify the policy passed to set_iam_policy
        updated_policy = call_kwargs["request"]["policy"]
        assert len(updated_policy.bindings) == 1
        assert updated_policy.bindings[0].role == "roles/editor"
        assert "user:new@test.com" in updated_policy.bindings[0].members

    def test_add_to_existing_binding(self, iam_policy_manager: Policy) -> None:
        """Test adding a member to an existing role binding."""
        initial_policy_dict = {
            "bindings": [{"role": "roles/viewer", "members": ["user:one@test.com"]}]
        }
        initial_policy = ParseDict(initial_policy_dict, policy_pb2.Policy()) # pylint: disable= no-member
        iam_policy_manager.client.get_iam_policy.return_value = initial_policy # type: ignore[attr-defined]

        iam_policy_manager.add(member="user:two@test.com", role="roles/viewer")

        iam_policy_manager.client.set_iam_policy.assert_called_once() # type: ignore[attr-defined]
        call_kwargs = iam_policy_manager.client.set_iam_policy.call_args.kwargs # type: ignore[attr-defined]

        updated_policy = call_kwargs["request"]["policy"]
        assert len(updated_policy.bindings) == 1
        assert "user:one@test.com" in updated_policy.bindings[0].members
        assert "user:two@test.com" in updated_policy.bindings[0].members

    def test_add_member_already_exists(self, iam_policy_manager: Policy) -> None:
        """Test adding a member that already exists in the binding."""
        initial_policy_dict = {
            "bindings": [{"role": "roles/viewer", "members": ["user:one@test.com"]}]
        }
        initial_policy = ParseDict(initial_policy_dict, policy_pb2.Policy()) # pylint: disable= no-member
        iam_policy_manager.client.get_iam_policy.return_value = initial_policy # type: ignore[attr-defined] # pylint: disable=line-too-long
        iam_policy_manager.add(member="user:one@test.com", role="roles/viewer")

        iam_policy_manager.client.set_iam_policy.assert_called_once() # type: ignore[attr-defined]
        call_kwargs = iam_policy_manager.client.set_iam_policy.call_args.kwargs # type: ignore[attr-defined] # pylint: disable=line-too-long

        updated_policy = call_kwargs["request"]["policy"]
        assert len(updated_policy.bindings[0].members) == 1

    def test_list_custom_roles_found(self, iam_policy_manager: Policy) -> None:
        """Test listing custom roles when they exist."""
        mock_role1 = MagicMock()
        mock_role1.name = f"{PROJECT_NAME}/roles/customRole1"
        mock_role2 = MagicMock()
        mock_role2.name = "roles/predefinedRole"

        iam_policy_manager.iam_client.list_roles.return_value = [mock_role1, mock_role2] # type: ignore[attr-defined] # pylint: disable=line-too-long

        result = iam_policy_manager.list_custom_roles()

        assert result is not None
        assert len(result) == 1
        assert result[0] == f"{PROJECT_NAME}/roles/customRole1"
        iam_policy_manager.iam_client.list_roles.assert_called_once() # type: ignore[attr-defined]

    def test_list_custom_roles_not_found(self, iam_policy_manager: Policy) -> None:
        """Test listing custom roles when none exist."""
        mock_role = MagicMock()
        mock_role.name = "roles/predefinedRole"

        iam_policy_manager.iam_client.list_roles.return_value = [mock_role] # type: ignore[attr-defined] # pylint: disable=line-too-long

        result = iam_policy_manager.list_custom_roles()

        assert result is None

    def test_create_custom_role(self, iam_policy_manager: Policy) -> None:
        """Test creating a new custom IAM role."""
        role_id = "my_custom_viewer"
        permissions = ["resourcemanager.projects.get", "resourcemanager.projects.list"]
        title = "My Custom Viewer"
        description = "A custom role for viewing projects."

        iam_policy_manager.create_custom_role(
            role_id=role_id,
            permissions=permissions,
            title=title,
            description=description,
        )

        iam_policy_manager.iam_client.create_role.assert_called_once() # type: ignore[attr-defined]
        call_args = iam_policy_manager.iam_client.create_role.call_args.kwargs["request"] # type: ignore[attr-defined] # pylint: disable=line-too-long

        assert call_args.parent == PROJECT_NAME
        assert call_args.role_id == role_id
        assert call_args.role.title == title
        assert call_args.role.description == description
        assert call_args.role.included_permissions == permissions
        assert call_args.role.stage == iam_policy_manager.iam_client.create_role.call_args.kwargs["request"].role.RoleLaunchStage.BETA # type: ignore[attr-defined] # pylint: disable=line-too-long

    def test_create_custom_role_minimal_args(self, iam_policy_manager: Policy) -> None:
        """Test creating a custom role with only required arguments."""
        role_id = "minimal_role"
        permissions = ["storage.objects.get"]

        iam_policy_manager.create_custom_role(role_id=role_id, permissions=permissions)

        iam_policy_manager.iam_client.create_role.assert_called_once() # type: ignore[attr-defined]
        call_args = iam_policy_manager.iam_client.create_role.call_args.kwargs["request"] # type: ignore[attr-defined] # pylint: disable=line-too-long

        assert call_args.parent == PROJECT_NAME
        assert call_args.role_id == role_id
        assert call_args.role.title == role_id  # Should default to role_id
        assert call_args.role.description == ""
        assert call_args.role.included_permissions == permissions
