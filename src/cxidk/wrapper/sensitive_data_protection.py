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

"""A wrapper for the Google Cloud Data Loss Prevention (DLP) API.

This module provides a simplified interface for interacting with the Google
Cloud DLP API. It includes a `DLP` class that facilitates the creation and
management of inspect and de-identify templates, as well as redacting sensitive
data from text and structured data.
"""

# pylint: disable= no-member
import enum
from typing import Optional
from google.cloud import dlp_v2
from cxidk.core import base

class RedactionType(enum.StrEnum):
    """Enum for supported redaction input types."""
    TEXT = "text"
    TABLE = "table"

class DLP:
    """A wrapper for Google Cloud Data Loss Prevention (DLP) operations.

    This class provides methods to create and manage DLP templates and to
    de-identify content using these templates.

    Attributes:
        project_id: The Google Cloud project ID.
        location: The Google Cloud location for DLP operations.
        auth: An authentication object.
        config: A configuration object.
        client: An instance of the `dlp_v2.DlpServiceClient`.
        parent: The formatted parent resource string for API requests.
    """
    def __init__(
        self,
        project_id: str,
        location: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ) -> None:
        """Initializes the DLP client.

        Args:
            project_id: The Google Cloud project ID.
            location: The Google Cloud location for DLP operations.
            auth: An optional, pre-configured authentication object.
            config: An optional, pre-configured configuration object.
        """
        self.auth = auth or base.Auth()
        self.config = config or base.Config()
        self.project_id = project_id
        self.location = location

        self.client = dlp_v2.DlpServiceClient()

        self.parent = f"projects/{self.project_id}/locations/{self.location}"

    def create_inspect_template(
        self,
        template_id: str = "default_insights_template",
        display_name: str = "Default Insights Template",
        description: str = "Default Insights Template",
        info_types: Optional[list[str]] = None,
    ) -> str:
        """Creates a DLP inspect template.
        Args:
            template_id: The ID of the template to create.
            display_name: The display name of the template.
            description: The description of the template.
            info_types: A list of infoType names to inspect for.
        Returns:
            The full path of the created InspectTemplate.
        """

        if info_types is None:
            info_types = ["PERSON_NAME", "EMAIL_ADDRESS"]

        # Specify the infoTypes to match.
        info_types_config = [{"name": info_type} for info_type in info_types]

        # Specify the inspection rule set.
        inspect_config = {
            "info_types": info_types_config,
            "min_likelihood": dlp_v2.Likelihood.POSSIBLE,
            "include_quote": True,
        }

        # Create the InspectTemplate object.
        inspect_template = {
            "display_name": display_name,
            "description": description,
            "inspect_config": inspect_config,
        }

        # Create the request.
        request = dlp_v2.CreateInspectTemplateRequest(
            parent=self.parent,
            template_id=template_id,
            inspect_template=inspect_template,
        )

        # Call the API.
        response = self.client.create_inspect_template(request=request)

        return response.name

    def get_inspect_template(
        self,
        template_id: str = "default_insights_template",
    ) -> dlp_v2.InspectTemplate:
        """Gets a DLP inspect template.
        Args:
            template_id: The ID of the template to retrieve.
        Returns:
            The InspectTemplate object.
        """
        # Construct the full template name.
        template_name = (
            f"{self.parent}/inspectTemplates/{template_id}"
        )

        # Create the request.
        request = dlp_v2.GetInspectTemplateRequest(
            name=template_name,
        )

        # Call the API.
        response = self.client.get_inspect_template(request=request)

        return response

    def create_deidentify_template(
        self,
        template_id: str = "default_deidentify_template",
        display_name: str = "Default deidentify template",
        description: str = "Default deidentify template",
        info_types: Optional[list[str]] = None,
    ) -> str:
        """Creates a DLP de-identify template.
        This example creates a template that replaces specified infoTypes with
        the name of the infoType. For example, "John Doe" becomes "[PERSON_NAME]".
        Args:
            template_id: The ID of the template to create.
            display_name: The display name of the template.
            description: The description of the template.
            info_types: A list of infoType names to de-identify.
                If None, defaults to ["PERSON_NAME", "EMAIL_ADDRESS"].
        Returns:
            The created DeidentifyTemplate object.
        """
        if info_types is None:
            info_types = ["PERSON_NAME", "EMAIL_ADDRESS"]

        # Define the transformation.
        transformation = {
            "primitive_transformation": {
                "replace_with_info_type_config": {}
            },
            "info_types": [{"name": name} for name in info_types],
        }

        # Create the de-identify config.
        deidentify_config = {
            "info_type_transformations": {
                "transformations": [transformation],
            }
        }

        # Create the DeidentifyTemplate object.
        deidentify_template = {
            "display_name": display_name or template_id,
            "description": description or "De-identify template using infoType replacement",
            "deidentify_config": deidentify_config,
        }

        # Create the request.
        request = dlp_v2.CreateDeidentifyTemplateRequest(
            parent=self.parent,
            template_id=template_id,
            deidentify_template=deidentify_template,
        )

        # Call the API.
        response = self.client.create_deidentify_template(request=request)

        return response.name

    def get_deidentify_template(
        self,
        template_id: str = "default_deidentify_template",
    ) -> dlp_v2.DeidentifyTemplate:
        """Gets a DLP de-identify template.
        Args:
            template_id: The ID of the template to retrieve.
        Returns:
            The DeidentifyTemplate object.
        """
        # Construct the full template name.
        template_name = (
            f"{self.parent}/deidentifyTemplates/{template_id}"
        )

        # Create the request.
        request = dlp_v2.GetDeidentifyTemplateRequest(
            name=template_name,
        )

        # Call the API.
        response = self.client.get_deidentify_template(request=request)

        return response

    def redact(
        self,
        data: dict,
        input_type: RedactionType= RedactionType.TABLE,
        inspect_template: Optional[str] = None,
        deidentify_template: Optional[str] = None,
    ) -> dlp_v2.DeidentifyContentResponse:
        """Redacts sensitive data from a given dictionary.

        This method de-identifies content within a table structure using specified
        or default DLP templates.

        Args:
            data: A dictionary containing 'transcript_header' and 'transcript' keys.
            input_type: The type of input data, currently supports `RedactionType.TABLE`.
            inspect_template: The resource name of the DLP inspect template to use.
            deidentify_template: The resource name of the DLP de-identify template to use.

        Returns:
            A `DeidentifyContentResponse` object containing the redacted content.

        Raises:
            NotImplementedError: If the `input_type` is not `RedactionType.TABLE`.
        """
        if inspect_template is None:
            inspect_template = self.create_inspect_template()

        if deidentify_template is None:
            deidentify_template = self.create_deidentify_template()

        if input_type == RedactionType.TABLE:
            header = data['transcript_header']
            values = data['transcript']
            table = {
                'table' : {
                    'headers': header,
                    'rows': [{
                            'values': values
                        }]
                }
            }

            response = self.client.deidentify_content(
                request= dlp_v2.types.DeidentifyContentRequest(
                    parent= self.parent,
                    inspect_template_name= inspect_template,
                    deidentify_template_name= deidentify_template,
                    item= table
                )
            )
            return response

        # This path should not be reachable if only TABLE is supported, but it satisfies the linter.
        raise NotImplementedError(f"Redaction for input_type '{input_type}' is not implemented.")
