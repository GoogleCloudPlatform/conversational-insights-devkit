# Wrapper Layer (`cxidk.wrapper`)

The `wrapper` layer provides task-oriented Python clients over Google Cloud SDKs with explicit `Auth` and regional `Config` support.

## Submodules

- **`insights/`**: Contact Center AI (CCAI) Insights subpackage:
  - `conversations.py`: Read clients (`Conversations`, `Analyses`, `Stats`).
  - `operations.py`: Write/LRO clients (`Settings`, `Ingestion`, `Analysis`, `Export`, `LongRunningOperation`).
  - `config_resources.py`: Resource collections (`ConfigCollection`, `PhraseMatchers`, `IssueModels`, `QaScorecards`, `ScorecardRevisions`, `RevisionQuestions`, `QaQuestionTags`, `AnalysisRules`, `AutoLabelingRules`, `AssessmentRules`) plus the proto-based `LegacyScorecards` retained for `workflow.config_copier`.
  - `scorecards.py`: `Scorecards` facade composing the scorecard collections into typed, revision-aware views (`list()`, `get()`, `list_revisions()`) with `ScorecardSummary`, `ScorecardDefinition`, `RevisionInfo`, `QuestionInfo`, and `AnswerChoice` dataclasses.
  - `views.py`: `AuthorizedViews` and `CorrelationConfig`.
- **`sensitive_data_protection.py`**: Cloud DLP text inspection and de-identification.
- **`speech.py`**: Cloud Speech-to-Text V1 and V2 wrappers.
- **`storage.py`**: Google Cloud Storage (`Gcs`) operations.
- **`vertex.py`**: Gemini client on Vertex AI (`google-genai`).
- **`agents.py`**: Dialogflow CX and Customer Engagement Suite (CES) Agent Studio clients.
- **`iam.py`**: Project IAM policy helpers.
- **`sheets.py`**: Google Sheets integration.
