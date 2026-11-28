from __future__ import annotations

from types import SimpleNamespace

from genesis_core import web
from genesis_core.evaluation import EvaluationEngine, validate_suite
from genesis_core.evolution_feedback import EvolutionFeedbackEngine
from genesis_core.experience import ExperienceStore
from genesis_core.state import StateStore


def test_feedback_loop_api_returns_auditable_read_only_report(tmp_path, monkeypatch):
    state = StateStore(tmp_path / "feedback-api.db")
    suite = validate_suite({
        "name": "api-mini",
        "tasks": [{"id": "one", "prompt": "question", "checks": [{"type": "equals", "value": "ok"}]}],
    })

    class FakeAdapter:
        config = SimpleNamespace(provider="fake", model="tiny")

        def chat(self, messages):
            return "ok"

    evaluations = EvaluationEngine(state, FakeAdapter(), suites={"api-mini": suite})
    evaluations.run_suite("api-mini", label="baseline")
    feedback = EvolutionFeedbackEngine(state, evaluations, ExperienceStore(state))
    monkeypatch.setattr(web, "feedback_engine", feedback)

    report = web.analyze_evolution_feedback()
    assert report["findings_count"] == 0
    assert report["policy"]["read_only"] is True
    assert web.latest_evolution_feedback()["id"] == report["id"]
