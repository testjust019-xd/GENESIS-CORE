# Evolution Lab

GENESIS does not change a model's native abilities by itself. It improves what the
model accomplishes through skills, memory, knowledge and workflows. The Evolution
Lab makes that claim **testable** instead of assumed.

## How it works

1. A *suite* is a fixed list of tasks. Each task has rule-based checks (`equals`,
   `contains`, `contains_any`, `not_contains`, `regex`, `max_words`, `number_equals`,
   `json_valid`, `language_fr`). No model judges itself.
2. `/eval run [suite]` runs the suite on the current model and stores a baseline.
3. `/eval skill <id>` runs the suite twice on the same model: once plain, once with
   the skill injected exactly as the agent would. The comparison lists tasks that now
   pass and tasks that now fail, and stores the verdict as evidence for that skill.
4. `/skill review <id> approve` shows the latest evidence before you decide.
5. `/evolve` shows the baseline score timeline, active skills, memory and documents.

Verdicts: `improved`, `slightly improved`, `mixed`, `regressed`, `no change`.

## Custom suites

Put JSON files in `~/.genesis/evals/`:

```json
{"name": "my-suite", "description": "...", "tasks": [
  {"id": "t1", "prompt": "What is 2+2? Number only.",
   "checks": [{"type": "number_equals", "value": 4}]}
]}
```

Invalid files are ignored; a task needs at least one check.

## Limits

- Small suites and sampled model output are noisy. A single comparison is weak
  evidence; re-run before deciding. Reports say so.
- Scores show measured behaviour on the suite only. They are not model-weight
  changes and not a measure of general intelligence.
- Evidence informs the human decision; it does not activate or block a skill (yet).
