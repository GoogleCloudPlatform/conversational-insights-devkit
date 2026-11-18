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

variable "project_id" {
  description = "Google Cloud project ID hosting Cloud Run Functions, GCS, and CCAI Insights."
  type        = string
}

variable "region" {
  description = "Google Cloud region for the GCS bucket, Eventarc trigger, and 2nd-gen function."
  type        = string
  default     = "us-central1"
}

variable "insights_location" {
  description = "Explicit regional CCAI Insights location (for example us-central1 or europe-west1)."
  type        = string
  default     = "us-central1"

  validation {
    condition     = trimspace(var.insights_location) != "" && lower(var.insights_location) != "global"
    error_message = "insights_location must be an explicit regional CCAI Insights location, not 'global'."
  }
}

variable "function_name" {
  description = "Name of the 2nd-gen Cloud Run Function."
  type        = string
  default     = "cxidk-transcript-ingest"
}

variable "language_code" {
  description = "Default BCP-47 language code passed to cxidk Ingestion.single()."
  type        = string
  default     = "en-US"
}

variable "dlp_redact_template" {
  description = "Optional Cloud DLP inspect template resource name applied during ingestion."
  type        = string
  default     = ""
}

variable "dlp_deidentify_template" {
  description = "Optional Cloud DLP de-identify template resource name applied during ingestion."
  type        = string
  default     = ""
}

variable "max_instance_count" {
  description = "Maximum concurrent Cloud Run Function instances."
  type        = number
  default     = 20
}

variable "force_destroy_buckets" {
  description = "Allow Terraform destroy to remove non-empty example buckets (keep false in production)."
  type        = bool
  default     = false
}
