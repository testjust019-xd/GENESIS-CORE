# Evolution Feedback Loop

The Evolution Feedback Loop is a read-only diagnostic layer over GENESIS evidence.
It cross-checks benchmark history and task-level results with captured mission
experiences to surface concrete opportunities for review.

## Signals

- **Baseline regression:** compares the two newest baseline runs for the same
  suite, provider and model; reports score delta and changed task IDs.
- **Recurring benchmark failure:** finds task IDs that failed in at least two
  of the five newest baseline runs for the same evaluation context.
- **Skill evaluation warning:** surfaces recorded skill comparisons whose
  verdict is `regressed` or `mixed`.
- **Repeated experience blocker:** groups exact normalized objective and
  instructions, then reports repeated blocked/failed attempts with source IDs.

## API

- `POST /api/evolution/feedback/analyze` — generate and persist a new report.
- `GET /api/evolution/feedback/latest` — retrieve the latest report.

Reports include the run IDs, task IDs, comparison IDs or experience IDs that
support each finding. The analysis is deterministic and does not ask a model to
judge itself.

## Boundaries

This feature is diagnostic only. It does not update model weights, execute
tools, promote memories, edit Skills, or activate Skills. Recommendations are
review prompts, not automatic actions. Re-run comparable benchmarks to confirm
a signal before making changes. Small benchmark suites and stochastic model
outputs can be noisy.

Run the test suite with:

```bash
pytest -q
```
