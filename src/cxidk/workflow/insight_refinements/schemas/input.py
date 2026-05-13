# Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.
"""
Input Schemas for QAI Optimization Framework.

This module defines the Pydantic models used for validating and structuring
the input configuration and data for the batch analysis and evaluation workflow.
"""

from typing import Optional, Dict
from pydantic import BaseModel, Field, field_validator
from src.core import base


class GCPConfig(BaseModel):
    """
    Configuration for Google Cloud Platform (GCP) resources.

    Attributes:
        project_id (str): The Google Cloud Project ID.
        project_number (str): The Google Cloud Project Number.
        location_id (str): The Google Cloud Location ID (e.g., 'us-central1').
    """

    project_id: str = Field(..., description="The Google Cloud Project ID.")
    project_number: str = Field(..., description="The Google Cloud Project Number.")
    location_id: str = Field(
        ..., description="The Google Cloud Location ID (e.g., 'us-central1')."
    )
    staging_bucket: Optional[str] = Field(
        default=None, description="The Google Cloud Storage bucket for staging files."
    )


class CCAIConfig(BaseModel):
    """
    Configuration for Contact Center AI (CCAI) Insights.

    Attributes:
        ccai_insights_project_id (Optional[str]): The GCP Project ID where CCAI Insights is hosted.
        insights_endpoint (str): The endpoint for CCAI Insights API. If None, derived from location.
        api_version (str): The API version to use (e.g., 'v1').
        scorecard_id (str): The ID of the QA scorecard to use for evaluation.
        feedback_regionalization (bool): Whether to use regionalized feedback endpoints.
    """

    ccai_insights_project_id: Optional[str] = Field(
        default=None,
        description="The GCP Project ID where CCAI Insights is hosted. Falls back to GCPConfig.project_id.",
    )
    insights_endpoint: Optional[str] = Field(
        default=None,
        description="The endpoint for CCAI Insights API. If None, derived from location.",
    )
    api_version: str = Field(
        default="v1", description="The API version to use (e.g., 'v1')."
    )
    scorecard_id: str = Field(
        ..., description="The ID of the QA scorecard to use for evaluation."
    )
    feedback_regionalization: bool = Field(
        default=False,
        description="Whether to use regionalized feedback endpoints.",
    )

    @field_validator("insights_endpoint")
    def validate_endpoint(cls, v):
        if v and not v.endswith("googleapis.com"):
            raise ValueError("Endpoint must be a valid googleapis.com domain")
        return v


class LLMConfig(BaseModel):
    """
    Configuration for the Large Language Model (LLM).

    Attributes:
        model_name (str): The name of the model to use (e.g., 'gemini-1.5-pro-002').
        location_id (str): The location/region for the model.
        max_concurrent_calls (int): Maximum number of concurrent calls to the LLM.
    """

    model_name: str = Field(
        ...,
        description="The name of the model to use (e.g., 'gemini-3.1-flash-lite-preview').",
    )
    location_id: str = Field(..., description="The location/region for the model.")
    max_concurrent_calls: int = Field(
        default=50, ge=1, description="Maximum number of concurrent calls to the LLM."
    )


class AnalysisConfig(BaseModel):
    """
    Configuration for the Batch Analysis process.

    Attributes:
        analysis_percentage (int): Percentage of conversations to re-analyze (0-100).
        max_concurrent_calls (int): Maximum number of concurrent calls to CCAI Insights.
        chunk_size (int): Size of chunks for batch processing.
        page_size (int): Number of conversations to list per page.
        annotator_selector (Optional[Dict[str, bool]]): Configuration to enable/disable specific annotators.
    """

    analysis_percentage: int = Field(
        default=100,
        ge=0,
        le=100,
        description="Percentage of conversations to re-analyze (0-100).",
    )
    max_concurrent_calls: int = Field(
        default=5,
        ge=1,
        description="Maximum number of concurrent calls to CCAI Insights.",
    )
    chunk_size: int = Field(
        default=50, ge=1, description="Size of chunks for batch processing."
    )
    page_size: int = Field(
        default=1000, ge=1, description="Number of conversations to list per page."
    )
    enable_bulk_analysis: bool = Field(
        default=False,
        description="If True, uses the BulkAnalyzeConversations API instead of iterating.",
    )
    filter: str = Field(
        default="",
        description="Filter string to select conversations for bulk analysis (e.g. 'labels.analyzed=false').",
    )
    annotator_selector: Optional[Dict[str, bool]] = Field(
        default={
            "run_entity_annotator": True,
            "run_intent_annotator": True,
            "run_interruption_annotator": True,
            "run_phrase_matcher_annotator": True,
            "run_qa_annotator": True,
            "run_sentiment_annotator": True,
            "run_silence_annotator": True,
            "run_summarization_annotator": True,
        },
        description="Configuration to enable/disable specific annotators.",
    )


