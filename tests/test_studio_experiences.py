from __future__ import annotations

import pytest
from fastapi import HTTPException

from genesis_core import web
from genesis_core.experience import ExperienceStore
from genesis_core.state import StateStore


@pytest.fixture
def studio_experiences(tmp_path, monkeypatch):
    store = ExperienceStore(StateStore(tmp_path / "studio-experiences.db"))
    monkeypatch.setattr(web, "experience_store", store)
    item = store.capture_task_result(
        mission_id="mission-studio",
        task_id="task-studio",
        title="Inspect Studio experience view",
        objective="Expose mission evidence in Studio",
        instructions="Check the recorded task output.",
        outcome="completed",
        result="The task result is available for inspection.",
        observer_summary="The observer recorded a completion.",
        confidence=0.5,
    )
    return store, item


def test_experience_api_lists_filters_and_returns_detail(studio_experiences):
    store, item = studio_experiences

    listed = web.list_experiences(status="captured", outcome="completed", limit=20)
    assert listed["count"] == 1
    assert listed["experiences"][0]["id"] == item["id"]

    detail = web.get_experience(item["id"])
    assert detail["experience"]["observer_summary"] == "The observer recorded a completion."

    assert web.list_experiences(status="archived")["count"] == 0


def test_experience_api_updates_review_state(studio_experiences):
    store, item = studio_experiences

    updated = web.update_experience_status(
        item["id"], web.ExperienceStatusInput(status="reviewed")
    )
    assert updated["experience"]["status"] == "reviewed"
    assert store.get(item["id"])["status"] == "reviewed"


def test_experience_api_reports_missing_records(studio_experiences):
    with pytest.raises(HTTPException) as missing:
        web.get_experience("does-not-exist")
    assert missing.value.status_code == 404

    with pytest.raises(HTTPException) as missing_update:
        web.update_experience_status(
            "does-not-exist", web.ExperienceStatusInput(status="archived")
        )
    assert missing_update.value.status_code == 404


def test_studio_html_exposes_experience_panel_and_mobile_toggle():
    assert 'id="experiences-list"' in web.HTML
    assert 'id="experience-detail"' in web.HTML
    assert 'id="toggle-panels"' in web.HTML
    assert "/api/experiences" in web.HTML
