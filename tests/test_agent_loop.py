import json
from types import SimpleNamespace

from genesis_core.agent import AgentRuntime
from genesis_core.state import StateStore
from genesis_core.tools import (
    ApprovalStore, PermissionManager, ToolExecutor, ToolRegistry, ToolSpec,
    build_core_registry,
)


class ScriptedAdapter:
    config = SimpleNamespace(provider="fake-local", model="agent-test")

    def __init__(self, responses):
        self.responses = list(responses)
        self.seen_messages = []

    def chat(self, messages):
        self.seen_messages.append(list(messages))
        return self.responses.pop(0)


def test_agent_persists_user_and_assistant_messages(tmp_path):
    store = StateStore(tmp_path / "genesis.db")
    session = store.create_session()
    adapter = ScriptedAdapter(["Hello from the GENESIS test model."])
    runtime = AgentRuntime(store=store, adapter=adapter)

    reply = runtime.chat(session["id"], "Hello GENESIS")

    assert reply.provider == "fake-local"
    assert reply.model == "agent-test"
    assert reply.assistant_message["content"] == "Hello from the GENESIS test model."
    messages = store.list_messages(session["id"])
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "Hello GENESIS"


def test_agent_includes_recent_conversation_context(tmp_path):
    store = StateStore(tmp_path / "genesis.db")
    session = store.create_session()
    store.add_message(session["id"], "user", "Earlier context")
    store.add_message(session["id"], "assistant", "Earlier answer")
    adapter = ScriptedAdapter(["Continue answer"])

    AgentRuntime(store=store, adapter=adapter).chat(session["id"], "Continue")

    assert adapter.seen_messages[0][0]["role"] == "system"
    assert adapter.seen_messages[0][-3]["content"] == "Earlier context"
    assert adapter.seen_messages[0][-2]["content"] == "Earlier answer"
    assert adapter.seen_messages[0][-1]["content"] == "Continue"


def test_planner_executor_observer_runs_read_tool_then_summarises(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "facts.txt").write_text("The project has three modules.", encoding="utf-8")
    store = StateStore(tmp_path / "genesis.db")
    session = store.create_session()
    adapter = ScriptedAdapter([
        json.dumps({"action": "tool", "tool": "read_text_file",
                    "arguments": {"path": "facts.txt"}}),
        json.dumps({"action": "final", "message": "The project has three modules."}),
    ])
    executor = ToolExecutor(
        build_core_registry(workspace), PermissionManager(),
        ApprovalStore(store.database_path),
    )

    reply = AgentRuntime(store=store, adapter=adapter, tool_executor=executor).chat(
        session["id"], "How many modules?"
    )

    assert reply.assistant_message["content"] == "The project has three modules."
    assert [event["type"] for event in reply.activity] == ["tool"]
    assert reply.activity[0]["status"] == "completed"
    assert "OBSERVER" in adapter.seen_messages[1][-1]["content"]


def test_planner_cannot_execute_write_without_user_approval(tmp_path):
    store = StateStore(tmp_path / "genesis.db")
    session = store.create_session()
    calls = []
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "write_note", "Write a note",
        {"type": "object", "properties": {}, "additionalProperties": False},
        lambda _: calls.append("executed") or {"written": True},
        capabilities=frozenset({"workspace_write"}), risk="write",
    ))
    approvals = ApprovalStore(store.database_path)
    executor = ToolExecutor(
        registry, PermissionManager({"approval_capabilities": ["workspace_write"]}), approvals
    )
    adapter = ScriptedAdapter([
        json.dumps({"action": "tool", "tool": "write_note", "arguments": {}})
    ])

    reply = AgentRuntime(store=store, adapter=adapter, tool_executor=executor).chat(
        session["id"], "Save this note"
    )

    assert calls == []
    assert reply.activity[0]["status"] == "approval_required"
    assert approvals.get(reply.activity[0]["approval_id"])["status"] == "pending"
    assert "needs your approval" in reply.assistant_message["content"]


def test_agent_stops_repeated_tool_calls(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "facts.txt").write_text("A fact.", encoding="utf-8")
    store = StateStore(tmp_path / "genesis.db")
    session = store.create_session()
    repeated = json.dumps({"action": "tool", "tool": "read_text_file",
                           "arguments": {"path": "facts.txt"}})
    adapter = ScriptedAdapter([repeated, repeated])
    executor = ToolExecutor(
        build_core_registry(workspace), PermissionManager(),
        ApprovalStore(store.database_path),
    )

    reply = AgentRuntime(store=store, adapter=adapter, tool_executor=executor).chat(
        session["id"], "Read the same file"
    )

    assert reply.activity[-1]["type"] == "loop_guard"
    assert "repeated tool request" in reply.assistant_message["content"]
