# Workflow Module

The `workflow` module contains specialized workflows and utilities that combine multiple steps or services to achieve specific tasks.

## Modules

- **`audio.py`**: Audio processing utilities.
- **`content_generator.py`**: Generation of content/transcripts.
- **`format.py`**: Tools for formatting and converting transcripts (e.g., from Genesys or AWS to Insights format).
- **`ops.py`**: Export and import of Insights configuration between environments. Supporting modules in `utils/`: `utils/ops_types.py` (vocabulary and bundle I/O), `utils/ops_handlers.py` (per-asset logic), `utils/ops_composite.py` (scorecards, analysis rules, correlation config).
- **`role_recognizer.py`**: Logic for identifying speaker roles in a conversation, potentially using Gemini.
- **`views.py`**: View definitions or helpers.

## Common Workflows

- **Transcript Formatting**: Converting transcripts from third-party vendors (Genesys, AWS) into the format required by Conversational Insights.
- **Role Recognition**: Enhancing transcripts by identifying who is speaking (e.g., Agent vs. User).
- **Configuration Promotion**: Moving scorecards, rules and highlighters from a sandbox project to production.

## Configuration Export and Import (`ops.py`)

`ConfigOps` moves configuration between Insights environments. Source and destination may differ in project, in region, or in both.

```python
from cxidk.workflow.ops import Asset, ConfigOps, ImportOptions

# Read from the sandbox.
source = ConfigOps("dev-proj", "us-central1")
source.export(uri="gs://my-bundles/config.json")

# Preview, then write to production.
destination = ConfigOps("prod-proj", "europe-west1")
print(destination.plan(uri="gs://my-bundles/config.json").summary())
report = destination.import_(uri="gs://my-bundles/config.json")
```

### Supported assets

| `Asset` | Insights resource |
| --- | --- |
| `SCORECARDS` | QA scorecards, their latest revision, and that revision's questions |
| `QA_QUESTION_TAGS` | Custom question tags |
| `PHRASE_MATCHERS` | Smart highlighters |
| `ISSUE_MODELS` | Topic models |
| `ANALYSIS_RULES` | Analysis rules |
| `AUTO_LABELING_RULES` | Auto labeling rules |
| `ASSESSMENT_RULES` | Assessment rules |
| `CORRELATION_CONFIG` | Correlation rules |

Selection is modular. Pass `assets=[Asset.SCORECARDS, Asset.PHRASE_MATCHERS]` to either method, or omit `assets` for everything. On import, omitting `assets` means everything the bundle contains.

Views, dashboards and discoveries are not implemented. Requesting them raises rather than silently exporting nothing.

### Behaviour worth knowing before the first run

**Import is create-only.** No update, no merge, no overwrite, no delete. If a resource of the same name already exists at the destination, another one is created alongside it, and re-running an import creates a further set of copies. The correlation configuration is the one unavoidable exception: the API exposes only get and update for that singleton, so rules are appended and pre-existing rules are left untouched.

A direct consequence is that resource IDs from the bundle are never reused; each copy gets a freshly minted ID with the source ID as a readable stem.

**Copies arrive inactive.** Export covers active resources only, so every rule in a bundle was live at the source. Recreating them live would start analysing production traffic the moment the import finished. Pass `ImportOptions(activate_imported=True)` to opt in.

**Copies are renamed by default.** `ImportOptions(naming=NamingPolicy.SUFFIX)` labels each copy `"{name} (imported {date})"`. Use `NamingPolicy.DUPLICATE` for byte-identical names, and `rename_template` to change the label.

**Bundles live in Cloud Storage only.** A local path is rejected rather than quietly written to disk. One GCS object per export gives an atomic write that a directory of files cannot.

**Scorecards carry their definition and conditional logic only.** Example conversations, feedback labels and fine-tuning state are excluded, so an imported scorecard arrives untuned. Discovery Engine and intent-taxonomy scorecards are exported, but `QaScorecard.source` is output-only, so the copies land as customer-defined; the original value is preserved in the bundle and stamped into the description.

**Topic models need a staging bucket to stay trained.** Pass `ExportOptions(gcs_bucket="my-bucket")` to use the native model export. Without it, only metadata is captured and the imported copy is untrained. Imported models are never deployed, because deployment is billable.

### Cross-environment references

Analysis rules point at phrase matchers, topic models and scorecard revisions by full resource name, and those names embed the source project. `ConfigOps` rewrites them to the copies created in the same run, which is why import order matters and why referenced assets should be included in the selection.

When a reference cannot be resolved, `ReferenceResolution.STRICT` (the default) refuses to create the rule. That is deliberate: per the API an empty `phraseMatchers` list means *all active phrase matchers*, and an empty `issueModels` list means *the most recently deployed model*, so pruning a dangling reference makes a rule broader rather than narrower. `ReferenceResolution.PRUNE` opts into pruning with a loud warning.

Dialogflow references (`summarizationConfig.conversationProfile`, `summarizationConfig.generator`) cannot be created by this devkit. Supply them explicitly:

```python
ImportOptions(
    external_reference_map={
        "projects/dev/locations/us-central1/conversationProfiles/abc": (
            "projects/prod/locations/europe-west1/conversationProfiles/xyz"
        ),
    },
)
```

### Preview and reporting

`plan()` reads the bundle and reports what an import would create, which display names already exist at the destination, and the billing impact of any analysis rules — including translating `analysisPercentage`, which is a fraction in `[0, 1]` rather than a percentage out of 100. It writes nothing. `ImportOptions(dry_run=True)` performs the same walk through the real import path, also without writing.

`export()`, `plan()` and `import_()` each return a report object carrying per-asset counts, created resource names, warnings and errors.
