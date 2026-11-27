import json
from types import SimpleNamespace

import pytest

from genesis_core import evaluation as ev
from genesis_core.adapters import ModelError
from genesis_core.skills import SkillStore
from genesis_core.state import StateStore


class MapAdapter:
    """Answers by prompt keyword; a skill in the system context can change behaviour."""

    config = SimpleNamespace(provider="fake", model="m1")

    def __init__(self, good, with_skill_good=None, fail=False):
        self.good, self.with_skill_good, self.fail = good, with_skill_good or good, fail

    def chat(self, messages):
        if self.fail:
            raise ModelError("down")
        skilled = any(m["role"] == "system" for m in messages)
        answers = self.with_skill_good if skilled else self.good
        prompt = messages[-1]["content"]
        return answers.get(prompt, "wrong")


SUITE = {"name": "mini", "description": "d", "tasks": [
    {"id": "a", "prompt": "q-a", "checks": [{"type": "equals", "value": "yes"}]},
    {"id": "b", "prompt": "q-b", "checks": [{"type": "contains", "value": "ok"}, {"type": "max_words", "value": 3}]},
]}


def engine(tmp_path, adapter):
    return ev.EvaluationEngine(StateStore(tmp_path / "g.db"), adapter, suites={"mini": ev.validate_suite(SUITE)})


def test_checks():
    assert ev.run_check({"type": "equals", "value": "paris"}, ' "Paris". ')
    assert ev.run_check({"type": "number_equals", "value": 43}, "The answer is 43.")
    assert not ev.run_check({"type": "number_equals", "value": 43}, "no number")
    assert ev.run_check({"type": "json_valid", "keys": ["name"]}, 'Sure: {"name": "Ada"}')
    assert not ev.run_check({"type": "json_valid", "keys": ["age"]}, '{"name": "Ada"}')
    assert ev.run_check({"type": "max_words", "value": 3}, "one two")
    assert not ev.run_check({"type": "max_words", "value": 1}, "")
    assert ev.run_check({"type": "not_contains", "value": "fur"}, "Cats purr")
    assert ev.run_check({"type": "language_fr"}, "Le ciel est bleu parce que la lumière se diffuse.")
    assert not ev.run_check({"type": "language_fr"}, "The sky is blue.")
    with pytest.raises(ev.EvaluationError):
        ev.run_check({"type": "magic"}, "x")


def test_builtin_suite_is_valid_and_loads_user_suites(tmp_path):
    suites = ev.load_suites(tmp_path)
    assert len(suites["core-basics"]["tasks"]) >= 10
    (tmp_path / "mine.json").write_text(json.dumps(SUITE))
    (tmp_path / "broken.json").write_text("{not json")
    assert "mini" in ev.load_suites(tmp_path)


@pytest.mark.parametrize("bad", [
    {}, {"name": "x", "tasks": []},
    {"name": "x", "tasks": [{"id": "a", "prompt": "p", "checks": []}]},
    {"name": "x", "tasks": [{"id": "a", "prompt": "p", "checks": [{"type": "regex", "pattern": "("}]}]},
    {"name": "x", "tasks": [{"id": "a", "prompt": "p", "checks": [{"type": "equals"}]}]},
    {"name": "x", "tasks": [{"id": "a", "prompt": "p", "checks": [{"type": "equals", "value": "1"}]},
                            {"id": "a", "prompt": "p", "checks": [{"type": "equals", "value": "1"}]}]},
])
def test_invalid_suites_rejected(bad):
    with pytest.raises(ev.EvaluationError):
        ev.validate_suite(bad)


def test_run_scores_and_persists(tmp_path):
    e = engine(tmp_path, MapAdapter({"q-a": "Yes.", "q-b": "ok fine"}))
    seen = []
    run = e.run_suite("mini", progress=lambda i, n, t, p: seen.append((i, n, t, p)))
    assert run["score"] == 1.0 and run["passed"] == 2 and seen[-1] == (2, 2, "b", True)
    stored = e.get_run(run["id"])
    assert stored["model"] == "m1" and [r["passed"] for r in stored["results"]] == [True, True]
    assert e.history()[0]["id"] == run["id"]
    with pytest.raises(ev.EvaluationError):
        e.get_run("nope")
    with pytest.raises(ev.EvaluationError):
        e.run_suite("unknown")


def test_partial_credit_and_total_failure(tmp_path):
    e = engine(tmp_path, MapAdapter({"q-a": "yes", "q-b": "ok but this is far too long"}))
    run = e.run_suite("mini")
    assert run["passed"] == 1 and run["score"] == pytest.approx(0.75)
    with pytest.raises(ev.EvaluationError, match="failed every request"):
        engine(tmp_path, MapAdapter({}, fail=True)).run_suite("mini")


def test_compare_verdicts(tmp_path):
    good = {"q-a": "yes", "q-b": "ok"}
    e = engine(tmp_path, MapAdapter({}, with_skill_good=good))
    base = e.run_suite("mini", label="baseline")
    e.adapter = MapAdapter(good)
    cand = e.run_suite("mini", label="cand")
    comp = e.compare(base["id"], cand["id"])
    assert comp["verdict"] == "improved" and set(comp["improved"]) == {"a", "b"} and comp["delta"] == pytest.approx(0.75)  # baseline keeps partial credit (max_words)
    back = e.compare(cand["id"], base["id"])
    assert back["verdict"] == "regressed" and set(back["regressed"]) == {"a", "b"}
    same = e.compare(cand["id"], cand["id"], record=False)
    assert same["verdict"] == "no change"
    assert "noisy" in comp["caveat"]


def test_evaluate_skill_records_evidence(tmp_path):
    store = StateStore(tmp_path / "g.db")
    skills = SkillStore(store.database_path, set())
    skill = skills.create("helper", "helps answer", "Answer yes.", checklist=["review"])
    e = ev.EvaluationEngine(store, MapAdapter({}, with_skill_good={"q-a": "yes", "q-b": "ok"}),
                            suites={"mini": ev.validate_suite(SUITE)})
    assert e.skill_evidence(skill["id"]) is None
    out = e.evaluate_skill(skill, "mini")
    assert out["baseline"]["score"] == pytest.approx(0.25) and out["candidate"]["score"] == 1.0
    evidence = e.skill_evidence(skill["id"])
    assert evidence["verdict"] == "improved" and evidence["delta"] == pytest.approx(0.75)
    assert "helper" in ev.skill_context_message(skill)["content"]


def test_timeline_only_baselines(tmp_path):
    e = engine(tmp_path, MapAdapter({"q-a": "yes", "q-b": "ok"}))
    e.run_suite("mini", label="baseline")
    e.run_suite("mini", label="skill:x")
    e.run_suite("mini", label="baseline")
    assert len(e.timeline("mini")) == 2 and len(e.timeline("mini", model="other")) == 0
