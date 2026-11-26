"""Provider-neutral chat adapters for GENESIS model runtimes.

Only inference requests are sent. GENESIS owns the conversation and agent flow.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from genesis_core.models import discover_runtimes


class ModelError(RuntimeError):
    """Raised when a model provider cannot complete a chat request."""


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    base_url: str
    model: str
    api_key: str | None = None


def _settings_path() -> Path:
    home = Path(os.environ.get("GENESIS_HOME", Path.home() / ".genesis"))
    return home / "config" / "settings.json"


def load_model_config() -> ModelConfig:
    """Load explicit model selection, or choose the first available local model."""
    settings: dict[str, Any] = {}
    path = _settings_path()
    if path.exists():
        try:
            settings = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ModelError(f"Cannot read GENESIS settings: {exc}") from exc

    model_settings = settings.get("model", {})
    provider = os.getenv("GENESIS_MODEL_PROVIDER") or model_settings.get("provider")
    model = os.getenv("GENESIS_MODEL") or model_settings.get("name")
    base_url = os.getenv("GENESIS_MODEL_URL") or model_settings.get("base_url")
    api_key = os.getenv("GENESIS_MODEL_API_KEY") or model_settings.get("api_key")

    runtimes = {item.provider: item for item in discover_runtimes()}
    if not provider:
        provider = next(
            (key for key in ("ollama", "lm_studio", "llama_cpp")
             if key in runtimes and runtimes[key].available and runtimes[key].models),
            None,
        )
    if not provider:
        raise ModelError(
            "No model runtime found. Start Ollama, LM Studio or llama.cpp, "
            "or configure GENESIS_MODEL_PROVIDER and GENESIS_MODEL."
        )
    if provider not in runtimes:
        raise ModelError(f"Unsupported provider '{provider}'.")
    runtime = runtimes[provider]
    base_url = (base_url or runtime.base_url).rstrip("/")
    if not model:
        if not runtime.models:
            raise ModelError(f"No model is available from {provider}.")
        model = runtime.models[0]
    if not isinstance(model, str) or not model.strip():
        raise ModelError("The selected model name is empty.")
    return ModelConfig(provider, base_url, model, api_key)


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str],
               timeout: float) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json", **headers},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise ModelError(f"Model provider returned HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ModelError(f"Cannot reach model provider at {url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ModelError("Model provider returned invalid JSON.") from exc
    if not isinstance(result, dict):
        raise ModelError("Model provider returned an unexpected response.")
    return result


class ChatAdapter:
    def __init__(self, config: ModelConfig, timeout: float = 120.0) -> None:
        self.config = config
        self.timeout = timeout

    def chat(self, messages: list[dict[str, str]]) -> str:
        if self.config.provider == "ollama":
            payload = {
                "model": self.config.model,
                "messages": messages,
                "stream": False,
            }
            result = _post_json(
                f"{self.config.base_url}/api/chat", payload, {}, self.timeout
            )
            content = result.get("message", {}).get("content")
        else:
            payload = {
                "model": self.config.model,
                "messages": messages,
                "stream": False,
            }
            headers = {}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            result = _post_json(
                f"{self.config.base_url}/v1/chat/completions",
                payload,
                headers,
                self.timeout,
            )
            choices = result.get("choices", [])
            content = choices[0].get("message", {}).get("content") if choices else None

        if not isinstance(content, str) or not content.strip():
            raise ModelError("The model returned an empty assistant response.")
        return content.strip()


def create_chat_adapter(config: ModelConfig | None = None) -> ChatAdapter:
    return ChatAdapter(config or load_model_config())
