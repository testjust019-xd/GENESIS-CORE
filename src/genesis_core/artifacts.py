"""Persistent, local-first HTML artifacts for GENESIS Studio."""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


class ArtifactError(ValueError):
    """Raised when an artifact cannot be stored."""


class ArtifactStore:
    """SQLite-backed collection of self-contained HTML artifacts."""

    MAX_HTML_BYTES = 200_000

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    html TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.database_path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _validate(title: str, html: str, description: str) -> tuple[str, str, str]:
        title = title.strip()
        description = description.strip()
        if not title or len(title) > 120:
            raise ArtifactError("Title must contain 1–120 characters.")
        if not html.strip():
            raise ArtifactError("HTML content cannot be empty.")
        if len(html.encode("utf-8")) > ArtifactStore.MAX_HTML_BYTES:
            raise ArtifactError("HTML content exceeds the 200 KB artifact limit.")
        if len(description) > 500:
            raise ArtifactError("Description cannot exceed 500 characters.")
        return title, description, html

    @staticmethod
    def _public(row: sqlite3.Row, include_html: bool = False) -> dict[str, Any]:
        item = {
            "id": row["id"], "title": row["title"],
            "description": row["description"], "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if include_html:
            item["html"] = row["html"]
        return item

    def create(self, title: str, html: str, description: str = "") -> dict[str, Any]:
        title, description, html = self._validate(title, html, description)
        now, artifact_id = self._now(), uuid.uuid4().hex[:12]
        with self._connect() as db:
            db.execute(
                "INSERT INTO artifacts(id,title,description,html,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?)",
                (artifact_id, title, description, html, now, now),
            )
            row = db.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
        return self._public(row, include_html=True)

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM artifacts ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [self._public(row) for row in rows]

    def get(self, artifact_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
        return self._public(row, include_html=True) if row else None

    def update(self, artifact_id: str, title: str, html: str,
               description: str = "") -> dict[str, Any]:
        title, description, html = self._validate(title, html, description)
        now = self._now()
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE artifacts SET title=?,description=?,html=?,updated_at=? WHERE id=?",
                (title, description, html, now, artifact_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(artifact_id)
            row = db.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
        return self._public(row, include_html=True)

    def delete(self, artifact_id: str) -> None:
        with self._connect() as db:
            cursor = db.execute("DELETE FROM artifacts WHERE id=?", (artifact_id,))
            if cursor.rowcount == 0:
                raise KeyError(artifact_id)
