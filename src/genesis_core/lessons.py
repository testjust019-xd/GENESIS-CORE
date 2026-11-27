"""Evidence-linked candidate lessons derived from recorded GENESIS experiences.

A lesson is a reviewable hypothesis, not a fact, skill, training example, or
model update. Approval records human acceptance of the lesson only.
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from genesis_core.experience import ExperienceStore


class LessonError(ValueError):
    """Invalid lesson content or lifecycle transition."""


class LessonStore:
    STATUSES = {"draft", "pending", "approved", "rejected"}

    def __init__(self, database_path: str | Path, experiences: ExperienceStore | None = None) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.experiences = experiences or ExperienceStore()
        with sqlite3.connect(self.database_path, timeout=10) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS lessons (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    applicability TEXT NOT NULL,
                    limitations TEXT NOT NULL,
                    evidence_ids TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_lessons_status ON lessons(status, updated_at DESC)")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _text(value: str, field: str, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
            raise LessonError(f"{field} must contain 1–{maximum} characters.")
        return value.strip()

    def create(
        self,
        *,
        title: str,
        statement: str,
        rationale: str,
        applicability: str,
        limitations: str,
        evidence_ids: list[str],
    ) -> dict[str, Any]:
        title = self._text(title, "Title", 160)
        statement = self._text(statement, "Lesson", 2000)
        rationale = self._text(rationale, "Rationale", 3000)
        applicability = self._text(applicability, "Applicability", 2000)
        limitations = self._text(limitations, "Limitations", 2000)
        if not isinstance(evidence_ids, list) or not 1 <= len(evidence_ids) <= 20:
            raise LessonError("A lesson must cite between 1 and 20 source experiences.")
        if any(not isinstance(item, str) or not re.fullmatch(r"[a-f0-9]{16}", item) for item in evidence_ids):
            raise LessonError("Evidence references must be valid experience IDs.")
        ids = list(dict.fromkeys(evidence_ids))
        if len(ids) != len(evidence_ids):
            raise LessonError("Duplicate evidence references are not allowed.")
        missing = [item for item in ids if self.experiences.get(item) is None]
        if missing:
            raise LessonError("Unknown source experience(s): " + ", ".join(missing))
        now, lesson_id = self._now(), uuid.uuid4().hex[:16]
        with sqlite3.connect(self.database_path, timeout=10) as db:
            db.execute(
                "INSERT INTO lessons VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)",
                (lesson_id, title, statement, rationale, applicability, limitations,
                 json.dumps(ids), now, now),
            )
        return self.get(lesson_id)  # type: ignore[return-value]

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["evidence_ids"] = json.loads(item["evidence_ids"])
        return item

    def get(self, lesson_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.database_path, timeout=10) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM lessons WHERE id=?", (lesson_id,)).fetchone()
        if row is None:
            return None
        item = self._decode(row)
        item["evidence"] = [self.experiences.get(ref) for ref in item["evidence_ids"]]
        return item

    def list(self, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if status is not None and status not in self.STATUSES:
            raise LessonError("Unknown lesson status.")
        with sqlite3.connect(self.database_path, timeout=10) as db:
            db.row_factory = sqlite3.Row
            if status:
                rows = db.execute(
                    "SELECT * FROM lessons WHERE status=? ORDER BY updated_at DESC LIMIT ?",
                    (status, max(1, min(int(limit), 200))),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM lessons ORDER BY updated_at DESC LIMIT ?",
                    (max(1, min(int(limit), 200)),),
                ).fetchall()
        result = []
        for row in rows:
            item = self._decode(row)
            item["evidence"] = [self.experiences.get(ref) for ref in item["evidence_ids"]]
            result.append(item)
        return result

    def submit(self, lesson_id: str) -> dict[str, Any]:
        current = self.get(lesson_id)
        if current is None:
            raise KeyError(lesson_id)
        if current["status"] != "draft":
            raise LessonError("Only draft lessons can be submitted for review.")
        self._set_status(lesson_id, "pending")
        return self.get(lesson_id)  # type: ignore[return-value]

    def review(self, lesson_id: str, decision: str) -> dict[str, Any]:
        current = self.get(lesson_id)
        if current is None:
            raise KeyError(lesson_id)
        if current["status"] != "pending":
            raise LessonError("Only pending lessons can be reviewed.")
        if decision not in {"approve", "reject"}:
            raise LessonError("Decision must be approve or reject.")
        self._set_status(lesson_id, "approved" if decision == "approve" else "rejected")
        return self.get(lesson_id)  # type: ignore[return-value]

    def _set_status(self, lesson_id: str, status: str) -> None:
        with sqlite3.connect(self.database_path, timeout=10) as db:
            db.execute(
                "UPDATE lessons SET status=?, updated_at=? WHERE id=?",
                (status, self._now(), lesson_id),
            )


__all__ = ["LessonError", "LessonStore"]
