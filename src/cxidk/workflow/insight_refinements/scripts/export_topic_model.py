# Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.
"""
One-off Utility: Export CCAI Topic Model to BigQuery.

This script exports an issue model from CCAI Insights to GCS as JSON,
parses it, and loads it into a BigQuery table for topic enrichment.
"""

import logging
import argparse
import sys
import json
import time
import requests
import pandas as pd
from typing import Optional
from pydantic_settings import BaseSettings
from cxidk.workflow.insight_refinements.analysis import ConversationAnalyzer, BigQueryOperator
from cxidk.workflow.insight_refinements.utils import get_storage_client
from cxidk.workflow.insight_refinements.schemas.input import (
    BatchAnalysisInput,
    GCPConfig,
    CCAIConfig,
    BigQueryConfig,
    LLMConfig,
    TopicRefinementConfig,
)
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ExportSettings(BaseSettings):
    """
    Settings for Topic Model Export.
    """

    gcp_project_id: str
    gcp_project_number: str
    gcp_location_id: str = "us-central1"
    gcp_staging_bucket: str

    ccai_insights_project_id: Optional[str] = None
    ccai_issue_model_id: str
    ccai_insights_endpoint: Optional[str] = None

    bq_project_id: Optional[str] = None
    bq_dataset_id: str
    bq_l1_definitions_table: str = "l1_topic_definitions"


def parse_args():
    parser = argparse.ArgumentParser(description="Export CCAI Topic Model to BigQuery.")
    parser.add_argument("--issue-model-id", help="CCAI Issue Model ID")
    parser.add_argument("--bucket", help="GCS bucket for intermediate export")
    parser.add_argument("--dataset", help="BigQuery Dataset ID")
    parser.add_argument("--table", help="BigQuery Table name for definitions")
    parser.add_argument(
        "--local-file", 
        help="Path to a local JSON export of the issue model. Bypasses the CCAI API."
    )
    return parser.parse_args()


class TopicModelExporter:
    """Handles the export and transformation of CCAI Issue Models."""

    def __init__(self, config: BatchAnalysisInput, staging_bucket: str):
        self.config = config
        self.analyzer = ConversationAnalyzer(config)
        self.bq_operator = BigQueryOperator(config)
        self.storage_client = get_storage_client(config)
        self.staging_bucket = staging_bucket

    def export_to_gcs(self) -> str:
        """Triggers the export API and waits for completion."""
        issue_model_id = self.config.topic_refinement.issue_model_id
        ccai_project_id = self.config.ccai.ccai_insights_project_id or self.config.gcp.project_id
        gcs_uri = f"gs://{self.staging_bucket}/exports/topic_model_{issue_model_id}_{int(time.time())}.json"

        url = "https://{}/{}/projects/{}/locations/{}/issueModels/{}:export".format(
            self.analyzer.insights_endpoint,
            self.analyzer.api_version,
            ccai_project_id,
            self.config.gcp.location_id,
            issue_model_id,
        )

        payload = {"gcs_destination": {"object_uri": gcs_uri}}
        headers = {
            "Authorization": f"Bearer {self.analyzer.token}",
            "Content-Type": "application/json",
        }

        logger.info(f"Triggering export for model {issue_model_id} to {gcs_uri}...")
        r = requests.post(url, headers=headers, json=payload)
        r.raise_for_status()

        operation = r.json()
        self.analyzer.wait_for_operation(operation, timeout_seconds=600)
        logger.info("Export operation completed.")
        return gcs_uri

    def parse_and_load_local(self, local_file_path: str):
        """Reads a local JSON export, parses it, and loads into BQ."""
        logger.info(f"Reading local export file: {local_file_path}")
        with open(local_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._process_and_load_data(data)

    def parse_and_load(self, gcs_uri: str):
        """Downloads the exported JSON, parses it, and loads into BQ."""
        bucket_name = gcs_uri.replace("gs://", "").split("/")[0]
        blob_name = "/".join(gcs_uri.replace("gs://", "").split("/")[1:])

        bucket = self.storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        content = blob.download_as_text()
        data = json.loads(content)
        self._process_and_load_data(data)

    def _process_and_load_data(self, data: dict):
        """Extracts issues from the JSON dict and loads them to BigQuery."""
        issues = data.get("issues", [])
        if not issues:
            logger.warning("No issues found in the exported model.")
            return

        issue_model_id = self.config.topic_refinement.issue_model_id
        exported_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Prepare DataFrame
        rows = []
        for issue in issues:
            rows.append(
                {
                    "issue_model_id": issue_model_id,
                    "issue_id": issue["name"].split("/")[-1],
                    "display_name": issue.get("displayName", ""),
                    "description": issue.get("displayDescription", ""),
                    "exported_at": exported_at,
                }
            )

        df = pd.DataFrame(rows)
        table_name = self.config.topic_refinement.l1_definitions_table
        logger.info(f"Loading {len(df)} topics into BigQuery table: {table_name}")

        # Use BigQueryOperator to load
        self.bq_operator.load_dataframe_to_staging(df, table_name)
        logger.info("Topic definitions loaded successfully.")


def main():
    args = parse_args()
    try:
        settings = ExportSettings()
    except Exception as e:
        logger.error(f"Missing configuration: {e}")
        sys.exit(1)

    # Construct the internal config object
    config = BatchAnalysisInput(
        gcp=GCPConfig(
            project_id=settings.gcp_project_id,
            project_number=settings.gcp_project_number,
            location_id=settings.gcp_location_id,
        ),
        ccai=CCAIConfig(
            ccai_insights_project_id=settings.ccai_insights_project_id,
            scorecard_id="dummy",  # Not needed for export
            insights_endpoint=settings.ccai_insights_endpoint,
        ),
        llm=LLMConfig(model_name="dummy", location_id=settings.gcp_location_id),
        bigquery=BigQueryConfig(
            project_id=settings.bq_project_id,
            dataset_id=settings.bq_dataset_id,
            staging_table_id="dummy",
            main_table_id="dummy",
        ),
        topic_refinement=TopicRefinementConfig(
            issue_model_id=args.issue_model_id or settings.ccai_issue_model_id,
            l1_definitions_table=args.table or settings.bq_l1_definitions_table,
        ),
    )

    exporter = TopicModelExporter(config, args.bucket or settings.gcp_staging_bucket)
    
    if args.local_file:
        logger.info("Bypassing CCAI API export. Using local file.")
        exporter.parse_and_load_local(args.local_file)
    else:
        gcs_uri = exporter.export_to_gcs()
        exporter.parse_and_load(gcs_uri)


if __name__ == "__main__":
    main()
