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

"""A wrapper for Google Cloud Storage (GCS) operations.

This module provides the `Gcs` class, which simplifies interactions with Google
Cloud Storage buckets. It allows for uploading, downloading, and listing files,
handling authentication and client setup.
"""

import enum
from typing import List, Optional, Union
from google.cloud.storage import Client #type: ignore

from cxidk.core import base

class ContentType(enum.StrEnum):
    """Enum for supported content types."""
    TEXT = "text/plain"
    WAV = "audio/wav"

class Gcs:
    """A wrapper for Google Cloud Storage (GCS) operations.

    This class provides methods to interact with a GCS bucket, including
    uploading, downloading, and listing files. It simplifies client
    initialization and authentication.

    Attributes:
        bucket_name: The name of the GCS bucket.
        project_id: The Google Cloud project ID.
        auth: An authentication object.
        config: A configuration object.
        client: An instance of `google.cloud.storage.Client`.
    """

    def __init__(
        self,
        bucket_name: str,
        project_id: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ) -> None:
        """Initializes the GCS wrapper.

        Args:
            bucket_name: The name of the GCS bucket (without 'gs://' prefix).
            project_id: The Google Cloud project ID.
            auth: An optional, pre-configured authentication object.
            config: An optional, pre-configured configuration object.
        """
        self.auth = auth or base.Auth()
        self.config = config or base.Config()

        self.bucket_name = bucket_name
        self.project_id = project_id
        self.client = Client(
            project=self.project_id,
            client_options=self.config.set_storage_endpoint(),
        )

    def download_blob(
        self,
        file_name: str,
        content_type: ContentType = ContentType.TEXT
    ) -> Union[str, bytes]:
        """Downloads a blob from the bucket.

        Args:
            file_name: The full path name of the blob to download.
            content_type: The expected content type of the blob.

        Returns:
            The contents of the blob as a decoded string or raw bytes.
        """

        bucket = self.client.bucket(self.bucket_name)
        blob = bucket.blob(file_name)
        if content_type == ContentType.WAV:
            return blob.download_as_bytes()
        return blob.download_as_string().decode("utf-8")

    def list_bucket(self) -> List[str]:
        """Lists blob names in the bucket.

        Returns:
            A list of blob names in the bucket.
        """

        tmp = []
        blobs = self.client.list_blobs(self.bucket_name)
        for blob in blobs:
            tmp.append(blob.name)
        return tmp

    def upload_blob(
            self,
            file_name: str,
            data: Union[str, bytes],
            content_type: ContentType = ContentType.TEXT
    ):
        """Uploads data to a blob in the bucket.

        Args:
            file_name: The destination name of the blob in the bucket.
            data: The data to upload, either as a string or bytes.
            content_type: The MIME type of the content being uploaded.
        """

        bucket = self.client.bucket(self.bucket_name)
        blob = bucket.blob(file_name)
        if isinstance(data, str):
            blob.upload_from_string(data, content_type=content_type)
        else:
            blob.upload_from_file(data, content_type=content_type)
