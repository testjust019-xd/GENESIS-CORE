from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi import HTTPException  # noqa: E402

from genesis_core import web  # noqa: E402
from genesis_core.state import StateStore  # noqa: E402


def test_root_serves_studio_shell():
    response = web.studio()
    assert str(response.path).endswith("static/studio/index.html")
    html = response.path.read_text(encoding="utf-8")
    assert 'id="input"' in html
    assert "cdn" not in html.lower()  # offline: no third-party assets


def test_studio_assets_are_whitelisted():
    assert web.studio_asset("studio.css").media_type.startswith("text/css")
    assert web.studio_asset("studio.js").media_type.startswith("text/javascript") or \
        web.studio_asset("studio.js").media_type.startswith("application/javascript")
    for bad in ("../web.py", "index.html", "secret.txt", "..%2Fweb.py"):
        with pytest.raises(HTTPException) as err:
            web.studio_asset(bad)
        assert err.value.status_code == 404


def test_classic_keeps_previous_interface():
    assert "GENESIS Studio" in web.classic_studio()


def test_evolution_summary_shape():
    data = web.evolution()
    assert set(data) == {"timeline", "runs", "counts"}
    assert set(data["counts"]) == {"skills_active", "memories", "documents"}


def test_skill_evidence_unknown_skill_is_404():
    with pytest.raises(HTTPException) as err:
        web.skill_evidence("does-not-exist")
    assert err.value.status_code == 404


def test_stream_forwards_activity_events(tmp_path, monkeypatch):
    state = StateStore(tmp_path / "activity.db")
    session = state.create_session()
    monkeypatch.setattr(web, "store", state)

    class FakeAgent:
        def chat(self, session_id, content, on_token=None, on_activity=None, on_approval=None):
            user = state.add_message(session_id, "user", content)
            if on_activity:
                on_activity({"tool": "read_text_file", "status": "ok"})
            assistant = state.add_message(session_id, "assistant", "done")
            return SimpleNamespace(user_message=user, assistant_message=assistant,
                                   provider="fake", model="m", activity=[])

    monkeypatch.setattr(web, "agent", FakeAgent())
    response = web.stream_message(session["id"], web.MessageInput(content="Hi"))

    async def collect():
        return [frame async for frame in response.body_iterator]

    body = "".join(asyncio.run(collect()))
    assert '"type": "activity"' in body
    assert "read_text_file" in body
    assert '"type": "done"' in body
