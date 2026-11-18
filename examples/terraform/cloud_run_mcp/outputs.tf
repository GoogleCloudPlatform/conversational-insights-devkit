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

output "service_uri" {
  description = "Base HTTPS URI of the deployed cxidk-mcp Cloud Run service."
  value       = google_cloud_run_v2_service.mcp.uri
}

output "mcp_endpoint" {
  description = "Streamable HTTP MCP JSON-RPC endpoint."
  value       = "${google_cloud_run_v2_service.mcp.uri}/mcp"
}

output "healthz_endpoint" {
  description = "Health check endpoint."
  value       = "${google_cloud_run_v2_service.mcp.uri}/healthz"
}

output "runtime_service_account_email" {
  description = "Dedicated least-privilege runtime service account email."
  value       = google_service_account.mcp_runtime.email
}

output "plan_signing_secret_id" {
  description = "Secret Manager secret ID holding CXIDK_PLAN_SIGNING_KEY."
  value       = google_secret_manager_secret.plan_signing_key.secret_id
}
