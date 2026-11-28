from __future__ import annotations

import pytest

from genesis_core.artifacts import ArtifactError, ArtifactStore


def test_artifacts_create_list_update_and_delete(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts.db")
    created = store.create("Demo", "<h1>Hello</h1>", "A tiny demo")
    assert created["title"] == "Demo"
    assert created["html"] == "<h1>Hello</h1>"
    assert len(store.list()) == 1

    updated = store.update(created["id"], "Updated", "<p>Changed</p>")
    assert updated["title"] == "Updated"
    assert updated["description"] == ""
    assert store.get(created["id"])["html"] == "<p>Changed</p>"

    store.delete(created["id"])
    assert store.get(created["id"]) is None
    with pytest.raises(KeyError):
        store.delete(created["id"])


def test_artifacts_validate_fields_and_size(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts.db")
    with pytest.raises(ArtifactError):
        store.create(" ", "<p>empty title</p>")
    with pytest.raises(ArtifactError):
        store.create("Missing HTML", "  ")
    with pytest.raises(ArtifactError):
        store.create("Too large", "x" * (store.MAX_HTML_BYTES + 1))
    with pytest.raises(ArtifactError):
        store.create("Description", "<p>ok</p>", "x" * 501)


def test_artifacts_are_isolated_between_databases(tmp_path):
    first = ArtifactStore(tmp_path / "one.db")
    second = ArtifactStore(tmp_path / "two.db")
    item = first.create("Private", "<p>local</p>")
    assert second.get(item["id"]) is None
