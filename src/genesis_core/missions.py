"""Persistent mission and goal tracking for GENESIS CORE."""

from __future__ import annotations

import json
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
TASK_STATUSES = {"planned", "running", "blocked", "completed", "failed"}


class MissionError(ValueError):
    """Raised when a mission cannot be created or transitioned."""


class MissionStore:
    """SQLite mission queue and durable task plans sharing conversation storage."""

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
                CREATE TABLE IF NOT EXISTS missions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 3,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    session_id TEXT
                )
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(missions)")}
            if "session_id" not in columns:
                db.execute("ALTER TABLE missions ADD COLUMN session_id TEXT")
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_missions_status_updated "
                "ON missions(status, updated_at)"
            )
            db.execute("""
                CREATE TABLE IF NOT EXISTS mission_tasks (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    instructions TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(mission_id, position)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS mission_plan_revisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mission_id TEXT NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
                    version INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(mission_id, version)
                )
            """)
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_mission_tasks_status "
                "ON mission_tasks(mission_id, status, position)"
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create(self, title: str, description: str = "", priority: int = 3) -> dict[str, Any]:
        title = title.strip()
        if not title:
            raise MissionError("Mission title cannot be empty.")
        if not 1 <= priority <= 5:
            raise MissionError("Priority must be between 1 (highest) and 5 (lowest).")
        now = self._now()
        item = {
            "id": uuid.uuid4().hex[:12], "title": title[:160],
            "description": description.strip()[:10000], "status": "planned",
            "priority": priority, "created_at": now, "updated_at": now,
            "session_id": None,
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO missions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
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
            raise MissionError(f"Cannot change mission from {current['status']} to {status}.")
        now = self._now()
        with self._connect() as db:
            db.execute(
                "UPDATE missions SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, mission_id),
            )
        return self.get(mission_id) or current

    def save_plan(
        self, mission_id: str, session_id: str, tasks: list[dict[str, str]],
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not tasks or len(tasks) > 8:
            raise MissionError("A mission plan must contain between 1 and 8 tasks.")
        now = self._now()
        with self._connect() as db:
            if not db.execute("SELECT 1 FROM missions WHERE id = ?", (mission_id,)).fetchone():
                raise KeyError(mission_id)
            count = db.execute(
                "SELECT COUNT(*) FROM mission_tasks WHERE mission_id = ?", (mission_id,)
            ).fetchone()[0]
            if count:
                raise MissionError("A plan already exists for this mission.")
            db.execute(
                "UPDATE missions SET session_id = ?, updated_at = ? WHERE id = ?",
                (session_id, now, mission_id),
            )
            self._save_revision(db, mission_id, "initial plan", {"tasks": tasks, "metadata": metadata or {}})
            for position, task in enumerate(tasks, start=1):
                db.execute(
                    "INSERT INTO mission_tasks "
                    "(id, mission_id, position, title, instructions, status, result, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, 'planned', '', ?, ?)",
                    (uuid.uuid4().hex[:12], mission_id, position,
                     task["title"], task["instructions"], now, now),
                )
        return self.list_tasks(mission_id)

    def _save_revision(self, db: sqlite3.Connection, mission_id: str,
                       reason: str, plan: dict[str, Any]) -> int:
        version = db.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM mission_plan_revisions WHERE mission_id=?",
            (mission_id,),
        ).fetchone()[0]
        db.execute(
            "INSERT INTO mission_plan_revisions(mission_id, version, reason, plan_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (mission_id, version, reason, json.dumps(plan, ensure_ascii=False), self._now()),
        )
        return version

    def plan_history(self, mission_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            if not db.execute("SELECT 1 FROM missions WHERE id=?", (mission_id,)).fetchone():
                raise KeyError(mission_id)
            rows = db.execute(
                "SELECT version, reason, plan_json, created_at FROM mission_plan_revisions "
                "WHERE mission_id=? ORDER BY version", (mission_id,)
            ).fetchall()
        return [{
            "version": row["version"], "reason": row["reason"],
            "plan": json.loads(row["plan_json"]), "created_at": row["created_at"],
        } for row in rows]

    def replan_remaining(self, mission_id: str, tasks: list[dict[str, str]],
                         metadata: dict[str, Any], reason: str) -> list[dict[str, Any]]:
        if not tasks or len(tasks) > 8:
            raise MissionError("A revised plan must contain between 1 and 8 remaining tasks.")
        with self._connect() as db:
            mission = db.execute("SELECT status FROM missions WHERE id=?", (mission_id,)).fetchone()
            if mission is None:
                raise KeyError(mission_id)
            if mission["status"] != "blocked":
                raise MissionError("Only blocked missions can be replanned.")
            rows = db.execute(
                "SELECT * FROM mission_tasks WHERE mission_id=? ORDER BY position", (mission_id,)
            ).fetchall()
            if not any(row["status"] == "blocked" for row in rows):
                raise MissionError("There is no blocked task to replan.")
            snapshot = {"tasks": [dict(row) for row in rows], "metadata": metadata}
            self._save_revision(db, mission_id, reason, snapshot)
            db.execute(
                "DELETE FROM mission_tasks WHERE mission_id=? AND status!='completed'",
                (mission_id,),
            )
            next_position = db.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 FROM mission_tasks WHERE mission_id=?",
                (mission_id,),
            ).fetchone()[0]
            now = self._now()
            for offset, task in enumerate(tasks):
                db.execute(
                    "INSERT INTO mission_tasks "
                    "(id, mission_id, position, title, instructions, status, result, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, 'planned', '', ?, ?)",
                    (uuid.uuid4().hex[:12], mission_id, next_position + offset,
                     task["title"], task["instructions"], now, now),
                )
            db.execute("UPDATE missions SET updated_at=? WHERE id=?", (now, mission_id))
        return self.list_tasks(mission_id)

    def list_tasks(self, mission_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM mission_tasks WHERE mission_id = ? ORDER BY position",
                (mission_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM mission_tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def set_task_status(
        self, task_id: str, status: str, result: str | None = None
    ) -> dict[str, Any]:
        if status not in TASK_STATUSES:
            raise MissionError(f"Unknown task status: {status}")
        current = self.get_task(task_id)
        if current is None:
            raise KeyError(task_id)
        now = self._now()
        with self._connect() as db:
            if result is None:
                db.execute(
                    "UPDATE mission_tasks SET status = ?, updated_at = ? WHERE id = ?",
                    (status, now, task_id),
                )
            else:
                db.execute(
                    "UPDATE mission_tasks SET status = ?, result = ?, updated_at = ? WHERE id = ?",
                    (status, result[:20000], now, task_id),
                )
        return self.get_task(task_id) or current


__all__ = ["MissionError", "MissionStore", "STATUSES", "TASK_STATUSES"]
