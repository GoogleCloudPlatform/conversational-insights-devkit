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

"""Unit tests for the Google Sheets wrapper."""

# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pylint: disable=line-too-long


from typing import Dict
from unittest.mock import MagicMock

from gspread import exceptions
import pandas as pd  # type: ignore
import pytest
from pandas.testing import assert_frame_equal

from cxidk.wrapper.sheets import Sheets

# --- Mocks and Fixtures ---


@pytest.fixture
def mock_base(mocker: MagicMock) -> Dict[str, MagicMock]:
    """Mocks the cxidk.core.base dependency."""
    mock_auth = mocker.patch("cxidk.wrapper.sheets.base.Auth", autospec=True)
    mock_config = mocker.patch("cxidk.wrapper.sheets.base.Config", autospec=True)
    # Ensure the mock auth instance has a 'creds' attribute
    mock_auth.return_value.creds = "mock-credentials"
    return {"Auth": mock_auth, "Config": mock_config}


@pytest.fixture
def mock_gspread(mocker: MagicMock) -> MagicMock:
    """Mocks the gspread library."""
    return mocker.patch("cxidk.wrapper.sheets.gspread", autospec=True)


@pytest.fixture
def sheets_wrapper(
    mock_base: Dict[str, MagicMock], mock_gspread: MagicMock
) -> Sheets:
    """Provides an initialized Sheets wrapper with mocked dependencies."""
    return Sheets(sheet_id="test-sheet-id")


# --- Test Class for Sheets ---


class TestSheets:
    """Test suite for the Sheets wrapper class."""

    def test_init_with_defaults(
        self,
        mock_base: Dict[str, MagicMock],
        mock_gspread: MagicMock,
    ) -> None:
        """Tests that __init__ uses default Auth and Config if none are provided."""
        Sheets(sheet_id="test-id")

        mock_base["Auth"].assert_called_once()
        mock_base["Config"].assert_called_once()
        mock_gspread.authorize.assert_called_once_with("mock-credentials")

    def test_init_with_provided_auth_and_config(
        self,
        mock_base: Dict[str, MagicMock],
        mock_gspread: MagicMock,
    ) -> None:
        """Tests that __init__ uses provided Auth and Config objects."""
        mock_auth_instance = MagicMock()
        mock_auth_instance.creds = "provided-credentials"
        mock_config_instance = MagicMock()

        sheets = Sheets(
            sheet_id="test-id", auth=mock_auth_instance, config=mock_config_instance
        )

        # Ensure default constructors were NOT called
        mock_base["Auth"].assert_not_called()
        mock_base["Config"].assert_not_called()

        # Ensure the provided objects were used
        assert sheets.auth is mock_auth_instance
        assert sheets.config is mock_config_instance
        mock_gspread.authorize.assert_called_once_with("provided-credentials")

    def test_to_dataframe_success_by_key(self, sheets_wrapper: Sheets) -> None:
        """Tests successful data retrieval using sheet ID (open_by_key)."""
        mock_spreadsheet = MagicMock()
        mock_worksheet = MagicMock()
        sheets_wrapper.client.open_by_key.return_value = mock_spreadsheet # type: ignore[attr-defined]
        mock_spreadsheet.worksheet.return_value = mock_worksheet
        mock_worksheet.get_all_values.return_value = [
            ["Header1", "Header2"],
            ["Data1", "Data2"],
        ]

        df = sheets_wrapper.to_dataframe(sheet_name="MySheet")

        sheets_wrapper.client.open_by_key.assert_called_once_with("test-sheet-id") # type: ignore[attr-defined]
        sheets_wrapper.client.open.assert_not_called() # type: ignore[attr-defined]
        mock_spreadsheet.worksheet.assert_called_once_with("MySheet")

        expected_df = pd.DataFrame([["Data1", "Data2"]], columns=["Header1", "Header2"])
        assert_frame_equal(df, expected_df)

    def test_to_dataframe_success_by_name(self, sheets_wrapper: Sheets) -> None:
        """Tests successful data retrieval using sheet name (open) as a fallback."""
        mock_spreadsheet = MagicMock()
        mock_worksheet = MagicMock()
        sheets_wrapper.client.open_by_key.side_effect = exceptions.SpreadsheetNotFound # type: ignore[attr-defined]
        sheets_wrapper.client.open.return_value = mock_spreadsheet # type: ignore[attr-defined]
        mock_spreadsheet.get_worksheet.return_value = mock_worksheet
        mock_worksheet.get_all_values.return_value = [["A"], ["1"]]

        df = sheets_wrapper.to_dataframe(sheet_name=0)  # type: ignore[arg-type]

        sheets_wrapper.client.open_by_key.assert_called_once_with("test-sheet-id") # type: ignore[attr-defined]
        sheets_wrapper.client.open.assert_called_once_with("test-sheet-id") # type: ignore[attr-defined]
        mock_spreadsheet.get_worksheet.assert_called_once_with(0)

        expected_df = pd.DataFrame([["1"]], columns=["A"])
        assert_frame_equal(df, expected_df)

    def test_to_dataframe_spreadsheet_not_found(self, sheets_wrapper: Sheets) -> None:
        """Tests that SpreadsheetNotFound is raised if the sheet is not found."""
        sheets_wrapper.client.open_by_key.side_effect = exceptions.SpreadsheetNotFound # type: ignore[attr-defined]
        sheets_wrapper.client.open.side_effect = exceptions.SpreadsheetNotFound # type: ignore[attr-defined]

        with pytest.raises(exceptions.SpreadsheetNotFound):
            sheets_wrapper.to_dataframe()

    def test_to_dataframe_invalid_sheet_name_type(self, sheets_wrapper: Sheets) -> None:
        """Tests that TypeError is raised for invalid sheet_name types."""
        sheets_wrapper.client.open_by_key.return_value = MagicMock() # type: ignore[attr-defined]

        with pytest.raises(
            TypeError, match=r"sheet_name must be a string \(name\) or an integer"
        ):
            # Using a float is an invalid type
            sheets_wrapper.to_dataframe(sheet_name=1.5)  # type: ignore

    def test_to_dataframe_empty_sheet(self, sheets_wrapper: Sheets) -> None:
        """Tests behavior when the sheet contains no data."""
        mock_spreadsheet = MagicMock()
        mock_worksheet = MagicMock()
        sheets_wrapper.client.open_by_key.return_value = mock_spreadsheet # type: ignore[attr-defined]
        mock_spreadsheet.worksheet.return_value = mock_worksheet
        mock_worksheet.get_all_values.return_value = []  # Empty data

        df = sheets_wrapper.to_dataframe(sheet_name="EmptySheet")

        assert df.empty
        assert isinstance(df, pd.DataFrame)
