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
    "contactcenterinsights.googleapis.com",
    "dlp.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
  ])

  optional_env_vars = {
    for key, val in {
      CXIDK_IAP_AUDIENCE            = var.iap_audience
      CXIDK_OAUTH_AUDIENCE          = var.oauth_audience
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

resource "google_service_account" "mcp_runtime" {
  project      = var.project_id
  account_id   = "${var.service_name}-sa"
  display_name = "cxidk-mcp Cloud Run runtime service account"
}

resource "google_project_iam_member" "insights_access" {
  project = var.project_id
  role = (
    var.allow_writes
    ? "roles/contactcenterinsights.editor"
    : "roles/contactcenterinsights.viewer"
  )
  member = google_service_account.mcp_runtime.member
}

resource "google_project_iam_member" "dlp_user" {
  count   = trimspace(var.dlp_deidentify_template) != "" ? 1 : 0
  project = var.project_id
  role    = "roles/dlp.user"
  member  = google_service_account.mcp_runtime.member
}

resource "random_password" "plan_signing_key" {
  length  = 64
  special = false
}

resource "google_secret_manager_secret" "plan_signing_key" {
  project   = var.project_id
  secret_id = "${var.service_name}-plan-signing-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "plan_signing_key" {
  secret      = google_secret_manager_secret.plan_signing_key.id
  secret_data = random_password.plan_signing_key.result
}

resource "google_secret_manager_secret_iam_member" "mcp_secret_accessor" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.plan_signing_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.mcp_runtime.member
}

resource "google_cloud_run_v2_service" "mcp" {
  project             = var.project_id
  name                = var.service_name
  location            = var.region
  ingress             = var.ingress
  deletion_protection = var.deletion_protection

  template {
    service_account                  = google_service_account.mcp_runtime.email
    timeout                          = "300s"
    max_instance_request_concurrency = 80

    scaling {
      min_instance_count = var.min_instance_count
      max_instance_count = var.max_instance_count
    }

    containers {
      image = var.container_image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle = true
      }

      env {
        name  = "CXIDK_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "CXIDK_LOCATION"
        value = var.insights_location
      }

      env {
        name  = "CXIDK_TRANSCRIPT_MODE"
        value = "redacted"
      }

      env {
        name  = "CXIDK_ALLOW_WRITES"
        value = tostring(var.allow_writes)
      }

      dynamic "env" {
        for_each = local.optional_env_vars
        content {
          name  = env.key
          value = env.value
        }
      }

      env {
        name = "CXIDK_PLAN_SIGNING_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.plan_signing_key.secret_id
            version = "latest"
          }
        }
      }

      startup_probe {
        initial_delay_seconds = 2
        period_seconds        = 5
        timeout_seconds       = 3
        failure_threshold     = 6
        http_get {
          path = "/healthz"
          port = 8080
        }
      }

      liveness_probe {
        period_seconds    = 30
        timeout_seconds   = 3
        failure_threshold = 3
        http_get {
          path = "/healthz"
          port = 8080
        }
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_version.plan_signing_key,
    google_secret_manager_secret_iam_member.mcp_secret_accessor,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "invokers" {
  for_each = toset(var.invoker_members)
  project  = google_cloud_run_v2_service.mcp.project
  location = google_cloud_run_v2_service.mcp.location
  name     = google_cloud_run_v2_service.mcp.name
  role     = "roles/run.invoker"
  member   = each.value
}
