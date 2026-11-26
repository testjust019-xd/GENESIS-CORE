from types import SimpleNamespace

import pytest

from genesis_core.agent import ModelError
from genesis_core.multi_agent import MultiAgentEngine, MultiAgentError
from genesis_core.state import StateStore


class FakeAdapter:
    config = SimpleNamespace(provider="ollama", model="base-model")

    def __init__(self, outputs=None):
        self.outputs = list(outputs or ["research", "analysis", "plan", "review"])
        self.calls = []

    def chat(self, messages):
        self.calls.append(messages)
        return self.outputs.pop(0)


def test_collaboration_works_with_one_primary_model_and_persists_steps(tmp_path):
    store = StateStore(tmp_path / "genesis.db")
    adapter = FakeAdapter()
    engine = MultiAgentEngine(store, adapter)

    result = engine.collaborate("Design a small offline-first feature")

    assert result["execution"] == "sequential_single_model"
    assert result["independent_models_used"] is False
    assert result["provider"] == "ollama"
    assert [step["role"] for step in result["steps"]] == [
        "researcher", "analyst", "planner", "reviewer"
    ]
    assert len(adapter.calls) == 4
    assert "research" in adapter.calls[1][1]["content"]
    assert engine.get_run(result["run_id"])["status"] == "completed"
    assert len(engine.get_run(result["run_id"])["steps"]) == 4


def test_collaboration_allows_subset_of_roles(tmp_path):
    engine = MultiAgentEngine(StateStore(tmp_path / "genesis.db"), FakeAdapter(["plan"]))
    result = engine.collaborate("Make a plan", roles=["planner"])
    assert len(result["steps"]) == 1


@pytest.mark.parametrize("objective,roles", [
    ("", ["planner"]),
    ("valid", []),
    ("valid", ["unknown"]),
    ("valid", ["planner", "planner"]),
    ("x" * 12001, ["planner"]),
    ("valid", ["planner", "analyst", "reviewer", "researcher", "planner"]),
])
def test_collaboration_rejects_invalid_requests(tmp_path, objective, roles):
    engine = MultiAgentEngine(StateStore(tmp_path / "genesis.db"), FakeAdapter())
    with pytest.raises(MultiAgentError):
        engine.collaborate(objective, roles)


def test_model_failure_marks_run_failed(tmp_path):
    class BrokenAdapter(FakeAdapter):
        def chat(self, messages):
            raise ModelError("offline")

    engine = MultiAgentEngine(StateStore(tmp_path / "genesis.db"), BrokenAdapter())
    with pytest.raises(ModelError):
        engine.collaborate("Test outage", roles=["analyst"])
    assert engine.list_runs()[0]["status"] == "failed"


@pytest.mark.parametrize("title,instructions,expected", [
    ("Research options", "Gather useful source material", "researcher"),
    ("Compare approaches", "Analyze constraints and trade-offs", "analyst"),
    ("Design architecture", "Create a practical outline", "planner"),
    ("Verify output", "Review and validate the result", "reviewer"),
    ("Implement feature", "Carry out the requested work", "executor"),
])
def test_task_specialist_routing_is_deterministic(title, instructions, expected):
    selected = MultiAgentEngine.specialist_for_task(title, instructions)
    assert selected["id"] == expected
    assert selected["label"]
    assert selected["instruction"]
