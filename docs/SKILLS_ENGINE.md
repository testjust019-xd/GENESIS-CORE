# Skills Engine (initial)

GENESIS skills are declarative, versioned instruction modules. They do not contain
Python, shell commands, plugins, or executable hooks. A skill can list existing
registered tool names as its intended tool scope, but this list does not grant
permissions or bypass the ToolRegistry / PermissionManager.

## Lifecycle

1. Create a draft with a name, description, instructions, tool-name allowlist and
   human-readable review checklist.
2. Submit it for review. It becomes pending and is not used by the agent.
3. A user explicitly approves or rejects it. Only approved skills become active.
4. Active skills can be disabled. Editing requires disabling first and creates a
   new immutable version snapshot; edited content returns to draft review.

Imported manifests always become drafts. Their claimed status is ignored. No
external skill code is loaded or executed.

## TUI

- \`/skills list [draft|pending|active|disabled]\`
- \`/skill create <name> | <description> | <instructions>\`
- \`/skill submit <id>\`
- \`/skill review <id> approve|reject\`
- \`/skill disable <id>\`
- \`/skill versions <id>\`

The create command supplies a minimal default checklist. Studio exposes the full
manifest fields through its API.

## API

- \`GET /api/skills?status=active\`
- \`POST /api/skills\`
- \`GET /api/skills/{skill_id}\`
- \`PUT /api/skills/{skill_id}\`
- \`POST /api/skills/{skill_id}/submit\`
- \`POST /api/skills/{skill_id}/review\`
- \`POST /api/skills/{skill_id}/disable\`
- \`GET /api/skills/{skill_id}/versions\`
- \`GET /api/skills/{skill_id}/export\`
- \`POST /api/skills/import\`

The first implementation uses lexical relevance to include up to three active
skills in the agent context. Skills are context guidance, not guaranteed model
compliance. Their tool lists are descriptive only; the existing tool executor
continues to enforce actual registered tools and permissions.
