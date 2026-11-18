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

"""
BigQuery Client for Topic Refinement.

This module handles querying CCAI export data, performing incremental reads,
and writing refined L2 taxonomy results and audit logs to BigQuery.
"""

import logging
from typing import Any, Dict, List
from google.cloud import bigquery
import pandas as pd
from cxidk.workflow.insight_refinements.schemas.input import (
    BatchAnalysisInput,
    TopicRefinementConfig,
)
from cxidk.workflow.insight_refinements.analysis import (
    BigQueryOperator,
    format_bq_table_ref,
)
from cxidk.workflow.insight_refinements.utils import qai_logger

logger = logging.getLogger(__name__)


def require_topic_config(config: BatchAnalysisInput) -> TopicRefinementConfig:
    """
    Returns the topic refinement configuration section, failing fast if absent.

    The section is optional on the root configuration object, but every topic
    refinement BigQuery operation depends on the table names it carries.

    Args:
        config (BatchAnalysisInput): The root configuration object.

    Returns:
        TopicRefinementConfig: The populated topic refinement configuration.

    Raises:
        ValueError: If the 'topic_refinement' section is missing.
    """
    topic_config = config.topic_refinement
    if topic_config is None:
        raise ValueError(
            "The 'topic_refinement' configuration section is required for topic "
            "refinement BigQuery operations but is missing from the config."
        )
    return topic_config


def _to_json_rows(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Converts a dataframe into streaming-insert rows keyed by column name.

    Pandas allows any hashable column label, while the BigQuery client requires
    string keys, so the labels are normalized here.

    Args:
        df (pd.DataFrame): The dataframe to convert.

    Returns:
        List[Dict[str, Any]]: One string-keyed dictionary per dataframe row.
    """
    return [
        {str(column): value for column, value in record.items()}
        for record in df.to_dict(orient="records")
    ]


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
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer.")

        ccai_project_id = (
            self.config.ccai.ccai_insights_project_id or self.config.gcp.project_id
        )
        source_table = format_bq_table_ref(
            ccai_project_id, self.dataset_id, self.config.bigquery.main_table_id
        )

        hub_project_id = self.config.bigquery.project_id or self.config.gcp.project_id
        topic_config = require_topic_config(self.config)
        defs_table = format_bq_table_ref(
            hub_project_id, self.dataset_id, topic_config.l1_definitions_table
        )
        results_table = format_bq_table_ref(
            hub_project_id, self.dataset_id, topic_config.l2_taxonomy_table
        )

        issue_model_id = str(topic_config.issue_model_id)

        sql = f"""
        WITH unprocessed_conversations AS (
            SELECT
                s.conversationName AS conversation_id,
                s.sentences,
                s.issues
            FROM `{source_table}` s
            LEFT JOIN `{results_table}` r ON s.conversationName = r.conversation_id
            WHERE r.conversation_id IS NULL
        ),
        transcript_agg AS (
            SELECT
                conversation_id,
                STRING_AGG(
                    CONCAT(sentence.participantRole, ': ', sentence.sentence),
                    '\\n' ORDER BY sentence_offset
                ) as formatted_transcript
            FROM unprocessed_conversations
            CROSS JOIN UNNEST(sentences) as sentence WITH OFFSET as sentence_offset
            GROUP BY 1
        ),
        top_topics AS (
            SELECT
                conversation_id,
                issue.issueId as l1_issue_id,
                issue.score
            FROM unprocessed_conversations
            CROSS JOIN UNNEST(issues) as issue
            WHERE issue.issueModelId = @issue_model_id
            QUALIFY ROW_NUMBER() OVER(
                PARTITION BY conversation_id ORDER BY issue.score DESC
            ) = 1
        )
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
        LIMIT @row_limit
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter(
                    "issue_model_id", "STRING", issue_model_id
                ),
                bigquery.ScalarQueryParameter("row_limit", "INT64", limit),
            ]
        )

        qai_logger.log(
            "Fetching conversations with transcripts from BigQuery...", severity="INFO"
        )
        query_job = self.client.query(sql, job_config=job_config)
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
        table_id = require_topic_config(self.config).l2_taxonomy_table
        full_table_id = format_bq_table_ref(
            self.project_id, self.dataset_id, table_id
        )

        qai_logger.log(
            f"Writing {len(df)} L2 results to {full_table_id}...", severity="INFO"
        )

        errors = self.client.insert_rows_json(full_table_id, _to_json_rows(df))
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
        table_id = require_topic_config(self.config).audit_table
        full_table_id = format_bq_table_ref(
            self.project_id, self.dataset_id, table_id
        )

        logger.info("Writing %d audit entries to %s...", len(df), full_table_id)

        errors = self.client.insert_rows_json(full_table_id, _to_json_rows(df))
        if errors:
            logger.error("Failed to write audit logs: %s", errors)
        else:
            logger.info("Audit logs written successfully.")
