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


def test_completed_mission_can_be_captured_as_idempotent_episode(tmp_path):
    from genesis_core.missions import MissionStore

    state = StateStore(tmp_path / "genesis.db")
    missions = MissionStore(state)
    memory = MemoryStore(state)
    mission = missions.create("Build a verified report", "Collect and verify project findings.")
    session = state.create_session("Mission: Build a verified report")
    tasks = missions.save_plan(mission["id"], session["id"], [
        {"title": "Inspect sources", "instructions": "Review source material."},
        {"title": "Check findings", "instructions": "Verify the findings."},
    ])
    missions.set_task_status(tasks[0]["id"], "completed", "Reviewed the repository. Observer: confirmed.")
    missions.set_task_status(tasks[1]["id"], "completed", "Cross-checked the results. Observer: confirmed.")
    missions.set_status(mission["id"], "running")
    missions.set_status(mission["id"], "completed")

    saved = memory.capture_completed_mission(missions, mission["id"])
    repeated = memory.capture_completed_mission(missions, mission["id"])

    assert saved["id"] == repeated["id"]
    assert saved["memory_type"] == "episodic"
    assert saved["source_type"] == "mission"
    assert saved["source_ref"] == f"mission:{mission['id']}"
    assert "Inspect sources" in saved["content"]
    assert "Observer: confirmed" in saved["content"]


def test_incomplete_mission_cannot_be_captured(tmp_path):
    from genesis_core.missions import MissionStore

    state = StateStore(tmp_path / "genesis.db")
    missions = MissionStore(state)
    memory = MemoryStore(state)
    mission = missions.create("Incomplete mission")
    session = state.create_session("Mission: Incomplete mission")
    tasks = missions.save_plan(mission["id"], session["id"], [
        {"title": "First step", "instructions": "Do the first step."}
    ])

    with pytest.raises(MemoryError, match="Only completed missions"):
        memory.capture_completed_mission(missions, mission["id"])

    missions.set_status(mission["id"], "running")
    missions.set_task_status(tasks[0]["id"], "blocked", "Needs review.")
    missions.set_status(mission["id"], "blocked")
    with pytest.raises(MemoryError, match="Only completed missions"):
        memory.capture_completed_mission(missions, mission["id"])

