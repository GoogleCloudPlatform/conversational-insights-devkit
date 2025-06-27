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

"""Unit tests for Role Recognizer"""

import json
import os
import pytest
import pathlib
from typing import Dict
from src.workflow import role_recognizer


@pytest.fixture(name="test_files")
def load_test_data() -> Dict[str, dict]:
    """Loads test data 

    This fixture loads a sample conversation from a JSON file located in the 
    `data` directory (relative to the project root).  

    Returns:
        Dict: Conversation
    """

    test_data_dir = pathlib.Path(__file__).parent.parent.parent / "data"
    test_convo_file = os.path.join(str(test_data_dir), "sample_conversation.json")

    with open(test_convo_file, "r", encoding="utf-8") as fp:
        conversation = json.load(fp)

    return {"conversation": conversation}


def find_element(data, key, value):

    """Finds the first element in a list of dictionaries that matches a given key and value.

    Args:
        data: A list of dictionaries.
        key: The key to search for within each dictionary.
        value: The value to match against the value associated with the key.

    Returns:
        The first dictionary in the list where `data[key] == value`.  Returns `None` if
        no such dictionary is found.
    """

    for item in data:
        if item[key] == value:
            return item
    return None


def test_role_recognizer(test_files: Dict[str, dict]):

    """Tests Role Recognizer class
    """
    conversation: Dict[str, list] = {"entries": []}

    input_data = test_files["conversation"]
    for item in input_data["entries"]:
        conv = {"text": item["text"], "uid": item["uid"]}
        conversation["entries"].append(conv)

    rr = role_recognizer.RoleRecognizer(model_name="gemini-2.0-flash-exp")
    predicted_roles = rr.predict_roles(conversation)

    # Assert that the return vlaue dict
    assert isinstance(predicted_roles, dict)

    # Assert that there is "predictions" in outout from LLM
    assert "predictions" in predicted_roles

    # Assert that number of utternances are the same in input and output
    assert len(input_data["entries"]) == len(predicted_roles["predictions"])
    
    # Check if roles in input_data are same as predicted_roles
    for item in input_data["entries"]:
        uid = item["uid"]
        output_item = find_element(predicted_roles["predictions"], "uid", uid)
        assert item["role"] == output_item["role"]

