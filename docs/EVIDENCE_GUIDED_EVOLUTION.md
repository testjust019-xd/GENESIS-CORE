# Evidence-guided evolution

GENESIS can turn repeated task observations into reviewable lesson proposals without
pretending that a language model has trained itself.

## Flow

1. The Experience Engine records task attempts with mission/task IDs, outcome,
   observer summary, confidence and provenance.
2. `EvolutionEngine.analyze()` groups only exact normalized matches of objective
   and instructions. It does not perform fuzzy or semantic clustering.
3. A group needs at least two observations by default. Archived experiences are
   excluded. The proposal records every source experience ID and the outcome counts.
4. A person accepts or rejects the proposal. A pending proposal is never injected
   into active memory or the agent's instructions.
5. An accepted proposal can be promoted to a declarative Skill **draft**. The
   existing Skill review workflow remains mandatory before activation.

## Studio API

- `POST /api/evolution/analyze` with optional `min_support` (2–20) and `limit` (1–200).
- `GET /api/evolution/proposals` with optional `status` and `limit`.
- `POST /api/evolution/proposals/{id}/review` with `{"decision":"accept"|"reject","note":""}`.
- `POST /api/evolution/proposals/{id}/skill-draft` creates or returns the Skill draft
  for an accepted proposal.

The Studio Evolution view exposes the scan, evidence summary, review actions and
draft creation. The Skills view remains the place to inspect and activate a draft.

## Safety and interpretation

- A completion ratio is descriptive evidence, not a probability of future success.
- A repeated task context is not proof of causation or general applicability.
- The proposal text is a deterministic summary of recorded outcomes, not a generated
  recipe. The source observer summaries remain visible for human inspection.
- Accepting a lesson does not activate a Skill. Draft promotion does not activate it.
- No model weights are changed and no shell code or executable skill content is run.
- Rejected proposals remain recorded; they are not silently regenerated on every scan.

## Tests

Run `python -m pytest tests/test_evolution.py tests/test_studio_web.py`.
