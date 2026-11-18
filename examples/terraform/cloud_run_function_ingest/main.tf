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

locals {
  required_apis = toset([
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudfunctions.googleapis.com",
    "contactcenterinsights.googleapis.com",
    "dlp.googleapis.com",
    "eventarc.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
    "storage.googleapis.com",
  ])

  dlp_enabled = (
    trimspace(var.dlp_redact_template) != ""
    || trimspace(var.dlp_deidentify_template) != ""
  )

  optional_env_vars = {
    for key, val in {
      CXIDK_DLP_REDACT_TEMPLATE     = var.dlp_redact_template
      CXIDK_DLP_DEIDENTIFY_TEMPLATE = var.dlp_deidentify_template
    } : key => val if trimspace(val) != ""
  }
}

resource "google_project_service" "apis" {
  for_each           = local.required_apis
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# Cloud Storage service agent requires pubsub.publisher for Eventarc GCS triggers.
data "google_storage_project_service_account" "gcs_account" {
  project    = var.project_id
  depends_on = [google_project_service.apis]
}

resource "google_project_iam_member" "gcs_pubsub_publisher" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${data.google_storage_project_service_account.gcs_account.email_address}"
}

resource "google_storage_bucket" "transcripts" {
  project                     = var.project_id
  name                        = "${var.project_id}-cxidk-transcripts-${random_id.bucket_suffix.hex}"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = var.force_destroy_buckets

  versioning {
    enabled = true
  }

  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket" "function_source" {
  project                     = var.project_id
  name                        = "${var.project_id}-cxidk-fn-src-${random_id.bucket_suffix.hex}"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = var.force_destroy_buckets

  depends_on = [google_project_service.apis]
}

data "archive_file" "function_zip" {
  type        = "zip"
  source_dir  = "${path.module}/function"
  output_path = "${path.module}/.terraform/tmp/function-source.zip"
}

resource "google_storage_bucket_object" "function_archive" {
  name   = "source-${data.archive_file.function_zip.output_sha256}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.function_zip.output_path
}

resource "google_service_account" "function_runtime" {
  project      = var.project_id
  account_id   = "${substr(var.function_name, 0, 24)}-sa"
  display_name = "cxidk Cloud Run Function runtime and Eventarc trigger SA"
}

resource "google_storage_bucket_iam_member" "transcripts_rw" {
  bucket = google_storage_bucket.transcripts.name
  role   = "roles/storage.objectAdmin"
  member = google_service_account.function_runtime.member
}

resource "google_project_iam_member" "insights_editor" {
  project = var.project_id
  role    = "roles/contactcenterinsights.editor"
  member  = google_service_account.function_runtime.member
}

resource "google_project_iam_member" "eventarc_receiver" {
  project = var.project_id
  role    = "roles/eventarc.eventReceiver"
  member  = google_service_account.function_runtime.member
}

resource "google_project_iam_member" "dlp_user" {
  count   = local.dlp_enabled ? 1 : 0
  project = var.project_id
  role    = "roles/dlp.user"
  member  = google_service_account.function_runtime.member
}

resource "google_cloudfunctions2_function" "ingest" {
  project  = var.project_id
  name     = var.function_name
  location = var.region
  description = (
    "Converts AWS / Genesys Cloud transcripts with cxidk and ingests into CCAI Insights."
  )

  build_config {
    runtime     = "python312"
    entry_point = "ingest_gcs_transcript"
    environment_variables = {
      GOOGLE_FUNCTION_SOURCE = "ingest_handler.py"
    }
    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.function_archive.name
      }
    }
  }

  service_config {
    available_memory               = "512M"
    available_cpu                  = "1"
    timeout_seconds                = 120
    max_instance_count             = var.max_instance_count
    ingress_settings               = "ALLOW_INTERNAL_ONLY"
    all_traffic_on_latest_revision = true
    service_account_email          = google_service_account.function_runtime.email

    environment_variables = merge(
      {
        CXIDK_PROJECT_ID    = var.project_id
        CXIDK_LOCATION      = var.insights_location
        CXIDK_LANGUAGE_CODE = var.language_code
      },
      local.optional_env_vars,
    )
  }

  event_trigger {
    trigger_region        = var.region
    event_type            = "google.cloud.storage.object.v1.finalized"
    retry_policy          = "RETRY_POLICY_RETRY"
    service_account_email = google_service_account.function_runtime.email

    event_filters {
      attribute = "bucket"
      value     = google_storage_bucket.transcripts.name
    }
  }

  depends_on = [
    google_project_service.apis,
    google_project_iam_member.gcs_pubsub_publisher,
    google_project_iam_member.eventarc_receiver,
    google_storage_bucket_iam_member.transcripts_rw,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "eventarc_invoker" {
  project  = google_cloudfunctions2_function.ingest.project
  location = google_cloudfunctions2_function.ingest.location
  name     = google_cloudfunctions2_function.ingest.name
  role     = "roles/run.invoker"
  member   = google_service_account.function_runtime.member
}
