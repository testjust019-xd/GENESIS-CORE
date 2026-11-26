import json

import pytest

from genesis_core.conversation_memory import (
    ConversationMemoryEngine, ConversationMemoryError,
)
from genesis_core.memory import MemoryStore
from genesis_core.state import StateStore


class FakeAdapter:
    def __init__(self, response):
        self.response = response

    def chat(self, messages):
        self.messages = messages
        return self.response


def make_session(state):
    session = state.create_session("Project planning")
    state.add_message(session["id"], "user", "I prefer Python for my local-first projects.")
    state.add_message(session["id"], "assistant", "Python is a great choice.")
    state.add_message(session["id"], "user", "GENESIS must work offline and support Ollama.")
    return session


def test_extraction_creates_pending_candidates_only_with_exact_user_evidence(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    memories = MemoryStore(state)
    session = make_session(state)
    adapter = FakeAdapter(json.dumps({"candidates": [
        {
            "memory_type": "semantic",
            "content": "The user prefers Python for local-first projects.",
            "evidence": "I prefer Python for my local-first projects.",
        },
        {
            "memory_type": "procedural",
            "content": "Assistant suggested a framework.",
            "evidence": "Python is a great choice.",
        },
        {
            "memory_type": "semantic",
            "content": "Unsupported preference.",
            "evidence": "I prefer Rust.",
        },
    ]}))
    engine = ConversationMemoryEngine(state, memories, adapter)

    candidates = engine.extract(session["id"])

    assert len(candidates) == 1
    assert candidates[0]["status"] == "pending"
    assert candidates[0]["source_message_ids"]
    assert memories.list() == []
    assert "USER messages" in adapter.messages[1]["content"]


def test_accepting_candidate_creates_provenance_aware_memory(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    memories = MemoryStore(state)
    session = make_session(state)
    adapter = FakeAdapter(json.dumps({"candidates": [{
        "memory_type": "semantic",
        "content": "GENESIS should support offline use and Ollama.",
        "evidence": "GENESIS must work offline and support Ollama.",
    }]}))
    engine = ConversationMemoryEngine(state, memories, adapter)
    candidate = engine.extract(session["id"])[0]

    reviewed = engine.decide(candidate["id"], "accept")

    assert reviewed["status"] == "accepted"
    assert reviewed["memory"]["source_type"] == "conversation"
    assert f"session:{session['id']}" in reviewed["memory"]["source_ref"]
    assert memories.get(reviewed["memory_id"])["content"] == candidate["content"]
    assert engine.decide(candidate["id"], "accept")["memory_id"] == reviewed["memory_id"]


def test_rejecting_candidate_never_creates_memory(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    memories = MemoryStore(state)
    session = make_session(state)
    adapter = FakeAdapter(json.dumps({"candidates": [{
        "memory_type": "episodic",
        "content": "A durable project decision.",
        "evidence": "GENESIS must work offline and support Ollama.",
    }]}))
    engine = ConversationMemoryEngine(state, memories, adapter)
    candidate = engine.extract(session["id"])[0]

    reviewed = engine.decide(candidate["id"], "reject")

    assert reviewed["status"] == "rejected"
    assert memories.list() == []


def test_invalid_model_json_fails_without_saving(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    memories = MemoryStore(state)
    session = make_session(state)
    engine = ConversationMemoryEngine(state, memories, FakeAdapter("not json"))

    with pytest.raises(ConversationMemoryError, match="invalid JSON"):
        engine.extract(session["id"])
    assert engine.list_candidates(status="all") == []
    assert memories.list() == []
