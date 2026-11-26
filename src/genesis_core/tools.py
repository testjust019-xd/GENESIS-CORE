"""Permission-aware tool registry and execution foundation for GENESIS CORE.

The initial built-ins are read-only and scoped to the GENESIS workspace.
No shell execution or arbitrary code evaluation is provided.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


class ToolError(RuntimeError):
    """Base error for tool registration and execution."""


class ToolValidationError(ToolError, ValueError):
    """Raised when tool arguments do not match their JSON schema."""


class ToolPermissionError(ToolError):
    """Raised when a tool is denied by the active permission profile."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]
    capabilities: frozenset[str] = field(default_factory=frozenset)
    risk: str = "read"
    timeout_seconds: int = 10


@dataclass(frozen=True)
class PermissionDecision:
    action: str
    reason: str


@dataclass(frozen=True)
class ToolResult:
    tool: str
    status: str
    output: Any = None
    approval_id: str | None = None
    reason: str | None = None


def validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> None:
    """Validate the intentionally small JSON Schema subset used by core tools."""
    if schema.get("type") != "object":
        raise ToolValidationError("Tool parameter schema must have type 'object'.")
    if not isinstance(arguments, dict):
        raise ToolValidationError("Tool arguments must be a JSON object.")

    properties = schema.get("properties", {})
    required = schema.get("required", [])
    if not isinstance(properties, dict) or not isinstance(required, list):
        raise ToolValidationError("Invalid tool schema definition.")
    missing = [key for key in required if key not in arguments]
    if missing:
        raise ToolValidationError(f"Missing required argument(s): {', '.join(missing)}")
    if schema.get("additionalProperties", False) is False:
        unknown = set(arguments) - set(properties)
        if unknown:
            raise ToolValidationError(f"Unknown argument(s): {', '.join(sorted(unknown))}")

    expected_types = {
        "string": str, "integer": int, "number": (int, float), "boolean": bool,
        "object": dict, "array": list,
    }
    for key, value in arguments.items():
        definition = properties.get(key)
        if definition is None:
            continue
        expected = expected_types.get(definition.get("type"))
        if expected and (not isinstance(value, expected) or (
            definition.get("type") == "integer" and isinstance(value, bool)
        )):
            raise ToolValidationError(f"Argument '{key}' must be {definition['type']}.")
        if isinstance(value, str):
            if len(value) > definition.get("maxLength", 10000):
                raise ToolValidationError(f"Argument '{key}' is too long.")
            if "enum" in definition and value not in definition["enum"]:
                raise ToolValidationError(f"Argument '{key}' must be one of: {definition['enum']}.")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if value < definition.get("minimum", float("-inf")):
                raise ToolValidationError(f"Argument '{key}' is below its minimum.")
            if value > definition.get("maximum", float("inf")):
                raise ToolValidationError(f"Argument '{key}' exceeds its maximum.")


