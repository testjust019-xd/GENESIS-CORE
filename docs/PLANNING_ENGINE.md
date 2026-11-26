# Planning Engine (initial adaptive planning)

The Planning Engine builds on the persistent MissionStore and the existing bounded
planner / executor / observer loop.

## Structured initial plans

The model returns JSON containing:
- \`summary\`: the intended approach;
- \`success_criteria\`: observable conditions for completion;
- \`assumptions\`: assumptions the plan depends on;
- \`risks\`: known risks or limitations;
- \`tasks\`: 1–8 ordered, focused steps with verifiable instructions.

The store keeps a plan revision snapshot in SQLite. Existing missions and task
records are migrated in place; no external dependency is added.

## Adaptive replanning

When a task is blocked, GENESIS does not silently discard it or automatically
retry a possibly unsafe action. The user can request a revised plan:

- TUI: \`/mission replan <id> [reason]\`
- Studio: \`POST /api/missions/{id}/replan\` with optional JSON \`{"reason":"..." }\`

The planner receives completed task results, blocked task evidence, remaining
work, the objective and relevant active skills. Mission data and skill text are
untrusted context and cannot grant tools or permissions.

The revised plan:
1. archives the previous task state in plan history;
2. preserves completed task rows and their evidence;
3. replaces only blocked / unfinished work with new planned tasks;
4. leaves the mission blocked until the next explicit run action.

Plan history:
- TUI: \`/mission history <id>\`
- Studio: \`GET /api/missions/{id}/plan-history\`

Invalid model output or a failed planning call leaves the current plan untouched.
Replanning is explicit and user-triggered. Execution still advances at most one
task per run call and completion still requires the observer's evidence-based
confirmation.

## Current boundaries

This is an initial adaptive planner, not a general optimizer. It does not yet
schedule independent tasks in parallel, calculate reliable time/cost estimates,
or autonomously retry blocked work. Task ordering remains sequential.
