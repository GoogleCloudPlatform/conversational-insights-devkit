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

"""Unit tests for storage"""

import pytest
from unittest.mock import MagicMock, patch
from google.api_core.exceptions import NotFound
from src.core.base import Auth, Config
from src.wrapper.storage import Gcs

# Mock Auth and Config since they are not relevant for these tests
class MockAuth(Auth):
    def __init__(self, *args, **kwargs):
        pass

class MockConfig(Config):
    def __init__(self, *args, **kwargs):
        pass

@patch('google.cloud.storage.Client')
def test_download_blob_success(mock_client):
    # Arrange
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_blob.download_as_string.return_value = b'test content'
    mock_bucket.blob.return_value = mock_blob
    mock_client.return_value.bucket.return_value = mock_bucket

    gcs = Gcs(bucket_name='test-bucket', project_id='test-project')

    # Act
    result = gcs.download_blob('test-file.txt')

    # Assert
    assert result == b'test content'
    mock_bucket.blob.assert_called_once_with('test-file.txt')
    mock_blob.download_as_string.assert_called_once()

@patch('google.cloud.storage.Client')
def test_download_blob_not_found(mock_client):
    # Arrange
    mock_client.return_value.bucket.side_effect = NotFound('Bucket not found')
    gcs = Gcs(bucket_name='nonexistent-bucket', project_id='test-project')

    # Act and Assert
    with pytest.raises(FileNotFoundError) as exc_info:
        gcs.download_blob('test-file.txt')
    assert 'Bucket (nonexistent-bucket) does not exists' in str(exc_info.value)

@patch('google.cloud.storage.Client')
def test_list_bucket_success(mock_client):
    # Arrange
    mock_bucket = MagicMock()
    mock_blob1 = MagicMock()
    mock_blob1.name = 'file1.txt'
    mock_blob2 = MagicMock()
    mock_blob2.name = 'file2.txt'
    mock_client.return_value.list_blobs.return_value = [mock_blob1, mock_blob2]
    mock_client.return_value.bucket.return_value = mock_bucket

    gcs = Gcs(bucket_name='test-bucket', project_id='test-project')

    # Act
    result = gcs.list_bucket()

    # Assert
    assert result == ['file1.txt', 'file2.txt']

@patch('google.cloud.storage.Client')
def test_list_bucket_not_found(mock_client):
    # Arrange
    mock_client.return_value.list_blobs.side_effect = NotFound('Bucket not found')
    gcs = Gcs(bucket_name='nonexistent-bucket', project_id='test-project')

    # Act and Assert
    with pytest.raises(FileNotFoundError) as exc_info:
        gcs.list_bucket()
    assert 'Bucket or File does not exists' in str(exc_info.value)

@patch('google.cloud.storage.Client')
def test_upload_blob_success(mock_client):
    # Arrange
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_client.return_value.bucket.return_value = mock_bucket

    gcs = Gcs(bucket_name='test-bucket', project_id='test-project')
    data = 'test content'

    # Act
    result = gcs.upload_blob('test-file.txt', data)

    # Assert
    assert result is None  # Confirming the function returns None as expected
    mock_bucket.blob.assert_called_once_with('test-file.txt')
    mock_blob.upload_from_string.assert_called_once_with(data)

@patch('google.cloud.storage.Client')
def test_upload_blob_type_error(mock_client):
    # Arrange
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_client.return_value.bucket.return_value = mock_bucket

    gcs = Gcs(bucket_name='test-bucket', project_id='test-project')
    data = 123  # Invalid data type

    # Act and Assert
    with pytest.raises(TypeError) as exc_info:
        gcs.upload_blob('test-file.txt', data)
    assert 'Data must be a string.' in str(exc_info.value)

@patch('google.cloud.storage.Client')
def test_upload_blob_value_error(mock_client):
    # Arrange
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_client.return_value.bucket.return_value = mock_bucket

    gcs = Gcs(bucket_name='test-bucket', project_id='test-project')
    data = 'test content'
    file_name = 123  # Invalid file name type

    # Act and Assert
    with pytest.raises(ValueError) as exc_info:
        gcs.upload_blob(file_name, data)
    assert 'File name must be a string.' in str(exc_info.value)

