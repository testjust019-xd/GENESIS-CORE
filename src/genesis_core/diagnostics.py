"""Non-destructive local diagnostics and self-tests for GENESIS CORE."""

from __future__ import annotations

import json
import os
import platform
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any

from genesis_core.hardware import inspect_hardware
from genesis_core.knowledge import KnowledgeStore
from genesis_core.memory import MemoryStore
from genesis_core.models import discover_runtimes
from genesis_core.state import StateStore
from genesis_core.tools import PermissionManager, ToolSpec


def _check(name: str, fn) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        detail = fn()
        return {"name": name, "status": "pass", "detail": str(detail),
                "duration_ms": round((time.perf_counter() - started) * 1000, 2)}
    except Exception as exc:  # diagnostics must report a failed check, not crash
        return {"name": name, "status": "fail", "detail": f"{type(exc).__name__}: {exc}",
                "duration_ms": round((time.perf_counter() - started) * 1000, 2)}


def _python_check() -> str:
    if platform.python_version_tuple() < ("3", "11", "0"):
        raise RuntimeError("Python 3.11 or newer is required.")
    return f"Python {platform.python_version()}"

def _home_check(home: Path) -> str:
    home.mkdir(parents=True, exist_ok=True)
    probe = home / f".genesis-doctor-{os.getpid()}.tmp"
    try:
        probe.write_text("ok", encoding="utf-8")
        if probe.read_text(encoding="utf-8") != "ok":
            raise OSError("temporary write verification failed")
    finally:
        probe.unlink(missing_ok=True)
    return f"Writable: {home}"

def _sqlite_check() -> str:
    with tempfile.TemporaryDirectory(prefix="genesis-test-") as temp:
        db_path = Path(temp) / "test.db"
        state = StateStore(db_path)
        session = state.create_session("Diagnostic self-test")
        state.add_message(session["id"], "user", "GENESIS diagnostic")
        reopened = StateStore(db_path)
        messages = reopened.list_messages(session["id"])
        if len(messages) != 1 or messages[0]["content"] != "GENESIS diagnostic":
            raise RuntimeError("SQLite persistence round-trip failed")
        with sqlite3.connect(db_path) as db:
            result = db.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"SQLite integrity_check: {result}")
    return "SQLite create/read/reopen and integrity check passed"

def _memory_check() -> str:
    with tempfile.TemporaryDirectory(prefix="genesis-memory-") as temp:
        state = StateStore(Path(temp) / "state.db")
        memory = MemoryStore(state)
        saved = memory.add("semantic", "diagnostic memory record", source_type="diagnostic")
        reopened = MemoryStore(StateStore(Path(temp) / "state.db"))
        if reopened.get(saved["id"]) is None:
            raise RuntimeError("Memory record did not persist")
    return "Memory store persistence passed"

def _knowledge_check() -> str:
    with tempfile.TemporaryDirectory(prefix="genesis-knowledge-") as temp:
        store = KnowledgeStore(StateStore(Path(temp) / "state.db"))
        saved = store.ingest_text("Diagnostic note", "GENESIS local knowledge diagnostic")
        if saved.get("duplicate") or saved.get("chunk_count", 0) < 1:
            raise RuntimeError("Knowledge ingestion did not create a chunk")
        duplicate = store.ingest_text("Another title", "GENESIS local knowledge diagnostic")
        if not duplicate.get("duplicate"):
            raise RuntimeError("Knowledge content deduplication failed")
    return "Knowledge ingestion, chunking and deduplication passed"

def _permission_check() -> str:
    spec = ToolSpec(
        name="diagnostic_write_probe", description="diagnostic only",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        handler=lambda _: None, capabilities=frozenset({"workspace_write"}), risk="write",
    )
    decision = PermissionManager({}).decide(spec)
    if decision.action != "approval_required":
        raise RuntimeError(f"Elevated tool was not gated: {decision.action}")
    denied = PermissionManager({"deny_all": True}).decide(spec)
    if denied.action != "deny":
        raise RuntimeError("deny_all did not fail closed")
    return "Elevated tools require approval; deny_all blocks execution"

def run_test_bench(home: str | Path, *, include_models: bool = False) -> dict[str, Any]:
    """Run isolated local self-tests. Model probes are opt-in and read-only."""
    home = Path(home).expanduser()
    checks = [
        _check("python", _python_check),
        _check("genesis_home", lambda: _home_check(home)),
        _check("sqlite_persistence", _sqlite_check),
        _check("memory_store", _memory_check),
        _check("knowledge_store", _knowledge_check),
        _check("tool_permissions", _permission_check),
    ]
    hardware = inspect_hardware()
    if include_models:
        runtimes = discover_runtimes()
        checks.append({
            "name": "local_model_runtimes",
            "status": "pass" if any(item.available for item in runtimes) else "warn",
            "detail": "; ".join(
                f"{item.provider}: {'online' if item.available else 'offline'}"
                + (f" ({len(item.models)} model(s))" if item.available else "")
                for item in runtimes
            ),
            "duration_ms": None,
        })
    passed = sum(item["status"] == "pass" for item in checks)
    failed = sum(item["status"] == "fail" for item in checks)
    warnings = sum(item["status"] == "warn" for item in checks)
    return {
        "product": "GENESIS CORE",
        "report_version": 1,
        "overall": "fail" if failed else ("warn" if warnings else "pass"),
        "summary": {"passed": passed, "failed": failed, "warnings": warnings,
                    "total": len(checks)},
        "hardware": hardware,
        "checks": checks,
        "model_probe_included": include_models,
        "notes": [
            "Self-tests use temporary databases and do not alter the user's GENESIS data.",
            "Model discovery is read-only and runs only when explicitly requested.",
            "No model inference, download, network research or shell command is run by default.",
        ],
    }

def format_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "GENESIS CORE — TEST BENCH",
        f"Result: {report['overall'].upper()}",
        f"Checks: {summary['passed']} passed, {summary['failed']} failed, "
        f"{summary['warnings']} warning(s) / {summary['total']} total",
        "",
    ]
    for item in report["checks"]:
        duration = f" ({item['duration_ms']} ms)" if item.get("duration_ms") is not None else ""
        lines.append(f"[{item['status'].upper():4}] {item['name']}: {item['detail']}{duration}")
    hw = report["hardware"]
    lines.extend(["", f"System: {hw['system']} {hw['machine']} | Python {hw['python']}",
                  f"CPU: {hw['cpu_logical'] or 'unknown'} logical core(s)"])
    if hw["memory_total_bytes"] is not None:
        lines.append(f"RAM: {hw['memory_total_bytes'] / (1024 ** 3):.1f} GB total")
    lines.append("No model inference or downloads were performed.")
    return "\n".join(lines)
