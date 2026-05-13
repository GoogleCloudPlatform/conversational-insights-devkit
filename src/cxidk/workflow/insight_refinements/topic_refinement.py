# Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.
"""
Topic Refinement Logic using Gemini.

This module implements the core refinement logic, taking L1 topics and their
descriptions and using Gemini 3.0/3.1 to generate more granular L2 categories.
"""

import logging
import json
import os
import time
import uuid
from typing import Tuple, List, Optional, Any
from google.genai import types
from cxidk.workflow.insight_refinements.schemas.input import BatchAnalysisInput
from cxidk.workflow.insight_refinements.schemas.topic import L2TaxonomyResult, TopicAuditLog
from cxidk.workflow.insight_refinements.utils import (
    handle_api_quota,
    get_gemini_client,
    get_storage_client,
)

logger = logging.getLogger(__name__)

# --- Fallback Prompt Templates (Used if GCS URI is missing) ---

DEFAULT_SYSTEM_PROMPT = """
You are a Taxonomy Architect. Refine L1 Topics into L2 Categories using the provided transcript.
"""

DEFAULT_USER_PROMPT_TEMPLATE = """
<context>
    <l1_topic>{l1_topic_name}</l1_topic>
    <l1_description>{l1_topic_description}</l1_description>
    <transcript>{formatted_transcript}</transcript>
</context>
Analyze the transcript and Level 1 context to deduce a granular Level 2 category.
"""

STRICT_MODE_INSTRUCTIONS = """
<constraints>
YOU MUST CLASSIFY THE CONVERSATION INTO EXACTLY ONE OF THE APPROVED CATEGORIES BELOW.
DO NOT INVENT NEW CATEGORIES.

APPROVED CATEGORIES:
{approved_categories_list}

If the transcript does not strongly match any approved category, you MUST select 'Other'. 
If you select 'Other', you MUST propose a better category name inside your 'reasoning' explanation.
</constraints>
"""