class BigQueryConfig(BaseModel):
    """
    Configuration for BigQuery input/output tables.

    Attributes:
        dataset_id (str): The BigQuery dataset ID.
        project_id (Optional[str]): The target Google Cloud Project ID for BigQuery.
        staging_table_id (str): The ID of the staging table for results.
        main_table_id (str): The ID of the main table for results.
    """

    dataset_id: str = Field(..., description="The BigQuery dataset ID.")
    project_id: Optional[str] = Field(
        default=None,
        description="The target Google Cloud Project ID for BigQuery. Falls back to GCPConfig.project_id if not provided.",
    )
    staging_table_id: str = Field(
        ..., description="The ID of the staging table for results."
    )
    main_table_id: str = Field(..., description="The ID of the main table for results.")


class TopicRefinementConfig(BaseModel):
    """
    Configuration for the Topic Refinement process.

    Attributes:
        issue_model_id (str): The CCAI Issue Model ID to export/use.
        l1_definitions_table (str): BQ table for static L1 topic definitions.
        l2_taxonomy_table (str): BQ table for refined L2 results.
        audit_table (str): BQ table for execution audit logs.
    """

    issue_model_id: str = Field(..., description="The CCAI Issue Model ID.")
    prompt_gcs_uri: Optional[str] = Field(
        default=None,
        description="GCS URI for the Gemini prompt template (e.g., gs://bucket/prompt.txt).",
    )
    l1_definitions_table: str = Field(
        default="l1_topic_definitions", description="BQ table for L1 definitions."
    )
    l2_taxonomy_table: str = Field(
        default="l2_taxonomy_results", description="BQ table for L2 results."
    )
    audit_table: str = Field(
        default="topic_refinement_audit", description="BQ table for audit logs."
    )
    approved_taxonomy_file: Optional[str] = Field(
        default=None,
        description="Path to a local JSON file containing a list of approved L2 categories.",
    )


class BatchAnalysisInput(BaseModel):
    """
    Root configuration schema for the Batch Analysis workflow.

    Attributes:
        gcp (GCPConfig): Google Cloud Platform configuration.
        ccai (CCAIConfig): Contact Center AI configuration.
        llm (LLMConfig): Large Language Model configuration.
        analysis (AnalysisConfig): Analysis process configuration.
        bigquery (BigQueryConfig): BigQuery configuration.
        topic_refinement (Optional[TopicRefinementConfig]): Topic refinement configuration.
    """

    gcp: GCPConfig = Field(..., description="Google Cloud Platform configuration.")
    ccai: CCAIConfig = Field(..., description="Contact Center AI configuration.")
    llm: LLMConfig = Field(..., description="Large Language Model configuration.")
    analysis: AnalysisConfig = Field(
        default_factory=AnalysisConfig, description="Analysis process configuration."
    )
    bigquery: BigQueryConfig = Field(..., description="BigQuery configuration.")
    topic_refinement: Optional[TopicRefinementConfig] = Field(
        None, description="Topic refinement configuration."
    )

    def get_auth(self) -> base.Auth:
        """Adapter method to generate the Devkit's native Auth object."""
        return base.Auth()

    def get_config(self) -> base.Config:
        """Adapter method to generate the Devkit's native Config object."""
        return base.Config(region=self.gcp.location_id)


class FeedbackCSVRow(BaseModel):
    """
    Represents a single row in the feedback CSV file.

    Attributes:
        conversation_id (str): The ID of the conversation.
        question_id (str): The ID of the scorecard question.
        answer_value (str): The label/answer to apply (e.g., "Yes", "No").
        rationale (Optional[str]): Explanation or reasoning for the answer.
        score (Optional[float]): Optional manual score override.
    """

    conversation_id: str = Field(..., description="The ID of the conversation.")
    question_id: str = Field(..., description="The ID of the scorecard question.")
    answer_value: str = Field(..., description="The label/answer to apply.")
    rationale: Optional[str] = Field(
        None, description="Explanation or reasoning for the answer."
    )
    score: Optional[float] = Field(None, description="Optional manual score override.")
