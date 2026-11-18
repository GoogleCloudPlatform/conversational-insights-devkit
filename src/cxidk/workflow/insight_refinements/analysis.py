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
Batch Analysis Logic for QAI Optimization Framework.

This module provides classes and functions for performing batch analysis
on CCAI conversations and exporting the results to BigQuery.
"""

import re
from typing import Dict, List, Optional

import pandas as pd
from google.cloud import bigquery
from cxidk.workflow.insight_refinements.schemas.input import BatchAnalysisInput
from cxidk.workflow.insight_refinements.utils import qai_logger, get_bq_client
from cxidk.wrapper.insights import Analysis, Annotators

_BQ_PART_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
_BQ_COL_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,127}$")


def validate_bq_identifier(
    value: str, field_name: str, *, is_column: bool = False
) -> str:
    """Validates a BigQuery project/dataset/table or column identifier."""
    pattern = _BQ_COL_RE if is_column else _BQ_PART_RE
    if not isinstance(value, str) or not pattern.match(value):
        raise ValueError(f"Unsafe BigQuery {field_name} identifier: {value!r}")
    return value


def format_bq_table_ref(project_id: str, dataset_id: str, table_id: str) -> str:
    """Validates and formats a `project.dataset.table` BigQuery reference."""
    safe_proj = validate_bq_identifier(project_id, "project_id")
    safe_ds = validate_bq_identifier(dataset_id, "dataset_id")
    safe_tbl = validate_bq_identifier(table_id, "table_id")
    return f"{safe_proj}.{safe_ds}.{safe_tbl}"


def _annotator_dict_to_enum_list(
    annotator_selector: Optional[Dict[str, bool]]
) -> List[Annotators]:
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
        "run_interruption_annotator",
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
        self,
        df: pd.DataFrame,
        table_id: str,
        write_disposition: str = "WRITE_TRUNCATE",
    ):
        """
        Loads a Pandas DataFrame into a BigQuery staging table.

        Args:
            df (pd.DataFrame): The data to load.
            table_id (str): The staging table ID.
            write_disposition (str): The BQ write disposition (default: WRITE_TRUNCATE).
        """
        full_table_id = format_bq_table_ref(
            self.project_id, self.dataset_id, table_id
        )
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
        if not merge_keys or not update_columns:
            raise ValueError("merge_keys and update_columns must be non-empty.")
        full_staging = format_bq_table_ref(
            self.project_id, self.dataset_id, staging_table
        )
        full_main = format_bq_table_ref(
            self.project_id, self.dataset_id, main_table
        )
        safe_keys = [
            validate_bq_identifier(k, "merge_key", is_column=True)
            for k in merge_keys
        ]
        safe_cols = [
            validate_bq_identifier(c, "update_column", is_column=True)
            for c in update_columns
        ]

        on_clause = " AND ".join([f"T.{k} = S.{k}" for k in safe_keys])
        update_set = ", ".join([f"{c} = S.{c}" for c in safe_cols])
        insert_cols = ", ".join(safe_cols + safe_keys)
        insert_vals = ", ".join([f"S.{c}" for c in safe_cols + safe_keys])

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
        # `analyzer.bulk()` returns a `google.api_core.operation.Operation`; the LRO
        # resource name lives on the wrapped protobuf, exposed via `.operation`.
        # pylint mis-resolves the wrapper's stale `operations_pb2.Operation` annotation,
        # whose members are generated dynamically, hence the narrow disable.
        qai_logger.log(
            "Bulk Analysis Operation triggered",
            operation_name=op.operation.name,  # pylint: disable=no-member
        )

        # Wait for LRO natively
        qai_logger.log("Waiting for operation to complete...")
        op.result(timeout=3600)

        return [{"status": "success", "operation_metadata": "Completed successfully"}]

    # This is the pipeline's top-level boundary: every failure must be surfaced as a
    # structured 'failed' result rather than propagating to the caller.
    except Exception as e:  # pylint: disable=broad-exception-caught
        qai_logger.log(
            "Analysis failed",
            severity="ERROR",
            error=str(e),
        )
        return [{"status": "failed", "error": str(e)}]
