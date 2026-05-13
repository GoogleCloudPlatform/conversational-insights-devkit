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

"""Unit tests for the GCS wrapper in cxidk.wrapper.storage."""

from typing import Generator, Optional, Union
from unittest.mock import MagicMock, patch

import pytest

# Assuming the Gcs class is in this path
from cxidk.core import base
from cxidk.wrapper.storage import ContentType, Gcs

# --- Constants for Reusability ---
TEST_BUCKET_NAME = "test-bucket"
TEST_PROJECT_ID = "test-project"
TEST_FILE_NAME = "test-file.txt"


# --- Pytest Fixtures for Mocks ---





@pytest.fixture(name="mock_gcs_client")
def fixture_mock_gcs_client() -> Generator[MagicMock, None, None]:
    """
    A pytest fixture that mocks the google.cloud.storage.Client.

    This patch targets the Client where it's looked up (in the 'storage' module)
    to ensure our Gcs class uses the mock.
    """
    with patch("cxidk.wrapper.storage.Client") as mock_client_class:
        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance
        yield mock_client_instance


@pytest.fixture(name="mock_base_config")
def fixture_mock_base_config() -> MagicMock:
    """A pytest fixture that mocks the cxidk.core.base.Config object."""
    mock_config = MagicMock(spec=base.Config)
    mock_config.set_storage_endpoint.return_value = {
        "api_endpoint": "storage.googleapis.com"
    }
    return mock_config


@pytest.fixture(name="mock_base_auth")
def fixture_mock_base_auth() -> MagicMock:
    """A pytest fixture that mocks the cxidk.core.base.Auth object."""
    return MagicMock(spec=base.Auth)


# --- Test Cases ---

##
# Tests for the __init__ method
##


@patch("cxidk.wrapper.storage.Client")
def test_gcs_init_with_defaults(mock_gcs_client_class: MagicMock) -> None:
    """
    Verifies Gcs initializes correctly when auth and config are not provided.
    """
    mock_gcs_client_instance = MagicMock()
    mock_gcs_client_class.return_value = mock_gcs_client_instance
    with patch("cxidk.wrapper.storage.base") as mock_base:
        mock_config_instance = MagicMock()
        mock_config_instance.set_storage_endpoint.return_value = {
            "api_endpoint": "storage.googleapis.com"
        }
        mock_base.Config.return_value = mock_config_instance
        mock_base.Auth.return_value = MagicMock()

        gcs_instance = Gcs(bucket_name=TEST_BUCKET_NAME, project_id=TEST_PROJECT_ID)

        mock_base.Auth.assert_called_once()
        mock_base.Config.assert_called_once()
        assert gcs_instance.client == mock_gcs_client_instance

        mock_gcs_client_class.assert_called_once_with(
            project=TEST_PROJECT_ID,
            client_options={"api_endpoint": "storage.googleapis.com"},
        )


def test_gcs_init_with_provided_dependencies(
    mock_gcs_client: MagicMock, mock_base_config: MagicMock, mock_base_auth: MagicMock
) -> None:
    """
    Verifies Gcs initializes correctly when auth/config objects are provided.
    """
    gcs_instance = Gcs(
        bucket_name=TEST_BUCKET_NAME,
        project_id=TEST_PROJECT_ID,
        auth=mock_base_auth,
        config=mock_base_config,
    )

    assert gcs_instance.auth == mock_base_auth
    assert gcs_instance.config == mock_base_config
    assert gcs_instance.client == mock_gcs_client
    mock_base_config.set_storage_endpoint.assert_called_once()


##
# Test for the download_blob method
##


def test_download_blob(
    mock_gcs_client: MagicMock, mock_base_auth: MagicMock, mock_base_config: MagicMock
) -> None:
    """
    Verifies download_blob calls the correct sequence of GCS client methods.
    """
    mock_blob = MagicMock()
    mock_blob.download_as_string.return_value = b"file content"
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_gcs_client.bucket.return_value = mock_bucket

    gcs_instance = Gcs(
        bucket_name=TEST_BUCKET_NAME,
        project_id=TEST_PROJECT_ID,
        auth=mock_base_auth,
        config=mock_base_config,
    )
    content = gcs_instance.download_blob(file_name=TEST_FILE_NAME)

    mock_gcs_client.bucket.assert_called_once_with(TEST_BUCKET_NAME)
    mock_bucket.blob.assert_called_once_with(TEST_FILE_NAME)
    mock_blob.download_as_string.assert_called_once()
    assert content == "file content"


##
# Test for the list_bucket method
##


def test_list_bucket(
    mock_gcs_client: MagicMock, mock_base_auth: MagicMock, mock_base_config: MagicMock
) -> None:
    """
    Verifies list_bucket correctly calls list_blobs and processes the results.
    """
    blob1 = MagicMock()
    blob1.name = "folder/file1.txt"
    blob2 = MagicMock()
    blob2.name = "file2.wav"
    mock_gcs_client.list_blobs.return_value = [blob1, blob2]

    gcs_instance = Gcs(
        bucket_name=TEST_BUCKET_NAME,
        project_id=TEST_PROJECT_ID,
        auth=mock_base_auth,
        config=mock_base_config,
    )
    file_list = gcs_instance.list_bucket()

    mock_gcs_client.list_blobs.assert_called_once_with(TEST_BUCKET_NAME)
    assert file_list == ["folder/file1.txt", "file2.wav"]


##
# Test for the upload_blob method
##


@pytest.mark.parametrize(
    "data_to_upload, content_type_arg, expected_content_type",
    [
        ("text data as string", None, ContentType.TEXT),
        (b"binary data as bytes", None, ContentType.TEXT),
        ("wav data", ContentType.WAV, ContentType.WAV),
        (b"wav data", ContentType.WAV, ContentType.WAV),
    ],
)
def test_upload_blob(
    mock_gcs_client: MagicMock,
    mock_base_auth: MagicMock,
    mock_base_config: MagicMock,
    data_to_upload: Union[str, bytes],
    content_type_arg: Optional[ContentType],
    expected_content_type: ContentType,
) -> None:
    """
    Verifies upload_blob handles different data types and content types.
    """
    mock_blob = MagicMock()
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_gcs_client.bucket.return_value = mock_bucket

    gcs_instance = Gcs(
        bucket_name=TEST_BUCKET_NAME,
        project_id=TEST_PROJECT_ID,
        auth=mock_base_auth,
        config=mock_base_config,
    )

    if content_type_arg:
        gcs_instance.upload_blob(
            file_name=TEST_FILE_NAME, data=data_to_upload, content_type=content_type_arg
        )
    else:
        gcs_instance.upload_blob(file_name=TEST_FILE_NAME, data=data_to_upload)

    mock_gcs_client.bucket.assert_called_once_with(TEST_BUCKET_NAME)
    mock_bucket.blob.assert_called_once_with(TEST_FILE_NAME)

    if isinstance(data_to_upload, str):
        mock_blob.upload_from_string.assert_called_once_with(
            data_to_upload, content_type=expected_content_type
        )
        mock_blob.upload_from_file.assert_not_called()
    else:  # It's bytes
        mock_blob.upload_from_file.assert_called_once_with(
            data_to_upload, content_type=expected_content_type
        )
        mock_blob.upload_from_string.assert_not_called()
