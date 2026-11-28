"""Evidence-guided evolution from repeated, attributable task experiences.

This module proposes reviewable lessons; it never changes model weights, activates
skills, or treats an unreviewed observation as truth.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from genesis_core.experience import ExperienceStore
from genesis_core.skills import SkillStore
from genesis_core.state import StateStore


class EvolutionError(ValueError):
    """Invalid evolution request or lifecycle transition."""


class EvolutionEngine:
    """Turn repeated task evidence into human-reviewed lesson proposals."""

    STATUSES = {"pending", "accepted", "rejected"}

    def __init__(
        self,
        state: StateStore | None = None,
        experiences: ExperienceStore | None = None,
    ) -> None:
        self.state = state or StateStore()
        self.database_path: Path = self.state.database_path
        self.experiences = experiences or ExperienceStore(self.state)
        self._initialise()

    def _initialise(self) -> None:
        with sqlite3.connect(self.database_path, timeout=10) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS evolution_proposals (
                    id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    pattern TEXT NOT NULL,
                    evidence_ids TEXT NOT NULL,
                    evidence_count INTEGER NOT NULL,
                    completed_count INTEGER NOT NULL,
                    blocked_count INTEGER NOT NULL,
                    failed_count INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    decision_note TEXT NOT NULL DEFAULT '',
                    skill_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL DEFAULT ''
                )
            """)
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_evolution_status "
                "ON evolution_proposals(status, created_at DESC)"
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _fingerprint(item: dict[str, Any]) -> str:
        # Exact normalized task context avoids speculative semantic clustering.
        text = " ".join(
            f"{item['objective']} {item['instructions']}".lower().split()
        )
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["evidence_ids"] = json.loads(item["evidence_ids"])
        item["evidence_count"] = int(item["evidence_count"])
        item["completed_count"] = int(item["completed_count"])
        item["blocked_count"] = int(item["blocked_count"])
        item["failed_count"] = int(item["failed_count"])
        item["confidence"] = float(item["confidence"])
        return item

    def analyze(self, *, min_support: int = 2, limit: int = 200) -> dict[str, Any]:
        """Create/update pending proposals for repeated, identical task contexts."""
        if isinstance(min_support, bool) or not isinstance(min_support, int) or not 2 <= min_support <= 20:
            raise EvolutionError("min_support must be an integer between 2 and 20.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise EvolutionError("limit must be an integer between 1 and 200.")

        records = self.experiences.list(limit=limit)
        groups: dict[str, list[dict[str, Any]]] = {}
        for item in records:
            if item["status"] == "archived":
                continue
            groups.setdefault(self._fingerprint(item), []).append(item)

        created = updated = skipped = 0
        now = self._now()
        with sqlite3.connect(self.database_path, timeout=10) as db:
            db.row_factory = sqlite3.Row
            for fingerprint, evidence in groups.items():
                if len(evidence) < min_support:
                    skipped += 1
                    continue
                counts = {
                    outcome: sum(item["outcome"] == outcome for item in evidence)
                    for outcome in ("completed", "blocked", "failed")
                }
                confidence = counts["completed"] / len(evidence)
                first = evidence[-1]
                title = f"Repeated pattern: {first['title']}"[:160]
                # This is an evidence summary, deliberately not an invented recipe.
                pattern = (
                    f"Same normalized objective and instructions appeared {len(evidence)} times. "
                    f"Observed outcomes: {counts['completed']} completed, "
                    f"{counts['blocked']} blocked, {counts['failed']} failed. "
                    "Review the linked observations before adopting any reusable guidance."
                )
                evidence_ids = json.dumps([item["id"] for item in evidence])
                existing = db.execute(
                    "SELECT id, status FROM evolution_proposals WHERE fingerprint = ?",
                    (fingerprint,),
                ).fetchone()
                if existing is None:
                    db.execute("""
                        INSERT INTO evolution_proposals
                        (id, fingerprint, title, pattern, evidence_ids, evidence_count,
                         completed_count, blocked_count, failed_count, confidence,
                         status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                    """, (
                        uuid.uuid4().hex[:16], fingerprint, title, pattern, evidence_ids,
                        len(evidence), counts["completed"], counts["blocked"],
                        counts["failed"], confidence, now,
                    ))
                    created += 1
                elif existing["status"] == "pending":
                    db.execute("""
                        UPDATE evolution_proposals
                        SET title=?, pattern=?, evidence_ids=?, evidence_count=?,
                            completed_count=?, blocked_count=?, failed_count=?, confidence=?
                        WHERE fingerprint=?
                    """, (
                        title, pattern, evidence_ids, len(evidence), counts["completed"],
                        counts["blocked"], counts["failed"], confidence, fingerprint,
                    ))
                    updated += 1
                else:
                    skipped += 1
        return {
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "groups_found": len(groups),
            "proposals": self.list(status="pending"),
        }

    def list(self, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if status is not None and status not in self.STATUSES:
            raise EvolutionError(f"Unsupported proposal status: {status}")
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise EvolutionError("limit must be an integer.")
        clauses, values = [], []
        if status:
            clauses.append("status = ?")
            values.append(status)
        values.append(max(1, min(limit, 200)))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with sqlite3.connect(self.database_path, timeout=10) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT * FROM evolution_proposals" + where
                + " ORDER BY created_at DESC LIMIT ?", values,
            ).fetchall()
        return [self._decode(row) for row in rows]

    def get(self, proposal_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.database_path, timeout=10) as db:
            db.row_factory = sqlite3.Row
            row = db.execute(
                "SELECT * FROM evolution_proposals WHERE id = ?", (proposal_id,)
            ).fetchone()
        return self._decode(row) if row else None

    def decide(self, proposal_id: str, decision: str, note: str = "") -> dict[str, Any]:
        if decision not in {"accept", "reject"}:
            raise EvolutionError("Decision must be accept or reject.")
        if not isinstance(note, str) or len(note) > 1000:
            raise EvolutionError("Decision note must be at most 1,000 characters.")
        current = self.get(proposal_id)
        if current is None:
            raise KeyError(proposal_id)
        if current["status"] != "pending":
            raise EvolutionError("Only pending proposals can be reviewed.")
        status = "accepted" if decision == "accept" else "rejected"
        with sqlite3.connect(self.database_path, timeout=10) as db:
            db.execute(
                "UPDATE evolution_proposals SET status=?, decision_note=?, reviewed_at=? "
                "WHERE id=? AND status='pending'",
                (status, note.strip(), self._now(), proposal_id),
            )
        return self.get(proposal_id)  # type: ignore[return-value]

    def promote_to_skill_draft(
        self, proposal_id: str, skills: SkillStore
    ) -> dict[str, Any]:
        """Create a non-active Skill draft from an accepted proposal and its evidence."""
        proposal = self.get(proposal_id)
        if proposal is None:
            raise KeyError(proposal_id)
        if proposal["status"] != "accepted":
            raise EvolutionError("A proposal must be accepted before draft promotion.")
        if Path(skills.database_path) != self.database_path:
            raise EvolutionError("Evolution proposals and skills must share the same database.")
        if proposal["skill_id"]:
            existing = skills.get(proposal["skill_id"])
            if existing is not None:
                return existing

        evidence = [
            self.experiences.get(item_id)
            for item_id in proposal["evidence_ids"]
        ]
        evidence = [item for item in evidence if item is not None]
        if len(evidence) < 2:
            raise EvolutionError("At least two source experiences must still exist.")
        source_lines = [
            f"- {item['outcome']}: {item['observer_summary'][:240]}"
            for item in evidence
        ]
        instructions = (
            "This is an evidence-backed reference draft, not an automatically verified rule. "
            "Check the task context and current evidence before applying it. "
            "Do not claim that this skill guarantees success.\n\n"
            f"Observed pattern: {proposal['pattern']}\n"
            "Source observations:\n" + "\n".join(source_lines)
        )
        skill = skills.create(
            name=proposal["title"][:100],
            description=(
                f"Human-reviewed evidence pattern from {len(evidence)} task attempts."
            )[:500],
            instructions=instructions[:12000],
            allowed_tools=[],
            checklist=[
                "Verify that the task context matches the source experiences.",
                "Check successful and unsuccessful observations.",
                "Confirm the guidance is still accurate before activation.",
            ],
        )
        with sqlite3.connect(self.database_path, timeout=10) as db:
            db.execute(
                "UPDATE evolution_proposals SET skill_id=? WHERE id=?",
                (skill["id"], proposal_id),
            )
        return skill


__all__ = ["EvolutionEngine", "EvolutionError"]
