# Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.
import pytest
from unittest.mock import MagicMock, patch
from cxidk.workflow.insight_refinements.topic_refinement import TopicRefiner
from cxidk.workflow.insight_refinements.schemas.topic import L2TaxonomyResult
from cxidk.workflow.insight_refinements.schemas.input import (
    BatchAnalysisInput,
    GCPConfig,
    CCAIConfig,
    BigQueryConfig,
    LLMConfig,
    TopicRefinementConfig,
)


@pytest.fixture
def mock_config():
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


@patch("src.workflow.insight_refinements.topic_refinement.get_storage_client")
@patch("src.workflow.insight_refinements.topic_refinement.get_gemini_client")
def test_refine_topic_success(mock_genai_client, mock_storage_client, mock_config):
    """Test that the TopicRefiner correctly calls Gemini and parses the response."""
    refiner = TopicRefiner(mock_config)

    # Mock Gemini response
    mock_response = MagicMock()
    mock_response.parsed = L2TaxonomyResult(
        conversation_id="conv-1",
        l1_issue_id="issue-1",
        l2_category="Granular Topic A",
        reasoning="Because of X, Y, Z",
    )
    mock_response.usage_metadata.prompt_token_count = 100
    mock_response.usage_metadata.candidates_token_count = 50
    mock_genai_client.return_value.models.generate_content.return_value = mock_response

    result, audit = refiner.refine_topic(
        conversation_id="conv-1",
        l1_issue_id="issue-1",
        l1_topic_name="General Topic",
        l1_topic_description="Description of general topic",
        formatted_transcript="Agent: Hello",
    )

    assert result.l2_category == "Granular Topic A"
    assert audit.input_tokens == 100
    assert audit.output_tokens == 50
    assert audit.status == "success"

    # Verify prompt contents (simplified)
    args, kwargs = mock_genai_client.return_value.models.generate_content.call_args
    assert "Description of general topic" in str(kwargs["contents"])
    assert "Agent: Hello" in str(kwargs["contents"])


@patch("src.workflow.insight_refinements.topic_refinement.get_storage_client")
@patch("src.workflow.insight_refinements.topic_refinement.get_gemini_client")
def test_refine_topic_malformed_json(
    mock_genai_client, mock_storage_client, mock_config
):
    """Test that TopicRefiner handles malformed LLM responses by falling back to 'Other'."""
    refiner = TopicRefiner(mock_config)

    # Mock Gemini to raise an exception
    mock_genai_client.return_value.models.generate_content.side_effect = Exception(
        "Invalid JSON"
    )

    result, audit = refiner.refine_topic(
        conversation_id="conv-fail",
        l1_issue_id="issue-1",
        l1_topic_name="T",
        l1_topic_description="D",
    )
    assert result.l2_category == "Other"
    assert "Pipeline Error" in result.reasoning
    assert audit.status == "error"


@patch("src.workflow.insight_refinements.topic_refinement.get_storage_client")
@patch("src.workflow.insight_refinements.topic_refinement.get_gemini_client")
def test_prompt_template_gcs_fallback(
    mock_genai_client, mock_storage_client, mock_config
):
    """Test that the refiner falls back to the default prompt if GCS fails."""
    # Force a GCS error during initialization
    mock_storage_client.return_value.bucket.side_effect = Exception("GCS Down")

    # Enable GCS URI in config
    mock_config.topic_refinement.prompt_gcs_uri = "gs://broken/prompt.txt"

    refiner = TopicRefiner(mock_config)

    # Verify it used the fallback template
    from cxidk.workflow.insight_refinements.topic_refinement import DEFAULT_USER_PROMPT_TEMPLATE

    assert refiner.prompt_template == DEFAULT_USER_PROMPT_TEMPLATE


@patch("src.workflow.insight_refinements.topic_refinement.get_storage_client")
@patch("src.workflow.insight_refinements.topic_refinement.get_gemini_client")
@patch("src.workflow.insight_refinements.topic_refinement.os.path.exists")
def test_strict_mode_taxonomy_enforcement(
    mock_exists, mock_genai_client, mock_storage_client, mock_config
):
    """Test that strict mode restricts categories and handles 'Other'."""
    import json
    from unittest.mock import mock_open

    # 1. Setup taxonomy mock
    taxonomy_data = ["Billing Dispute", "Plan Downgrade"]
    mock_config.topic_refinement.approved_taxonomy_file = "approved_taxonomy.json"
    mock_exists.return_value = True

    # 2. Mock Gemini response for 'Other' case
    mock_response = MagicMock()
    mock_response.parsed = L2TaxonomyResult(
        conversation_id="conv-strict",
        l1_issue_id="i1",
        l2_category="Other",
        reasoning="Does not match billing or plan downgrade. Proposing: Novel Urgent Request",
    )
    mock_genai_client.return_value.models.generate_content.return_value = mock_response

    # 3. Execute with patched open for the taxonomy file
    with patch("builtins.open", mock_open(read_data=json.dumps(taxonomy_data))):
        refiner = TopicRefiner(mock_config)
        assert "Billing Dispute" in refiner.approved_categories
        assert "Other" in refiner.approved_categories

        result, _ = refiner.refine_topic("conv-strict", "i1", "T", "D", "Transcript")

        # 4. Assertions
        assert result.l2_category == "Other"
        assert "Novel Urgent Request" in result.reasoning

        # Verify the dynamic response_schema was passed as a dict with enum
        _, kwargs = mock_genai_client.return_value.models.generate_content.call_args
        schema = kwargs["config"].response_schema
        assert "enum" in schema["properties"]["l2_category"]
        assert "Plan Downgrade" in schema["properties"]["l2_category"]["enum"]
