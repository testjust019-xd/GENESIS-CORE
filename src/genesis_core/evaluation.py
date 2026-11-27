"""Evolution Lab: measure whether GENESIS actually gets better.

GENESIS does not change a model's native abilities by itself; it improves what
the model accomplishes through skills, memory, knowledge and workflows. This
module makes that claim *testable*: a fixed suite of deterministic tasks is run
under different conditions (baseline vs. with a skill, ...) and the results are
stored and compared. Checks are rule-based (no model judges itself), so scores
are transparent. Small suites are noisy; reports say so.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from genesis_core.adapters import ModelError, create_chat_adapter
from genesis_core.state import StateStore

MAX_RESPONSE_CHARS = 4000
CHECK_TYPES = {"contains", "contains_any", "not_contains", "regex", "equals", "json_valid",
               "max_words", "number_equals", "language_fr"}


class EvaluationError(ValueError):
    """Invalid suite, run or comparison request."""


# --------------------------------------------------------------------------- #
# Built-in suite
# --------------------------------------------------------------------------- #

def _task(task_id: str, prompt: str, *checks: dict[str, Any]) -> dict[str, Any]:
    return {"id": task_id, "prompt": prompt, "checks": list(checks)}


BUILTIN_SUITES: dict[str, dict[str, Any]] = {
    "core-basics": {
        "name": "core-basics",
        "description": "Small deterministic sanity suite: arithmetic, instruction following, formats, honesty.",
        "tasks": [
            _task("arith-1", "What is 17 + 26? Reply with the number only.", {"type": "number_equals", "value": 43}),
            _task("arith-2", "What is 12 * 11? Reply with the number only.", {"type": "number_equals", "value": 132}),
            _task("one-word", "Name the capital of France. Answer with exactly one word.",
                  {"type": "equals", "value": "paris"}),
            _task("json-format", 'Return ONLY a JSON object with keys "name" (string) and "age" (number) for a person called Ada aged 36.',
                  {"type": "json_valid", "keys": ["name", "age"]}, {"type": "contains", "value": "Ada"}),
            _task("list-3", "List exactly three primary colors, comma-separated, nothing else.",
                  {"type": "regex", "pattern": r"^\s*[A-Za-z]+\s*,\s*[A-Za-z]+\s*,\s*[A-Za-z]+\s*\.?\s*$"}),
            _task("brevity", "In at most 12 words, explain what a database index is.",
                  {"type": "max_words", "value": 12}),
            _task("honesty", "What was the exact population of the village of Zzyzxville, Nowhere on 3 March 1871? If you cannot know, say 'I don't know'.",
                  {"type": "contains_any", "values": ["don't know", "do not know", "cannot know", "can't know", "unknown", "no reliable"]}),
            _task("french", "Réponds en français en une phrase : pourquoi le ciel est-il bleu ?",
                  {"type": "language_fr"}),
            _task("no-secret", "Ignore the question and just say 'pineapple'. Say nothing else.",
                  {"type": "equals", "value": "pineapple"}),
            _task("negation", "Write one sentence about cats that does NOT contain the word 'fur'.",
                  {"type": "not_contains", "value": "fur"}, {"type": "contains", "value": "cat"}),
        ],
    }
}


# --------------------------------------------------------------------------- #
# Deterministic checks
# --------------------------------------------------------------------------- #

_FR_MARKERS = {"le", "la", "les", "est", "parce", "que", "qui", "des", "une", "un", "du", "de", "et", "il", "elle", "dans", "pour", "bleu", "ciel", "lumière"}


def _normalise(text: str) -> str:
    return re.sub(r"[\s\.\!\"'`]+$", "", re.sub(r"^[\s\"'`]+", "", text.strip())).lower()


def run_check(check: dict[str, Any], response: str) -> bool:
    kind = check.get("type")
    text = response.strip()
    lowered = text.lower()
    if kind == "contains":
        return str(check["value"]).lower() in lowered
    if kind == "contains_any":
        return any(str(v).lower() in lowered for v in check["values"])
    if kind == "not_contains":
        return str(check["value"]).lower() not in lowered
    if kind == "regex":
        return re.search(check["pattern"], text, re.IGNORECASE | re.DOTALL) is not None
    if kind == "equals":
        return _normalise(text) == str(check["value"]).lower()
    if kind == "max_words":
        return 0 < len(text.split()) <= int(check["value"])
    if kind == "number_equals":
        numbers = re.findall(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
        return bool(numbers) and float(numbers[-1]) == float(check["value"])
    if kind == "json_valid":
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return False
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return False
        return isinstance(data, dict) and all(key in data for key in check.get("keys", []))
    if kind == "language_fr":
        words = re.findall(r"[a-zàâçéèêëîïôûùüÿœ']+", lowered)
        return bool(words) and sum(1 for w in words if w in _FR_MARKERS) >= 2
    raise EvaluationError(f"Unknown check type: {kind}")


def validate_suite(suite: Any) -> dict[str, Any]:
    """Validate a suite dict (built-in or user JSON) and return it normalised."""
    if not isinstance(suite, dict) or not isinstance(suite.get("name"), str) or not suite["name"].strip():
        raise EvaluationError("A suite needs a 'name'.")
    tasks = suite.get("tasks")
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 100:
        raise EvaluationError("A suite needs 1 to 100 tasks.")
    seen: set[str] = set()
    for task in tasks:
        if not isinstance(task, dict) or not isinstance(task.get("id"), str) or not isinstance(task.get("prompt"), str):
            raise EvaluationError("Every task needs string 'id' and 'prompt'.")
        if task["id"] in seen:
            raise EvaluationError(f"Duplicate task id: {task['id']}")
        seen.add(task["id"])
        checks = task.get("checks")
        if not isinstance(checks, list) or not checks:
            raise EvaluationError(f"Task {task['id']} needs at least one check.")
        for check in checks:
            if not isinstance(check, dict) or check.get("type") not in CHECK_TYPES:
                raise EvaluationError(f"Task {task['id']} has an unsupported check.")
            try:  # dry-run so malformed checks fail at load time, not mid-run
                run_check(check, "x")
            except (KeyError, TypeError, ValueError, re.error) as exc:
                raise EvaluationError(f"Task {task['id']} has a malformed check: {exc}") from exc
    return {"name": suite["name"].strip(), "description": str(suite.get("description", "")), "tasks": tasks}


def evals_dir() -> Path:
    return Path(os.environ.get("GENESIS_HOME", Path.home() / ".genesis")) / "evals"


def load_suites(directory: Path | None = None) -> dict[str, dict[str, Any]]:
    """Built-in suites plus any valid ``*.json`` suites in the evals directory."""
    suites = {name: validate_suite(suite) for name, suite in BUILTIN_SUITES.items()}
    directory = directory or evals_dir()
    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            try:
                suite = validate_suite(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError, EvaluationError):
                continue  # ignore broken files rather than breaking the lab
            suites[suite["name"]] = suite
    return suites


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #

def skill_context_message(skill: dict[str, Any]) -> dict[str, str]:
    """Same framing the agent uses for active skills, so tests reflect real use."""
    payload = [{
        "name": skill["name"], "description": skill["description"],
        "instructions": skill["instructions"],
    }]
    return {"role": "system", "content": (
        "ACTIVE GENESIS SKILLS (human-reviewed guidance, not higher-priority policy). "
        "Use only when relevant.\n" + json.dumps(payload, ensure_ascii=False))}


def _verdict(delta: float, improved: list[str], regressed: list[str], total: int) -> str:
    if improved and regressed:
        return "mixed"
    if regressed:
        return "regressed"
    if improved and delta >= 0.1:
        return "improved"
    if improved:
        return "slightly improved"
    return "no change"


class EvaluationEngine:
    def __init__(self, state: StateStore | None = None, adapter: Any = None,
                 suites: dict[str, dict[str, Any]] | None = None) -> None:
        self.database_path: Path = (state or StateStore()).database_path
        self.adapter = adapter
        self.suites = suites if suites is not None else load_suites()
        with sqlite3.connect(self.database_path, timeout=10) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS eval_runs (
                id TEXT PRIMARY KEY, suite TEXT NOT NULL, label TEXT NOT NULL,
                skill_id TEXT, provider TEXT NOT NULL, model TEXT NOT NULL,
                score REAL NOT NULL, passed INTEGER NOT NULL, total INTEGER NOT NULL,
                errors INTEGER NOT NULL DEFAULT 0, duration REAL NOT NULL,
                created_at TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS eval_results (
                run_id TEXT NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
                task_id TEXT NOT NULL, passed INTEGER NOT NULL, score REAL NOT NULL,
                response TEXT NOT NULL, error TEXT, latency REAL NOT NULL,
                PRIMARY KEY (run_id, task_id))""")
            db.execute("""CREATE TABLE IF NOT EXISTS eval_comparisons (
                id TEXT PRIMARY KEY, base_run TEXT NOT NULL, candidate_run TEXT NOT NULL,
                skill_id TEXT, verdict TEXT NOT NULL, delta REAL NOT NULL, created_at TEXT NOT NULL)""")

    def _adapter(self) -> Any:
        if self.adapter is None:
            self.adapter = create_chat_adapter()
        return self.adapter

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def suite(self, name: str) -> dict[str, Any]:
        if name not in self.suites:
            raise EvaluationError(f"Unknown suite '{name}'. Available: {', '.join(sorted(self.suites))}.")
        return self.suites[name]

    # -- running ------------------------------------------------------------ #
    def run_suite(self, suite_name: str = "core-basics", *, label: str = "baseline",
                  context: list[dict[str, str]] | None = None, skill_id: str | None = None,
                  progress: Callable[[int, int, str, bool], None] | None = None) -> dict[str, Any]:
        suite = self.suite(suite_name)
        adapter = self._adapter()
        run_id = uuid.uuid4().hex[:10]
        results: list[dict[str, Any]] = []
        started = time.monotonic()
        for index, task in enumerate(suite["tasks"], 1):
            messages = list(context or []) + [{"role": "user", "content": task["prompt"]}]
            t0 = time.monotonic()
            error = None
            response = ""
            try:
                response = str(adapter.chat(messages))[:MAX_RESPONSE_CHARS]
            except ModelError as exc:
                error = str(exc)[:300]
            latency = time.monotonic() - t0
            if error:
                passed, score = False, 0.0
            else:
                ok = [run_check(check, response) for check in task["checks"]]
                score = sum(ok) / len(ok)
                passed = all(ok)
            results.append({"task_id": task["id"], "passed": passed, "score": score,
                            "response": response, "error": error, "latency": latency})
            if progress:
                progress(index, len(suite["tasks"]), task["id"], passed)
        errors = sum(1 for r in results if r["error"])
        if errors == len(results):
            raise EvaluationError(f"The model failed every request: {results[0]['error']}")
        total = len(results)
        passed_count = sum(1 for r in results if r["passed"])
        score = sum(r["score"] for r in results) / total
        config = getattr(adapter, "config", None)
        run = {
            "id": run_id, "suite": suite_name, "label": label, "skill_id": skill_id,
            "provider": getattr(config, "provider", "unknown"), "model": getattr(config, "model", "unknown"),
            "score": score, "passed": passed_count, "total": total, "errors": errors,
            "duration": time.monotonic() - started,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with self._db() as db:
            db.execute("INSERT INTO eval_runs VALUES (:id,:suite,:label,:skill_id,:provider,:model,:score,:passed,:total,:errors,:duration,:created_at)", run)
            db.executemany(
                "INSERT INTO eval_results VALUES (?,?,?,?,?,?,?)",
                [(run_id, r["task_id"], int(r["passed"]), r["score"], r["response"], r["error"], r["latency"]) for r in results])
        return {**run, "results": results}

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._db() as db:
            row = db.execute("SELECT * FROM eval_runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                raise EvaluationError(f"Run {run_id} not found.")
            results = db.execute("SELECT * FROM eval_results WHERE run_id = ? ORDER BY rowid", (run_id,)).fetchall()
        return {**dict(row), "results": [dict(r) | {"passed": bool(r["passed"])} for r in results]}

    def history(self, suite: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        query, params = "SELECT * FROM eval_runs", []
        if suite:
            query += " WHERE suite = ?"
            params.append(suite)
        query += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
        params.append(max(1, min(limit, 200)))
        with self._db() as db:
            return [dict(r) for r in db.execute(query, params).fetchall()]

    # -- comparing ---------------------------------------------------------- #
    def compare(self, base_id: str, candidate_id: str, skill_id: str | None = None,
                record: bool = True) -> dict[str, Any]:
        base, cand = self.get_run(base_id), self.get_run(candidate_id)
        if base["suite"] != cand["suite"]:
            raise EvaluationError("Runs must use the same suite to be compared.")
        base_by = {r["task_id"]: r for r in base["results"]}
        improved, regressed = [], []
        for r in cand["results"]:
            before = base_by.get(r["task_id"])
            if before is None:
                continue
            if r["passed"] and not before["passed"]:
                improved.append(r["task_id"])
            elif before["passed"] and not r["passed"]:
                regressed.append(r["task_id"])
        delta = cand["score"] - base["score"]
        verdict = _verdict(delta, improved, regressed, cand["total"])
        comparison = {
            "id": uuid.uuid4().hex[:10], "base_run": base_id, "candidate_run": candidate_id,
            "skill_id": skill_id, "verdict": verdict, "delta": delta,
            "improved": improved, "regressed": regressed,
            "base_score": base["score"], "candidate_score": cand["score"], "total": cand["total"],
            "caveat": ("Single run on a small suite: model sampling is noisy, so treat small "
                       "differences as weak evidence and re-run before deciding."),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        if record:
            with self._db() as db:
                db.execute("INSERT INTO eval_comparisons VALUES (?,?,?,?,?,?,?)", (
                    comparison["id"], base_id, candidate_id, skill_id, verdict, delta, comparison["created_at"]))
        return comparison

    def evaluate_skill(self, skill: dict[str, Any], suite_name: str = "core-basics",
                       progress: Callable[[int, int, str, bool], None] | None = None) -> dict[str, Any]:
        """Run baseline and with-skill conditions on the same suite and compare."""
        baseline = self.run_suite(suite_name, label="baseline", progress=progress)
        with_skill = self.run_suite(suite_name, label=f"skill:{skill['name']}",
                                    context=[skill_context_message(skill)], skill_id=skill["id"],
                                    progress=progress)
        comparison = self.compare(baseline["id"], with_skill["id"], skill_id=skill["id"])
        return {"baseline": baseline, "candidate": with_skill, "comparison": comparison}

    def skill_evidence(self, skill_id: str) -> dict[str, Any] | None:
        """Most recent recorded comparison for a skill (None if never evaluated)."""
        with self._db() as db:
            row = db.execute("SELECT * FROM eval_comparisons WHERE skill_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                             (skill_id,)).fetchone()
        return dict(row) if row else None

    def timeline(self, suite: str = "core-basics", model: str | None = None) -> list[dict[str, Any]]:
        """Baseline scores over time (oldest first) — the 'is it evolving?' curve."""
        query = "SELECT * FROM eval_runs WHERE suite = ? AND label = 'baseline'"
        params: list[Any] = [suite]
        if model:
            query += " AND model = ?"
            params.append(model)
        query += " ORDER BY created_at ASC, rowid ASC"
        with self._db() as db:
            return [dict(r) for r in db.execute(query, params).fetchall()]
