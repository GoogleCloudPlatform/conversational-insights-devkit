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

"""A wrapper for Google Sheets API operations.

This module provides the `Sheets` class, which simplifies reading data from a
Google Sheet and converting it into a pandas DataFrame. It uses the `gspread`
library for API interactions and `pandas` for data manipulation.
"""

from typing import Optional

import gspread
from gspread import exceptions
import pandas as pd  # type: ignore

from cxidk.core import base

_SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


class Sheets:
    """A wrapper for Google Sheets API to simplify interactions with spreadsheets.

    This class uses `gspread` to authorize and interact with the Google Sheets
    API, providing a simple method to fetch sheet data as a pandas DataFrame.

    Attributes:
        sheet_id: The ID or name of the Google Sheet.
        auth: An authentication object.
        config: A configuration object.
        client: An authorized `gspread` client instance.
    """

    def __init__(
        self,
        sheet_id: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    )->None:
        """Initializes the Sheets wrapper.

        Args:
            sheet_id: The ID or name of the Google Sheet.
            auth: An optional, pre-configured authentication object.
            config: An optional, pre-configured configuration object.
        """
        self.auth = auth or base.Auth(scope=_SHEETS_SCOPES)
        self.config = config or base.Config()
        self.sheet_id = sheet_id
        self.client = gspread.authorize(self.auth.creds)

    def to_dataframe (
        self,
        sheet_name: str = "Sheet1"
    ) -> pd.DataFrame:
        """Reads a sheet from the spreadsheet and returns it as a pandas DataFrame.

        Args:
            sheet_name: The name (str) or index (int) of the sheet to read.

        Returns:
            A pandas DataFrame containing the sheet data.

        Raises:
            gspread.exceptions.SpreadsheetNotFound: If the spreadsheet cannot be found.
            TypeError: If sheet_name is not a string or an integer.
        """
        try:
            spreadsheet = self.client.open_by_key(self.sheet_id)
        except exceptions.SpreadsheetNotFound:
            spreadsheet = self.client.open(self.sheet_id)

        # Select the worksheet
        if isinstance(sheet_name, str):
            worksheet = spreadsheet.worksheet(sheet_name)
        elif isinstance(sheet_name, int):
            worksheet = spreadsheet.get_worksheet(sheet_name)
        else:
            raise TypeError("sheet_name must be a string (name) or an integer (index).")

        # Get all data as a list of lists
        data = worksheet.get_all_values()

        # Convert to DataFrame
        if not data:
            return pd.DataFrame() # Return empty DataFrame if no data

        return pd.DataFrame(data[1:], columns=data[0])
