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
One-off Utility: Export CCAI Topic Model to BigQuery.

This script exports an issue model from CCAI Insights to GCS as JSON,
parses it, and loads it into a BigQuery table for topic enrichment.
"""

import argparse
import json
import logging
import re
import sys
import time
from typing import Optional

import google.auth
import google.auth.transport.requests
import pandas as pd
import requests
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

from cxidk.core import base as core_base
from cxidk.workflow.insight_refinements.analysis import BigQueryOperator
from cxidk.workflow.insight_refinements.utils import get_storage_client
from cxidk.workflow.insight_refinements.schemas.input import (
    BatchAnalysisInput,
    GCPConfig,
    CCAIConfig,
    BigQueryConfig,
    LLMConfig,
    TopicRefinementConfig,
)

logger = logging.getLogger(__name__)

# Seconds to wait for the export API to accept the request and return the
# long-running operation handle. The export itself is polled separately.
EXPORT_REQUEST_TIMEOUT_SECONDS = 60

_SAFE_SEGMENT_RE = re.compile(r"^[a-zA-Z0-9._-]{1,128}$")
_SAFE_BUCKET_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{1,220}[a-zA-Z0-9]$")
_SAFE_OPERATION_RE = re.compile(
    r"^projects/[a-zA-Z0-9._-]+/locations/[a-zA-Z0-9._-]+/operations/[a-zA-Z0-9._-]+$"
)


def _validate_segment(value: str, field_name: str) -> str:
    """Validates a single URL/GCS path segment against traversal or injection."""
    if (
        not isinstance(value, str)
        or ".." in value
        or not _SAFE_SEGMENT_RE.match(value)
    ):
        raise ValueError(f"Unsafe {field_name} value: {value!r}")
    return value


def _validate_bucket_name(bucket: str) -> str:
    """Validates a GCS bucket name before URI interpolation."""
    if (
        not isinstance(bucket, str)
        or ".." in bucket
        or not _SAFE_BUCKET_RE.match(bucket)
    ):
        raise ValueError(f"Unsafe GCS bucket name: {bucket!r}")
    return bucket


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
    """Parses command-line arguments for the topic model export utility.

    Returns:
        argparse.Namespace: The parsed arguments, covering the issue model,
        the GCS staging bucket, the BigQuery destination and the optional
        local JSON export used to bypass the CCAI API.
    """
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


def _get_oauth_token() -> str:
    """Retrieves a Google OAuth2 token using Application Default Credentials (ADC).

    Returns:
        str: The OAuth2 access token.
    """
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)
    return creds.token


def _resolve_insights_endpoint(config: BatchAnalysisInput) -> str:
    """Resolves the regional CCAI Insights host for the configured location.

    Args:
        config (BatchAnalysisInput): The pipeline configuration.

    Returns:
        str: The API host name, without scheme.
    """
    if config.ccai.insights_endpoint:
        endpoint = config.ccai.insights_endpoint
    elif config.gcp.location_id == "us-central1":
        endpoint = "contactcenterinsights.googleapis.com"
    else:
        safe_loc = _validate_segment(config.gcp.location_id, "location_id")
        endpoint = f"{safe_loc}-contactcenterinsights.googleapis.com"

    if not core_base.is_trusted_google_host(endpoint):
        raise ValueError(f"Untrusted insights_endpoint: {endpoint!r}")
    return endpoint


class TopicModelExporter:
    """Handles the export and transformation of CCAI Issue Models."""

    def __init__(self, config: BatchAnalysisInput, staging_bucket: str):
        self.config = config
        # `topic_refinement` is optional on BatchAnalysisInput, but this exporter
        # cannot do anything without it. Fail fast with an explicit message
        # instead of raising an AttributeError deep inside the export calls.
        if config.topic_refinement is None:
            raise ValueError(
                "The 'topic_refinement' configuration section is required to export "
                "a topic model. Provide the issue model ID and the L1 definitions "
                "table."
            )
        self.topic_refinement: TopicRefinementConfig = config.topic_refinement
        # The issue-model export endpoint has no SDK surface, so this script talks
        # REST directly. Validate host, version, and bucket before fetching tokens.
        self.insights_endpoint = _resolve_insights_endpoint(config)
        self.api_version = _validate_segment(config.ccai.api_version, "api_version")
        self.staging_bucket = _validate_bucket_name(staging_bucket)
        self.token = _get_oauth_token()
        self.bq_operator = BigQueryOperator(config)
        self.storage_client = get_storage_client(config)

    def _wait_for_operation(self, operation: dict, timeout_seconds: int = 900) -> dict:
        """Waits for a Long-Running Operation (LRO) to complete.

        Args:
            operation (dict): The operation object returned by the export call.
            timeout_seconds (int): Maximum time to wait.

        Returns:
            dict: The operation metadata upon completion.

        Raises:
            TimeoutError: If the operation does not finish within the timeout.
            RuntimeError: If the operation completes with an error.
        """
        operation_name = operation["name"]
        if (
            not isinstance(operation_name, str)
            or ".." in operation_name
            or not _SAFE_OPERATION_RE.match(operation_name)
        ):
            raise ValueError(f"Unsafe operation resource name: {operation_name!r}")
        url = f"https://{self.insights_endpoint}/{self.api_version}/{operation_name}"
        core_base.validate_request_url(url)

        start_time = time.time()
        while True:
            if time.time() - start_time > timeout_seconds:
                raise TimeoutError(
                    f"Operation {operation_name} timed out after {timeout_seconds}s"
                )

            poll = requests.get(
                url,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=EXPORT_REQUEST_TIMEOUT_SECONDS,
            )
            poll.raise_for_status()
            result = poll.json()

            if result.get("done"):
                if result.get("error"):
                    raise RuntimeError(f"Operation failed: {result['error']}")
                return result.get("metadata", {})

            logger.debug("Operation %s still running...", operation_name)
            time.sleep(10)

    def export_to_gcs(self) -> str:
        """Triggers the export API and waits for completion."""
        issue_model_id = _validate_segment(
            self.topic_refinement.issue_model_id, "issue_model_id"
        )
        raw_project_id = (
            self.config.ccai.ccai_insights_project_id or self.config.gcp.project_id
        )
        ccai_project_id = _validate_segment(raw_project_id, "ccai_project_id")
        location_id = _validate_segment(self.config.gcp.location_id, "location_id")
        gcs_uri = (
            f"gs://{self.staging_bucket}/exports/"
            f"topic_model_{issue_model_id}_{int(time.time())}.json"
        )

        url = (
            f"https://{self.insights_endpoint}"
            f"/{self.api_version}"
            f"/projects/{ccai_project_id}"
            f"/locations/{location_id}"
            f"/issueModels/{issue_model_id}:export"
        )
        core_base.validate_request_url(url)

        payload = {"gcs_destination": {"object_uri": gcs_uri}}
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        logger.info("Triggering export for model %s to %s...", issue_model_id, gcs_uri)
        r = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=EXPORT_REQUEST_TIMEOUT_SECONDS,
        )
        r.raise_for_status()

        operation = r.json()
        self._wait_for_operation(operation, timeout_seconds=600)
        logger.info("Export operation completed.")
        return gcs_uri

    def parse_and_load_local(self, local_file_path: str):
        """Reads a local JSON export, parses it, and loads into BQ."""
        logger.info("Reading local export file: %s", local_file_path)
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

        issue_model_id = self.topic_refinement.issue_model_id
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
        table_name = self.topic_refinement.l1_definitions_table
        logger.info("Loading %d topics into BigQuery table: %s", len(df), table_name)

        # Use BigQueryOperator to load
        self.bq_operator.load_dataframe_to_staging(df, table_name)
        logger.info("Topic definitions loaded successfully.")


def main():
    """Runs the topic model export workflow.

    Loads settings from the environment, builds the internal configuration and
    then either parses a local JSON export of the issue model or triggers the
    CCAI export to GCS before loading the topic definitions into BigQuery.
    Exits with status 1 if the configuration is incomplete.
    """
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    args = parse_args()
    try:
        settings = ExportSettings()
    # pylint: disable-next=broad-exception-caught  # CLI boundary: any config error must exit(1)
    except Exception as e:
        logger.error("Missing configuration: %s", e)
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
