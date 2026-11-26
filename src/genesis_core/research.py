"""Local-first research orchestration and human-reviewed source vault.

External search is optional. Search snippets are untrusted evidence, never instructions.
A source is only marked approved after an explicit human review decision.
"""
from __future__ import annotations

import ipaddress
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from genesis_core.knowledge import KnowledgeStore
from genesis_core.state import StateStore


class ResearchError(ValueError):
    """Raised when a research request or provider response is invalid."""


class SearchProvider(Protocol):
    name: str

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """Return normalized, untrusted search results."""


def _validate_provider_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ResearchError("Search provider URL must be an absolute HTTP(S) URL.")
    host = parsed.hostname.lower()
    if parsed.scheme != "https" and host not in {"localhost", "127.0.0.1", "::1"}:
        raise ResearchError("Remote search providers must use HTTPS.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and not address.is_global and not address.is_loopback:
        raise ResearchError("Private or reserved provider addresses are not allowed.")
    if parsed.username or parsed.password:
        raise ResearchError("Credentials must not be embedded in provider URLs.")
    return value.rstrip("/")


def _request_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "GENESIS-CORE/0.1", **(headers or {})})
    try:
        with urlopen(request, timeout=12) as response:
            raw = response.read(2_000_000)
        payload = json.loads(raw.decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResearchError(f"Search provider request failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise ResearchError("Search provider returned an invalid response.")
    return payload


class SearXNGProvider:
    name = "searxng"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = _validate_provider_url(
            base_url or os.environ.get("GENESIS_SEARXNG_URL", "")
        )

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        payload = _request_json(
            self.base_url + "/search?" + urlencode({"q": query, "format": "json", "categories": "general"})
        )
        results = []
        for item in payload.get("results", [])[:limit]:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            results.append({
                "title": str(item.get("title") or item["url"])[:500],
                "url": str(item["url"])[:2000],
                "snippet": str(item.get("content") or "")[:4000],
                "published_at": str(item.get("publishedDate") or "")[:80] or None,
                "provider": self.name,
            })
        return results


class BraveSearchProvider:
    name = "brave"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("GENESIS_BRAVE_API_KEY", "")
        if not self.api_key:
            raise ResearchError("Set GENESIS_BRAVE_API_KEY to use Brave Search.")

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        url = "https://api.search.brave.com/res/v1/web/search?" + urlencode({
            "q": query, "count": max(1, min(limit, 20))
        })
        payload = _request_json(url, {"X-Subscription-Token": self.api_key})
        web = payload.get("web") or {}
        results = []
        for item in web.get("results", [])[:limit]:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            results.append({
                "title": str(item.get("title") or item["url"])[:500],
                "url": str(item["url"])[:2000],
                "snippet": str(item.get("description") or "")[:4000],
                "published_at": str(item.get("page_age") or "")[:80] or None,
                "provider": self.name,
            })
        return results


class ResearchStore:
    """Persistent research runs and source records sharing GENESIS's SQLite database."""

    def __init__(self, state: StateStore | None = None) -> None:
        self.database_path = (state or StateStore()).database_path
        with sqlite3.connect(self.database_path, timeout=10) as db:
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("""
                CREATE TABLE IF NOT EXISTS research_runs (
                    id TEXT PRIMARY KEY, query TEXT NOT NULL, provider TEXT NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS research_sources (
                    id TEXT PRIMARY KEY, url TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
                    snippet TEXT NOT NULL, provider TEXT NOT NULL, published_at TEXT,
                    retrieved_at TEXT NOT NULL, review_status TEXT NOT NULL DEFAULT 'pending',
                    review_note TEXT NOT NULL DEFAULT ''
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS research_run_sources (
                    run_id TEXT NOT NULL REFERENCES research_runs(id) ON DELETE CASCADE,
                    source_id TEXT NOT NULL REFERENCES research_sources(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    PRIMARY KEY(run_id, source_id)
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def save_run(self, query: str, provider: str, results: list[dict[str, Any]]) -> dict[str, Any]:
        run_id, now = uuid.uuid4().hex[:16], self._now()
        with self._connect() as db:
            db.execute(
                "INSERT INTO research_runs VALUES (?, ?, ?, ?, ?)",
                (run_id, query, provider, "completed" if results else "empty", now),
            )
            saved = []
            for position, item in enumerate(results):
                url = str(item["url"]).strip()[:2000]
                if not url.startswith(("http://", "https://", "knowledge://")):
                    continue
                existing = db.execute(
                    "SELECT id, review_status FROM research_sources WHERE url = ?", (url,)
                ).fetchone()
                if existing:
                    source_id = existing["id"]
                    db.execute(
                        "UPDATE research_sources SET title = ?, snippet = ?, provider = ?, "
                        "published_at = ?, retrieved_at = ? WHERE id = ?",
                        (str(item.get("title") or url)[:500], str(item.get("snippet") or "")[:4000],
                         str(item.get("provider") or provider)[:80], item.get("published_at"), now, source_id),
                    )
                else:
                    source_id = uuid.uuid4().hex[:16]
                    db.execute(
                        "INSERT INTO research_sources VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', '')",
                        (source_id, url, str(item.get("title") or url)[:500],
                         str(item.get("snippet") or "")[:4000], str(item.get("provider") or provider)[:80],
                         item.get("published_at"), now),
                    )
                db.execute(
                    "INSERT OR IGNORE INTO research_run_sources VALUES (?, ?, ?)",
                    (run_id, source_id, position),
                )
                saved.append(source_id)
            return {"id": run_id, "query": query, "provider": provider,
                    "status": "completed" if saved else "empty", "source_count": len(saved),
                    "created_at": now}

    def list_runs(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("""
                SELECT r.*, COUNT(rs.source_id) AS source_count
                FROM research_runs r LEFT JOIN research_run_sources rs ON rs.run_id = r.id
                GROUP BY r.id ORDER BY r.created_at DESC LIMIT ?
            """, (max(1, min(limit, 100)),)).fetchall()
        return [dict(row) for row in rows]

    def list_sources(self, run_id: str | None = None, review_status: str | None = None,
                     limit: int = 100) -> list[dict[str, Any]]:
        clauses, values = [], []
        if run_id:
            clauses.append("s.id IN (SELECT source_id FROM research_run_sources WHERE run_id = ?)")
            values.append(run_id)
        if review_status:
            if review_status not in {"pending", "approved", "rejected"}:
                raise ResearchError("Review status must be pending, approved or rejected.")
            clauses.append("s.review_status = ?")
            values.append(review_status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        values.append(max(1, min(limit, 200)))
        with self._connect() as db:
            rows = db.execute(
                "SELECT s.* FROM research_sources s" + where +
                " ORDER BY s.retrieved_at DESC LIMIT ?", values
            ).fetchall()
        return [dict(row) for row in rows]

    def decide_source(self, source_id: str, decision: str, note: str = "") -> dict[str, Any]:
        if decision not in {"approved", "rejected", "pending"}:
            raise ResearchError("Decision must be approved, rejected or pending.")
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE research_sources SET review_status = ?, review_note = ? WHERE id = ?",
                (decision, note.strip()[:1000], source_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(source_id)
            row = db.execute("SELECT * FROM research_sources WHERE id = ?", (source_id,)).fetchone()
        return dict(row)


class ResearchEngine:
    """Runs optional web search or falls back to the local Knowledge Engine."""

    def __init__(self, state: StateStore | None = None, knowledge: KnowledgeStore | None = None,
                 provider: SearchProvider | None = None) -> None:
        self.store = ResearchStore(state)
        self.knowledge = knowledge or KnowledgeStore(state)
        self.provider = provider

    @staticmethod
    def configured_provider(name: str | None = None) -> SearchProvider | None:
        selected = (name or os.environ.get("GENESIS_SEARCH_PROVIDER", "")).strip().lower()
        if selected in {"", "offline", "local", "none"}:
            return None
        if selected == "searxng":
            return SearXNGProvider()
        if selected == "brave":
            return BraveSearchProvider()
        raise ResearchError("Unknown search provider. Choose searxng, brave or offline.")

    def search(self, query: str, limit: int = 8,
               provider: SearchProvider | None = None) -> dict[str, Any]:
        query = query.strip() if isinstance(query, str) else ""
        if not query or len(query) > 500:
            raise ResearchError("Research query must contain 1 to 500 characters.")
        safe_limit = max(1, min(limit, 20))
        selected = provider or self.provider or self.configured_provider()
        if selected:
            results = selected.search(query, safe_limit)
            provider_name = selected.name
        else:
            results = [{
                "title": item["citation"]["title"],
                "url": item["citation"]["source"],
                "snippet": item["excerpt"],
                "published_at": None,
                "provider": "local-knowledge",
            } for item in self.knowledge.search(query, safe_limit)]
            provider_name = "local-knowledge"
        run = self.store.save_run(query, provider_name, results)
        return {**run, "sources": self.store.list_sources(run_id=run["id"], limit=safe_limit),
                "mode": "web" if selected else "offline",
                "notice": "Search excerpts are unverified and untrusted. Review sources before relying on them."}

    def list_sources(self, run_id: str | None = None,
                     review_status: str | None = None) -> list[dict[str, Any]]:
        return self.store.list_sources(run_id, review_status)

    def review_source(self, source_id: str, decision: str, note: str = "") -> dict[str, Any]:
        return self.store.decide_source(source_id, decision, note)


__all__ = [
    "BraveSearchProvider", "ResearchEngine", "ResearchError", "ResearchStore",
    "SearchProvider", "SearXNGProvider",
]
