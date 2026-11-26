"""Inspectable, provenance-aware long-term memory for GENESIS CORE.

Memory is deliberately explicit: this module never promotes model output to a fact
on its own. Callers must choose the memory type and provide provenance.
"""
from __future__ import annotations

import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from genesis_core.state import StateStore

MEMORY_TYPES = {"episodic", "semantic", "procedural"}
MEMORY_STATUSES = {"active", "inactive"}


class MemoryError(ValueError):
    """Raised when a memory record is invalid or cannot be changed."""


class MemoryStore:
    """SQLite memory records with provenance, confidence and user controls."""

    def __init__(self, state: StateStore | None = None) -> None:
        self.database_path: Path = (state or StateStore()).database_path
        self._initialise()

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

    def _initialise(self) -> None:
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    memory_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_ref TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0.5,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_type_status "
                "ON memories(memory_type, status, updated_at)"
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def add(
        self,
        memory_type: str,
        content: str,
        source_type: str = "user",
        source_ref: str = "",
        confidence: float = 0.8,
    ) -> dict[str, Any]:
        if memory_type not in MEMORY_TYPES:
            raise MemoryError(f"Unknown memory type: {memory_type}")
        content = content.strip()
        source_type = source_type.strip()
        if not content or len(content) > 4000:
            raise MemoryError("Memory content must contain 1 to 4000 characters.")
        if not source_type or len(source_type) > 80:
            raise MemoryError("A source_type of 1 to 80 characters is required.")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            raise MemoryError("Confidence must be a number between 0 and 1.")
        now = self._now()
        item = {
            "id": uuid.uuid4().hex[:12], "memory_type": memory_type,
            "content": content, "source_type": source_type,
            "source_ref": source_ref.strip()[:500], "confidence": float(confidence),
            "status": "active", "created_at": now, "updated_at": now,
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO memories VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                tuple(item.values()),
            )
        return item

    def get(self, memory_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return dict(row) if row else None

    def list(
        self, memory_type: str | None = None, status: str = "active", limit: int = 100
    ) -> list[dict[str, Any]]:
        if memory_type is not None and memory_type not in MEMORY_TYPES:
            raise MemoryError(f"Unknown memory type: {memory_type}")
        if status not in MEMORY_STATUSES:
            raise MemoryError(f"Unknown memory status: {status}")
        query = "SELECT * FROM memories WHERE status = ?"
        params: list[Any] = [status]
        if memory_type:
            query += " AND memory_type = ?"
            params.append(memory_type)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        with self._connect() as db:
            rows = db.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        terms = list(dict.fromkeys(re.findall(r"[a-zA-Z0-9_'-]{2,}", query.lower())))[:12]
        if not terms:
            return []
        candidates = self.list(status="active", limit=500)
        scored: list[tuple[int, str, dict[str, Any]]] = []
        for item in candidates:
            haystack = (item["content"] + " " + item["source_ref"]).lower()
            score = sum(3 if term in item["content"].lower() else 1 for term in terms if term in haystack)
            if score:
                scored.append((score, item["updated_at"], item))
        scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return [item for _, _, item in scored[:max(1, min(limit, 30))]]

    def set_status(self, memory_id: str, status: str) -> dict[str, Any]:
        if status not in MEMORY_STATUSES:
            raise MemoryError(f"Unknown memory status: {status}")
        if self.get(memory_id) is None:
            raise KeyError(memory_id)
        with self._connect() as db:
            db.execute(
                "UPDATE memories SET status = ?, updated_at = ? WHERE id = ?",
                (status, self._now(), memory_id),
            )
        return self.get(memory_id)  # type: ignore[return-value]

    def delete(self, memory_id: str) -> None:
        with self._connect() as db:
            cursor = db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            if cursor.rowcount == 0:
                raise KeyError(memory_id)


__all__ = ["MEMORY_TYPES", "MEMORY_STATUSES", "MemoryError", "MemoryStore"]
