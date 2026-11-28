from types import SimpleNamespace

import pytest

from genesis_core.evaluation import EvaluationEngine, validate_suite
from genesis_core.evolution_feedback import EvolutionFeedbackEngine, FeedbackError
from genesis_core.experience import ExperienceStore
from genesis_core.state import StateStore


class Adapter:
    config = SimpleNamespace(provider="fake", model="tiny")

    def __init__(self, answer):
        self.answer = answer

    def chat(self, messages):
        if isinstance(self.answer, dict):
            return self.answer.get(messages[-1]["content"], "wrong")
        return self.answer


SUITE = validate_suite({
    "name": "feedback-mini",
    "tasks": [
        {"id": "stable", "prompt": "stable?", "checks": [{"type": "equals", "value": "ok"}]},
        {"id": "fragile", "prompt": "fragile?", "checks": [{"type": "equals", "value": "ok"}]},
    ],
})


def test_feedback_detects_regression_and_repeated_failures(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    evaluations = EvaluationEngine(
        state, Adapter({"stable?": "ok", "fragile?": "wrong"}),
        suites={"feedback-mini": SUITE},
    )
    first = evaluations.run_suite("feedback-mini", label="baseline")
    evaluations.adapter = Adapter("wrong")
    second = evaluations.run_suite("feedback-mini", label="baseline")

    feedback = EvolutionFeedbackEngine(state, evaluations)
    report = feedback.analyze()

    kinds = [item["kind"] for item in report["findings"]]
    assert "benchmark_regression" in kinds
    assert "recurring_benchmark_failure" in kinds
    regression = next(x for x in report["findings"] if x["kind"] == "benchmark_regression")
    assert regression["evidence"]["previous_run_id"] == first["id"]
    assert regression["evidence"]["latest_run_id"] == second["id"]
    assert set(regression["evidence"]["regressed_tasks"]) == {"stable"}
    assert feedback.latest()["id"] == report["id"]


def test_feedback_detects_repeated_experience_blockers_with_provenance(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    experiences = ExperienceStore(state)
    common = dict(
        mission_id="m", title="Connect local model",
        objective="Connect to the configured local model",
        instructions="Check runtime availability and report connection status.",
        result="No connection.", observer_summary="Runtime endpoint was unavailable.",
        confidence=0.9,
    )
    first = experiences.capture_task_result(task_id="t1", outcome="blocked", **common)
    second = experiences.capture_task_result(task_id="t2", outcome="failed", **common)

    feedback = EvolutionFeedbackEngine(state, experiences=experiences)
    report = feedback.analyze()
    finding = next(x for x in report["findings"] if x["kind"] == "repeated_experience_blocker")
    assert set(finding["evidence"]["experience_ids"]) == {first["id"], second["id"]}
    assert finding["evidence"]["blocked_count"] == 1
    assert finding["evidence"]["failed_count"] == 1
    assert report["policy"]["read_only"] is True
    assert report["policy"]["automatic_skill_changes"] is False


def test_archived_experiences_are_excluded(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    experiences = ExperienceStore(state)
    item = experiences.capture_task_result(
        mission_id="m", task_id="t", title="Task", objective="same objective",
        instructions="same instructions", outcome="blocked", result="blocked",
        observer_summary="blocked", confidence=0.5,
    )
    experiences.set_status(item["id"], "archived")
    report = EvolutionFeedbackEngine(state, experiences=experiences).analyze()
    assert not any(x["kind"] == "repeated_experience_blocker" for x in report["findings"])


@pytest.mark.parametrize("kwargs", [
    {"history_limit": 1}, {"history_limit": 201},
    {"experience_limit": 0}, {"experience_limit": 201},
    {"history_limit": True},
])
def test_feedback_validates_limits(tmp_path, kwargs):
    engine = EvolutionFeedbackEngine(StateStore(tmp_path / "genesis.db"))
    with pytest.raises(FeedbackError):
        engine.analyze(**kwargs)
