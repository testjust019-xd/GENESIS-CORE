# Lesson Engine — evidence-linked candidate lessons

The initial Lesson Engine stores candidate lessons linked to one or more
persisted Experience Engine records. It provides a review workflow, not an
automatic learning claim.

## Workflow

1. Inspect captured mission experiences in Studio.
2. A user or future synthesis component drafts a concise lesson with rationale,
   applicability boundaries, limitations, and one to twenty source experience IDs.
3. GENESIS verifies that every cited experience exists and preserves those IDs.
4. Submit the draft for human review.
5. A human may approve or reject the candidate. Approval means the lesson was
   accepted for the lesson library; it does not activate a skill or prove the
   statement universally true.

## Evidence and safety boundaries

- Lessons cannot be created without existing experience references.
- Source experience records are retained and returned with lesson details.
- The lesson statement, rationale, applicability, and limitations are separate
  fields so uncertainty is visible.
- An approved lesson is not a fact, skill, training example, or model-weight update.
- No skill is created or activated automatically.
- This first slice does not ask the model to certify its own observations. A
  later synthesis provider can draft candidates, but source validation and
  human review remain separate.

## API

- `GET /api/lessons?status=draft`
- `POST /api/lessons`
- `GET /api/lessons/{lesson_id}`
- `POST /api/lessons/{lesson_id}/submit`
- `POST /api/lessons/{lesson_id}/review`