class ToolRegistry:
    """In-memory registry; duplicate names are rejected to avoid silent overrides."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if not spec.name or not spec.name.replace("_", "").isalnum():
            raise ToolError("Tool names may contain only letters, numbers and underscores.")
        if spec.name in self._tools:
            raise ToolError(f"Tool already registered: {spec.name}")
        if spec.risk not in {"read", "write", "network", "system"}:
            raise ToolError(f"Unsupported risk category: {spec.risk}")
        if spec.timeout_seconds < 1 or spec.timeout_seconds > 300:
            raise ToolError("Tool timeout must be between 1 and 300 seconds.")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolError(f"Unknown tool: {name}") from exc

    def list(self) -> list[dict[str, Any]]:
        return [
            {"name": item.name, "description": item.description,
             "capabilities": sorted(item.capabilities), "risk": item.risk,
             "parameters": item.parameters}
            for item in sorted(self._tools.values(), key=lambda tool: tool.name)
        ]


class PermissionManager:
    """Fail-closed permission policy with explicit approval for elevated actions."""

    def __init__(self, profile: dict[str, Any] | None = None) -> None:
        self.profile = profile or {}

    def decide(self, spec: ToolSpec) -> PermissionDecision:
        if self.profile.get("deny_all", False):
            return PermissionDecision("deny", "All tool execution is disabled.")
        denied = set(self.profile.get("deny_capabilities", []))
        if spec.capabilities & denied:
            return PermissionDecision("deny", "A required capability is explicitly denied.")
        allowed = set(self.profile.get("allow_capabilities", ["workspace_read", "clock"]))
        if spec.risk == "read" and spec.capabilities <= allowed:
            return PermissionDecision("allow", "Read-only capability is allowed by profile.")
        approval = set(self.profile.get("approval_capabilities", []))
        if spec.capabilities & approval or spec.risk != "read":
            return PermissionDecision("approval_required", "This action requires user approval.")
        return PermissionDecision("deny", "No permission was granted for this capability.")


class ApprovalStore:
    """Durable approval queue sharing the GENESIS SQLite database."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS tool_approvals (
                    id TEXT PRIMARY KEY, tool_name TEXT NOT NULL, arguments TEXT NOT NULL,
                    status TEXT NOT NULL, reason TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                )
            """)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create(self, tool_name: str, arguments: dict[str, Any], reason: str) -> str:
        approval_id = uuid.uuid4().hex[:12]
        now = self._now()
        with sqlite3.connect(self.database_path) as db:
            db.execute(
                "INSERT INTO tool_approvals VALUES (?, ?, ?, 'pending', ?, ?, ?)",
                (approval_id, tool_name, json.dumps(arguments), reason, now, now),
            )
        return approval_id

    def get(self, approval_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.database_path) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM tool_approvals WHERE id = ?", (approval_id,)).fetchone()
        return dict(row) if row else None

    def list(self, status: str | None = "pending") -> list[dict[str, Any]]:
        with sqlite3.connect(self.database_path) as db:
            db.row_factory = sqlite3.Row
            if status is None:
                rows = db.execute("SELECT * FROM tool_approvals ORDER BY created_at").fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM tool_approvals WHERE status = ? ORDER BY created_at",
                    (status,),
                ).fetchall()
        return [dict(row) for row in rows]

    def decide(self, approval_id: str, approved: bool) -> dict[str, Any]:
        current = self.get(approval_id)
        if current is None:
            raise ToolError(f"Approval request not found: {approval_id}")
        if current["status"] != "pending":
            raise ToolError("Approval request has already been decided.")
        status = "approved" if approved else "rejected"
        with sqlite3.connect(self.database_path) as db:
            db.execute(
                "UPDATE tool_approvals SET status = ?, updated_at = ? WHERE id = ?",
                (status, self._now(), approval_id),
            )
        return self.get(approval_id) or current


class ToolExecutor:
    """Validates, authorizes and dispatches registered tools."""

    def __init__(
        self, registry: ToolRegistry, permissions: PermissionManager, approvals: ApprovalStore
    ) -> None:
        self.registry = registry
        self.permissions = permissions
        self.approvals = approvals

    def execute(
        self, name: str, arguments: dict[str, Any], approval_id: str | None = None
    ) -> ToolResult:
        spec = self.registry.get(name)
        validate_arguments(spec.parameters, arguments)
        decision = self.permissions.decide(spec)
        if decision.action == "deny":
            raise ToolPermissionError(decision.reason)
        if decision.action == "approval_required":
            if not approval_id:
                request_id = self.approvals.create(name, arguments, decision.reason)
                return ToolResult(name, "approval_required", approval_id=request_id,
                                  reason=decision.reason)
            request = self.approvals.get(approval_id)
            if not request or request["tool_name"] != name:
                raise ToolPermissionError("Approval does not match this tool.")
            if json.loads(request["arguments"]) != arguments:
                raise ToolPermissionError("Approval arguments do not match this request.")
            if request["status"] != "approved":
                raise ToolPermissionError(f"Approval is {request['status']}.")
        try:
            output = spec.handler(arguments)
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError(f"Tool '{name}' failed: {exc}") from exc
        return ToolResult(name, "completed", output=output)


def build_core_registry(workspace: str | Path) -> ToolRegistry:
    """Create safe built-ins; all filesystem access is confined to workspace."""
    root = Path(workspace).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    registry = ToolRegistry()

    registry.register(ToolSpec(
        name="time_now", description="Return the current UTC time.",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        handler=lambda _: {"utc": datetime.now(timezone.utc).isoformat()},
        capabilities=frozenset({"clock"}),
    ))

    registry.register(ToolSpec(
        name="workspace_list", description="List entries in a workspace directory.",
        parameters={"type": "object", "properties": {
            "path": {"type": "string", "maxLength": 500}},
            "additionalProperties": False},
        handler=lambda args: _list_workspace(root, args.get("path", ".")),
        capabilities=frozenset({"workspace_read"}),
    ))

    registry.register(ToolSpec(
        name="read_text_file", description="Read a UTF-8 text file inside the workspace (max 256 KB).",
        parameters={"type": "object", "properties": {
            "path": {"type": "string", "maxLength": 500}},
            "required": ["path"], "additionalProperties": False},
        handler=lambda args: _read_workspace_file(root, args["path"]),
        capabilities=frozenset({"workspace_read"}),
    ))
    return registry


def _safe_path(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise ToolPermissionError("Path escapes the GENESIS workspace.")
    return candidate


def _list_workspace(root: Path, relative: str) -> list[dict[str, str]]:
    directory = _safe_path(root, relative)
    if not directory.is_dir():
        raise ToolError("Workspace directory not found.")
    return [{"name": item.name, "type": "directory" if item.is_dir() else "file"}
            for item in sorted(directory.iterdir(), key=lambda entry: entry.name.lower())]


def _read_workspace_file(root: Path, relative: str) -> dict[str, str]:
    path = _safe_path(root, relative)
    if not path.is_file():
        raise ToolError("Workspace file not found.")
    if path.stat().st_size > 256 * 1024:
        raise ToolError("File exceeds the 256 KB read limit.")
    try:
        return {"path": relative, "content": path.read_text(encoding="utf-8")}
    except UnicodeDecodeError as exc:
        raise ToolError("File is not valid UTF-8 text.") from exc


__all__ = [
    "ApprovalStore", "PermissionDecision", "PermissionManager", "ToolError",
    "ToolExecutor", "ToolPermissionError", "ToolRegistry", "ToolResult",
    "ToolSpec", "ToolValidationError", "build_core_registry", "validate_arguments",
]
