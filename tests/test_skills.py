from __future__ import annotations

import pytest

from genesis_core.skills import SkillError, SkillStore
from genesis_core.state import StateStore


def make_store(tmp_path, tool_names=None):
    state = StateStore(tmp_path / "genesis.db")
    return SkillStore(state.database_path, tool_names=tool_names)


def create_skill(store):
    return store.create(
        "Research Assistant", "Research and summarize reliable sources.",
        "Compare sources, note uncertainty, and cite evidence.",
        ["read_text_file"], ["Check source quality", "Cite claims"],
    )


def test_skills_start_as_draft_and_need_explicit_review(tmp_path):
    store = make_store(tmp_path, {"read_text_file"})
    skill = create_skill(store)
    assert skill["status"] == "draft"
    assert store.relevant("research sources") == []
    pending = store.submit(skill["id"])
    assert pending["status"] == "pending"
    active = store.review(skill["id"], "approve")
    assert active["status"] == "active"
    assert store.relevant("research sources")[0]["id"] == skill["id"]


def test_rejected_skill_returns_to_draft_and_is_not_injected(tmp_path):
    store = make_store(tmp_path)
    skill = create_skill(store)
    store.submit(skill["id"])
    rejected = store.review(skill["id"], "reject")
    assert rejected["status"] == "draft"
    assert store.relevant("research") == []


def test_skill_versions_are_immutable_snapshots(tmp_path):
    store = make_store(tmp_path)
    skill = create_skill(store)
    updated = store.update(skill["id"], instructions="Use two independent sources.")
    assert updated["version"] == 2
    assert updated["status"] == "draft"
    versions = store.versions(skill["id"])
    assert [item["version"] for item in versions] == [1, 2]
    assert "Compare sources" in versions[0]["manifest"]["instructions"]


def test_active_skill_must_be_disabled_before_editing(tmp_path):
    store = make_store(tmp_path)
    skill = create_skill(store)
    store.submit(skill["id"])
    store.review(skill["id"], "approve")
    with pytest.raises(SkillError):
        store.update(skill["id"], instructions="Changed")
    disabled = store.disable(skill["id"])
    assert disabled["status"] == "disabled"
    assert store.update(skill["id"], instructions="Changed")["status"] == "draft"


def test_unknown_tools_and_invalid_manifests_are_rejected(tmp_path):
    store = make_store(tmp_path, {"time_now"})
    with pytest.raises(SkillError):
        store.create("Bad skill", "Description", "Instructions", ["shell"], ["Review"])
    with pytest.raises(SkillError):
        store.import_manifest({"format": "unknown"})
    manifest = {
        "format": "genesis-skill-v1", "name": "Imported", "description": "External skill",
        "instructions": "Untrusted imported instructions.", "allowed_tools": [],
        "checklist": ["Review content"],
    }
    imported = store.import_manifest(manifest)
    assert imported["status"] == "draft"


def test_duplicate_slugs_and_missing_review_checklist_fail(tmp_path):
    store = make_store(tmp_path)
    create_skill(store)
    with pytest.raises(SkillError):
        create_skill(store)
    no_checks = store.create("No checks", "Description", "Instructions", [], [])
    with pytest.raises(SkillError):
        store.submit(no_checks["id"])
