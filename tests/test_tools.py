import pytest

from genesis_core.tools import (
    ApprovalStore, PermissionManager, ToolError, ToolExecutor, ToolPermissionError,
    ToolRegistry, ToolSpec, ToolValidationError, build_core_registry, validate_arguments,
)


def test_registry_rejects_duplicate_and_unknown_tools():
    registry = ToolRegistry()
    spec = ToolSpec("sample", "Sample", {"type": "object", "properties": {}}, lambda _: {})
    registry.register(spec)
    with pytest.raises(ToolError):
        registry.register(spec)
    with pytest.raises(ToolError):
        registry.get("missing")


def test_schema_validation_checks_required_types_and_unknown_keys():
    schema = {"type": "object", "properties": {"name": {"type": "string"}},
              "required": ["name"], "additionalProperties": False}
    validate_arguments(schema, {"name": "GENESIS"})
    with pytest.raises(ToolValidationError):
        validate_arguments(schema, {})
    with pytest.raises(ToolValidationError):
        validate_arguments(schema, {"name": 42})
    with pytest.raises(ToolValidationError):
        validate_arguments(schema, {"name": "x", "extra": True})


def test_read_only_workspace_tools_are_scoped(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.txt").write_text("hello", encoding="utf-8")
    registry = build_core_registry(workspace)
    executor = ToolExecutor(registry, PermissionManager(), ApprovalStore(tmp_path / "state.db"))

    result = executor.execute("read_text_file", {"path": "notes.txt"})
    assert result.status == "completed"
    assert result.output["content"] == "hello"
    assert executor.execute("workspace_list", {}).output[0]["name"] == "notes.txt"

    with pytest.raises(ToolPermissionError):
        executor.execute("read_text_file", {"path": "../outside.txt"})


def test_approval_required_actions_are_persisted_and_gated(tmp_path):
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "write_note", "Write a note", {"type": "object", "properties": {}},
        lambda _: {"written": True}, capabilities=frozenset({"workspace_write"}), risk="write",
    ))
    approvals = ApprovalStore(tmp_path / "state.db")
    executor = ToolExecutor(
        registry, PermissionManager({"approval_capabilities": ["workspace_write"]}), approvals
    )

    pending = executor.execute("write_note", {})
    assert pending.status == "approval_required"
    assert approvals.get(pending.approval_id)["status"] == "pending"
    with pytest.raises(ToolPermissionError):
        executor.execute("write_note", {}, approval_id=pending.approval_id)

    approvals.decide(pending.approval_id, approved=True)
    result = executor.execute("write_note", {}, approval_id=pending.approval_id)
    assert result.output == {"written": True}
    assert approvals.get(pending.approval_id)["status"] == "used"
    with pytest.raises(ToolPermissionError):
        executor.execute("write_note", {}, approval_id=pending.approval_id)


def test_denied_capability_cannot_be_overridden_by_approval(tmp_path):
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "dangerous", "Denied", {"type": "object", "properties": {}}, lambda _: None,
        capabilities=frozenset({"shell"}), risk="system",
    ))
    executor = ToolExecutor(
        registry, PermissionManager({"deny_capabilities": ["shell"],
                                     "approval_capabilities": ["shell"]}),
        ApprovalStore(tmp_path / "state.db"),
    )
    with pytest.raises(ToolPermissionError):
        executor.execute("dangerous", {})
