import json
from types import SimpleNamespace

import pytest

from genesis_core.learning import LearningEngine, LearningError
from genesis_core.state import StateStore


CURRICULUM = {
    "title": "Python foundations",
    "goal": "Learn Python basics",
    "lessons": [
        {
            "title": "Variables",
            "prompt": "Explain variables and assignment.",
            "expected_concepts": ["variable stores a value", "assignment operator"],
            "hints": ["Think about names and values."],
        },
        {
            "title": "Functions",
            "prompt": "Explain how functions help organize code.",
            "expected_concepts": ["reusable block of code", "function parameters"],
            "hints": [],
        },
    ],
}


class FakeAdapter:
    config = SimpleNamespace(provider="fake-local", model="test-model")

    def __init__(self, payload=None):
        self.payload = payload if payload is not None else CURRICULUM
        self.messages = []

    def chat(self, messages):
        self.messages = messages
        return json.dumps(self.payload)


def test_learning_creates_and_persists_curriculum(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    engine = LearningEngine(state, FakeAdapter())
    course = engine.create_course("Learn Python basics")
    assert course["title"] == "Python foundations"
    assert len(course["lessons"]) == 2
    assert course["progress_percent"] == 0
    assert course["xp"] == 0
    reopened = LearningEngine(StateStore(tmp_path / "genesis.db"), FakeAdapter())
    assert reopened.get_course(course["id"])["lessons"][0]["title"] == "Variables"


def test_learning_requires_valid_curriculum_and_does_not_persist_bad_output(tmp_path):
    engine = LearningEngine(StateStore(tmp_path / "genesis.db"), FakeAdapter({
        "title": "Incomplete", "goal": "Learn", "lessons": []
    }))
    with pytest.raises(LearningError, match="between 2 and 8"):
        engine.create_course("Learn something")
    assert engine.list_courses() == []


def test_assessment_uses_transparent_phrase_coverage_and_awards_only_improvement_xp(tmp_path):
    engine = LearningEngine(StateStore(tmp_path / "genesis.db"), FakeAdapter())
    course = engine.create_course("Learn Python basics")
    lesson = course["lessons"][0]
    first = engine.submit_answer(
        lesson["id"],
        "A variable stores a value. Python uses an assignment operator.",
    )
    assert first["score"] == 100
    assert first["completed"] is True
    assert first["xp_awarded"] == 10
    retry = engine.submit_answer(lesson["id"], "A variable stores a value.")
    assert retry["score"] == 50
    assert retry["xp_awarded"] == 0
    improved = engine.submit_answer(
        lesson["id"], "A variable stores a value and uses an assignment operator."
    )
    assert improved["xp_awarded"] == 0
    assert engine.get_course(course["id"])["xp"] == 10
    assert len(engine.attempts(lesson["id"])) == 3


def test_xp_rewards_only_new_best_score_bands(tmp_path):
    engine = LearningEngine(StateStore(tmp_path / "genesis.db"), FakeAdapter())
    course = engine.create_course("Learn Python basics")
    lesson = course["lessons"][0]
    a = engine.submit_answer(lesson["id"], "variable stores a value")
    b = engine.submit_answer(lesson["id"], "variable stores a value; assignment operator")
    c = engine.submit_answer(lesson["id"], "variable stores a value; assignment operator")
    assert a["score"] == 50 and a["xp_awarded"] == 5
    assert b["score"] == 100 and b["xp_awarded"] == 5
    assert c["xp_awarded"] == 0


def test_learning_validates_goal_and_answer_sizes(tmp_path):
    engine = LearningEngine(StateStore(tmp_path / "genesis.db"), FakeAdapter())
    with pytest.raises(LearningError):
        engine.create_course(" ")
    course = engine.create_course("Learn Python")
    with pytest.raises(LearningError):
        engine.submit_answer(course["lessons"][0]["id"], " ")
    with pytest.raises(KeyError):
        engine.submit_answer("missing-lesson", "Some answer")
