from __future__ import annotations

import pytest

from genesis_core.knowledge import KnowledgeStore
from genesis_core.research import ResearchEngine, ResearchError, ResearchStore, SearXNGProvider
from genesis_core.state import StateStore


class FakeProvider:
    name = "fake"

    def search(self, query: str, limit: int = 8):
        return [
            {"title": "Example source", "url": "https://example.org/article",
             "snippet": "A useful unverified excerpt.", "published_at": None,
             "provider": self.name}
        ][:limit]


def test_search_results_are_persisted_as_pending_and_reviewable(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    engine = ResearchEngine(state=state, provider=FakeProvider())
    result = engine.search("genesis architecture")
    assert result["mode"] == "web"
    assert result["source_count"] == 1
    source = result["sources"][0]
    assert source["review_status"] == "pending"
    assert "unverified" in result["notice"].lower()

    reviewed = engine.review_source(source["id"], "approved", "Checked against the original source.")
    assert reviewed["review_status"] == "approved"
    assert reviewed["review_note"] == "Checked against the original source."


def test_repeated_url_deduplicates_and_preserves_review_status(tmp_path):
    store = ResearchStore(StateStore(tmp_path / "genesis.db"))
    first = store.save_run("first query", "fake", [
        {"title": "One", "url": "https://example.org/a", "snippet": "first"}
    ])
    source = store.list_sources(run_id=first["id"])[0]
    store.decide_source(source["id"], "approved", "Reviewed")
    second = store.save_run("second query", "fake", [
        {"title": "Updated", "url": "https://example.org/a", "snippet": "updated"}
    ])
    updated = store.list_sources(run_id=second["id"])[0]
    assert updated["id"] == source["id"]
    assert updated["review_status"] == "approved"
    assert updated["title"] == "Updated"


def test_offline_search_uses_local_knowledge(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    knowledge = KnowledgeStore(state)
    knowledge.ingest_text("Architecture notes", "GENESIS uses local SQLite and modular agents.")
    engine = ResearchEngine(state=state, knowledge=knowledge)
    result = engine.search("SQLite modular agents")
    assert result["mode"] == "offline"
    assert result["provider"] == "local-knowledge"
    assert result["sources"][0]["url"].startswith("knowledge://")
    assert result["sources"][0]["review_status"] == "pending"


def test_provider_url_requires_https_except_localhost():
    with pytest.raises(ResearchError):
        SearXNGProvider("http://search.example.org")
    with pytest.raises(ResearchError):
        SearXNGProvider("file:///etc/passwd")
    assert SearXNGProvider("http://127.0.0.1:8080").base_url == "http://127.0.0.1:8080"


def test_review_rejects_unknown_decisions_and_missing_sources(tmp_path):
    store = ResearchStore(StateStore(tmp_path / "genesis.db"))
    with pytest.raises(ResearchError):
        store.decide_source("missing", "maybe")
    with pytest.raises(KeyError):
        store.decide_source("missing", "approved")


def test_search_validates_query_and_bounds_limit(tmp_path):
    engine = ResearchEngine(state=StateStore(tmp_path / "genesis.db"), provider=FakeProvider())
    with pytest.raises(ResearchError):
        engine.search(" ")
    result = engine.search("query", limit=1000)
    assert result["source_count"] == 1
