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

def test_interrupted_running_task_can_be_resumed(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    missions = MissionStore(state)
    mission = missions.create("Resume interrupted task")
    session = state.create_session("Mission: Resume interrupted task")
    tasks = missions.save_plan(mission["id"], session["id"], [
        {"title": "Continue work", "instructions": "Continue the interrupted step."}
    ])
    missions.set_status(mission["id"], "running")
    missions.set_task_status(tasks[0]["id"], "running")
    adapter = ScriptedAdapter([
        "The remaining work is complete.",
        json.dumps({"status": "completed", "summary": "The remaining work was verified."}),
    ])
    engine = MissionEngine(state, missions, AgentRuntime(store=state, adapter=adapter))

    result = engine.run_next(mission["id"])

    assert result["task"]["status"] == "completed"
    assert "interrupted during a previous run" in adapter.calls[0][-1]["content"]
    assert result["mission"]["status"] == "completed"


def test_adaptive_replan_preserves_completed_work_and_records_history(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    missions = MissionStore(state)
    mission = missions.create("Prepare a launch report", "Prepare a verified launch report.")
    session = state.create_session("Mission: launch report")
    original = missions.save_plan(mission["id"], session["id"], [
        {"title": "Collect data", "instructions": "Collect available data."},
        {"title": "Access private dashboard", "instructions": "Inspect the private dashboard."},
        {"title": "Write report", "instructions": "Write the report."},
    ], metadata={"success_criteria": ["Report cites evidence"]})
    missions.set_status(mission["id"], "running")
    missions.set_task_status(original[0]["id"], "completed", "Collected public release notes.")
    missions.set_task_status(original[1]["id"], "blocked", "Dashboard access is unavailable.")
    missions.set_status(mission["id"], "blocked")

    revised_document = {
        "summary": "Use public sources instead of the unavailable dashboard.",
        "success_criteria": ["Report cites public sources"],
        "assumptions": ["Public release notes are sufficient"],
        "risks": ["Some private metrics will be unavailable"],
        "tasks": [
            {"title": "Cross-check public sources", "instructions": "Compare official public sources."},
            {"title": "Write evidence-based report", "instructions": "Write the report and note limitations."},
        ],
    }
    adapter = ScriptedAdapter([json.dumps(revised_document)])
    engine = MissionEngine(state, missions, AgentRuntime(store=state, adapter=adapter))

    result = engine.replan(mission["id"], reason="Use only accessible public information.")

    assert result["replanned"] is True
    assert result["preserved_completed"] == 1
    assert result["tasks"][0]["id"] == original[0]["id"]
    assert result["tasks"][0]["status"] == "completed"
    assert [item["title"] for item in result["tasks"][1:]] == [
        "Cross-check public sources", "Write evidence-based report"
    ]
    history = engine.plan_history(mission["id"])
    assert len(history) == 2
    assert history[0]["version"] == 1
    assert history[1]["version"] == 2
    assert history[1]["plan"]["tasks"][0]["title"] == "Cross-check public sources"
    assert "Dashboard access is unavailable" in history[1]["plan"]["supersedes"]["tasks"][1]["result"]
    assert "Collected public release notes" in adapter.calls[0][-1]["content"]


def test_replan_requires_blocked_mission_and_keeps_old_plan_on_invalid_output(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    missions = MissionStore(state)
    mission = missions.create("Blocked objective")
    session = state.create_session("Mission: blocked objective")
    tasks = missions.save_plan(mission["id"], session["id"], [
        {"title": "First", "instructions": "Do first."}
    ])
    missions.set_status(mission["id"], "running")
    missions.set_task_status(tasks[0]["id"], "blocked", "A dependency is unavailable.")
    missions.set_status(mission["id"], "blocked")
    adapter = ScriptedAdapter(["not valid JSON"])
    engine = MissionEngine(state, missions, AgentRuntime(store=state, adapter=adapter))

    with pytest.raises(MissionEngineError):
        engine.replan(mission["id"])
    assert missions.list_tasks(mission["id"])[0]["id"] == tasks[0]["id"]
    assert len(engine.plan_history(mission["id"])) == 1

    missions.set_status(mission["id"], "running")
    with pytest.raises(MissionEngineError):
        engine.replan(mission["id"])

def test_mission_planning_uses_analyst_and_planner_specialists_with_one_model(tmp_path):
    from genesis_core.multi_agent import MultiAgentEngine

    state = StateStore(tmp_path / "genesis.db")
    missions = MissionStore(state)
    mission = missions.create("Specialist-planned mission", "Prepare a concise report.")
    plan_json = json.dumps({
        "summary": "A specialist-reviewed plan",
        "success_criteria": ["Report is complete"],
        "assumptions": [],
        "risks": [],
        "tasks": [{"title": "Draft report", "instructions": "Prepare the report."}],
    })
    adapter = ScriptedAdapter(["Identify constraints and missing context.", plan_json])
    agent = AgentRuntime(store=state, adapter=adapter)
    specialists = MultiAgentEngine(state, adapter=adapter)
    engine = MissionEngine(state, missions, agent, multi_agent=specialists)

    result = engine.plan(mission["id"])

    assert result["created"] is True
    assert result["specialists"] == ["analyst", "planner"]
    assert result["specialist_run_id"]
    assert len(adapter.calls) == 2
    assert "Identify constraints" in adapter.calls[1][1]["content"]
    assert result["tasks"][0]["title"] == "Draft report"


def test_mission_planning_without_multi_agent_keeps_legacy_single_pass(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    missions = MissionStore(state)
    mission = missions.create("Single pass mission")
    plan_json = json.dumps({
        "tasks": [{"title": "One step", "instructions": "Do one step."}]
    })
    adapter = ScriptedAdapter([plan_json])
    engine = MissionEngine(state, missions, AgentRuntime(store=state, adapter=adapter))

    result = engine.plan(mission["id"])

    assert result["created"] is True
    assert result["specialists"] == []
    assert len(adapter.calls) == 1


def test_adaptive_replanning_uses_analyst_and_planner_specialists(tmp_path):
    from genesis_core.multi_agent import MultiAgentEngine

    state = StateStore(tmp_path / "genesis.db")
    missions = MissionStore(state)
    mission = missions.create("Specialist replan", "Prepare a report.")
    session = state.create_session("Mission: Specialist replan")
    tasks = missions.save_plan(mission["id"], session["id"], [
        {"title": "Blocked access", "instructions": "Access unavailable data."}
    ])
    missions.set_status(mission["id"], "running")
    missions.set_task_status(tasks[0]["id"], "blocked", "The data source is unavailable.")
    missions.set_status(mission["id"], "blocked")
    revised_json = json.dumps({
        "summary": "Use accessible sources",
        "success_criteria": ["Report documents limitations"],
        "assumptions": [],
        "risks": ["Some data is unavailable"],
        "tasks": [{"title": "Use public data", "instructions": "Use verified public sources."}],
    })
    adapter = ScriptedAdapter(["Identify a public alternative.", revised_json])
    agent = AgentRuntime(store=state, adapter=adapter)
    engine = MissionEngine(
        state, missions, agent, multi_agent=MultiAgentEngine(state, adapter=adapter)
    )

    result = engine.replan(mission["id"], reason="Avoid unavailable data.")

    assert result["replanned"] is True
    assert result["specialists"] == ["analyst", "planner"]
    assert result["specialist_run_id"]
    assert len(adapter.calls) == 2
    assert "public alternative" in adapter.calls[1][1]["content"]


def test_mission_execution_uses_task_specialist_and_keeps_runtime_permissions(tmp_path):
    from genesis_core.multi_agent import MultiAgentEngine

    state = StateStore(tmp_path / "genesis.db")
    missions = MissionStore(state)
    mission = missions.create("Research a topic", "Collect and summarize reliable sources.")
    session = state.create_session("Mission: Research a topic")
    task = missions.save_plan(mission["id"], session["id"], [
        {"title": "Research available sources", "instructions": "Gather relevant sources and summarize evidence."}
    ])[0]
    adapter = ScriptedAdapter([
        "I gathered the available source material and summarized its evidence and gaps.",
        json.dumps({"status": "completed", "summary": "The source summary is present and limitations are stated."}),
    ])
    agent = AgentRuntime(store=state, adapter=adapter)
    engine = MissionEngine(state, missions, agent, multi_agent=MultiAgentEngine(state, adapter=adapter))

    result = engine.run_next(mission["id"])

    assert result["specialist"] == "researcher"
    assert "SPECIALIST ROLE: Researcher" in adapter.calls[0][-1]["content"]
    assert result["task"]["status"] == "completed"
    assert result["task"]["result"].startswith("[Specialist: researcher]")
