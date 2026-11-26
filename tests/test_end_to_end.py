from types import SimpleNamespace

from genesis_core.agent import AgentRuntime
from genesis_core.knowledge import KnowledgeStore
from genesis_core.memory import MemoryStore
from genesis_core.research import ResearchEngine
from genesis_core.state import StateStore


class FakeConversationAdapter:
    config = SimpleNamespace(provider="mock-local", model="integration-model")

    def __init__(self):
        self.messages = []

    def chat(self, messages):
        self.messages = messages
        return "A grounded response from the integration test model."


class FakeSearchProvider:
    name = "mock-search"

    def search(self, query, limit=8):
        return [{
            "title": "GENESIS local architecture",
            "url": "https://example.org/genesis-architecture",
            "snippet": "GENESIS stores persistent state in SQLite.",
            "published_at": None,
            "provider": self.name,
        }][:limit]


def test_local_conversation_uses_persisted_memory_and_knowledge_with_research(tmp_path):
    state = StateStore(tmp_path / "integration.db")
    session = state.create_session("Integrated workflow")
    memories = MemoryStore(state)
    knowledge = KnowledgeStore(state)
    memories.add(
        "semantic",
        "The test workspace uses SQLite for persistent state.",
        source_type="user",
        source_ref="integration fixture",
        confidence=0.95,
    )
    knowledge.ingest_text(
        "GENESIS design notes",
        "GENESIS is local-first and stores its conversation state in SQLite.",
        "docs/design.md",
    )

    research = ResearchEngine(state=state, knowledge=knowledge, provider=FakeSearchProvider())
    run = research.search("GENESIS persistence")
    assert run["source_count"] == 1
    source = run["sources"][0]
    approved = research.review_source(source["id"], "approved", "Reviewed in integration test.")
    assert approved["review_status"] == "approved"

    adapter = FakeConversationAdapter()
    runtime = AgentRuntime(
        store=state,
        adapter=adapter,
        memory_store=memories,
        knowledge_store=knowledge,
    )
    reply = runtime.chat(session["id"], "Where is the workspace state stored?")

    system_context = "\n".join(
        item["content"] for item in adapter.messages if item["role"] == "system"
    )
    assert "RECALLED GENESIS MEMORY" in system_context
    assert "integration fixture" in system_context
    assert "RETRIEVED GENESIS KNOWLEDGE" in system_context
    assert "docs/design.md" in system_context
    assert reply.assistant_message["content"] == "A grounded response from the integration test model."

    persisted = state.list_messages(session["id"])
    assert [item["role"] for item in persisted] == ["user", "assistant"]
    assert persisted[-1]["content"] == reply.assistant_message["content"]
