"""Small helpers for persistent GENESIS configuration."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def settings_path() -> Path:
    home = Path(os.environ.get("GENESIS_HOME", Path.home() / ".genesis"))
    return home / "config" / "settings.json"


def read_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read settings file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("GENESIS settings must contain a JSON object.")
    return data


def write_settings(settings: dict[str, Any]) -> Path:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def set_model(provider: str, model: str, base_url: str | None = None) -> Path:
    if provider not in {"ollama", "llama_cpp", "lm_studio"}:
        raise ValueError("Provider must be ollama, llama_cpp, or lm_studio.")
    if not model.strip():
        raise ValueError("Model name cannot be empty.")
    settings = read_settings()
    selected = {"provider": provider, "name": model.strip()}
    if base_url:
        selected["base_url"] = base_url.rstrip("/")
    settings["model"] = selected
    return write_settings(settings)
