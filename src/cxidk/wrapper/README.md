# Wrapper Module

The `wrapper` module provides simplified interfaces for various Google Cloud services, making them easier to use within the context of Conversational Insights.

## Modules

- **`agents.py`**: Wrappers for Dialogflow CX Agents and Agent Studio.
- **`iam.py`**: Helper functions for IAM management.
- **`insights.py`**: Core Conversational Insights functionality (ingestion, analysis).
- **`sheets.py`**: Integration with Google Sheets.
- **`speech.py`**: Wrappers for Speech-to-Text (STT) V1 and V2.
- **`storage.py`**: Google Cloud Storage (GCS) operations.
- **`vertex.py`**: Vertex AI integration.

## Usage

These wrappers are intended to abstract away some of the complexity of the raw Google Cloud client libraries, providing a more "pythonic" and task-oriented API.
