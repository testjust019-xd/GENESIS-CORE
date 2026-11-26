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


def get_search_settings() -> dict[str, str]:
    """Return persisted optional search-provider settings."""
    search = read_settings().get("research", {})
    if not isinstance(search, dict):
        search = {}
    return {
        "provider": str(search.get("provider", "offline")),
        "searxng_url": str(search.get("searxng_url", "")),
    }


def set_search_settings(provider: str, searxng_url: str = "") -> Path:
    """Persist a search provider without storing credentials or enabling network access implicitly."""
    provider = provider.strip().lower()
    if provider not in {"offline", "searxng", "brave"}:
        raise ValueError("Search provider must be offline, searxng, or brave.")
    if provider == "searxng":
        from urllib.parse import urlparse
        parsed = urlparse(searxng_url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("SearXNG URL must be an absolute HTTP(S) URL.")
        if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("A remote SearXNG instance must use HTTPS.")
    settings = read_settings()
    settings["research"] = {"provider": provider, "searxng_url": searxng_url.strip().rstrip("/")}
    return write_settings(settings)


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
