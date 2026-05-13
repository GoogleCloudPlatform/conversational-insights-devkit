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

"""Workflow for Authorized Views in Contact Center AI Insights."""

import os
import enum
import logging
from typing import Optional
import pandas as pd
from google.api_core import exceptions
from cxidk.wrapper import iam
from cxidk.wrapper import insights
from cxidk.wrapper import sheets


class AgentType(enum.StrEnum):
    """Enumeration of supported agent types."""

    AGENT = "agent"

class SourceType(enum.StrEnum):
    """Enumeration of supported data source types for agent information."""

    CSV = "csv"
    SHEETS = "sheets"

class Manager:
    """Manages the creation and configuration of Contact Center AI Insights Authorized Views.

    This class automates the process of setting up authorized views for agents,
    which includes creating view sets, views with specific agent filters,
    custom IAM roles, and applying the necessary IAM policies to restrict
    data access. It can process agent data from CSV files or Google Sheets.

    Attributes:
        project_id: The Google Cloud project ID.
        location: The Google Cloud location (e.g., 'us-central1').
        parent: The full resource name of the parent location.
        insights: An instance of the insights.AuthorizedViews wrapper.
        iam: An instance of the iam.Policy wrapper.
        view_set_id: The ID of the authorized view set to manage.
        custom_role_id: The ID of the custom IAM role to use.
    """

    def __init__(
        self,
        project_id: str,
        location: str,
        view_set_id: Optional[str] = None,
        custom_role_id: Optional[str] = None,
    ):
        """Initializes the Manager for authorized views.

        Args:
            project_id: The Google Cloud project ID.
            location: The Google Cloud location.
            view_set_id: Optional. The ID of an existing authorized view set.
                If not provided, a default one will be created.
            custom_role_id: Optional. The ID of an existing custom IAM role.
                If not provided, a default one will be created.
        """
        self.project_id = project_id
        self.location = location
        self.parent = f"projects/{project_id}/locations/{location}"
        self.insights = insights.AuthorizedViews(parent=self.parent)
        self.iam = iam.Policy(project_id=project_id)
        self.view_set_id = view_set_id
        self.custom_role_id = custom_role_id

    def _create_view(
        self,
        view_set_id: str,
        agent_id: str,
        agent_name: str,
    ) -> Optional[str]:
        """Creates an authorized view for a specific agent if it doesn't already exist.

        This method first checks if a view with a standardized display name for the
        agent already exists within the given view set. If it does, it returns the
        existing view's ID. If not, it creates a new view with a filter based on
        the agent's ID.

        Args:
            view_set_id: The ID of the parent authorized view set.
            agent_id: The ID of the agent for whom the view is being created.
            agent_name: The name of the agent, used to generate the display name.

        Returns:
            The ID of the created or existing view, or None if creation fails.
        """
        ## Generates standard id
        display_name = f"agent-{agent_name.lower().replace(' ', '-')}-{agent_id}"
        if not any(char.isdigit() for char in display_name):
            display_name = display_name + "-0000"

        list_views = self.insights.list_view(
            view_set_id=view_set_id
        )

        if list_views is not None and 'authorizedViews' in list_views:
            for view in list_views['authorizedViews']:
                if view['displayName'] == display_name:
                    return os.path.basename(view['name'])

        view = self.insights.create_view(
            authorized_view_set_id=view_set_id,
            display_name=display_name,
            conversation_filter=f'agent_id = "{agent_id}"',
        )
        if view and "name" in view:
            return os.path.basename(view["name"])

        logging.error("Failed to create view for agent_id: %s", agent_id)
        return None

    def _create_default_view_set(self) -> Optional[str]:
        """Creates or retrieves the default authorized view set.

        If a `view_set_id` was provided during initialization, this method
        attempts to retrieve it. Otherwise, it creates a new view set with a
        default name.

        Returns:
            The ID of the view set, or None if creation/retrieval fails.
        """
        view_set = None
        if self.view_set_id is not None:
            view_set = self.insights.get_view_set(view_set_id=self.view_set_id)

        if self.view_set_id is None or view_set is None:
            view_set = self.insights.create_view_set(
                authorized_view_set_name="default-viewer"
            )

        if view_set and "name" in view_set:
            name_string = view_set["name"]
            return os.path.basename(name_string)

        logging.error("Failed to create or retrieve authorized view set.")
        return None

    def _create_deafult_role(self, role_id: str = "default_insights_viewer") -> str:
        """Creates a default custom IAM role with minimum required permissions.

        This role grants permissions necessary for an agent to view their own
        authorized conversations in Contact Center AI Insights. If a role with
        the specified ID already exists, it logs the information and proceeds.

        Args:
            role_id: The ID to assign to the new custom role.

        Returns:
            The ID of the created or existing role.
        """
        try:
            self.iam.create_custom_role(
                role_id=role_id,
                title="Default Agent Authorized View",
                description="The minimum required permissions to agents visualize their own data",
                permissions=[
                    "contactcenterinsights.authorizedConversations.get",
                    "monitoring.timeSeries.list",
                    "resourcemanager.projects.get",
                    "storage.objects.get",
                ],
            )
        except exceptions.AlreadyExists:
            logging.info("Role '%s' already exists.", role_id)

        return role_id

    def _add_iam_policy(
        self,
        role: str,
    ) -> None:
        """Adds an IAM policy binding for the authorized view set principal.

        This method grants a specified role to the principal set associated with
        the authorized view set, allowing the Insights service to enforce the
        view's filters.

        Args:
            role: The full name of the IAM role to grant
            (e.g., 'roles/contactcenterinsights.viewer').
        """
        member = (
            "principalSet://contactcenterinsights.googleapis.com/projects/"
            f"{self.project_id}/type/AuthorizedView/ancestor.name/"
            f"authorizedViewSets/{self.view_set_id}"
        )
        policy = self.iam.get()
        for binding in policy.bindings:
            if binding.role == role and member in binding.members:
                break

        self.iam.add(member=member, role=role)

    def _add_agent_custom_role(self, agent_ldap: str, custom_role: str) -> None:
        """Adds an IAM policy binding to grant a custom role to an agent.

        Args:
            agent_ldap: The agent's user identifier (e.g., 'user:agent@example.com').
            custom_role: The ID of the custom role to grant.
        """
        full_role = f"projects/{self.project_id}/roles/{custom_role}"
        self.iam.add(member=agent_ldap, role=full_role)

    def bulk_create_agent_views(
        self,
        source_type: SourceType,
        source_path: str,
        sheet_name: str = "Sheet1",
    ):
        """Orchestrates the bulk creation of authorized views from a data source.

        This method reads agent information from a CSV file or Google Sheet, then
        iterates through each agent to perform the full setup:
        1. Creates a default view set and custom role if they don't exist.
        2. Applies necessary IAM policies.
        3. Creates an authorized view for each agent.
        4. Assigns the custom role to each agent's user account.

        Args:
            source_type: The type of the source, either 'csv' or 'sheets'.
            source_path: The file path for a CSV or the sheet ID for Google Sheets.
        """
        ##Determine based on the type
        if source_type == SourceType.CSV:
            df = pd.read_csv(source_path)
        elif source_type == SourceType.SHEETS:
            logging.info("Reading data from Google Sheets.")
            gsheet = sheets.Sheets(sheet_id=source_path)
            df = gsheet.to_dataframe(sheet_name=sheet_name)
        else:
            raise ValueError("source_type must be either 'csv' or 'sheets'")

        if self.view_set_id is None:
            self.view_set_id = self._create_default_view_set()
        view_set_id: str = self.view_set_id  # type: ignore
        logging.info("Created/founded view set %s", view_set_id)

        ## Creats custom role (if needed)
        if self.custom_role_id is None:
            self.custom_role_id = self._create_deafult_role()
        logging.info("Created custom role %s", self.custom_role_id)

        ## Assign permissions to custom set (if needed)
        self._add_iam_policy(role="roles/contactcenterinsights.viewer")
        logging.info("Assigned permissions to principalset")

        for _, row in df.iterrows():
            logging.info("Processing data for %s", row["agent_id"])
            agent_id = row["agent_id"]
            agent_name = row["agent_name"]
            agent_ldap = row["agent_ldap"]

            ## Assign permissions to agent ldap to the given custom role
            self._add_agent_custom_role(
                agent_ldap=f"user:{agent_ldap}", custom_role=self.custom_role_id
            )
            logging.info("Assigned permissions to %s", str(row["agent_ldap"]))

            try:
                agent_type = AgentType(row["agent_type"])
            except ValueError:
                logging.warning(
                    "Invalid agent_type '%s' for agent_id %s. Skipping.",
                    row["agent_type"],
                    agent_id,
                )
                continue

            if agent_type != AgentType.AGENT:
                raise ValueError(
                    f"Invalid agent_type '{agent_type}' for agent_id {agent_id}"
                )

            view_id = self._create_view(
                view_set_id=view_set_id,
                agent_id=agent_id,
                agent_name=agent_name,
            )
            logging.info("Created view for %s, with view_id: %s", agent_id, view_id)
