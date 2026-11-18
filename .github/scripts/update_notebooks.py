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

"""
This script uses the Gemini API to automatically generate Colab (.ipynb)
notebooks for Python source files.

It scans specified source directories (e.g., 'src/cxidk/wrapper'), reads the
content of each Python file, and then prompts the Gemini API to generate a
complete Colab notebook in JSON format that demonstrates the features in that file.

The generated notebooks are saved in the '/examples' directory.

The script requires the 'google-genai' library to be installed and a
Gemini API key to be provided as an environment variable 'GEMINI_API_KEY'.
"""

import json
import os
import sys

from google import genai

SRC_DIRECTORIES = ["src/cxidk/wrapper", "src/cxidk/workflow"]
EXAMPLES_DIRECTORY = "examples"
MODEL_NAME = "gemini-2.5-flash"


def _get_client() -> genai.Client:
    """Builds a google-genai Client using GEMINI_API_KEY or ADC."""
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key)
    try:
        return genai.Client(vertexai=True)
    except Exception:  # pylint: disable=broad-exception-caught
        print(
            "Could not initialize google-genai client: "
            "GEMINI_API_KEY not set and Application Default Credentials not found."
        )
        sys.exit(1)


def generate_notebook_json(
    client: genai.Client, file_path: str, file_content: str
) -> str:
    """Uses the Gemini API to generate the JSON content for a Colab notebook."""
    filename = os.path.basename(file_path)
    feature_name = filename.replace(".py", "").replace("_", " ").title()

    prompt = f"""
    You are an expert developer advocate and technical writer. Your task is to create a
    Jupyter/Colab notebook (.ipynb) in JSON format that demonstrates the features of the
    following Python module: `{filename}`.

    **Instructions:**
    1.  **Analyze the Code:** Understand the classes, methods, and functionality in the
        provided code.
    2.  **Create a Tutorial:** Structure the notebook as a tutorial. Start with an
        introduction, explain the key concepts, and provide runnable code examples for
        the main features.
    3.  **Use Markdown and Code Cells:**
        - Use Markdown cells (cell_type: "markdown") for explanations, titles, and
          instructions.
        - Use Code cells (cell_type: "code") for Python code.
    4.  **Placeholder for Secrets:** For any required credentials, API keys, or project
        IDs, use clear placeholders like `YOUR_PROJECT_ID` or `YOUR_API_KEY` and
        instruct the user to replace them.
    5.  **Output Format:** The entire output *must* be a single, valid JSON object that
        represents the .ipynb file structure. Do not include any other text or markdown
        formatting outside of the JSON structure.

    **JSON Structure:**
    ```json
    {{
      "cells": [
        {{
          "cell_type": "markdown",
          "source": [
            "# Tutorial: Using the {feature_name} Feature"
          ]
        }},
        {{
          "cell_type": "code",
          "execution_count": null,
          "source": [
            "# Install necessary libraries\\n",
            "!pip install cxidk google-genai"
          ]
        }}
      ],
      "metadata": {{}},
      "nbformat": 4,
      "nbformat_minor": 5
    }}
    ```

    Here is the source code for `{filename}`:
    ---
    {file_content}
    ---
    """

    print(f"  - Generating notebook for {filename}...")
    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        json_text = (response.text or "").strip()
        if json_text.startswith("```json"):
            json_text = json_text[len("```json") :].strip()
        if json_text.endswith("```"):
            json_text = json_text[: -len("```")].strip()

        json.loads(json_text)
        return json_text
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"  - Could not generate notebook for {filename}: {exc}")
        return ""


def main() -> None:  # pylint: disable=too-many-branches
    """Finds Python files, generates notebooks, and saves them."""
    client = _get_client()
    print("Starting notebook generation process...")
    if not os.path.exists(EXAMPLES_DIRECTORY):
        os.makedirs(EXAMPLES_DIRECTORY)

    all_files = []
    for src_dir in SRC_DIRECTORIES:
        for root, _, files in os.walk(src_dir):
            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                    all_files.append((os.path.join(root, file), file))

    if not all_files:
        print("No Python source files found to process.")
        sys.exit(0)

    print(f"Found {len(all_files)} Python files to process:")
    for file_path, _ in all_files:
        print(f"- {file_path}")

    successful_notebooks = 0
    for i, (file_path, filename) in enumerate(all_files):
        print(f"\nProcessing file {i + 1}/{len(all_files)}: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            print(f"  - File not found: {file_path}")
            continue

        notebook_json_str = generate_notebook_json(client, file_path, content)

        if notebook_json_str:
            dir_name = os.path.basename(os.path.dirname(file_path))
            stem = filename.replace(".py", "")
            notebook_filename = f"{i + 1:02d}-{dir_name}-{stem}.ipynb"
            output_path = os.path.join(EXAMPLES_DIRECTORY, notebook_filename)

            try:
                notebook_data = json.loads(notebook_json_str)
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(notebook_data, f, indent=2)

                if os.path.exists(output_path):
                    print(f"  -> Successfully created notebook: {output_path}")
                    successful_notebooks += 1
                else:
                    print(f"  - FAILED to create notebook: {output_path}")

            except (json.JSONDecodeError, TypeError) as exc:
                print(f"  - Failed to write notebook due to invalid JSON: {exc}")

    print("Notebook generation process complete.")
    print(
        f"Successfully generated {successful_notebooks} "
        f"out of {len(all_files)} notebooks."
    )

    if successful_notebooks == 0 and all_files:
        print(
            "\nERROR: No notebooks were generated. "
            "Check the logs for errors from the API."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
