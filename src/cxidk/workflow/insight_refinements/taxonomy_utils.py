# Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.
"""
Utilities for Taxonomy Standardization and Mapping.
"""

import json
import logging
from typing import List, Dict, Any, Tuple
from google.genai import types
from cxidk.workflow.insight_refinements.schemas.input import BatchAnalysisInput
from cxidk.workflow.insight_refinements.bq_client import TopicBQClient
from cxidk.workflow.insight_refinements.utils import get_gemini_client, qai_logger

logger = logging.getLogger(__name__)

class TaxonomyStandardizer:
    """
    Handles the clustering and standardization of exploratory L2 categories
    using LLM-driven reasoning.
    """

    def __init__(self, config: BatchAnalysisInput):
        self.config = config
        self.bq_client = TopicBQClient(config)
        self.gemini_client = get_gemini_client(config)

    def fetch_unique_categories(self) -> List[str]:
        """Queries BigQuery for all unique L2 categories currently in the results table."""
        dataset_id = self.config.bigquery.dataset_id
        table_id = self.config.topic_refinement.l2_taxonomy_table
        project_id = self.config.bigquery.project_id or self.config.gcp.project_id
        
        full_table_id = f"{project_id}.{dataset_id}.{table_id}"
        
        sql = f"SELECT DISTINCT l2_category FROM `{full_table_id}` WHERE l2_category IS NOT NULL"
        
        qai_logger.log(f"Fetching unique categories from {full_table_id}...", severity="INFO")
        df = self.bq_client.client.query(sql).to_dataframe()
        return df["l2_category"].tolist()

    def generate_standardized_mapping(self, raw_categories: List[str]) -> Tuple[Dict[str, Any], int, int]:
        """
        Calls Gemini to cluster raw strings into master categories 
        and provide a one-to-one mapping.

        Returns:
            Tuple[dict, int, int]: (mapping_data, input_tokens, output_tokens)
        """
        prompt = f"""
<instructions>
Your task:
1. Cluster these raw strings into a clean, concise set of "Master Categories" (L2).
2. Create a JSON mapping where each raw string points to exactly one Master Category.
3. Ensure you include an 'Other' category for items that don't fit well.

Return your response in the following JSON format:
{{
    "master_categories": ["Category 1", "Category 2", ...],
    "mapping": {{
        "Raw String A": "Category 1",
        "Raw String B": "Category 1",
        "Raw String C": "Category 2"
    }}
}}
</instructions>

<data>
{json.dumps(raw_categories, indent=2)}
</data>
"""

        qai_logger.log(f"Requesting LLM standardization for {len(raw_categories)} raw strings...", severity="INFO")
        
        response = self.gemini_client.models.generate_content(
            model=self.config.llm.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are a Taxonomy Architect. Group raw conversational topics into standardized master categories.",
                temperature=1.0,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
            )
        )
        
        try:
            # Note: We rely on response.text and manual parsing if the SDK doesn't 
            # support direct dict parsing for this specific unstructured prompt.
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            mapping_data = json.loads(clean_text)
            
            input_tokens = response.usage_metadata.prompt_token_count
            output_tokens = response.usage_metadata.candidates_token_count
            
            return mapping_data, input_tokens, output_tokens
        except Exception as e:
            logger.error(f"Failed to parse LLM response for taxonomy: {e}")
            raise e
