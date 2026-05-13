# Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.
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
from cxidk.workflow.insight_refinements.schemas.input import BatchAnalysisInput, FeedbackCSVRow
from cxidk.workflow.insight_refinements.utils import handle_api_quota, qai_logger


class BulkFeedbackManager:
    """
    Manager for bulk feedback label operations.
    """

    def __init__(self, config: BatchAnalysisInput):
        """
        Initializes the BulkFeedbackManager.

        Args:
            config (BatchAnalysisInput): The root configuration object.
        """
        self.project_id = config.gcp.project_id
        self.location_id = config.gcp.location_id
        self.parent = f"projects/{self.project_id}/locations/{self.location_id}"

        # Regional Endpoint Logic
        if config.ccai.insights_endpoint:
            endpoint = config.ccai.insights_endpoint
        elif self.location_id == "us-central1":
            endpoint = "contactcenterinsights.googleapis.com"
        else:
            endpoint = f"{self.location_id}-contactcenterinsights.googleapis.com"

        # Initialize clients
        client_options = {"api_endpoint": endpoint}
        self.client = contact_center_insights_v1.ContactCenterInsightsClient(
            client_options=client_options
        )
        from cxidk.workflow.insight_refinements.utils import get_storage_client

        self.storage_client = get_storage_client(config)

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

        gcs_source = contact_center_insights_v1.GcsSource(
            object_uri=gcs_uri, format_=contact_center_insights_v1.GcsSource.Format.JSON
        )

        request = contact_center_insights_v1.BulkUploadFeedbackLabelsRequest(
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

        gcs_destination = contact_center_insights_v1.GcsDestination(
            object_uri=gcs_uri,
            format_=contact_center_insights_v1.GcsDestination.Format.JSON,
        )

        request = contact_center_insights_v1.BulkDownloadFeedbackLabelsRequest(
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
        feedback_row = FeedbackCSVRow(**row)

        label_obj = {
            "labeled_resource": f"{self.parent}/conversations/{feedback_row.conversation_id}",
            "qa_answer_label": {
                "key": feedback_row.question_id,
                "qa_answer_rationale": {"rationale": feedback_row.rationale}
                if feedback_row.rationale
                else None,
            },
        }

        # Determine value type (simplified logic, can be expanded)
        val = feedback_row.answer_value
        if val.lower() in ["yes", "true"]:
            label_obj["qa_answer_label"]["bool_value"] = True
        elif val.lower() in ["no", "false"]:
            label_obj["qa_answer_label"]["bool_value"] = False
        elif val.lower() in ["na", "n/a"]:
            label_obj["qa_answer_label"]["na_value"] = True
        else:
            # Default to string value
            label_obj["qa_answer_label"]["string_value"] = val

        if feedback_row.score is not None:
            label_obj["qa_answer_label"]["score"] = feedback_row.score

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
