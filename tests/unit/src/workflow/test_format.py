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

"""Test Class for format."""

import json
import os
import pathlib
from typing import Dict
import pytest
import jsonschema
import pathlib
from src.workflow import format as ft


_TEST_DATA_DIR = pathlib.Path(__file__).parent.parent / "data"


def load_test_data(filename: str) -> dict:
    fpath = _TEST_DATA_DIR / filename
    with open(fpath, "r", encoding="utf-8") as fp:
        return json.load(fp)


@pytest.fixture(name="test_files")
def load_test_files() -> Dict[str, dict]:
    data_dir = pathlib.Path(__file__).parent.parent.parent / "data"

    fpath = os.path.join(str(data_dir), "genesys_input.json")
    with open(fpath, "r", encoding="utf-8") as fp:
        genesys_input = json.load(fp)

    fpath = os.path.join(data_dir, "genesys_output.json")
    with open(fpath, "r", encoding="utf-8") as fp:
        genesys_output = json.load(fp)

    fpath = os.path.join(data_dir, "aws_input.json")
    with open(fpath, "r", encoding="utf-8") as fp:
        aws_input = json.load(fp)

    fpath = os.path.join(data_dir, "aws_output.json")
    with open(fpath, "r", encoding="utf-8") as fp:
        aws_output = json.load(fp)

    return {
        "genesys_input": genesys_input,
        "genesys_output": genesys_output,
        "aws_input": aws_input,
        "aws_output": aws_output,
    }

def test_genesys_cloud_to_insights(test_files: Dict[str, dict]):

    formatter = ft.Insights()
    insights_format = formatter.from_genesys_cloud(test_files["genesys_input"])

    assert isinstance(insights_format, dict)
    assert insights_format == test_files["genesys_output"]

def test_genesys_cloud_to_insights_invalid_schema():

    formatter = ft.Insights()
    with pytest.raises(ValueError):
        formatter.from_genesys_cloud({})

def test_aws_insights(test_files: Dict[str, dict]):

    formatter = ft.Insights()
    insights_format = formatter.from_aws(test_files["aws_input"], "2024/01/01 00:00:00")

    assert isinstance(insights_format, dict)
    assert insights_format == test_files["aws_output"]

def test_aws_insights_invalid_input_date(test_files: Dict[str, dict]):

    formatter = ft.Insights()
    with pytest.raises(ValueError):
        formatter.from_aws(test_files["aws_input"], "2023/14/01 00:00:00")

def test_aws_to_insights_invalid_schema():

    formatter = ft.Insights()
    with pytest.raises(ValueError):
        formatter.from_aws({}, "2024/01/01 00:00:00")
