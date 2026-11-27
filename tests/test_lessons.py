from __future__ import annotations

import pytest

from genesis_core.experience import ExperienceStore
from genesis_core.lessons import LessonError, LessonStore
from genesis_core.state import StateStore


def setup_stores(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    experiences = ExperienceStore(state)
    lesson_store = LessonStore(state.database_path, experiences)
    return experiences, lesson_store


def capture(experiences, suffix="1"):
    return experiences.capture_task_result(
        mission_id="mission-" + suffix, task_id="task-" + suffix,
        title="Check retry behavior", objective="Verify retry result",
        instructions="Run the operation and record the result.",
        outcome="completed", result="The second attempt succeeded.",
        observer_summary="A retry succeeded after a transient failure.",
        confidence=0.5,
    )


def test_lesson_keeps_evidence_and_requires_explicit_review(tmp_path):
    experiences, lessons = setup_stores(tmp_path)
    first = capture(experiences)
    second = capture(experiences, "2")
    lesson = lessons.create(
        title="Retry transient failures",
        statement="Retry transient failures once before escalating.",
        rationale="Two recorded attempts show a transient failure followed by success.",
        applicability="Only for operations documented as safe to retry.",
        limitations="Two observations do not establish a universal rule.",
        evidence_ids=[first["id"], second["id"]],
    )
    assert lesson["status"] == "draft"
    assert [item["id"] for item in lesson["evidence"]] == [first["id"], second["id"]]
    assert lessons.submit(lesson["id"])["status"] == "pending"
    assert lessons.review(lesson["id"], "approve")["status"] == "approved"
    assert lessons.get(lesson["id"])["status"] == "approved"


def test_lesson_requires_existing_evidence_and_bounded_content(tmp_path):
    _, lessons = setup_stores(tmp_path)
    values = dict(
        title="A lesson", statement="A useful statement",
        rationale="Why it may be useful", applicability="Where it may apply",
        limitations="What remains uncertain", evidence_ids=["0000000000000000"],
    )
    with pytest.raises(LessonError, match="Unknown source"):
        lessons.create(**values)
    values["evidence_ids"] = []
    with pytest.raises(LessonError, match="cite between"):
        lessons.create(**values)


def test_lesson_rejects_invalid_transitions(tmp_path):
    experiences, lessons = setup_stores(tmp_path)
    item = capture(experiences)
    lesson = lessons.create(
        title="Lesson", statement="Statement", rationale="Rationale",
        applicability="Applicability", limitations="Limitations",
        evidence_ids=[item["id"]],
    )
    with pytest.raises(LessonError, match="Only draft"):
        lessons.review(lesson["id"], "approve")
    pending = lessons.submit(lesson["id"])
    with pytest.raises(LessonError, match="Only pending"):
        lessons.submit(pending["id"])
    assert lessons.review(pending["id"], "reject")["status"] == "rejected"


def test_lesson_persists_across_store_instances(tmp_path):
    experiences, lessons = setup_stores(tmp_path)
    item = capture(experiences)
    created = lessons.create(
        title="Persistence", statement="Keep provenance",
        rationale="Evidence must remain traceable",
        applicability="Across restarts", limitations="No generalization claim",
        evidence_ids=[item["id"]],
    )
    restored = LessonStore(lessons.database_path, experiences).get(created["id"])
    assert restored["evidence_ids"] == [item["id"]]
    assert restored["evidence"][0]["mission_id"] == item["mission_id"]
