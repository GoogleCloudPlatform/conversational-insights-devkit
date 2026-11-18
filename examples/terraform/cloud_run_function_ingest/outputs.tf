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

output "transcripts_bucket_name" {
  description = "Landing GCS bucket for raw/{aws,genesys,insights}/*.json transcripts."
  value       = google_storage_bucket.transcripts.name
}

output "function_uri" {
  description = "Underlying Cloud Run v2 URI of the 2nd-gen function."
  value       = google_cloudfunctions2_function.ingest.url
}

output "runtime_service_account_email" {
  description = "Dedicated runtime and Eventarc trigger service account email."
  value       = google_service_account.function_runtime.email
}
