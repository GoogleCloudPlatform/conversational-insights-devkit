# Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.
"""
Batch Analysis Logic for QAI Optimization Framework.

This module provides classes and functions for performing batch analysis
on CCAI conversations and exporting the results to BigQuery.
"""

from typing import Dict, List, Optional

import pandas as pd
from google.cloud import bigquery
from cxidk.workflow.insight_refinements.schemas.input import BatchAnalysisInput
from cxidk.workflow.insight_refinements.utils import qai_logger, get_bq_client
from src.wrapper.insights import Analysis, Annotators


def _annotator_dict_to_enum_list(annotator_selector: Optional[Dict[str, bool]]) -> List[Annotators]:
    """
    Translates the pipeline's boolean dictionary into the Devkit's Annotators Enum list.
    """
    selected: List[Annotators] = []
    if annotator_selector is None:
        return selected

    if annotator_selector.get("run_issue_model_annotator"):
        selected.append(Annotators.TOPIC_MODEL)
    if annotator_selector.get("run_summarization_annotator"):
        selected.append(Annotators.SUMMARIZATION)

    # If any of the insights annotators are true, we just map to INSIGHTS enum
    # which the wrapper expands into the full suite.
    insights_keys = [
        "run_intent_annotator",
        "run_entity_annotator",
        "run_sentiment_annotator",
        "run_phrase_matcher_annotator",
        "run_silence_annotator",
        "run_interruption_annotator"
    ]
    if any(annotator_selector.get(k) for k in insights_keys):
        selected.append(Annotators.INSIGHTS)

    return selected


class BigQueryOperator:
    """
    Class for managing BigQuery operations for analysis results.
    """

    def __init__(self, config: BatchAnalysisInput):
        """
        Initializes the BigQueryOperator.

        Args:
            config (BatchAnalysisInput): The root configuration object.
        """
        self.project_id = config.bigquery.project_id or config.gcp.project_id
        self.dataset_id = config.bigquery.dataset_id
        self.client = get_bq_client(config)

    def load_dataframe_to_staging(
        self, df: pd.DataFrame, table_id: str, write_disposition: str = "WRITE_TRUNCATE"
    ):
        """
        Loads a Pandas DataFrame into a BigQuery staging table.

        Args:
            df (pd.DataFrame): The data to load.
            table_id (str): The staging table ID.
            write_disposition (str): The BQ write disposition (default: WRITE_TRUNCATE).
        """
        full_table_id = f"{self.project_id}.{self.dataset_id}.{table_id}"
        job_config = bigquery.LoadJobConfig(write_disposition=write_disposition)

        job = self.client.load_table_from_dataframe(
            df, full_table_id, job_config=job_config
        )
        job.result()
        qai_logger.log(
            "Loaded rows into staging", table_id=full_table_id, row_count=len(df)
        )

    def merge_staging_to_main(
        self,
        staging_table: str,
        main_table: str,
        merge_keys: List[str],
        update_columns: List[str],
    ):
        """
        Merges data from a staging table into a main table.

        Args:
            staging_table (str): Staging table ID.
            main_table (str): Main table ID.
            merge_keys (List[str]): Columns to use for matching.
            update_columns (List[str]): Columns to update on match.
        """
        full_staging = f"{self.project_id}.{self.dataset_id}.{staging_table}"
        full_main = f"{self.project_id}.{self.dataset_id}.{main_table}"

        on_clause = " AND ".join([f"T.{k} = S.{k}" for k in merge_keys])
        update_set = ", ".join([f"{c} = S.{c}" for c in update_columns])
        insert_cols = ", ".join(update_columns + merge_keys)
        insert_vals = ", ".join([f"S.{c}" for c in update_columns + merge_keys])

        sql = f"""
        MERGE `{full_main}` T
        USING `{full_staging}` S
        ON {on_clause}
        WHEN MATCHED THEN
            UPDATE SET {update_set}
        WHEN NOT MATCHED BY TARGET THEN
            INSERT ({insert_cols})
            VALUES ({insert_vals})
        """

        query_job = self.client.query(sql)
        query_job.result()
        qai_logger.log(
            "BigQuery Merge complete", affected_rows=query_job.num_dml_affected_rows
        )


def run_batch_analysis(config: BatchAnalysisInput):
    """
    High-level orchestrator for the batch analysis workflow.

    Args:
        config (BatchAnalysisInput): The validated configuration.
    """
    qai_logger.log(
        "Starting Analysis using Devkit native wrappers...",
        filter=config.analysis.filter,
        percentage=config.analysis.analysis_percentage,
    )

    try:
        # 1. Map adapter config
        auth = config.get_auth()
        base_config = config.get_config()

        # 2. Instantiate native wrapper
        parent = f"projects/{config.gcp.project_id}/locations/{config.gcp.location_id}"
        analyzer = Analysis(parent=parent, auth=auth, config=base_config)

        # 3. Translate Annotators
        annotators_list = _annotator_dict_to_enum_list(config.analysis.annotator_selector)

        # 4. Trigger Analysis via wrapper
        if not config.analysis.enable_bulk_analysis:
            qai_logger.log(
                "Non-bulk analysis not natively supported in Devkit bulk method. "
                "Falling back to single is inefficient, forcing bulk."
            )

        op = analyzer.bulk(
            annotators=annotators_list,
            analysis_percentage=float(config.analysis.analysis_percentage),
            analysis_filter=config.analysis.filter
        )
        qai_logger.log("Bulk Analysis Operation triggered", operation_name=op.name)

        # Wait for LRO natively
        qai_logger.log("Waiting for operation to complete...")
        op.result(timeout=3600)

        return [{"status": "success", "operation_metadata": "Completed successfully"}]

    except Exception as e:
        qai_logger.log(
            "Analysis failed",
            severity="ERROR",
            error=str(e),
        )
        return [{"status": "failed", "error": str(e)}]