class TopicRefiner:
    """Orchestrates topic refinement using Gemini 3.0/3.1."""

    def __init__(self, config: BatchAnalysisInput):
        """
        Initializes the TopicRefiner.

        Args:
            config (BatchAnalysisInput): The root configuration object.
        """
        self.config = config
        self.client = get_gemini_client(config)
        self.storage_client = get_storage_client(config)
        self.model_name = config.llm.model_name
        self.run_id = str(uuid.uuid4())

        # 1. Load prompt from GCS if available
        self.prompt_template = self._load_prompt_template()

        # 2. Load approved taxonomy for Strict Mode
        self.approved_categories = self._load_approved_taxonomy()

    def _load_prompt_template(self) -> str:
        """Loads the prompt template from GCS or falls back to default."""
        if (
            not self.config.topic_refinement
            or not self.config.topic_refinement.prompt_gcs_uri
        ):
            logger.info("No prompt_gcs_uri provided. Using default template.")
            return DEFAULT_USER_PROMPT_TEMPLATE

        uri = self.config.topic_refinement.prompt_gcs_uri
        try:
            bucket_name = uri.replace("gs://", "").split("/")[0]
            blob_name = "/".join(uri.replace("gs://", "").split("/")[1:])
            bucket = self.storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            content = blob.download_as_text()
            logger.info(f"Successfully loaded prompt template from {uri}")
            return content
        except Exception as e:
            logger.error(f"Failed to load prompt from {uri}: {e}. Falling back.")
            return DEFAULT_USER_PROMPT_TEMPLATE

    def _load_approved_taxonomy(self) -> Optional[List[str]]:
        """Loads the approved list of categories from a local JSON file."""
        if (
            not self.config.topic_refinement
            or not self.config.topic_refinement.approved_taxonomy_file
        ):
            return None

        file_path = self.config.topic_refinement.approved_taxonomy_file
        if not os.path.exists(file_path):
            logger.warning(f"Taxonomy file {file_path} not found. Skipping strict mode.")
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Support both a simple list and the structured output from our script
            if isinstance(data, dict) and "master_categories" in data:
                categories = data["master_categories"]
            elif isinstance(data, list):
                categories = data
            else:
                logger.error(f"Unsupported taxonomy format in {file_path}")
                return None
            
            # Ensure 'Other' is always an option
            if "Other" not in categories:
                categories.append("Other")
            
            logger.info(f"Strict Mode Enabled. Loaded {len(categories)} categories.")
            return categories
        except Exception as e:
            logger.error(f"Failed to load taxonomy from {file_path}: {e}")
            return None

    def _get_response_schema(self) -> Any:
        """
        Generates the response schema. If strict mode is enabled, 
        injects an 'enum' constraint into the JSON schema.
        """
        if not self.approved_categories:
            return L2TaxonomyResult

        # Convert Pydantic model to a raw JSON Schema dict and inject enum
        schema = L2TaxonomyResult.model_json_schema()
        schema["properties"]["l2_category"]["enum"] = self.approved_categories
        return schema

    @handle_api_quota()
    def refine_topic(
        self,
        conversation_id: str,
        l1_issue_id: str,
        l1_topic_name: str,
        l1_topic_description: str,
        formatted_transcript: str = "",
        is_retry: bool = False,
    ) -> Tuple[L2TaxonomyResult, TopicAuditLog]:
        """
        Calls Gemini to refine an L1 topic into an L2 category.
        """
        full_user_prompt = self.prompt_template.format(
            l1_topic_name=l1_topic_name,
            l1_topic_description=l1_topic_description,
            formatted_transcript=formatted_transcript,
        )

        # Inject strict mode instructions if enabled
        if self.approved_categories:
            full_user_prompt += "\n\n" + STRICT_MODE_INSTRUCTIONS.format(
                approved_categories_list=", ".join(self.approved_categories)
            )

        start_time = time.time()
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=DEFAULT_SYSTEM_PROMPT,
                    temperature=1.0,
                    response_mime_type="application/json",
                    response_schema=self._get_response_schema(),
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
                ),
            )
            latency = (time.time() - start_time) * 1000

            # Manual parsing since we might have passed a raw dict schema
            if isinstance(response.parsed, L2TaxonomyResult):
                result = response.parsed
            else:
                # If we passed a dict schema, the SDK might return a dict or string
                result = L2TaxonomyResult.model_validate(response.parsed)

            result.conversation_id = conversation_id
            result.l1_issue_id = l1_issue_id
            result.model_version = self.model_name
            result.processed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            audit = TopicAuditLog(
                run_id=self.run_id,
                conversation_id=conversation_id,
                status="success",
                latency_ms=latency,
                input_tokens=response.usage_metadata.prompt_token_count,
                output_tokens=response.usage_metadata.candidates_token_count,
            )

            return result, audit

        except Exception as e:
            if not is_retry:
                logger.warning(f"Refinement failed for {conversation_id}: {e}. Retrying...")
                return self.refine_topic(
                    conversation_id, l1_issue_id, l1_topic_name, l1_topic_description, 
                    formatted_transcript, is_retry=True
                )
            
            # Fallback to 'Other' on second failure
            latency = (time.time() - start_time) * 1000
            logger.error(f"Refinement failed twice for {conversation_id}. Falling back to 'Other'.")
            
            result = L2TaxonomyResult(
                conversation_id=conversation_id,
                l1_issue_id=l1_issue_id,
                l2_category="Other",
                reasoning=f"Pipeline Error: {str(e)}",
                model_version=self.model_name,
                processed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            )
            
            audit = TopicAuditLog(
                run_id=self.run_id,
                conversation_id=conversation_id,
                status="error",
                error_message=str(e),
                latency_ms=latency,
                input_tokens=0,
                output_tokens=0,
            )
            return result, audit
