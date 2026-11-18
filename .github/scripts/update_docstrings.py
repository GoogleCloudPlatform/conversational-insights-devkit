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
This script automatically updates docstrings in Python files using the Gemini API.

It recursively finds all Python files in a specified directory (e.g., 'src'),
parses them to identify functions and classes, and uses the Gemini API to
generate new docstrings based on the source code.

The script requires the 'google-genai' library to be installed and a
Gemini API key to be provided as an environment variable 'GEMINI_API_KEY'.

Warning: This script will modify files in place. Make sure your code is
under version control.
"""

import ast
import os

from google import genai

SRC_DIRECTORY = "src"
MODEL_NAME = "gemini-2.5-flash"


def _get_client() -> genai.Client:
    """Builds a google-genai Client from GEMINI_API_KEY."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set.")
    return genai.Client(api_key=api_key)


def generate_docstring(client: genai.Client, code: str) -> str:
    """Uses the Gemini API to generate a docstring for a piece of code."""
    prompt = f"""
    You are a Python expert. Write a concise, professional, and PEP 257 compliant
    docstring for the following Python code. The docstring should explain what
    the code does, its arguments (if any), and what it returns (if any).
    Do not include the function signature or any introductory text like
    "Here is the docstring:".
    Only return the docstring itself, enclosed in triple quotes.

    Code:
    ```python
    {code}
    ```
    """
    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        new_docstring = (response.text or "").strip()
        if new_docstring.startswith("```python"):
            new_docstring = new_docstring[len("```python") :].strip()
        if new_docstring.endswith("```"):
            new_docstring = new_docstring[: -len("```")].strip()
        return new_docstring
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"  - Could not generate docstring: {exc}")
        return ""


def update_file_docstrings(client: genai.Client, filepath: str) -> None:
    """
    Reads a Python file, updates docstrings for functions and classes,
    and writes the changes back to the file.
    """
    print(f"Processing {filepath}...")
    with open(filepath, "r", encoding="utf-8") as f:
        original_source = f.read()

    try:
        tree = ast.parse(original_source)
    except SyntaxError as exc:
        print(f"  - Could not parse {filepath}: {exc}")
        return

    new_source = original_source
    for node in reversed(list(ast.walk(tree))):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            code_segment = ast.get_source_segment(original_source, node)
            if not code_segment:
                continue

            generated_docstring = generate_docstring(client, code_segment)
            if not generated_docstring:
                continue

            existing_docstring_node = ast.get_docstring(node, clean=False)
            if existing_docstring_node:
                docstring_node = node.body[0]
                start_lineno = docstring_node.lineno - 1
                end_lineno = docstring_node.end_lineno

                lines = new_source.split("\n")
                first_line_index = start_lineno
                indentation = ""
                if first_line_index < len(lines):
                    line_content = lines[first_line_index]
                    indentation = line_content[
                        : len(line_content) - len(line_content.lstrip())
                    ]

                indented_new_docstring = "\n".join(
                    f"{indentation}{line}" for line in generated_docstring.split("\n")
                )

                lines[start_lineno:end_lineno] = [indented_new_docstring]
                new_source = "\n".join(lines)
                print(f"  - Updated docstring for: {node.name}")

    if new_source != original_source:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_source)
        print(f"  -> Saved changes to {filepath}")


def main() -> None:
    """Runs the docstring update workflow across SRC_DIRECTORY."""
    client = _get_client()
    for root, _, files in os.walk(SRC_DIRECTORY):
        for file in files:
            if file.endswith(".py"):
                update_file_docstrings(client, os.path.join(root, file))

    print("\nDocstring update process complete.")


if __name__ == "__main__":
    main()
