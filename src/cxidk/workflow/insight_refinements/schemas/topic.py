# Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.
"""
Topic Schemas for QAI Optimization Framework.

This module defines the Pydantic models used for structuring topic-related data,
including L1 definitions, L2 taxonomy results, and audit logging.
"""

from typing import Optional
from pydantic import BaseModel, Field


class L1TopicDefinition(BaseModel):
    """
    Represents a static L1 topic definition exported from CCAI.

    Attributes:
        issue_model_id (str): The ID of the issue model this topic belongs to.
        issue_id (str): Unique identifier for the issue/topic.
        display_name (str): Human-readable name of the topic.
        description (str): Detailed description of what this topic covers.
        exported_at (str): ISO timestamp of when this definition was exported.
    """

    issue_model_id: str = Field(..., description="The ID of the issue model.")
    issue_id: str = Field(..., description="Unique identifier for the issue.")
    display_name: str = Field(..., description="Human-readable name of the topic.")
    description: str = Field(..., description="Detailed description of the topic.")
    exported_at: str = Field(..., description="ISO timestamp of export.")


class L2TaxonomyResult(BaseModel):
    """
    Represents the result of refining an L1 topic into an L2 category.

    Attributes:
        conversation_id (str): Unique identifier for the conversation.
        l1_issue_id (str): The original L1 issue ID.
        l2_category (str): The refined L2 category name.
        reasoning (str): The model's reasoning for this categorization.
        model_version (Optional[str]): The Gemini model version used.
        processed_at (Optional[str]): ISO timestamp of processing.
    """

    conversation_id: str = Field(
        ..., description="Unique identifier for the conversation."
    )
    l1_issue_id: str = Field(..., description="The original L1 issue ID.")
    l2_category: str = Field(..., description="The refined L2 category name.")
    reasoning: str = Field(
        ..., description="The model's reasoning for this categorization."
    )
    model_version: Optional[str] = Field(
        None, description="The Gemini model version used."
    )
    processed_at: Optional[str] = Field(
        None, description="ISO timestamp of processing."
    )


class TopicAuditLog(BaseModel):
    """
    Audit log entry for a topic refinement execution.

    Attributes:
        run_id (str): Unique ID for the execution run.
        conversation_id (str): The conversation processed.
        status (str): Outcome of the refinement (e.g., 'success', 'error').
        error_message (Optional[str]): Detailed error if status is 'error'.
        latency_ms (float): API latency in milliseconds.
        input_tokens (int): Count of input tokens.
        output_tokens (int): Count of output tokens.
    """

    run_id: str = Field(..., description="Unique ID for the execution run.")
    conversation_id: str = Field(..., description="The conversation processed.")
    status: str = Field(..., description="Outcome of the refinement.")
    error_message: Optional[str] = Field(None, description="Detailed error if failed.")
    latency_ms: float = Field(..., description="API latency in milliseconds.")
    input_tokens: int = Field(..., description="Count of input tokens.")
    output_tokens: int = Field(..., description="Count of output tokens.")
