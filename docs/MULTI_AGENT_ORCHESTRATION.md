# Multi-Agent Orchestration — Initial

GENESIS can delegate one objective to sequential specialist roles while using
only its configured primary model. Specialists are bounded role prompts
(Researcher, Analyst, Planner, Reviewer), not separate model downloads or
separate model processes.

## Design

- One primary model is sufficient; this is the default and supported path.
- The same configured adapter performs every specialist pass.
- Each specialist receives the objective and earlier specialist notes.
- Roles run sequentially to keep RAM and inference load predictable.
- Runs and each specialist output are persisted in the shared SQLite database.
- A failed model call marks the run failed and preserves completed steps.
- The feature does not grant tools to specialists. Existing ToolRegistry,
  PermissionManager and approval controls remain the only execution boundary.
- A Reviewer pass is a critique by the same model, not independent verification.
  A genuinely independent review can be configured later with an optional
  second provider/model, but is never required.

## API

- `GET /api/agents/roles` — available specialist roles.
- `POST /api/agents/collaborate` — body: `{"objective":"...", "roles":["researcher","analyst","planner","reviewer"]}`.
- `GET /api/agents/runs` — recent collaboration runs.
- `GET /api/agents/runs/{run_id}` — run and persisted specialist steps.

The default role sequence is Researcher → Analyst → Planner → Reviewer.
Clients may select one to four unique roles.

## Deliberate limits

This first slice is sequential and uses one model. It does not claim true
multi-model consensus, parallel execution, independent fact verification,
automatic model training, or unrestricted agent tool access. Optional
multi-provider routing and bounded parallelism can be added after resource
budgets and evaluation are in place.


## Mission integration

When the multi-agent engine is supplied to MissionEngine (as in Studio and
TUI), mission planning and adaptive replanning use two sequential specialist
passes: Analyst → Planner. The Analyst identifies constraints and assumptions;
the Planner produces the structured JSON plan required by the mission store.
Both passes use the same configured primary model, and the collaboration run
ID is returned with the plan result for traceability.

Task execution remains in the existing AgentRuntime so it can use the existing
ToolRegistry, permission checks, approval queue, conversation context and
activity events. The mission observer still checks execution results as a
separate pass of the same configured model; it is not described as
independent-model verification.

The integration is injectable and optional. A MissionEngine created without a
MultiAgentEngine retains its original single-pass planner behavior. No extra
model is downloaded or required.
