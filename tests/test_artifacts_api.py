from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi import HTTPException

from genesis_core import web
from genesis_core.artifacts import ArtifactStore


def test_artifact_api_crud(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "artifact_store", ArtifactStore(tmp_path / "api.db"))
    payload = web.ArtifactInput(title="API demo", description="test", html="<h1>Hi</h1>")
    created = web.create_artifact(payload)["artifact"]
    assert web.list_artifacts()["artifacts"][0]["id"] == created["id"]
    assert web.get_artifact(created["id"])["artifact"]["html"] == "<h1>Hi</h1>"

    updated = web.update_artifact(
        created["id"],
        web.ArtifactInput(title="Updated", html="<p>Updated</p>"),
    )["artifact"]
    assert updated["title"] == "Updated"

    assert web.delete_artifact(created["id"]) == {"deleted": created["id"]}
    with pytest.raises(HTTPException) as err:
        web.get_artifact(created["id"])
    assert err.value.status_code == 404


def test_artifact_api_validation_and_missing_update(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "artifact_store", ArtifactStore(tmp_path / "validation.db"))
    with pytest.raises(HTTPException) as err:
        web.create_artifact(web.ArtifactInput(title="Bad", html=" "))
    assert err.value.status_code == 422
    with pytest.raises(HTTPException) as err:
        web.update_artifact("missing", web.ArtifactInput(title="Demo", html="<p>ok</p>"))
    assert err.value.status_code == 404
