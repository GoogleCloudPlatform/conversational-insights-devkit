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

"""Manages IAM policies for Google Cloud projects.
This module provides a wrapper for managing Identity and Access Management (IAM)
policies and custom roles within a Google Cloud project. It simplifies common
IAM operations such as getting, setting, and modifying policies, as well as
creating and listing custom roles by using the `google-cloud-resourcemanager`
and `google-cloud-iam` client libraries.
"""
# pylint: disable= no-member,

from typing import Any, Dict, List, Optional
from google.protobuf.json_format import ParseDict  # type: ignore
from google.protobuf.json_format import MessageToDict

from google.cloud import iam_admin_v1  # type: ignore
from google.cloud.iam_admin_v1 import types as iam_types  # types: ignore
from google.cloud import resourcemanager_v3
from google.cloud.iam_admin_v1.types import CreateRoleRequest
from google.cloud.iam_admin_v1.types import Role


from google.iam.v1 import policy_pb2  # type: ignore
from cxidk.core import base


class Policy:
    """Manages IAM policies and custom roles for a Google Cloud project.
    
    This class wraps the `resourcemanager_v3` and `iam_admin_v1` clients to
    provide a high-level interface for IAM operations. It allows for getting,
    setting, and modifying IAM policies, as well as listing and creating custom
    roles scoped to a specific project.
    
    Attributes:
        project_id: The Google Cloud project ID.
        project_name: The formatted project name string (e.g., "projects/your-project-id").
        client: An instance of `resourcemanager_v3.ProjectsClient`.
        iam_client: An instance of `iam_admin_v1.IAMClient`.
        auth: An authentication handler object.
        config: A configuration handler object.
    """

    def __init__(
        self,
        project_id: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ) -> None:
        """Initializes the Policy client for a specific project.
        
        Args:
            project_id: The unique identifier for the Google Cloud project.
            auth: An optional, pre-configured authentication object.
            config: An optional, pre-configured configuration object.
        """
        self.auth = auth or base.Auth()
        self.config = config or base.Config()

        self.project_id = project_id
        self.project_name = f"projects/{project_id}"
        self.client = resourcemanager_v3.ProjectsClient()
        self.iam_client = iam_admin_v1.IAMClient()

    def set(self, policy: Dict[str, Any]) -> policy_pb2.Policy:
        """Sets the IAM policy for the project, overwriting any existing policy.
        
        Args:
            policy: A dictionary representing the IAM policy to be set.
        
        Returns:
            The updated `policy_pb2.Policy` object returned by the API.
        """
        # The `set_iam_policy` method accepts a dictionary that mirrors
        # the `SetIamPolicyRequest` structure.
        request = {"resource": f"projects/{self.project_id}", "policy": policy}

        return self.client.set_iam_policy(request=request)

    def get(self) -> policy_pb2.Policy:
        """Retrieves the current IAM policy for the project.
        
        Returns:
            The current `policy_pb2.Policy` object.
        """
        request = {"resource": f"projects/{self.project_id}"}
        return self.client.get_iam_policy(request=request)

    def add(self, member: str, role: str) -> None:
        """Adds a new member and role binding to the project's IAM policy.

        Args:
            member: The identifier of the member to add.
            role: The IAM role to assign to the member.
        """
        policy = self.client.get_iam_policy(resource=self.project_name)
        policy_dict = MessageToDict(policy)

        # Find the binding for the given role, or create a new one
        binding_found = False
        for binding in policy_dict.get("bindings", []):
            if binding.get("role") == role:
                if member not in binding.get("members", []):
                    binding.get("members", []).append(member)
                binding_found = True
                break

        if not binding_found:
            policy_dict.setdefault("bindings", []).append(
                {"role": role, "members": [member]}
            )

        policy_object = ParseDict(policy_dict, policy_pb2.Policy())
        self.client.set_iam_policy(
            request={"resource": self.project_name, "policy": policy_object}
        )

    def list_custom_roles(self) -> Optional[list[str]]:
        """Lists the full resource names of custom IAM roles in the project.
        
        Returns:
            A list of custom role resource names, or None if no custom roles exist.
        """
        request = iam_admin_v1.ListRolesRequest(
            parent=self.project_name,
            view=iam_types.RoleView.FULL,
            show_deleted=False,  # Set to True to include deleted roles
        )

        page_result = self.iam_client.list_roles(request=request)
        roles = []
        custom_roles_found = False
        for role in page_result:
            # Custom roles have a path that includes "organizations/" or "projects/"
            if "organizations/" in role.name or "projects/" in role.name:
                roles.append(role.name)
                custom_roles_found = True

        if not custom_roles_found:
            return None
        return roles

    def create_custom_role(
        self,
        role_id: str,
        permissions: List[str],
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Role:
        """Creates a new custom IAM role in the project.
        
        Args:
            role_id: The unique identifier for the custom role.
            permissions: A list of IAM permissions to include in the role.
            title: An optional display title for the role. Defaults to `role_id`.
            description: An optional description for the role.
        
        Returns:
            The created `Role` object.
        """
        # Create the role object with the desired permissions and title
        role_definition = Role(
            title=title if title else role_id,  # Use role_id as title if not provided
            included_permissions=permissions,
            stage=Role.RoleLaunchStage.BETA,
            description=description,
        )

        request = CreateRoleRequest(
            parent=self.project_name, role_id=role_id, role=role_definition
        )

        return self.iam_client.create_role(request=request)
