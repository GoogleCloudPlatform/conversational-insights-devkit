# Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.
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
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
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


def main():
    args = parse_args()

    # 1. Load Settings (Env Vars -> CLI Overrides)
    try:
        settings = ScriptSettings()
    except Exception as e:
        logger.warning(f"Could not load full settings from environment: {e}")
        logger.info("Attempting to fallback to CLI arguments...")
        if (
            not (args.project_id and args.scorecard_id and args.dataset_id)
            and not args.optimize_scorecard_item
        ):
            logger.error(
                "Missing required configuration. Set environment variables (e.g. GCP_PROJECT_ID) or provide CLI args."
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
            f"Starting Meta-Prompting Optimization for item: {args.optimize_scorecard_item}"
        )
        try:
            with open(args.optimize_scorecard_item, "r") as f:
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

        except Exception as e:
            logger.error(f"Optimization failed: {e}")
            sys.exit(1)
        return

    # 3. Standard Analysis Workflow
    config = BatchAnalysisInput(
        gcp=GCPConfig(
            project_id=args.project_id or settings.gcp_project_id,
            project_number=settings.gcp_project_number,
            location_id=settings.gcp_location_id,
            staging_bucket=args.staging_bucket or settings.gcp_staging_bucket,
        ),
        ccai=CCAIConfig(
            scorecard_id=args.scorecard_id or settings.ccai_scorecard_id,
            insights_endpoint=settings.ccai_insights_endpoint,
        ),
        llm=LLMConfig(
            model_name=settings.llm_model_name,
            location_id="global",
        ),
        analysis=AnalysisConfig(
            analysis_percentage=args.analysis_percentage,
            enable_bulk_analysis=args.enable_bulk_analysis,
            filter=args.analysis_filter,
        ),
        bigquery=BigQueryConfig(
            dataset_id=args.dataset_id or settings.bq_dataset_id,
            staging_table_id=settings.bq_staging_table,
            main_table_id=settings.bq_main_table,
        ),
    )

    logger.info(
        f"Starting job for Project: {config.gcp.project_id}, Scorecard: {config.ccai.scorecard_id}"
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
            f"Uploading feedback from {args.upload_feedback_csv} via bucket {bucket}..."
        )
        bulk_manager = BulkFeedbackManager(config)
        bulk_manager.upload_from_local_csv(args.upload_feedback_csv, bucket)
        logger.info("Feedback upload complete.")

    # 5. Run Analysis
    try:
        results = run_batch_analysis(config)
        if config.analysis.enable_bulk_analysis:
            logger.info("Bulk Analysis job completed successfully via Devkit wrappers.")
        else:
            logger.info(f"Analysis complete. Processed {len(results)} conversations.")
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        sys.exit(1)

    # 6. Run Evaluation
    logger.info(
        "Evaluation phase would start here (querying BQ for results vs golden)."
    )


if __name__ == "__main__":
    main()
