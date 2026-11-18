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
Granular Topic Refinement Pipeline.

This script orchestrates the end-to-end flow:
1. Fetch new conversations and their top topics from BigQuery.
2. Refine each topic using Gemini 3.0/3.1 into a granular L2 category.
3. Write the refined results and execution audit logs back to BigQuery.
"""

import logging
import argparse
import sys
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

from cxidk.workflow.insight_refinements.schemas.input import (
    BatchAnalysisInput,
    GCPConfig,
    CCAIConfig,
    LLMConfig,
    BigQueryConfig,
    TopicRefinementConfig,
)
from cxidk.workflow.insight_refinements.bq_client import TopicBQClient
from cxidk.workflow.insight_refinements.topic_refinement import TopicRefiner

logger = logging.getLogger(__name__)


class RefinementSettings(BaseSettings):
    """
    Environment-based settings for Topic Refinement.
    """

    # Core Application Project (where Gemini runs)
    gcp_project_id: str
    gcp_project_number: str
    gcp_location_id: str = "us-central1"

    # CCAI Insights (Source Project)
    ccai_insights_project_id: Optional[str] = None
    ccai_issue_model_id: str
    ccai_insights_endpoint: Optional[str] = None
    ccai_feedback_regionalization: bool = False

    # LLM Config
    llm_model_name: str = "gemini-3.1-flash-lite-preview"
    llm_location_id: str = "global"

    # BigQuery Config (Hub & Spoke Support)
    bq_project_id: Optional[str] = None
    bq_dataset_id: str
    bq_main_table: str = "insights"
    bq_l1_definitions_table: str = "l1_topic_definitions"
    bq_l2_taxonomy_table: str = "l2_taxonomy_results"
    bq_audit_table: str = "topic_refinement_audit"

    # Strict Mode
    approved_taxonomy_file: Optional[str] = None

    # V2 Prompting
    prompt_gcs_uri: Optional[str] = None


def parse_args():
    """Parses command-line arguments for the topic refinement pipeline.

    Returns:
        argparse.Namespace: The parsed arguments, containing the ``batch_size``
        of conversations to process in this run.
    """
    parser = argparse.ArgumentParser(
        description="Run granular topic refinement pipeline."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of conversations to process in this run.",
    )
    return parser.parse_args()


def run_pipeline(batch_size: int = 100):
    """Executes the refinement pipeline."""
    # 1. Load Settings
    try:
        # pydantic-settings populates every required field from the environment
        # (and the .env file) at runtime. mypy only sees the dataclass-style
        # __init__ synthesised from the field annotations, so it wrongly reports
        # the env-provided fields as missing arguments.
        settings = RefinementSettings()  # type: ignore[call-arg]
    # pylint: disable-next=broad-exception-caught  # logs any config error, then re-raises unchanged
    except Exception as e:
        logger.error("Missing required configuration: %s", e)
        raise e

    # 2. Construct internal config
    llm_config = LLMConfig(
        model_name=settings.llm_model_name,
        location_id=settings.llm_location_id,
    )
    config = BatchAnalysisInput(
        gcp=GCPConfig(
            project_id=settings.gcp_project_id,
            project_number=settings.gcp_project_number,
            location_id=settings.gcp_location_id,
        ),
        ccai=CCAIConfig(
            ccai_insights_project_id=settings.ccai_insights_project_id,
            scorecard_id="n/a",  # Not used in this pipeline
            insights_endpoint=settings.ccai_insights_endpoint,
            feedback_regionalization=settings.ccai_feedback_regionalization,
        ),
        llm=llm_config,
        bigquery=BigQueryConfig(
            project_id=settings.bq_project_id,
            dataset_id=settings.bq_dataset_id,
            staging_table_id="dummy",
            main_table_id=settings.bq_main_table,
        ),
        topic_refinement=TopicRefinementConfig(
            issue_model_id=settings.ccai_issue_model_id,
            prompt_gcs_uri=settings.prompt_gcs_uri,
            l1_definitions_table=settings.bq_l1_definitions_table,
            l2_taxonomy_table=settings.bq_l2_taxonomy_table,
            audit_table=settings.bq_audit_table,
            approved_taxonomy_file=settings.approved_taxonomy_file,
        ),
    )

    # 3. Initialize Clients
    bq_client = TopicBQClient(config)
    refiner = TopicRefiner(config)

    # 4. Fetch New Conversations
    new_records = bq_client.fetch_new_conversations(limit=batch_size)
    if new_records.empty:
        logger.info("No new conversations found for refinement. Exiting.")
        return 0

    # 5. Process Refinements
    results = []
    audit_logs = []

    logger.info("Processing %d records...", len(new_records))

    def process_row(row):
        try:
            result, audit = refiner.refine_topic(
                conversation_id=row["conversation_id"],
                l1_issue_id=row["l1_issue_id"],
                l1_topic_name=row["l1_topic_name"],
                l1_topic_description=row["l1_topic_description"],
                formatted_transcript=row["formatted_transcript"],
            )
            return result.model_dump(), audit.model_dump()
        # pylint: disable-next=broad-exception-caught  # one bad row must not abort the whole batch
        except Exception as e:
            logger.error(
                "Failed to refine conversation %s: %s", row["conversation_id"], e
            )
            return None, None

    # Use ThreadPoolExecutor for concurrent API calls to Gemini
    max_workers = llm_config.max_concurrent_calls
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(process_row, row) for _, row in new_records.iterrows()
        ]
        for future in as_completed(futures):
            res, aud = future.result()
            if res and aud:
                results.append(res)
                audit_logs.append(aud)

    # 6. Write Results to BigQuery
    if results:
        results_df = pd.DataFrame(results)
        bq_client.write_l2_results(results_df)

    if audit_logs:
        audit_df = pd.DataFrame(audit_logs)
        bq_client.write_audit_log(audit_df)

    logger.info("Pipeline execution complete.")
    return len(results)


def main():
    """Parses the CLI arguments and runs the refinement pipeline.

    Exits with status 1 if the pipeline raises, after logging the traceback.
    """
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    args = parse_args()
    try:
        run_pipeline(batch_size=args.batch_size)
    # pylint: disable-next=broad-exception-caught  # CLI boundary: any failure must exit(1)
    except Exception as e:
        logger.error(e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
