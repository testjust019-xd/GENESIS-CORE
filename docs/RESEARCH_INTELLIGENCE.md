# Research Intelligence

Research Intelligence turns one saved research run into a structured synthesis using GENESIS's configured primary model. Extra models are not required.

## Workflow

1. Run a search in Studio or TUI.
2. Review sources explicitly. Only sources marked `approved` are eligible; pending and rejected sources are excluded.
3. Optionally fetch page text for a source. Reports prefer fetched page text and otherwise use the saved search snippet.
4. Generate a report for the research run, optionally supplying a narrower focus.
5. Inspect the summary, claims, disagreements and open questions. Each claim is classified as `supported`, `inference` or `unverified`.

## Provenance and limits

- Source content is passed to the model as untrusted evidence, never as instructions.
- A supported claim must cite at least one source ID from the approved sources in that exact run.
- Citations to unknown, pending, rejected, or unrelated source IDs are rejected before a report is saved.
- Unverified claims cannot carry citations. Inferences are labelled as inferences.
- Reports record the provider, model, run ID and creation time.
- The report is a model-generated draft. Citation validation checks provenance, not whether a source is accurate, independent, current or correctly interpreted.
- Search snippets are weaker evidence than fetched page text. Reports expose which content was available in the prompt only through the stored source snapshot; they do not certify source quality.
- This feature does not browse additional pages, execute source instructions, or independently fact-check claims.

## TUI

```text
/research search <query>
/research sources [pending|approved|rejected]
/research review <source-id> approve|reject
/research report <run-id> [focus]
/research reports [run-id]
```

## Studio API

- `POST /api/research/runs/{run_id}/report` with optional JSON `{"question":"..." }`
- `GET /api/research/reports?run_id=...`
- `GET /api/research/reports/{report_id}`

Generation requires an available configured model. Reports are stored locally in the shared SQLite database.
