from types import SimpleNamespace

from genesis_core.agent import AgentRuntime
from genesis_core.state import StateStore


class FakeAdapter:
    config = SimpleNamespace(provider="fake-local", model="test-model")

    def __init__(self):
        self.seen_messages = []

    def chat(self, messages):
        self.seen_messages = messages
        return "Hello from the GENESIS test model."


def test_agent_persists_user_and_assistant_messages(tmp_path):
    store = StateStore(tmp_path / "genesis.db")
    session = store.create_session()
    adapter = FakeAdapter()
    runtime = AgentRuntime(store=store, adapter=adapter)

    reply = runtime.chat(session["id"], "Hello GENESIS")

    assert reply.provider == "fake-local"
    assert reply.model == "test-model"
    assert reply.assistant_message["content"] == "Hello from the GENESIS test model."
    messages = store.list_messages(session["id"])
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "Hello GENESIS"


def test_agent_includes_recent_conversation_context(tmp_path):
    store = StateStore(tmp_path / "genesis.db")
    session = store.create_session()
    store.add_message(session["id"], "user", "Earlier context")
    store.add_message(session["id"], "assistant", "Earlier answer")
    adapter = FakeAdapter()

    AgentRuntime(store=store, adapter=adapter).chat(session["id"], "Continue")

    assert adapter.seen_messages[0]["role"] == "system"
    assert adapter.seen_messages[-3]["content"] == "Earlier context"
    assert adapter.seen_messages[-2]["content"] == "Earlier answer"
    assert adapter.seen_messages[-1]["content"] == "Continue"



def test_agent_injects_relevant_managed_memory(tmp_path):
    from genesis_core.memory import MemoryStore

    store = StateStore(tmp_path / "genesis.db")
    session = store.create_session()
    memories = MemoryStore(store)
    memories.add(
        "semantic", "The GENESIS workspace is stored in SQLite.",
        source_type="user", source_ref="manual note", confidence=0.9,
    )
    adapter = FakeAdapter()

    AgentRuntime(store=store, adapter=adapter, memory_store=memories).chat(
        session["id"], "Where is the GENESIS workspace stored?"
    )

    recalled = [m["content"] for m in adapter.seen_messages if "RECALLED GENESIS MEMORY" in m["content"]]
    assert len(recalled) == 1
    assert "stored in SQLite" in recalled[0]
    assert "manual note" in recalled[0]


def test_agent_injects_relevant_local_knowledge_with_citation(tmp_path):
    from genesis_core.knowledge import KnowledgeStore

    store = StateStore(tmp_path / "genesis.db")
    session = store.create_session()
    knowledge = KnowledgeStore(store)
    knowledge.ingest_text(
        "GENESIS architecture",
        "GENESIS uses SQLite to store persistent local conversation state.",
        "docs/architecture.md",
    )
    adapter = FakeAdapter()

    AgentRuntime(store=store, adapter=adapter, knowledge_store=knowledge).chat(
        session["id"], "How does GENESIS store local conversation state?"
    )

    recalled = [
        m["content"] for m in adapter.seen_messages
        if "RETRIEVED GENESIS KNOWLEDGE" in m["content"]
    ]
    assert len(recalled) == 1
    assert "SQLite" in recalled[0]
    assert "docs/architecture.md" in recalled[0]
    assert "chunk" in recalled[0]
