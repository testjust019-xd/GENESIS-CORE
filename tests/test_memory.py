import pytest

from genesis_core.memory import MemoryError, MemoryStore
from genesis_core.state import StateStore


def test_memory_records_persist_with_provenance(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    memory = MemoryStore(state)
    saved = memory.add(
        "semantic", "GENESIS uses SQLite for local persistence.",
        source_type="user", source_ref="architecture discussion", confidence=0.95,
    )

    reopened = MemoryStore(StateStore(tmp_path / "genesis.db"))
    loaded = reopened.get(saved["id"])
    assert loaded["content"] == saved["content"]
    assert loaded["source_type"] == "user"
    assert loaded["source_ref"] == "architecture discussion"
    assert loaded["confidence"] == 0.95


def test_search_returns_relevant_active_memories_only(tmp_path):
    memory = MemoryStore(StateStore(tmp_path / "genesis.db"))
    relevant = memory.add("procedural", "Run pytest before publishing changes.")
    memory.add("semantic", "The project uses SQLite.")
    memory.set_status(relevant["id"], "inactive")

    assert memory.search("pytest publishing") == []


def test_search_matches_memory_content(tmp_path):
    memory = MemoryStore(StateStore(tmp_path / "genesis.db"))
    saved = memory.add("episodic", "The mission completed after validating three tests.")

    results = memory.search("mission validating")
    assert [item["id"] for item in results] == [saved["id"]]


def test_memory_can_be_deactivated_and_deleted(tmp_path):
    memory = MemoryStore(StateStore(tmp_path / "genesis.db"))
    saved = memory.add("semantic", "A remembered fact.")
    assert memory.set_status(saved["id"], "inactive")["status"] == "inactive"
    memory.delete(saved["id"])
    assert memory.get(saved["id"]) is None


@pytest.mark.parametrize("kwargs", [
    {"memory_type": "unknown", "content": "x"},
    {"memory_type": "semantic", "content": ""},
    {"memory_type": "semantic", "content": "valid", "confidence": 1.5},
    {"memory_type": "semantic", "content": "valid", "source_type": ""},
])
def test_invalid_memory_is_rejected(tmp_path, kwargs):
    memory = MemoryStore(StateStore(tmp_path / "genesis.db"))
    with pytest.raises(MemoryError):
        memory.add(**kwargs)
