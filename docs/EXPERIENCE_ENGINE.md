# Experience Engine — initial foundation

The Experience Engine records what GENESIS actually attempted and what its
mission observer concluded. It is the first durable input to an experience-led
improvement loop.

## What is captured

Each mission task attempt stores:

- mission and task identifiers;
- objective, task instructions and task title;
- the executor's recorded result;
- the observer's evidence summary and outcome;
- a neutral, uncalibrated confidence placeholder and capture timestamp.

Records are local SQLite data and can be listed by outcome or review status.
The initial lifecycle is `captured → reviewed → archived`.

## Important boundaries

- A captured result is an experience record, not automatically a verified fact.
- The observer is the configured model, not an independent external auditor.
- The initial confidence value is a neutral placeholder, not a calibrated probability.\n- A completed task does not prove that the strategy generalizes to other tasks.
- Experiences are not automatically promoted into semantic/procedural memory.
- They are not automatically converted into training data or model updates.
- Future skill proposals must be evaluated against reproducible tests before activation.

The initial implementation deliberately stores evidence first. Later work can
add lesson synthesis, deduplication, retrieval, user review UI and benchmark
evaluation without silently changing the meaning of existing records.
