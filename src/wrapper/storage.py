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

"""The goal of this class is to implement all wrappers for GCS"""

from typing import Optional
from google.cloud.storage import Client
from src.core import base


class Gcs:
    """Initializes the GCS Wrapper calss.

    Args:
        bucket_name: The name of the GCS bucket.
        project_id: The name of the GCP project.
        auth: An optional Auth object for authentication.
        config: An optional Config object for configuration settings.
    """

    def __init__(
        self,
        bucket_name: str,
        project_id: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ) -> None:
        self.auth = auth or base.Auth()
        self.config = config or base.Config()

        self.bucket_name = bucket_name
        self.project_id = project_id
        self.client = Client(
            project=self.project_id,
            client_options=self.config.set_storage_endpoint(),
        )

    def download_blob(self, file_name: str) -> str:
        """Downloads a blob from the bucket as string.

        Args:
            file_name: The name of the blob to download.

        Returns:
            The contents of the blob as string.
        """

        bucket = self.client.bucket(self.bucket_name)
        blob = bucket.blob(file_name)
        return blob.download_as_string()

    def list_bucket(self) -> list[str]:
        """Lists blobs names in the bucket.

        Args:
            None

        Returns:
            A list of the names of the blob objects.
        """

        tmp = []
        blobs = self.client.list_blobs(self.bucket_name)
        for blob in blobs:
            tmp.append(blob.name)
        return tmp

    def upload_blob(self, file_name: str, data: str):
        """Uploads data to a blob in the bucket.

        Args:
            blob_name: The name of the blob to upload to.
            data: The data to upload (as bytes).
            content_type: Optional content type for the blob.

        Returns:
            None
        """

        bucket = self.client.bucket(self.bucket_name)
        blob = bucket.blob(file_name)
        blob.upload_from_string(data)