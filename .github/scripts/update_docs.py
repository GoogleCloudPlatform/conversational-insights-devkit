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
This script uses the Gemini API to create or improve the content of README.md
files across the entire project.

For each directory, it checks for Python files. If a README.md doesn't exist,
it generates one based on the Python files in that directory. If a README.md
already exists, it improves its content.

The script requires the 'google-genai' library to be installed and a
Gemini API key to be provided as an environment variable 'GEMINI_API_KEY'.
"""

import os

from google import genai

MODEL_NAME = "gemini-2.5-flash"


def _get_client() -> genai.Client:
    """Builds a google-genai Client from GEMINI_API_KEY."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set.")
    return genai.Client(api_key=api_key)


def get_python_files(directory: str) -> list[str]:
    """Returns a list of Python files in a given directory."""
    py_files = []
    for file in os.listdir(directory):
        if file.endswith(".py"):
            py_files.append(os.path.join(directory, file))
    return py_files


def get_file_content(file_path: str) -> str:
    """Reads and returns the content of a file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def improve_readme(client: genai.Client, content: str) -> str:
    """Improves the content of a README file using the Gemini API."""
    prompt = f"""
    As an expert technical writer, your task is to improve the following README.md file.
    Your goal is to make it clearer, more concise, and more engaging for developers
    and potential users. Please review the content and provide an improved version.

    - Ensure the structure is logical.
    - Correct any grammatical errors or typos.
    - If sections are unclear, rewrite them.
    - Do not invent new features or information; base your improvements solely on the
      provided content.
    - Return only the full, updated content of the README.md file. Do not include any
      introductory text like "Here is the improved README.md:".

    Here is the original README.md content:
    ---
    {content}
    ---
    """
    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        return (response.text or "").strip()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"Error calling Gemini API for improvement: {exc}")
        return ""


def generate_readme(
    client: genai.Client, directory: str, py_files: list[str]
) -> str:
    """Generates a README.md file for a directory based on its Python files."""
    if not py_files:
        return ""

    file_contents = ""
    for file_path in py_files:
        file_contents += f"--- {os.path.basename(file_path)} ---"
        file_contents += get_file_content(file_path)
        file_contents += "\n\n"

    prompt = f"""
    As an expert technical writer, create a README.md for the directory '{directory}'.
    The README should explain the purpose of the Python modules in this directory.
    Based on the content of the files, create a clear and concise README.

    - The README should have a title.
    - It should provide a brief overview of the directory's functionality.
    - If applicable, describe each module's role.
    - Do not invent new features or information.
    - Return only the full content of the README.md file. Do not include any
      introductory text.

    Here are the contents of the Python files:
    {file_contents}
    """
    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        return (response.text or "").strip()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"Error calling Gemini API for generation: {exc}")
        return ""


def update_readme_in_directory(client: genai.Client, directory: str) -> None:
    """Updates or creates a README.md file in a directory."""
    readme_path = os.path.join(directory, "README.md")
    py_files = get_python_files(directory)

    if os.path.exists(readme_path):
        print(f"Improving README.md in {directory}...")
        original_content = get_file_content(readme_path)
        if original_content:
            improved_content = improve_readme(client, original_content)
            if improved_content and improved_content != original_content:
                with open(readme_path, "w", encoding="utf-8") as f:
                    f.write(improved_content)
                print(f"Successfully updated {readme_path}")
            else:
                print(f"No changes made to {readme_path}")
    elif py_files:
        print(f"Creating README.md in {directory}...")
        generated_content = generate_readme(client, directory, py_files)
        if generated_content:
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(generated_content)
            print(f"Successfully created {readme_path}")


def main() -> None:
    """Walks through the project directory and updates or creates README.md files."""
    client = _get_client()
    ignored_dirs = [
        ".git",
        ".venv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        "build",
        "dist",
        ".coverage",
        "kokoro",
        ".vscode",
        "cxidk.egg-info",
        "conidk.egg-info",
    ]

    for root, _, _ in os.walk("."):
        if any(d in root for d in ignored_dirs):
            continue
        update_readme_in_directory(client, root)


if __name__ == "__main__":
    main()
