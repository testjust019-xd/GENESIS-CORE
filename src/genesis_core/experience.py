"""Evidence-preserving experience records for GENESIS CORE.

Task observations are captured as raw, attributable experience. They are not
automatically promoted to facts, skills, training data, or model updates.
"""
from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from genesis_core.state import StateStore

EXPERIENCE_OUTCOMES = {"completed", "blocked", "failed"}
EXPERIENCE_STATUSES = {"captured", "reviewed", "archived"}


class ExperienceError(ValueError):
    """Raised when an experience record is invalid."""


class ExperienceStore:
    """Persistent, provenance-aware records of agent task experiences."""

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
                CREATE TABLE IF NOT EXISTS experiences (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    instructions TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    result TEXT NOT NULL,
                    observer_summary TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'captured',
                    created_at TEXT NOT NULL
                )
            """)
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_experiences_created "
                "ON experiences(created_at DESC)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_experiences_mission "
                "ON experiences(mission_id, task_id)"
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def capture_task_result(
        self,
        *,
        mission_id: str,
        task_id: str,
        title: str,
        objective: str,
        instructions: str,
        outcome: str,
        result: str,
        observer_summary: str,
        confidence: float,
    ) -> dict[str, Any]:
        """Capture one task attempt without claiming that it taught the model."""
        required = {
            "mission_id": mission_id, "task_id": task_id, "title": title,
            "objective": objective, "instructions": instructions,
            "result": result, "observer_summary": observer_summary,
        }
        if any(not isinstance(value, str) or not value.strip() for value in required.values()):
            raise ExperienceError("Experience fields must be non-empty text.")
        if not isinstance(outcome, str) or outcome not in EXPERIENCE_OUTCOMES:
            raise ExperienceError(f"Unsupported experience outcome: {outcome}")
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0 <= confidence <= 1
        ):
            raise ExperienceError("Confidence must be a number between 0 and 1.")

        item = {
            "id": uuid.uuid4().hex[:16],
            "mission_id": mission_id[:64],
            "task_id": task_id[:64],
            "title": title.strip()[:160],
            "objective": objective.strip()[:2000],
            "instructions": instructions.strip()[:4000],
            "outcome": outcome,
            "result": result.strip()[:12000],
            "observer_summary": observer_summary.strip()[:2000],
            "confidence": float(confidence),
            "status": "captured",
            "created_at": self._now(),
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO experiences "
                "(id, mission_id, task_id, title, objective, instructions, outcome, "
                "result, observer_summary, confidence, status, created_at) "
                "VALUES (:id, :mission_id, :task_id, :title, :objective, :instructions, "
                ":outcome, :result, :observer_summary, :confidence, :status, :created_at)",
                item,
            )
        return item

    def get(self, experience_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM experiences WHERE id = ?", (experience_id,)
            ).fetchone()
        return dict(row) if row else None

    def list(
        self,
        *,
        status: str | None = None,
        outcome: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if status is not None and (
            not isinstance(status, str) or status not in EXPERIENCE_STATUSES
        ):
            raise ExperienceError(f"Unsupported experience status: {status}")
        if outcome is not None and (
            not isinstance(outcome, str) or outcome not in EXPERIENCE_OUTCOMES
        ):
            raise ExperienceError(f"Unsupported experience outcome: {outcome}")
        clauses: list[str] = []
        values: list[Any] = []
        if status:
            clauses.append("status = ?")
            values.append(status)
        if outcome:
            clauses.append("outcome = ?")
            values.append(outcome)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        values.append(max(1, min(int(limit), 200)))
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM experiences" + where +
                " ORDER BY created_at DESC LIMIT ?", values
            ).fetchall()
        return [dict(row) for row in rows]

    def set_status(self, experience_id: str, status: str) -> dict[str, Any]:
        if not isinstance(status, str) or status not in EXPERIENCE_STATUSES:
            raise ExperienceError(f"Unsupported experience status: {status}")
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE experiences SET status = ? WHERE id = ?",
                (status, experience_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(experience_id)
        return self.get(experience_id)  # type: ignore[return-value]


__all__ = [
    "EXPERIENCE_OUTCOMES", "EXPERIENCE_STATUSES", "ExperienceError", "ExperienceStore",
]
