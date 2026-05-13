# Workflow Module

The `workflow` module contains specialized workflows and utilities that combine multiple steps or services to achieve specific tasks.

## Modules

- **`audio.py`**: Audio processing utilities.
- **`content_generator.py`**: Generation of content/transcripts.
- **`format.py`**: Tools for formatting and converting transcripts (e.g., from Genesys or AWS to Insights format).
- **`role_recognizer.py`**: Logic for identifying speaker roles in a conversation, potentially using Gemini.
- **`views.py`**: View definitions or helpers.

## Common Workflows

- **Transcript Formatting**: Converting transcripts from third-party vendors (Genesys, AWS) into the format required by Conversational Insights.
- **Role Recognition**: Enhancing transcripts by identifying who is speaking (e.g., Agent vs. User).
