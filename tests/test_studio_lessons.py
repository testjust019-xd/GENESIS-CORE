from __future__ import annotations

import pytest
from fastapi import HTTPException

from genesis_core import web
from genesis_core.experience import ExperienceStore
from genesis_core.lessons import LessonStore
from genesis_core.state import StateStore


@pytest.fixture
def studio_lessons(tmp_path, monkeypatch):
    state = StateStore(tmp_path / "studio-lessons.db")
    experiences = ExperienceStore(state)
    lessons = LessonStore(state.database_path, experiences)
    monkeypatch.setattr(web, "experience_store", experiences)
    monkeypatch.setattr(web, "lesson_store", lessons)
    evidence = experiences.capture_task_result(
        mission_id="mission-api", task_id="task-api", title="API test",
        objective="Test lesson API", instructions="Record a result",
        outcome="completed", result="The recorded task succeeded.",
        observer_summary="One successful observation.", confidence=0.5,
    )
    return lessons, evidence


def payload(evidence_id):
    return web.LessonInput(
        title="A candidate lesson",
        statement="Check assumptions before retrying.",
        rationale="The recorded result supports a cautious retry policy.",
        applicability="Only operations known to be safe to retry.",
        limitations="One experience cannot establish a general rule.",
        evidence_ids=[evidence_id],
    )


def test_lesson_api_create_list_submit_and_review(studio_lessons):
    lessons, evidence = studio_lessons
    created = web.create_lesson(payload(evidence["id"]))["lesson"]
    assert created["status"] == "draft"
    assert created["evidence"][0]["id"] == evidence["id"]
    assert web.list_lessons(status="draft")["count"] == 1
    assert web.submit_lesson(created["id"])["lesson"]["status"] == "pending"
    assert web.review_lesson(
        created["id"], web.LessonReviewInput(decision="approve")
    )["lesson"]["status"] == "approved"


def test_lesson_api_rejects_missing_evidence_and_missing_ids(studio_lessons):
    _, evidence = studio_lessons
    invalid = payload(evidence["id"])
    invalid.evidence_ids = ["0000000000000000"]
    with pytest.raises(HTTPException) as rejected:
        web.create_lesson(invalid)
    assert rejected.value.status_code == 422
    with pytest.raises(HTTPException) as missing:
        web.get_lesson("does-not-exist")
    assert missing.value.status_code == 404


def test_studio_html_exposes_lesson_workflow():
    assert 'id="lesson-create"' in web.HTML
    assert 'id="lessons-list"' in web.HTML
    assert "/api/lessons" in web.HTML
