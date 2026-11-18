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
Day 2 Operational Script: Batch Analysis & Evaluation.

This script performs the full QAI Optimization lifecycle:
1. Triggers batch analysis on CCAI conversations.
2. Evaluates AI scores against human-provided feedback (Golden Set).
3. (Optional) Triggers Meta-Prompting to optimize scorecard logic.
"""

import logging
import argparse
import sys
import json
from typing import Optional

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

from cxidk.workflow.insight_refinements.schemas.input import (
    BatchAnalysisInput,
    GCPConfig,
    CCAIConfig,
    AnalysisConfig,
    BigQueryConfig,
    LLMConfig,
)
from cxidk.workflow.insight_refinements.analysis import run_batch_analysis
from cxidk.workflow.insight_refinements.bulk_feedback import BulkFeedbackManager
from cxidk.workflow.insight_refinements.optimization import ScorecardOptimizer

logger = logging.getLogger(__name__)


class ScriptSettings(BaseSettings):
    """
    Environment-based settings for Day 2 operations.
    """

    # GCP Defaults
    gcp_project_id: str
    gcp_project_number: str = "dummy"
    gcp_location_id: str = "global"
    gcp_staging_bucket: Optional[str] = None

    # CCAI Defaults
    ccai_scorecard_id: str
    ccai_insights_endpoint: Optional[str] = None

    # LLM Defaults
    llm_model_name: str = "gemini-3.1-flash-lite-preview"

    # BigQuery Defaults
    bq_dataset_id: str
    bq_staging_table: str = "qai_analysis_staging"
    bq_main_table: str = "qai_analysis_results"


def parse_args():
    """Parses command-line arguments for the Day 2 operations script.

    Returns:
        argparse.Namespace: The parsed arguments, covering GCP/CCAI/BigQuery
        overrides, analysis options, bulk feedback upload and scorecard
        optimization.
    """
    parser = argparse.ArgumentParser(
        description="Run batch analysis and evaluation for QAI Optimization."
    )

    # Allow overriding critical params via CLI
    parser.add_argument("--project-id", help="GCP Project ID")
    parser.add_argument("--scorecard-id", help="CCAI Scorecard ID")
    parser.add_argument("--dataset-id", help="BigQuery Dataset ID")
    parser.add_argument(
        "--analysis-percentage",
        type=int,
        default=100,
        help="Percentage of conversations to analyze (0-100)",
    )
    parser.add_argument(
        "--enable-bulk-analysis",
        action="store_true",
        help="Use bulk analysis API instead of iterative analysis",
    )
    parser.add_argument(
        "--analysis-filter",
        default="",
        help="Filter string for bulk analysis (e.g., 'labels.analyzed=false')",
    )

    # Feedback Upload
    parser.add_argument(
        "--upload-feedback-csv", help="Path to a local CSV for bulk feedback upload"
    )
    parser.add_argument(
        "--staging-bucket", help="GCS bucket for temporary staging during upload"
    )

    # Optimization
    parser.add_argument(
        "--optimize-scorecard-item",
        help="Path to JSON file containing failing item and evidence for optimization",
    )

    return parser.parse_args()


def run_optimization(item_path: str, settings: ScriptSettings) -> None:
    """Runs the meta-prompting optimization workflow for a single scorecard item.

    Args:
        item_path: Path to the JSON file holding the failing scorecard item
            and the disagreement evidence used to drive the optimization.
        settings: Resolved script settings providing the GCP project and the
            LLM model used by the optimizer.

    Exits with status 1 if the optimization fails.
    """
    try:
        with open(item_path, "r", encoding="utf-8") as f:
            item_data = json.load(f)

        optimizer = ScorecardOptimizer(
            project_id=settings.gcp_project_id,
            location_id="global",  # Optimization region
            model_name=settings.llm_model_name,
        )

        optimized = optimizer.optimize_question(
            question=item_data["question"],
            instructions=item_data["instructions"],
            answers=item_data["answers"],
            disagreement_cases=item_data["evidence"],
            reference_examples=item_data.get("few_shot_examples"),
        )

        print("\n=== OPTIMIZED SCORECARD ITEM ===")
        print(optimized.model_dump_json(indent=2))

        failures = optimizer.verify_optimization(optimized, item_data["evidence"])
        if failures:
            print(f"\n⚠️ Verification Found {len(failures)} Disagreements:")
            print(json.dumps(failures, indent=2))
        else:
            print(
                "\n✅ Verification Passed: New instructions align with all evidence cases."
            )

    # pylint: disable-next=broad-exception-caught  # CLI boundary: any failure must exit(1)
    except Exception as e:
        logger.error("Optimization failed: %s", e)
        sys.exit(1)


def main():
    """Runs the Day 2 batch analysis and evaluation workflow.

    Loads settings from the environment (falling back to CLI arguments), then
    either runs the exclusive meta-prompting optimization workflow or the
    standard workflow: optional bulk feedback upload, batch analysis and the
    evaluation phase. Exits with status 1 on failure.
    """
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    args = parse_args()

    # 1. Load Settings (Env Vars -> CLI Overrides)
    try:
        settings = ScriptSettings()
    # pylint: disable-next=broad-exception-caught  # any settings error falls back to CLI args
    except Exception as e:
        logger.warning("Could not load full settings from environment: %s", e)
        logger.info("Attempting to fallback to CLI arguments...")
        if (
            not (args.project_id and args.scorecard_id and args.dataset_id)
            and not args.optimize_scorecard_item
        ):
            logger.error(
                "Missing required configuration. Set environment variables "
                "(e.g. GCP_PROJECT_ID) or provide CLI args."
            )
            sys.exit(1)

        # Create minimal settings object to avoid crashing
        settings = ScriptSettings.model_construct(
            gcp_project_id=args.project_id or "dummy",
            ccai_scorecard_id=args.scorecard_id or "dummy",
            bq_dataset_id=args.dataset_id or "dummy",
            gcp_staging_bucket=args.staging_bucket,
            gcp_location_id="global",
        )

    # 2. Optimization Workflow (Exclusive)
    if args.optimize_scorecard_item:
        logger.info(
            "Starting Meta-Prompting Optimization for item: %s",
            args.optimize_scorecard_item,
        )
        run_optimization(args.optimize_scorecard_item, settings)
        return

    # 3. Standard Analysis Workflow
    gcp_config = GCPConfig(
        project_id=args.project_id or settings.gcp_project_id,
        project_number=settings.gcp_project_number,
        location_id=settings.gcp_location_id,
        staging_bucket=args.staging_bucket or settings.gcp_staging_bucket,
    )
    ccai_config = CCAIConfig(
        scorecard_id=args.scorecard_id or settings.ccai_scorecard_id,
        insights_endpoint=settings.ccai_insights_endpoint,
    )
    analysis_config = AnalysisConfig(
        analysis_percentage=args.analysis_percentage,
        enable_bulk_analysis=args.enable_bulk_analysis,
        filter=args.analysis_filter,
    )
    config = BatchAnalysisInput(
        gcp=gcp_config,
        ccai=ccai_config,
        llm=LLMConfig(
            model_name=settings.llm_model_name,
            location_id="global",
        ),
        analysis=analysis_config,
        bigquery=BigQueryConfig(
            dataset_id=args.dataset_id or settings.bq_dataset_id,
            staging_table_id=settings.bq_staging_table,
            main_table_id=settings.bq_main_table,
        ),
    )

    logger.info(
        "Starting job for Project: %s, Scorecard: %s",
        gcp_config.project_id,
        ccai_config.scorecard_id,
    )

    # 4. Bulk Feedback Upload (if requested)
    if args.upload_feedback_csv:
        bucket = args.staging_bucket or settings.gcp_staging_bucket
        if not bucket:
            logger.error(
                "--staging-bucket or GCP_STAGING_BUCKET is required for CSV upload."
            )
            sys.exit(1)

        logger.info(
            "Uploading feedback from %s via bucket %s...",
            args.upload_feedback_csv,
            bucket,
        )
        bulk_manager = BulkFeedbackManager(config)
        bulk_manager.upload_from_local_csv(args.upload_feedback_csv, bucket)
        logger.info("Feedback upload complete.")

    # 5. Run Analysis
    try:
        results = run_batch_analysis(config)
        if analysis_config.enable_bulk_analysis:
            logger.info("Bulk Analysis job completed successfully via Devkit wrappers.")
        else:
            logger.info("Analysis complete. Processed %d conversations.", len(results))
    # pylint: disable-next=broad-exception-caught  # CLI boundary: any failure must exit(1)
    except Exception as e:
        logger.error("Analysis failed: %s", e)
        sys.exit(1)

    # 6. Run Evaluation
    logger.info(
        "Evaluation phase would start here (querying BQ for results vs golden)."
    )


if __name__ == "__main__":
    main()
