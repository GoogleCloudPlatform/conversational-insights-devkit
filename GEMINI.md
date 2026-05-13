# Gemini Development Guide

This guide provides context for using Gemini to assist with development in the `conversational-insights-devkit-alpha` repository.

## Project Overview

The Conversational Insights DevKit is a Python-based toolkit for extracting insights from conversational data from various sources (e.g., AWS, Genesys). It provides tools for audio processing, content generation, and data formatting.

## Development Setup

The project uses Python with a virtual environment.

1.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Running Quality Checks

This project uses `pylint` for linting, `mypy` for type checking, and `pytest` for testing.

*   **Run tests:**
    ```bash
    pytest
    ```

*   **Run linter:**
    ```bash
    pylint src tests
    ```

*   **Run type checker:**
    ```bash
    mypy src
    ```

## Project Structure

-   `src/cxidk/`: The main source code for the devkit.
    -   `core/`: Base classes and core abstractions.
    -   `workflow/`: Components for building conversation processing workflows (audio, formatting, etc.).
    -   `wrapper/`: Wrappers for external services (Vertex AI, Google Sheets, etc.).
-   `tests/`: Unit and integration tests.
    -   `unit/`: Tests for individual components.
    -   `integration/`: Tests for component interactions and workflows.
-   `examples/`: Example usage of the devkit.
-   `pyproject.toml`: Project metadata and dependencies.
-   `.github/workflows/`: CI/CD pipelines for linting, testing, and type checking.
