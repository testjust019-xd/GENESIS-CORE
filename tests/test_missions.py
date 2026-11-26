import pytest

from genesis_core.missions import MissionError, MissionStore
from genesis_core.state import StateStore


def test_missions_persist_and_sort_by_priority(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    missions = MissionStore(state)
    low = missions.create("Low priority", priority=5)
    high = missions.create("Urgent task", priority=1)

    reopened = MissionStore(StateStore(tmp_path / "genesis.db"))
    items = reopened.list()

    assert [item["id"] for item in items] == [high["id"], low["id"]]


def test_mission_status_transitions(tmp_path):
    missions = MissionStore(StateStore(tmp_path / "genesis.db"))
    mission = missions.create("Research Godot")
    running = missions.set_status(mission["id"], "running")
    blocked = missions.set_status(mission["id"], "blocked")
    resumed = missions.set_status(mission["id"], "running")
    completed = missions.set_status(mission["id"], "completed")

    assert running["status"] == "running"
    assert blocked["status"] == "blocked"
    assert resumed["status"] == "running"
    assert completed["status"] == "completed"


def test_completed_mission_cannot_be_reopened(tmp_path):
    missions = MissionStore(StateStore(tmp_path / "genesis.db"))
    mission = missions.create("Finished task")
    missions.set_status(mission["id"], "running")
    missions.set_status(mission["id"], "completed")

    with pytest.raises(MissionError):
        missions.set_status(mission["id"], "running")


def test_mission_validation(tmp_path):
    missions = MissionStore(StateStore(tmp_path / "genesis.db"))
    with pytest.raises(MissionError):
        missions.create("   ")
    with pytest.raises(MissionError):
        missions.create("Bad priority", priority=9)
