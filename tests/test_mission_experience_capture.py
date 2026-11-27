from __future__ import annotations

import json
from types import SimpleNamespace

from genesis_core.agent import AgentRuntime
from genesis_core.mission_engine import MissionEngine
from genesis_core.missions import MissionStore
from genesis_core.state import StateStore


class ScriptedAdapter:
    config = SimpleNamespace(provider="test", model="scripted")

    def __init__(self, replies):
        self.replies = list(replies)

    def chat(self, messages):
        return self.replies.pop(0)


def test_mission_task_outcome_is_captured_as_experience(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    missions = MissionStore(state)
    mission = missions.create("Verify a small task", "Verify a small task.")
    adapter = ScriptedAdapter([
        json.dumps({"tasks": [
            {"title": "Check a result", "instructions": "Check the supplied result."}
        ]}),
        "The result was checked and matches the expected value.",
        json.dumps({
            "status": "completed",
            "summary": "The result matches the stated verification condition.",
        }),
    ])
    engine = MissionEngine(
        state, missions, AgentRuntime(store=state, adapter=adapter)
    )

    result = engine.run_next(mission["id"])

    experience = engine.experiences.get(result["experience_id"])
    assert experience is not None
    assert experience["mission_id"] == mission["id"]
    assert experience["task_id"] == result["task"]["id"]
    assert experience["outcome"] == "completed"
    assert experience["status"] == "captured"
    assert experience["confidence"] == 0.5
