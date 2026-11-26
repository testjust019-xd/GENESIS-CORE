"""Model runtime discovery for local GENESIS providers.

The first implementation uses only Python's standard library and read-only
health/model-list endpoints. It never starts, downloads, or modifies a model.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class RuntimeStatus:
    provider: str
    base_url: str
    available: bool
    models: list[str]
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_RUNTIMES = (
    ("ollama", "Ollama", "http://127.0.0.1:11434"),
    ("llama_cpp", "llama.cpp", "http://127.0.0.1:8080"),
    ("lm_studio", "LM Studio", "http://127.0.0.1:1234"),
)


def _get_json(url: str, timeout: float) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("The runtime returned an unexpected JSON document")
    return payload


def _normalise_models(payload: dict[str, Any], provider: str) -> list[str]:
    if provider == "ollama":
        entries = payload.get("models", [])
        return [
            str(item.get("name") or item.get("model"))
            for item in entries
            if isinstance(item, dict) and (item.get("name") or item.get("model"))
        ]

    entries = payload.get("data", [])
    return [
        str(item["id"])
        for item in entries
        if isinstance(item, dict) and item.get("id")
    ]


def inspect_runtime(
    provider: str,
    base_url: str,
    *,
    timeout: float = 1.5,
) -> RuntimeStatus:
    """Inspect one local runtime using its non-destructive model-list endpoint."""
    base_url = base_url.rstrip("/")
    endpoint = "/api/tags" if provider == "ollama" else "/v1/models"
    try:
        payload = _get_json(f"{base_url}{endpoint}", timeout)
        models = _normalise_models(payload, provider)
        detail = f"{len(models)} model(s) reported" if models else "Runtime reachable; no models reported"
        return RuntimeStatus(provider, base_url, True, models, detail)
    except HTTPError as exc:
        detail = f"HTTP {exc.code}"
    except (URLError, TimeoutError, OSError):
        detail = "Not reachable"
    except (ValueError, json.JSONDecodeError):
        detail = "Invalid response"
    return RuntimeStatus(provider, base_url, False, [], detail)


def discover_runtimes(
    *,
    ollama_url: str | None = None,
    llama_cpp_url: str | None = None,
    lm_studio_url: str | None = None,
    timeout: float = 1.5,
) -> list[RuntimeStatus]:
    """Probe configured local providers; environment variables override defaults."""
    overrides = {
        "ollama": ollama_url or os.getenv("GENESIS_OLLAMA_URL"),
        "llama_cpp": llama_cpp_url or os.getenv("GENESIS_LLAMA_CPP_URL"),
        "lm_studio": lm_studio_url or os.getenv("GENESIS_LM_STUDIO_URL"),
    }
    results = []
    for key, label, default_url in DEFAULT_RUNTIMES:
        url = overrides[key] or default_url
        results.append(inspect_runtime(key, url, timeout=timeout))
    return results
