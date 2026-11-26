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
    assert updated["review_status"] == "pending"
    assert updated["title"] == "Updated"
    assert "changed" in updated["review_note"].lower()


def test_unchanged_approved_snapshot_keeps_its_review(tmp_path):
    store = ResearchStore(StateStore(tmp_path / "genesis.db"))
    first = store.save_run("first query", "fake", [
        {"title": "One", "url": "https://example.org/a", "snippet": "same text"}
    ])
    source = store.list_sources(run_id=first["id"])[0]
    store.decide_source(source["id"], "approved", "Reviewed carefully")
    second = store.save_run("second query", "fake", [
        {"title": "One", "url": "https://example.org/a", "snippet": "same text"}
    ])
    updated = store.list_sources(run_id=second["id"])[0]
    assert updated["review_status"] == "approved"
    assert updated["review_note"] == "Reviewed carefully"


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


def test_page_text_parser_ignores_scripts_and_extracts_readable_content():
    from genesis_core.research import _VisibleTextParser

    parser = _VisibleTextParser()
    parser.feed("<html><h1>Useful title</h1><script>secret()</script><p>Visible paragraph</p></html>")
    text = "".join(parser.parts)
    assert "Useful title" in text
    assert "Visible paragraph" in text
    assert "secret()" not in text


def test_page_url_validation_blocks_local_and_non_http_targets():
    from genesis_core.research import _validate_page_url

    with pytest.raises(ResearchError):
        _validate_page_url("file:///etc/passwd")
    with pytest.raises(ResearchError):
        _validate_page_url("http://127.0.0.1/private")
    with pytest.raises(ResearchError):
        _validate_page_url("http://localhost/admin")
    with pytest.raises(ResearchError):
        _validate_page_url("https://user:pass@example.org/page")


def test_fetch_source_page_persists_extracted_text_and_rejects_rejected_source(tmp_path, monkeypatch):
    import genesis_core.research as research

    state = StateStore(tmp_path / "genesis.db")
    store = ResearchStore(state)
    run = store.save_run("topic", "fake", [
        {"title": "Example", "url": "https://example.org/page", "snippet": "summary"}
    ])
    source = store.list_sources(run_id=run["id"])[0]
    monkeypatch.setattr(research, "fetch_web_page", lambda url: {
        "url": url, "content_type": "text/html", "text": "Extracted article text",
        "truncated": False, "characters": 22,
    })

    result = store.fetch_source_page(source["id"])
    assert result["text"] == "Extracted article text"
    saved = store.get_source_page(source["id"])
    assert saved["page_text"] == "Extracted article text"
    assert saved["page_fetched_at"]

    store.decide_source(source["id"], "rejected")
    with pytest.raises(ResearchError):
        store.fetch_source_page(source["id"])


def test_research_store_migrates_existing_source_table(tmp_path):
    import sqlite3

    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as db:
        db.execute("""
            CREATE TABLE research_sources (
                id TEXT PRIMARY KEY, url TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
                snippet TEXT NOT NULL, provider TEXT NOT NULL, published_at TEXT,
                retrieved_at TEXT NOT NULL, review_status TEXT NOT NULL DEFAULT 'pending',
                review_note TEXT NOT NULL DEFAULT ''
            )
        """)
    store = ResearchStore(StateStore(path))
    with sqlite3.connect(path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(research_sources)")}
    assert "page_text" in columns
    assert "page_fetched_at" in columns
