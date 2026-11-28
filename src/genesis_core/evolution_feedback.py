"""Read-only feedback loop connecting benchmark and experience evidence.

The engine surfaces reproducible improvement opportunities. It does not edit
skills, promote memories, execute tools, or change model weights.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from genesis_core.evaluation import EvaluationEngine
from genesis_core.experience import ExperienceStore
from genesis_core.state import StateStore


class FeedbackError(ValueError):
    """Invalid feedback analysis request."""


class EvolutionFeedbackEngine:
    """Build auditable, deterministic improvement findings from stored evidence."""

    def __init__(
        self,
        state: StateStore | None = None,
        evaluations: EvaluationEngine | None = None,
        experiences: ExperienceStore | None = None,
    ) -> None:
        self.state = state or StateStore()
        self.database_path: Path = self.state.database_path
        self.evaluations = evaluations or EvaluationEngine(self.state)
        self.experiences = experiences or ExperienceStore(self.state)
        self._initialise()

    def _initialise(self) -> None:
        with sqlite3.connect(self.database_path, timeout=10) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS evolution_feedback_reports (
                    id TEXT PRIMARY KEY,
                    findings_count INTEGER NOT NULL,
                    report_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_feedback_created "
                "ON evolution_feedback_reports(created_at DESC)"
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _context_key(item: dict[str, Any]) -> str:
        context = " ".join(
            f"{item['objective']} {item['instructions']}".lower().split()
        )
        return hashlib.sha256(context.encode("utf-8")).hexdigest()

    def analyze(self, *, history_limit: int = 100, experience_limit: int = 200) -> dict[str, Any]:
        if isinstance(history_limit, bool) or not isinstance(history_limit, int) or not 2 <= history_limit <= 200:
            raise FeedbackError("history_limit must be an integer between 2 and 200.")
        if isinstance(experience_limit, bool) or not isinstance(experience_limit, int) or not 1 <= experience_limit <= 200:
            raise FeedbackError("experience_limit must be an integer between 1 and 200.")

        findings: list[dict[str, Any]] = []
        history = self.evaluations.history(limit=history_limit)
        baseline_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for run in history:
            if run.get("label") != "baseline":
                continue
            key = (run["suite"], run["provider"], run["model"])
            baseline_groups.setdefault(key, []).append(run)

        # Compare the two newest baseline runs within an identical evaluation context.
        for (suite, provider, model), runs in baseline_groups.items():
            if len(runs) < 2:
                continue
            newest, previous = runs[0], runs[1]
            delta = float(newest["score"]) - float(previous["score"])
            if delta <= -0.05:
                comparison = self.evaluations.compare(previous["id"], newest["id"], record=False)
                findings.append({
                    "id": uuid.uuid4().hex[:12],
                    "kind": "benchmark_regression",
                    "severity": "high" if delta <= -0.15 else "medium",
                    "title": f"Baseline score regressed on {suite}",
                    "summary": (
                        f"{provider}/{model} changed from {previous['score']:.1%} "
                        f"to {newest['score']:.1%} ({delta:+.1%})."
                    ),
                    "recommendation": "Inspect the linked task results and repeat the same suite before changing any skill or model configuration.",
                    "evidence": {
                        "suite": suite, "provider": provider, "model": model,
                        "previous_run_id": previous["id"], "latest_run_id": newest["id"],
                        "previous_score": previous["score"], "latest_score": newest["score"],
                        "delta": delta, "improved_tasks": comparison["improved"],
                        "regressed_tasks": comparison["regressed"],
                    },
                })

        # Find task IDs that failed in at least two of the newest baseline runs.
        task_runs: dict[tuple[str, str, str, str], list[str]] = {}
        for (suite, provider, model), runs in baseline_groups.items():
            for run in runs[:5]:
                try:
                    detail = self.evaluations.get_run(run["id"])
                except Exception:
                    continue
                for result in detail["results"]:
                    if not result["passed"]:
                        key = (suite, provider, model, result["task_id"])
                        task_runs.setdefault(key, []).append(run["id"])
        for (suite, provider, model, task_id), run_ids in task_runs.items():
            if len(run_ids) >= 2:
                findings.append({
                    "id": uuid.uuid4().hex[:12],
                    "kind": "recurring_benchmark_failure",
                    "severity": "medium",
                    "title": f"Recurring benchmark failure: {task_id}",
                    "summary": f"Task {task_id} failed in {len(run_ids)} recent baseline runs.",
                    "recommendation": "Review the task prompt, expected behavior and model limitations; add a focused regression test before proposing a skill change.",
                    "evidence": {
                        "suite": suite, "provider": provider, "model": model,
                        "task_id": task_id, "run_ids": run_ids,
                    },
                })

        # Surface skill comparisons that already carry a measured regression.
        with sqlite3.connect(self.database_path, timeout=10) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT * FROM eval_comparisons "
                "WHERE verdict IN ('regressed', 'mixed') "
                "ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
        for row in rows:
            item = dict(row)
            findings.append({
                "id": uuid.uuid4().hex[:12],
                "kind": "skill_evaluation_warning",
                "severity": "high" if item["verdict"] == "regressed" else "medium",
                "title": f"Skill evaluation {item['verdict']}",
                "summary": f"Recorded comparison for skill {item['skill_id'] or 'unknown'} has verdict '{item['verdict']}' ({item['delta']:+.1%}).",
                "recommendation": "Inspect both runs and the skill instructions. Keep the skill in draft/disabled state until a repeated evaluation confirms the result.",
                "evidence": {
                    "comparison_id": item["id"], "skill_id": item["skill_id"],
                    "base_run_id": item["base_run"], "candidate_run_id": item["candidate_run"],
                    "verdict": item["verdict"], "delta": item["delta"],
                },
            })

        # Repeated blocked/failed attempts on an identical task context are a review signal.
        groups: dict[str, list[dict[str, Any]]] = {}
        for item in self.experiences.list(limit=experience_limit):
            if item["status"] == "archived":
                continue
            groups.setdefault(self._context_key(item), []).append(item)
        for group in groups.values():
            unsuccessful = [x for x in group if x["outcome"] in {"blocked", "failed"}]
            if len(unsuccessful) < 2:
                continue
            findings.append({
                "id": uuid.uuid4().hex[:12],
                "kind": "repeated_experience_blocker",
                "severity": "medium",
                "title": f"Repeated blocker: {group[-1]['title']}",
                "summary": (
                    f"The same normalized task context has {len(unsuccessful)} "
                    f"blocked/failed attempts out of {len(group)} recorded attempts."
                ),
                "recommendation": "Inspect the source attempts and observer summaries. Clarify missing prerequisites or permissions before drafting reusable guidance.",
                "evidence": {
                    "experience_ids": [x["id"] for x in group],
                    "unsuccessful_ids": [x["id"] for x in unsuccessful],
                    "completed_count": sum(x["outcome"] == "completed" for x in group),
                    "blocked_count": sum(x["outcome"] == "blocked" for x in group),
                    "failed_count": sum(x["outcome"] == "failed" for x in group),
                },
            })

        findings.sort(
            key=lambda item: (
                {"high": 0, "medium": 1, "low": 2}.get(item["severity"], 3),
                item["kind"], item["title"].lower(),
            )
        )
        report = {
            "id": uuid.uuid4().hex[:12],
            "created_at": self._now(),
            "findings_count": len(findings),
            "sources": {
                "benchmark_runs_examined": len(history),
                "baseline_contexts": len(baseline_groups),
                "experience_records_examined": sum(len(g) for g in groups.values()),
            },
            "findings": findings,
            "policy": {
                "read_only": True,
                "automatic_skill_changes": False,
                "automatic_memory_promotion": False,
                "model_weight_changes": False,
                "human_review_required": True,
            },
        }
        with sqlite3.connect(self.database_path, timeout=10) as db:
            db.execute(
                "INSERT INTO evolution_feedback_reports VALUES (?, ?, ?, ?)",
                (report["id"], report["findings_count"],
                 json.dumps(report, ensure_ascii=False), report["created_at"]),
            )
        return report

    def latest(self) -> dict[str, Any] | None:
        with sqlite3.connect(self.database_path, timeout=10) as db:
            row = db.execute(
                "SELECT report_json FROM evolution_feedback_reports "
                "ORDER BY created_at DESC, rowid DESC LIMIT 1"
            ).fetchone()
        return json.loads(row[0]) if row else None


__all__ = ["EvolutionFeedbackEngine", "FeedbackError"]
