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
Bulk Feedback Logic for QAI Optimization Framework.

This module provides functionality for bulk uploading and downloading
feedback labels using the CCAI Insights SDK.
"""

import json
import csv
import time
from typing import Dict, Any
from google.cloud import contact_center_insights_v1
from cxidk.workflow.insight_refinements import utils
from cxidk.workflow.insight_refinements.schemas.input import (
    BatchAnalysisInput,
    FeedbackCSVRow,
)
from cxidk.workflow.insight_refinements.utils import handle_api_quota, qai_logger


class BulkFeedbackManager:
    """
    Manager for bulk feedback label operations.
    """

    def __init__(self, config: BatchAnalysisInput, auth=None):
        """
        Initializes the BulkFeedbackManager.

        Args:
            config (BatchAnalysisInput): The root configuration object.
            auth: Optional `cxidk.core.base.Auth` instance for explicit credentials.
        """
        from cxidk.core import base as core_base  # pylint: disable=import-outside-toplevel

        self.project_id = config.gcp.project_id
        self.location_id = config.gcp.location_id
        self.parent = f"projects/{self.project_id}/locations/{self.location_id}"
        self.auth = auth

        # Regional Endpoint Logic
        if config.ccai.insights_endpoint:
            if not core_base.is_trusted_google_host(config.ccai.insights_endpoint):
                raise ValueError(
                    f"Untrusted insights_endpoint: {config.ccai.insights_endpoint!r}"
                )
            endpoint = config.ccai.insights_endpoint
        elif self.location_id == "us-central1":
            endpoint = "contactcenterinsights.googleapis.com"
        else:
            endpoint = core_base.Config().insights_host(self.location_id)

        # Initialize clients
        creds = self.auth.creds if self.auth is not None else None
        client_options = {"api_endpoint": endpoint}
        self.client = contact_center_insights_v1.ContactCenterInsightsClient(
            credentials=creds,
            client_options=client_options,
        )
        self.storage_client = (
            utils.get_storage_client(config, credentials=creds)
            if creds is not None
            else utils.get_storage_client(config)
        )

    @handle_api_quota()
    def upload_feedback_labels(
        self, gcs_uri: str, validate_only: bool = False
    ) -> Dict[str, Any]:
        """
        Bulk uploads feedback labels from a GCS source (JSONL).

        Args:
            gcs_uri (str): The Google Cloud Storage URI (gs://...) containing the labels.
            validate_only (bool): If True, checks validity without uploading.

        Returns:
            Dict[str, Any]: The result of the operation.
        """
        qai_logger.log(
            "Starting bulk upload", gcs_uri=gcs_uri, validate_only=validate_only
        )

        upload_request_cls = contact_center_insights_v1.BulkUploadFeedbackLabelsRequest
        gcs_source = upload_request_cls.GcsSource(
            object_uri=gcs_uri, format_=upload_request_cls.GcsSource.Format.JSON
        )

        request = upload_request_cls(
            parent=self.parent, gcs_source=gcs_source, validate_only=validate_only
        )

        try:
            operation = self.client.bulk_upload_feedback_labels(request=request)
            qai_logger.log(
                "Bulk upload operation started. Waiting for completion...",
                severity="DEBUG",
            )
            response = operation.result()
            qai_logger.log("Bulk upload completed successfully.")

            return {
                "status": "success",
                "processed_count": response.upload_stats.success_count,
                "failed_count": response.upload_stats.failure_count,
            }

        except Exception as e:
            qai_logger.log("Bulk upload failed", severity="ERROR", error=str(e))
            raise

    @handle_api_quota()
    def download_feedback_labels(
        self, gcs_uri: str, filter_expression: str = ""
    ) -> Dict[str, Any]:
        """
        Bulk downloads feedback labels to a GCS destination.

        Args:
            gcs_uri (str): The Google Cloud Storage URI (gs://...) to save the labels.
            filter_expression (str): Optional filter to select specific labels.

        Returns:
            Dict[str, Any]: The result of the operation.
        """
        qai_logger.log("Starting bulk download", gcs_uri=gcs_uri)

        download_request_cls = (
            contact_center_insights_v1.BulkDownloadFeedbackLabelsRequest
        )
        gcs_destination = download_request_cls.GcsDestination(
            object_uri=gcs_uri,
            format_=download_request_cls.GcsDestination.Format.JSON,
        )

        request = download_request_cls(
            parent=self.parent,
            gcs_destination=gcs_destination,
            filter=filter_expression,
        )

        try:
            operation = self.client.bulk_download_feedback_labels(request=request)
            qai_logger.log(
                "Bulk download operation started. Waiting for completion...",
                severity="DEBUG",
            )
            operation.result()
            qai_logger.log("Bulk download completed successfully.")

            return {"status": "success", "destination": gcs_uri}

        except Exception as e:
            qai_logger.log("Bulk download failed", severity="ERROR", error=str(e))
            raise

    def _csv_row_to_json_label(self, row: Dict[str, str]) -> Dict[str, Any]:
        """
        Transforms a flat CSV row into the nested JSON structure required by CCAI.
        """
        # Validate using Pydantic
        # Note: We handle the mapping from string "score" to float/int here if needed
        feedback_row = FeedbackCSVRow.model_validate(row)

        qa_answer_label: Dict[str, Any] = {
            "key": feedback_row.question_id,
            "qa_answer_rationale": {"rationale": feedback_row.rationale}
            if feedback_row.rationale
            else None,
        }
        label_obj: Dict[str, Any] = {
            "labeled_resource": f"{self.parent}/conversations/{feedback_row.conversation_id}",
            "qa_answer_label": qa_answer_label,
        }

        # Determine value type (simplified logic, can be expanded)
        val = feedback_row.answer_value
        # pylint: disable-next=no-member  # pydantic Field() default inferred as FieldInfo, not str
        val_lower = val.lower()
        if val_lower in ["yes", "true"]:
            qa_answer_label["bool_value"] = True
        elif val_lower in ["no", "false"]:
            qa_answer_label["bool_value"] = False
        elif val_lower in ["na", "n/a"]:
            qa_answer_label["na_value"] = True
        else:
            # Default to string value
            qa_answer_label["string_value"] = val

        if feedback_row.score is not None:
            qa_answer_label["score"] = feedback_row.score

        return label_obj

    def upload_from_local_csv(
        self, csv_path: str, gcs_bucket_name: str
    ) -> Dict[str, Any]:
        """
        Orchestrates the upload from a local CSV file.
        1. Reads CSV.
        2. Converts to JSONL.
        3. Uploads to GCS.
        4. Triggers Bulk Upload API.
        """
        jsonl_lines = []

        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    label_json = self._csv_row_to_json_label(row)
                    jsonl_lines.append(json.dumps(label_json))
                # Row-level failures must skip the row, not abort the whole batch.
                # pylint: disable-next=broad-exception-caught
                except Exception as e:
                    qai_logger.log(
                        f"Skipping invalid row: {row}", severity="WARNING", error=str(e)
                    )

        if not jsonl_lines:
            raise ValueError("No valid labels found in CSV.")

        # Upload to GCS
        timestamp = int(time.time())
        blob_name = f"staging/feedback_upload_{timestamp}.jsonl"
        bucket = self.storage_client.bucket(gcs_bucket_name)
        blob = bucket.blob(blob_name)

        qai_logger.log(
            f"Uploading transformed JSONL to gs://{gcs_bucket_name}/{blob_name}"
        )
        blob.upload_from_string("\n".join(jsonl_lines))

        # Trigger Bulk Upload
        gcs_uri = f"gs://{gcs_bucket_name}/{blob_name}"
        return self.upload_feedback_labels(gcs_uri)
