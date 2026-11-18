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
This script uses the Gemini API to automatically add comments to Python code.

It recursively finds all Python files in a specified directory (e.g., 'src'),
parses them to identify functions, and uses the Gemini API to generate helpful
comments for the code within those functions. The script then replaces the
original function code with the newly commented version.

The script requires the 'google-genai' library to be installed and a
Gemini API key to be provided as an environment variable 'GEMINI_API_KEY'.

Warning: This script modifies files in place. Ensure your code is under
version control.
"""

import ast
import os
import textwrap
from typing import Optional

from google import genai

SRC_DIRECTORY = "src"
MODEL_NAME = "gemini-2.5-flash"


def _get_client() -> genai.Client:
    """Builds a google-genai Client from GEMINI_API_KEY."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set.")
    return genai.Client(api_key=api_key)


def add_comments_to_code(
    client: genai.Client, code: str, previous_error: Optional[str] = None
) -> str:
    """Uses the Gemini API to add comments to a block of Python code."""
    feedback_prompt = ""
    if previous_error:
        feedback_prompt = f"""
    IMPORTANT: Your previous attempt to modify this code failed with a syntax error.
    You MUST fix this error in your new response. The error was: "{previous_error}"
    Please return the complete and syntactically correct code block with comments.
    """

    prompt = f"""
    As a senior Python developer, your task is to add concise, helpful comments to the
    following Python code. The code you receive will be dedented (no base indentation).
    {feedback_prompt}
    - Focus on explaining the 'why' behind the code, not just the 'what'.
    - Add comments for complex, non-obvious, or important parts of the code.
    - Do not comment on every line; only where it adds value.
    - Ensure your comments are correctly indented relative to the code they describe.
    - Return the *entire* original code block with the new comments integrated. Do not
      wrap it in markdown.
    - Ensure that you are ONLY and ONLY adding comments and nothing else.
    - Ensure that the comments are extra concise, 1 liners are recommended, never go
      above 3 lines.
    - Avoid adding more than 250 lines of comment per file.

    Here is the python code:
    {code}
    """
    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        commented_code = (response.text or "").strip()
        if commented_code.startswith("```python"):
            commented_code = "\n".join(commented_code.split("\n")[1:])
        if commented_code.endswith("```"):
            commented_code = "\n".join(commented_code.split("\n")[:-1])
        return commented_code.strip()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"  - Could not generate comments: {exc}")
        return ""


def update_file_comments(  # pylint: disable=too-many-branches,too-many-statements
    client: genai.Client, filepath: str
) -> None:
    """
    Reads a Python file, adds comments to functions, and writes the changes
    back to the file, validating syntax for each change and retrying with feedback.
    """
    print(f"Processing {filepath}...")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            original_source = f.read()
    except FileNotFoundError:
        print(f"  - File not found: {filepath}")
        return

    try:
        ast.parse(original_source)
    except SyntaxError as exc:
        print(f"  - Could not parse original file {filepath}. Skipping. Details: {exc}")
        return

    new_source = original_source
    source_changed_at_all = False

    for node in reversed(list(ast.walk(ast.parse(original_source)))):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            original_function_code = ast.get_source_segment(original_source, node)
            if not original_function_code:
                continue

            print(f"  - Analyzing function: {node.name}")
            last_error = None
            for attempt in range(2):
                indentation_prefix = " " * node.col_offset
                dedented_code = textwrap.dedent(original_function_code)
                commented_dedented_code = add_comments_to_code(
                    client,
                    dedented_code,
                    previous_error=last_error,
                )

                if (
                    not commented_dedented_code
                    or commented_dedented_code == dedented_code
                ):
                    if attempt == 0:
                        print(f"-> Model returned no changes. '{node.name}'.")
                    else:
                        print(f"-> Retry attempt returned no changes. '{node.name}'.")
                    break

                reindented_code = textwrap.indent(
                    commented_dedented_code, indentation_prefix
                )

                if original_function_code.endswith(
                    "\n"
                ) and not reindented_code.endswith("\n"):
                    reindented_code += "\n"
                if not original_function_code.endswith(
                    "\n"
                ) and reindented_code.endswith("\n"):
                    reindented_code = reindented_code.rstrip("\n")

                candidate_source = new_source.replace(
                    original_function_code, reindented_code
                )

                try:
                    ast.parse(candidate_source)
                    new_source = candidate_source
                    source_changed_at_all = True
                    message = (
                        "Successful" if attempt == 0 else "Successful self-healing"
                    )
                    print(f"    -> {message} function: {node.name}")
                    break
                except SyntaxError as exc:
                    last_error = str(exc)
                    if attempt == 0:
                        print(
                            f"    -> WARNING: Generated code for '{node.name}' was "
                            "syntactically incorrect. Retrying with error feedback..."
                        )
                    else:
                        print(
                            f"    -> ERROR: Retry for '{node.name}' also failed. "
                            "Discarding changes for this function."
                        )
                        print(f"       Details: {exc}")

    if source_changed_at_all:
        print(f"  -> Writing updated content to {filepath}")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_source)


def main() -> None:
    """Runs the comment update process across SRC_DIRECTORY."""
    client = _get_client()
    print("Starting comment update process...")
    for root, _, files in os.walk(SRC_DIRECTORY):
        for file in files:
            if file.endswith(".py"):
                update_file_comments(client, os.path.join(root, file))
    print("\nComment update process complete.")


if __name__ == "__main__":
    main()
