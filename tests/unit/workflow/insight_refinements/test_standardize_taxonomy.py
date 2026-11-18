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

"""Unit tests for the LLM-driven taxonomy standardization helpers."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from cxidk.workflow.insight_refinements.schemas.input import (
    BatchAnalysisInput,
    GCPConfig,
    CCAIConfig,
    BigQueryConfig,
    TopicRefinementConfig,
    LLMConfig,
)

# We'll implement the core logic in a class we can test easily
# even though the final script will be a CLI wrapper.

@pytest.fixture
def mock_config():
    """Returns a minimal BatchAnalysisInput config for the taxonomy standardizer."""
    return BatchAnalysisInput(
        gcp=GCPConfig(project_id="p", project_number="123", location_id="l"),
        ccai=CCAIConfig(scorecard_id="s"),
        llm=LLMConfig(model_name="gemini-3.0-flash", location_id="l"),
        bigquery=BigQueryConfig(
            dataset_id="d", staging_table_id="st", main_table_id="main"
        ),
        topic_refinement=TopicRefinementConfig(
            issue_model_id="model-123",
            l1_definitions_table="l1_table",
            l2_taxonomy_table="l2_table",
            audit_table="audit_table",
        ),
    )

@patch("cxidk.workflow.insight_refinements.taxonomy_utils.TopicBQClient")
@patch("cxidk.workflow.insight_refinements.utils.get_gemini_client")
# pylint: disable-next=redefined-outer-name  # pytest fixture injection
def test_standardize_taxonomy_logic(mock_gemini, mock_bq, mock_config):
    """
    Tests that the standardizer fetches unique strings and calls Gemini
    to produce a valid taxonomy mapping.
    """
    # 1. Mock BQ unique category response
    mock_df = pd.DataFrame({
        "l2_category": ["Service Downgrade", "Downgraded Service", "Billing Dispute"]
    })
    mock_bq.return_value.client.query.return_value.to_dataframe.return_value = mock_df

    # 2. Mock Gemini response for clustering
    mock_response = MagicMock()
    # Simulating the structured output we want: a list of master categories and a mapping
    mock_response.text = """
    {
        "master_categories": ["Plan Downgrade", "Billing Issue"],
        "mapping": {
            "Service Downgrade": "Plan Downgrade",
            "Downgraded Service": "Plan Downgrade",
            "Billing Dispute": "Billing Issue"
        }
    }
    """
    mock_response.usage_metadata.prompt_token_count = 100
    mock_response.usage_metadata.candidates_token_count = 50
    mock_gemini.return_value.models.generate_content.return_value = mock_response

    # --- This is where we define the class we ARE GOING to build ---
    # Imported here on purpose: taxonomy_utils binds get_gemini_client into its
    # own namespace at import time, so it must be imported while the patch above
    # is active for the stub to take effect.
    # pylint: disable-next=import-outside-toplevel
    from cxidk.workflow.insight_refinements.taxonomy_utils import TaxonomyStandardizer
    standardizer = TaxonomyStandardizer(mock_config)

    unique_categories = standardizer.fetch_unique_categories()
    assert len(unique_categories) == 3

    mapping_data, in_tokens, out_tokens = standardizer.generate_standardized_mapping(
        unique_categories
    )

    assert "master_categories" in mapping_data
    assert "mapping" in mapping_data
    assert mapping_data["mapping"]["Service Downgrade"] == "Plan Downgrade"
    assert isinstance(in_tokens, int)
    assert isinstance(out_tokens, int)
