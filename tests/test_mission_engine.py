import json
from types import SimpleNamespace

import pytest

from genesis_core.agent import AgentRuntime
from genesis_core.mission_engine import MissionEngine, MissionEngineError
from genesis_core.missions import MissionStore
from genesis_core.state import StateStore


class ScriptedAdapter:
    config = SimpleNamespace(provider="test", model="scripted")

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages):
        self.calls.append(messages)
        return self.replies.pop(0)


def test_mission_plan_is_persisted_and_steps_run_one_at_a_time(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    missions = MissionStore(state)
    mission = missions.create("Prepare project report", "Research the project and write a report.")
    adapter = ScriptedAdapter([
        json.dumps({"tasks": [
            {"title": "Inspect project", "instructions": "Review the project structure."},
            {"title": "Summarise findings", "instructions": "Write a concise summary."},
        ]}),
        "The project contains a CLI and a web interface.",
        json.dumps({"status": "completed", "summary": "The project structure was inspected."}),
        "The report summary is ready.",
        json.dumps({"status": "completed", "summary": "The report summary is present."}),
    ])
    agent = AgentRuntime(store=state, adapter=adapter)
    engine = MissionEngine(state, missions, agent)

    plan = engine.plan(mission["id"])
    assert plan["created"] is True
    assert len(plan["tasks"]) == 2
    assert plan["mission"]["session_id"]

    first = engine.run_next(mission["id"])
    assert first["task"]["status"] == "completed"
    assert first["mission"]["status"] == "running"
    assert missions.list_tasks(mission["id"])[1]["status"] == "planned"

    second = engine.run_next(mission["id"])
    assert second["task"]["status"] == "completed"
    assert second["mission"]["status"] == "completed"
    assert [task["status"] for task in missions.list_tasks(mission["id"])] == [
        "completed", "completed"
    ]


def test_mission_plan_is_not_overwritten(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    missions = MissionStore(state)
    mission = missions.create("Plan once")
    session = state.create_session("Mission: Plan once")
    missions.save_plan(mission["id"], session["id"], [
        {"title": "One", "instructions": "Do one."}
    ])

    adapter = ScriptedAdapter([])
    engine = MissionEngine(state, missions, AgentRuntime(store=state, adapter=adapter))
    result = engine.plan(mission["id"])

    assert result["created"] is False
    assert len(result["tasks"]) == 1
    assert adapter.calls == []


def test_invalid_planner_output_is_not_saved(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    missions = MissionStore(state)
    mission = missions.create("Invalid plan")
    adapter = ScriptedAdapter(["not json"])
    engine = MissionEngine(state, missions, AgentRuntime(store=state, adapter=adapter))

    with pytest.raises(MissionEngineError):
        engine.plan(mission["id"])
    assert missions.list_tasks(mission["id"]) == []


def test_mission_task_limit_is_enforced(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    missions = MissionStore(state)
    mission = missions.create("Too many tasks")
    adapter = ScriptedAdapter([
        json.dumps({"tasks": [
            {"title": f"Task {i}", "instructions": "Do a small step."}
            for i in range(9)
        ]})
    ])
    engine = MissionEngine(state, missions, AgentRuntime(store=state, adapter=adapter))

    with pytest.raises(MissionEngineError):
        engine.plan(mission["id"])
    assert missions.list_tasks(mission["id"]) == []

def test_observer_blocks_unverified_task_completion(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    missions = MissionStore(state)
    mission = missions.create("Research uncertain topic")
    adapter = ScriptedAdapter([
        json.dumps({"tasks": [
            {"title": "Verify claim", "instructions": "Find reliable evidence for the claim."}
        ]}),
        "I could not access reliable sources.",
        json.dumps({"status": "blocked", "summary": "No reliable evidence was available."}),
    ])
    engine = MissionEngine(state, missions, AgentRuntime(store=state, adapter=adapter))

    result = engine.run_next(mission["id"])

    assert result["task"]["status"] == "blocked"
    assert result["mission"]["status"] == "blocked"
    assert "No reliable evidence" in result["observation"]["summary"]


def test_invalid_observer_output_fails_closed(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    missions = MissionStore(state)
    mission = missions.create("Unverified task")
    adapter = ScriptedAdapter([
        json.dumps({"tasks": [
            {"title": "Check result", "instructions": "Check the result."}
        ]}),
        "Done.",
        "not-json",
    ])
    engine = MissionEngine(state, missions, AgentRuntime(store=state, adapter=adapter))

    result = engine.run_next(mission["id"])

    assert result["task"]["status"] == "blocked"
    assert result["mission"]["status"] == "blocked"
