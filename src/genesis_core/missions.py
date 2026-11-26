"""Persistent mission and goal tracking for GENESIS CORE."""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from genesis_core.state import StateStore

STATUSES = {"planned", "running", "blocked", "completed", "failed", "cancelled"}
TRANSITIONS = {
    "planned": {"running", "cancelled"},
    "running": {"blocked", "completed", "failed", "cancelled"},
    "blocked": {"running", "cancelled"},
    "failed": {"planned", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


class MissionError(ValueError):
    """Raised when a mission cannot be created or transitioned."""


class MissionStore:
    """SQLite mission queue sharing the same database as conversations."""

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
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS missions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 3,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_missions_status_updated "
                "ON missions(status, updated_at)"
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create(
        self, title: str, description: str = "", priority: int = 3
    ) -> dict[str, Any]:
        title = title.strip()
        if not title:
            raise MissionError("Mission title cannot be empty.")
        if not 1 <= priority <= 5:
            raise MissionError("Priority must be between 1 (highest) and 5 (lowest).")
        now = self._now()
        item = {
            "id": uuid.uuid4().hex[:12],
            "title": title[:160],
            "description": description.strip()[:10000],
            "status": "planned",
            "priority": priority,
            "created_at": now,
            "updated_at": now,
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO missions VALUES (?, ?, ?, ?, ?, ?, ?)",
                tuple(item.values()),
            )
        return item

    def list(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if status is not None and status not in STATUSES:
            raise MissionError(f"Unknown mission status: {status}")
        with self._connect() as db:
            if status:
                rows = db.execute(
                    "SELECT * FROM missions WHERE status = ? "
                    "ORDER BY priority ASC, updated_at DESC LIMIT ?",
                    (status, max(1, min(limit, 500))),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM missions ORDER BY priority ASC, updated_at DESC LIMIT ?",
                    (max(1, min(limit, 500)),),
                ).fetchall()
        return [dict(row) for row in rows]

    def get(self, mission_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM missions WHERE id = ?", (mission_id,)).fetchone()
        return dict(row) if row else None

    def set_status(self, mission_id: str, status: str) -> dict[str, Any]:
        if status not in STATUSES:
            raise MissionError(f"Unknown mission status: {status}")
        current = self.get(mission_id)
        if current is None:
            raise KeyError(mission_id)
        if status == current["status"]:
            return current
        if status not in TRANSITIONS[current["status"]]:
            raise MissionError(
                f"Cannot change mission from {current['status']} to {status}."
            )
        now = self._now()
        with self._connect() as db:
            db.execute(
                "UPDATE missions SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, mission_id),
            )
        return self.get(mission_id) or current


__all__ = ["MissionError", "MissionStore", "STATUSES"]
