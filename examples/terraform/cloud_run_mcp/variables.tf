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
  description = "Google Cloud project ID hosting CCAI Insights and Cloud Run."
  type        = string
}

variable "region" {
  description = "Google Cloud region for the Cloud Run service."
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

variable "service_name" {
  description = "Name of the Cloud Run v2 service."
  type        = string
  default     = "cxidk-mcp"
}

variable "container_image" {
  description = "Artifact Registry container image built from deploy/mcp-cloud-run/Dockerfile."
  type        = string
}

variable "iap_audience" {
  description = "Expected Identity-Aware Proxy JWT audience (e.g. /projects/<NUM>/locations/<REGION>/services/cxidk-mcp)."
  type        = string
  default     = ""
}

variable "oauth_audience" {
  description = "Expected OIDC Bearer token audience when authenticating directly without IAP."
  type        = string
  default     = ""

  validation {
    condition     = trimspace(var.iap_audience) != "" || trimspace(var.oauth_audience) != ""
    error_message = "At least one of iap_audience or oauth_audience must be configured for application-layer JWT verification."
  }
}

variable "dlp_deidentify_template" {
  description = "Optional full Cloud DLP de-identify template resource name for transcript PII redaction."
  type        = string
  default     = ""
}

variable "allow_writes" {
  description = "Whether to enable guarded write tools (writes toolset). Keep false for read-only deployments."
  type        = bool
  default     = false
}

variable "ingress" {
  description = "Cloud Run network ingress setting."
  type        = string
  default     = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  validation {
    condition = contains([
      "INGRESS_TRAFFIC_ALL",
      "INGRESS_TRAFFIC_INTERNAL_ONLY",
      "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER",
    ], var.ingress)
    error_message = "ingress must be INGRESS_TRAFFIC_ALL, INGRESS_TRAFFIC_INTERNAL_ONLY, or INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER."
  }
}

variable "invoker_members" {
  description = "Authenticated IAM principals granted roles/run.invoker (for example user:alice@example.com or serviceAccount:...)."
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for member in var.invoker_members :
      !contains(["allUsers", "allAuthenticatedUsers"], member)
    ])
    error_message = "Public invokers (allUsers / allAuthenticatedUsers) are prohibited on cxidk-mcp."
  }
}

variable "min_instance_count" {
  description = "Minimum warm Cloud Run instances."
  type        = number
  default     = 0
}

variable "max_instance_count" {
  description = "Maximum horizontally scaled Cloud Run instances."
  type        = number
  default     = 10
}

variable "deletion_protection" {
  description = "Enable Cloud Run deletion protection (recommended true in production)."
  type        = bool
  default     = false
}
