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

"""Integration tests for the GCS module."""

import uuid
import pytest

from google.cloud import exceptions

from cxidk.wrapper import storage

def test_upload_files():
    """Test uploading files to GCS and also tests list"""
    gcs = storage.Gcs(
        project_id = 'insights-python-tooling-prober',
        bucket_name = 'upload-tmp-prober'
    )

    # Test uploading a normal string file
    file_name = f"{uuid.uuid4()}.txt"
    gcs.upload_blob(
        file_name = file_name,
        data = 'test'
    )
    assert file_name in gcs.list_bucket()

    # Test uploading empty file
    file_name = f"{uuid.uuid4()}.txt"
    gcs.upload_blob(
        file_name = file_name,
        data = ''
    )
    assert file_name in gcs.list_bucket()

    # Test uploading None
    with pytest.raises(TypeError):
        gcs.upload_blob(
            file_name = 'typeerror.txt',
            data = None
        )

def test_download_files():
    """Test downloading files from GCS"""
    gcs = storage.Gcs(
        project_id = 'insights-python-tooling-prober',
        bucket_name = 'upload-tmp-prober'
    )
    # Test uploading a normal string file
    file_name = f"{uuid.uuid4()}.txt"
    gcs.upload_blob(
        file_name = file_name,
        data = 'test'
    )
    assert file_name in gcs.list_bucket()
    downloaded_data = gcs.download_blob(file_name)
    assert downloaded_data == 'test'.encode('utf-8')

    with pytest.raises(exceptions.NotFound):
        gcs.download_blob("non-existing.txt")
