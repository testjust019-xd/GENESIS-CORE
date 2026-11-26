"""Lightweight, best-effort host hardware inspection."""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path
from typing import Any


def inspect_hardware() -> dict[str, Any]:
    """Return a portable hardware snapshot without requiring third-party packages."""
    memory_total = None
    memory_available = None

    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        values: dict[str, int] = {}
        try:
            for line in meminfo.read_text(encoding="utf-8").splitlines():
                key, _, value = line.partition(":")
                if key in {"MemTotal", "MemAvailable"}:
                    values[key] = int(value.strip().split()[0]) * 1024
            memory_total = values.get("MemTotal")
            memory_available = values.get("MemAvailable")
        except (OSError, ValueError, IndexError):
            pass

    disk = shutil.disk_usage(Path.home())
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cpu_logical": os.cpu_count(),
        "memory_total_bytes": memory_total,
        "memory_available_bytes": memory_available,
        "disk_free_bytes": disk.free,
        "disk_total_bytes": disk.total,
    }


def format_bytes(value: int | None) -> str:
    if value is None:
        return "unavailable"
    amount = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TB"
