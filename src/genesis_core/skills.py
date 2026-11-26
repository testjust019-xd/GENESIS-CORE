"""Declarative, review-gated skill library for GENESIS CORE.

Skills contain instructions and metadata only. They never execute code; any tool
use remains subject to the existing ToolRegistry and PermissionManager.
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SkillError(ValueError):
    """Invalid skill content or lifecycle transition."""


class SkillStore:
    STATUSES = {"draft", "pending", "active", "disabled"}

    def __init__(self, database_path: str | Path, tool_names: set[str] | None = None) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.tool_names = tool_names
        with sqlite3.connect(self.database_path) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS skills (
                    id TEXT PRIMARY KEY,
                    slug TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    instructions TEXT NOT NULL,
                    allowed_tools TEXT NOT NULL,
                    checklist TEXT NOT NULL,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS skill_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    manifest TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(skill_id, version)
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_skills_status ON skills(status)")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
        if not slug or len(slug) > 64:
            raise SkillError("Skill slug must contain 1–64 lowercase letters, numbers or hyphens.")
        return slug

    def _validate(self, name: str, description: str, instructions: str,
                  allowed_tools: list[str], checklist: list[str]) -> tuple[str, list[str], list[str]]:
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise SkillError("Skill name must contain 1–100 characters.")
        if not isinstance(description, str) or not description.strip() or len(description) > 500:
            raise SkillError("Description must contain 1–500 characters.")
        if not isinstance(instructions, str) or not instructions.strip() or len(instructions) > 12000:
            raise SkillError("Instructions must contain 1–12,000 characters.")
        if not isinstance(allowed_tools, list) or len(allowed_tools) > 30:
            raise SkillError("allowed_tools must be a list of at most 30 tool names.")
        if any(not isinstance(item, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,64}", item)
               for item in allowed_tools):
            raise SkillError("Allowed tool names may contain only letters, numbers and underscores.")
        allowed_tools = sorted(set(allowed_tools))
        if self.tool_names is not None:
            unknown = set(allowed_tools) - self.tool_names
            if unknown:
                raise SkillError("Unknown registered tool(s): " + ", ".join(sorted(unknown)))
        if not isinstance(checklist, list) or len(checklist) > 20:
            raise SkillError("A review checklist may contain at most 20 items.")
        if any(not isinstance(item, str) or not item.strip() or len(item) > 300
               for item in checklist):
            raise SkillError("Each checklist item must contain 1–300 characters.")
        return self._slug(name), allowed_tools, [item.strip() for item in checklist]

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["allowed_tools"] = json.loads(item["allowed_tools"])
        item["checklist"] = json.loads(item["checklist"])
        return item

    def create(self, name: str, description: str, instructions: str,
               allowed_tools: list[str] | None = None,
               checklist: list[str] | None = None) -> dict[str, Any]:
        slug, tools, checks = self._validate(
            name, description, instructions, allowed_tools or [], checklist or []
        )
        now, skill_id = self._now(), uuid.uuid4().hex[:12]
        manifest = {
            "slug": slug, "name": name.strip(), "description": description.strip(),
            "instructions": instructions.strip(), "allowed_tools": tools,
            "checklist": checks,
        }
        with sqlite3.connect(self.database_path) as db:
            try:
                db.execute(
                    "INSERT INTO skills VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', 1, ?, ?)",
                    (skill_id, slug, manifest["name"], manifest["description"],
                     manifest["instructions"], json.dumps(tools), json.dumps(checks), now, now),
                )
                db.execute(
                    "INSERT INTO skill_versions(skill_id, version, manifest, created_at) "
                    "VALUES (?, 1, ?, ?)", (skill_id, json.dumps(manifest), now),
                )
            except sqlite3.IntegrityError as exc:
                raise SkillError(f"A skill named '{slug}' already exists.") from exc
        return self.get(skill_id)  # type: ignore[return-value]

    def get(self, skill_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.database_path) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM skills WHERE id = ? OR slug = ?",
                             (skill_id, skill_id)).fetchone()
        return self._decode(row) if row else None

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        if status is not None and status not in self.STATUSES:
            raise SkillError("Unknown skill status.")
        with sqlite3.connect(self.database_path) as db:
            db.row_factory = sqlite3.Row
            if status is None:
                rows = db.execute("SELECT * FROM skills ORDER BY name COLLATE NOCASE").fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM skills WHERE status = ? ORDER BY name COLLATE NOCASE",
                    (status,),
                ).fetchall()
        return [self._decode(row) for row in rows]

    def update(self, skill_id: str, *, description: str | None = None,
               instructions: str | None = None, allowed_tools: list[str] | None = None,
               checklist: list[str] | None = None) -> dict[str, Any]:
        current = self.get(skill_id)
        if current is None:
            raise KeyError(skill_id)
        if current["status"] == "active":
            raise SkillError("Deactivate an active skill before editing it.")
        values = {
            "description": description if description is not None else current["description"],
            "instructions": instructions if instructions is not None else current["instructions"],
            "allowed_tools": allowed_tools if allowed_tools is not None else current["allowed_tools"],
            "checklist": checklist if checklist is not None else current["checklist"],
        }
        _, tools, checks = self._validate(
            current["name"], values["description"], values["instructions"],
            values["allowed_tools"], values["checklist"],
        )
        version = current["version"] + 1
        manifest = {
            "slug": current["slug"], "name": current["name"],
            "description": values["description"].strip(),
            "instructions": values["instructions"].strip(),
            "allowed_tools": tools, "checklist": checks,
        }
        now = self._now()
        with sqlite3.connect(self.database_path) as db:
            db.execute(
                "UPDATE skills SET description=?, instructions=?, allowed_tools=?, checklist=?, "
                "status='draft', version=?, updated_at=? WHERE id=?",
                (manifest["description"], manifest["instructions"], json.dumps(tools),
                 json.dumps(checks), version, now, current["id"]),
            )
            db.execute(
                "INSERT INTO skill_versions(skill_id, version, manifest, created_at) "
                "VALUES (?, ?, ?, ?)",
                (current["id"], version, json.dumps(manifest), now),
            )
        return self.get(current["id"])  # type: ignore[return-value]

    def submit(self, skill_id: str) -> dict[str, Any]:
        current = self.get(skill_id)
        if current is None:
            raise KeyError(skill_id)
        if current["status"] not in {"draft", "disabled"}:
            raise SkillError("Only draft or disabled skills can be submitted for review.")
        if not current["checklist"]:
            raise SkillError("A review checklist is required.")
        self._set_status(current["id"], "pending")
        return self.get(current["id"])  # type: ignore[return-value]

    def review(self, skill_id: str, decision: str) -> dict[str, Any]:
        current = self.get(skill_id)
        if current is None:
            raise KeyError(skill_id)
        if current["status"] != "pending":
            raise SkillError("Only pending skills can be reviewed.")
        if decision not in {"approve", "reject"}:
            raise SkillError("Decision must be approve or reject.")
        self._set_status(current["id"], "active" if decision == "approve" else "draft")
        return self.get(current["id"])  # type: ignore[return-value]

    def disable(self, skill_id: str) -> dict[str, Any]:
        current = self.get(skill_id)
        if current is None:
            raise KeyError(skill_id)
        if current["status"] != "active":
            raise SkillError("Only active skills can be disabled.")
        self._set_status(current["id"], "disabled")
        return self.get(current["id"])  # type: ignore[return-value]

    def _set_status(self, skill_id: str, status: str) -> None:
        with sqlite3.connect(self.database_path) as db:
            db.execute("UPDATE skills SET status=?, updated_at=? WHERE id=?",
                       (status, self._now(), skill_id))

    def versions(self, skill_id: str) -> list[dict[str, Any]]:
        current = self.get(skill_id)
        if current is None:
            raise KeyError(skill_id)
        with sqlite3.connect(self.database_path) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT version, manifest, created_at FROM skill_versions "
                "WHERE skill_id=? ORDER BY version", (current["id"],)
            ).fetchall()
        return [{"version": row["version"], "manifest": json.loads(row["manifest"]),
                 "created_at": row["created_at"]} for row in rows]

    def relevant(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        """Return active skills with simple deterministic lexical relevance."""
        terms = {word.lower() for word in re.findall(r"[A-Za-z0-9_-]{3,}", query)}
        if not terms:
            return []
        ranked = []
        for item in self.list("active"):
            haystack = " ".join((item["name"], item["description"], item["instructions"])).lower()
            score = sum(1 for term in terms if term in haystack)
            if score:
                ranked.append((score, item))
        ranked.sort(key=lambda pair: (-pair[0], pair[1]["name"].lower()))
        return [item for _, item in ranked[:max(1, min(limit, 8))]]

    def export_manifest(self, skill_id: str) -> dict[str, Any]:
        item = self.get(skill_id)
        if item is None:
            raise KeyError(skill_id)
        return {
            "format": "genesis-skill-v1", "slug": item["slug"], "name": item["name"],
            "description": item["description"], "instructions": item["instructions"],
            "allowed_tools": item["allowed_tools"], "checklist": item["checklist"],
        }

    def import_manifest(self, manifest: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(manifest, dict) or manifest.get("format") != "genesis-skill-v1":
            raise SkillError("Unsupported skill manifest format.")
        # Imported skills are always drafts; imported status and executable fields are ignored.
        return self.create(
            manifest.get("name", ""), manifest.get("description", ""),
            manifest.get("instructions", ""), manifest.get("allowed_tools", []),
            manifest.get("checklist", []),
        )


__all__ = ["SkillError", "SkillStore"]
