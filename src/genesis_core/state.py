"""Shared persistent state used by every GENESIS interface."""

from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def default_database_path() -> Path:
    home = Path(os.environ.get("GENESIS_HOME", Path.home() / ".genesis"))
    return home / "data" / "genesis.db"


class StateStore:
    """Small SQLite-backed source of truth for sessions and messages."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path else default_database_path()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialise(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            db.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id)")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, title, created_at, updated_at FROM sessions "
                "ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_session(self, title: str = "New conversation") -> dict[str, Any]:
        now = self._now()
        item = {"id": uuid.uuid4().hex[:12], "title": title.strip()[:120] or "New conversation",
                "created_at": now, "updated_at": now}
        with self._connect() as db:
            db.execute(
                "INSERT INTO sessions(id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (item["id"], item["title"], now, now),
            )
        return item

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT id, title, created_at, updated_at FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, session_id, role, content, created_at FROM messages "
                "WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_message(self, session_id: str, role: str, content: str) -> dict[str, Any]:
        if role not in {"user", "assistant", "system"}:
            raise ValueError("Unsupported message role")
        if not content.strip():
            raise ValueError("Message content cannot be empty")
        now = self._now()
        with self._connect() as db:
            exists = db.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not exists:
                raise KeyError(session_id)
            cursor = db.execute(
                "INSERT INTO messages(session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (session_id, role, content.strip(), now),
            )
            db.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
            if role == "user":
                count = db.execute(
                    "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
                ).fetchone()[0]
                if count == 1:
                    title = content.strip().replace("\n", " ")[:60]
                    db.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))
        return {"id": cursor.lastrowid, "session_id": session_id, "role": role,
                "content": content.strip(), "created_at": now}
