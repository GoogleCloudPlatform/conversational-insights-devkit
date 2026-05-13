# Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.
"""
BigQuery Client for Topic Refinement.

This module handles querying CCAI export data, performing incremental reads,
and writing refined L2 taxonomy results and audit logs to BigQuery.
"""

import logging
import pandas as pd
from google.cloud import bigquery
from cxidk.workflow.insight_refinements.schemas.input import BatchAnalysisInput
from cxidk.workflow.insight_refinements.analysis import BigQueryOperator
from cxidk.workflow.insight_refinements.utils import qai_logger

logger = logging.getLogger(__name__)


class TopicBQClient:
    """Specialized BigQuery client for the topic refinement pipeline."""

    def __init__(self, config: BatchAnalysisInput):
        """
        Initializes the TopicBQClient.

        Args:
            config (BatchAnalysisInput): The root configuration object.
        """
        self.config = config
        self.project_id = config.bigquery.project_id or config.gcp.project_id
        self.dataset_id = config.bigquery.dataset_id
        self.bq_operator = BigQueryOperator(config)
        self.client = self.bq_operator.client

    def fetch_new_conversations(self, limit: int = 1000) -> pd.DataFrame:
        """
        Queries the CCAI export table for conversations not yet refined.
        Selects the single highest-scored topic per conversation and
        aggregates the speaker-attributed transcript.

        Args:
            limit (int): Maximum number of conversations to fetch.

        Returns:
            pd.DataFrame: Dataframe containing new conversations, topics, and transcripts.
        """
        # Hub & Spoke: The source table lives in the CCAI Project (Spoke)
        ccai_project_id = (
            self.config.ccai.ccai_insights_project_id or self.config.gcp.project_id
        )
        source_table = (
            f"{ccai_project_id}.{self.dataset_id}.{self.config.bigquery.main_table_id}"
        )

        # Definitions and Results live in the Analytics Project (Hub)
        hub_project_id = self.config.bigquery.project_id or self.config.gcp.project_id
        defs_table = f"{hub_project_id}.{self.dataset_id}.{self.config.topic_refinement.l1_definitions_table}"
        results_table = f"{hub_project_id}.{self.dataset_id}.{self.config.topic_refinement.l2_taxonomy_table}"

        issue_model_id = self.config.topic_refinement.issue_model_id

        sql = f"""
        -- 1. Identify conversations that haven't been processed yet (Incremental Load Pattern)
        WITH unprocessed_conversations AS (
            SELECT 
                s.conversationName AS conversation_id,
                s.sentences,
                s.issues
            FROM `{source_table}` s
            LEFT JOIN `{results_table}` r ON s.conversationName = r.conversation_id
            WHERE r.conversation_id IS NULL
        ),
        -- 2. Unnest the sentences arrays and format into a chronological string
        transcript_agg AS (
            SELECT 
                conversation_id,
                STRING_AGG(CONCAT(sentence.participantRole, ': ', sentence.sentence), '\\n' ORDER BY sentence_offset) as formatted_transcript
            FROM unprocessed_conversations
            CROSS JOIN UNNEST(sentences) as sentence WITH OFFSET as sentence_offset
            GROUP BY 1
        ),
        -- 3. Extract the highest-scored L1 issue for each conversation
        top_topics AS (
            SELECT 
                conversation_id, 
                issue.issueId as l1_issue_id, 
                issue.score
            FROM unprocessed_conversations
            CROSS JOIN UNNEST(issues) as issue
            WHERE issue.issueModelId = '{issue_model_id}'
            -- QUALIFY ensures we only keep the #1 highest scoring issue per conversation
            QUALIFY ROW_NUMBER() OVER(PARTITION BY conversation_id ORDER BY issue.score DESC) = 1
        )
        -- 4. Join the extracted data with the static L1 definitions
        SELECT 
            t.conversation_id, 
            t.l1_issue_id, 
            t.score,
            COALESCE(d.display_name, "Unknown Topic") as l1_topic_name,
            COALESCE(d.description, "No description provided.") as l1_topic_description,
            ta.formatted_transcript
        FROM top_topics t
        JOIN transcript_agg ta ON t.conversation_id = ta.conversation_id
        LEFT JOIN `{defs_table}` d ON t.l1_issue_id = d.issue_id
        LIMIT {limit}
        """

        qai_logger.log(
            "Fetching conversations with transcripts from BigQuery...", severity="INFO"
        )
        query_job = self.client.query(sql)
        df = query_job.to_dataframe()

        qai_logger.log(
            f"Fetched {len(df)} new records with transcripts.", row_count=len(df)
        )
        return df

    def write_l2_results(self, df: pd.DataFrame):
        """
        Writes refined L2 taxonomy results to BigQuery using high-speed streaming inserts.

        Args:
            df (pd.DataFrame): Dataframe containing L2TaxonomyResult data.
        """
        table_id = self.config.topic_refinement.l2_taxonomy_table
        full_table_id = f"{self.project_id}.{self.dataset_id}.{table_id}"

        qai_logger.log(
            f"Writing {len(df)} L2 results to {full_table_id}...", severity="INFO"
        )

        # Use streaming inserts for low-latency batch processing
        errors = self.client.insert_rows_json(full_table_id, df.to_dict(orient="records"))
        if errors:
            qai_logger.log(f"Failed to write L2 results: {errors}", severity="ERROR")
        else:
            qai_logger.log("L2 results written successfully.")

    def write_audit_log(self, df: pd.DataFrame):
        """
        Writes execution audit logs to BigQuery using high-speed streaming inserts.

        Args:
            df (pd.DataFrame): Dataframe containing TopicAuditLog data.
        """
        table_id = self.config.topic_refinement.audit_table
        full_table_id = f"{self.project_id}.{self.dataset_id}.{table_id}"

        logger.info(f"Writing {len(df)} audit entries to {full_table_id}...")

        # Use streaming inserts for low-latency batch processing
        errors = self.client.insert_rows_json(full_table_id, df.to_dict(orient="records"))
        if errors:
            logger.error(f"Failed to write audit logs: {errors}")
        else:
            logger.info("Audit logs written successfully.")
