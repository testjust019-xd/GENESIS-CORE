from __future__ import annotations

import pytest

from genesis_core.experience import ExperienceError, ExperienceStore
from genesis_core.state import StateStore


def make_store(tmp_path):
    return ExperienceStore(StateStore(tmp_path / "genesis.db"))


def capture(store, **overrides):
    values = {
        "mission_id": "mission-1",
        "task_id": "task-1",
        "title": "Inspect provider configuration",
        "objective": "Verify local model connectivity",
        "instructions": "Check the configured local endpoint.",
        "outcome": "completed",
        "result": "The local endpoint returned a valid model list.",
        "observer_summary": "The requested check is supported by the recorded result.",
        "confidence": 0.8,
    }
    values.update(overrides)
    return store.capture_task_result(**values)


def test_capture_is_persistent_and_keeps_provenance(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    store = ExperienceStore(state)
    item = capture(store)

    restored = ExperienceStore(state).get(item["id"])
    assert restored is not None
    assert restored["mission_id"] == "mission-1"
    assert restored["task_id"] == "task-1"
    assert restored["outcome"] == "completed"
    assert restored["status"] == "captured"
    assert restored["confidence"] == 0.8


def test_filter_and_review_lifecycle(tmp_path):
    store = make_store(tmp_path)
    completed = capture(store)
    blocked = capture(
        store, task_id="task-2", outcome="blocked",
        observer_summary="The task needs user input.", confidence=0.4,
    )

    assert [item["id"] for item in store.list(outcome="completed")] == [completed["id"]]
    assert [item["id"] for item in store.list(status="captured")] == [
        blocked["id"], completed["id"]
    ]
    assert store.set_status(completed["id"], "reviewed")["status"] == "reviewed"
    assert store.list(status="reviewed")[0]["id"] == completed["id"]


@pytest.mark.parametrize("overrides", [
    {"outcome": "unknown"},
    {"confidence": 1.1},
    {"confidence": -0.1},
    {"title": ""},
])
def test_invalid_experiences_are_rejected(tmp_path, overrides):
    with pytest.raises(ExperienceError):
        capture(make_store(tmp_path), **overrides)


def test_missing_experience_status_target_raises(tmp_path):
    with pytest.raises(KeyError):
        make_store(tmp_path).set_status("missing", "reviewed")
