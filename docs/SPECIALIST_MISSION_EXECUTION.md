# Specialist-routed mission execution — Initial

GENESIS can assign each mission task a specialist role before execution. The
selected role is a bounded instruction profile applied to the configured
primary model through the existing AgentRuntime.

## Role routing

Routing is deterministic and does not require an additional model call:

- Researcher: research, search, sources, collection and information gathering.
- Analyst: analysis, comparison, diagnosis and evaluation.
- Planner: planning, design, architecture and structuring.
- Reviewer: review, verification, audit, checks and tests.
- Executor: the default role for other task types.

The role is included in the task prompt and persisted with the task result.

## Important boundaries

- One configured base model is sufficient.
- Roles do not start separate model processes or download additional models.
- Execution still goes through AgentRuntime, ToolRegistry and PermissionManager.
- A role cannot grant itself tools, permissions or approvals.
- The existing mission observer independently checks whether the task result
  contains enough evidence to mark it complete.
- Execution remains one task per run call; no parallel task execution is added.
- This is role prompting and orchestration, not model-weight training.

The role router is intentionally lightweight and heuristic. Future evaluation
should measure routing quality before introducing model-based routing or
optional multi-provider collaboration.
