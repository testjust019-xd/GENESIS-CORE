"""Native model management: pick, download and list GGUF models without Ollama.

GENESIS downloads open-weight GGUF files straight from Hugging Face into
``$GENESIS_HOME/models`` using only the standard library. Downloads are
resumable, size-checked and refuse to start when disk space is short.
Running the model is handled by :mod:`genesis_core.native_runtime`.
"""

from __future__ import annotations

import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

GB = 1024 ** 3
ALLOWED_HOSTS = {"huggingface.co", "hf.co"}


class HubError(RuntimeError):
    """Raised when a model cannot be selected or downloaded."""


@dataclass(frozen=True)
class CatalogModel:
    key: str
    title: str
    repo: str
    filename: str
    size_gb: float
    min_ram_gb: float
    note: str = ""

    @property
    def url(self) -> str:
        return hf_url(self.repo, self.filename)


# Small, widely used instruct models in Q4_K_M quantisation (single-file GGUF).
CATALOG: tuple[CatalogModel, ...] = (
    CatalogModel("qwen2.5-0.5b", "Qwen2.5 0.5B Instruct", "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
                 "qwen2.5-0.5b-instruct-q4_k_m.gguf", 0.4, 1.5, "tiny · any phone"),
    CatalogModel("qwen2.5-1.5b", "Qwen2.5 1.5B Instruct", "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
                 "qwen2.5-1.5b-instruct-q4_k_m.gguf", 1.1, 3.0, "light · good for phones"),
    CatalogModel("qwen2.5-3b", "Qwen2.5 3B Instruct", "Qwen/Qwen2.5-3B-Instruct-GGUF",
                 "qwen2.5-3b-instruct-q4_k_m.gguf", 2.1, 5.0, "balanced"),
    CatalogModel("llama3.2-3b", "Llama 3.2 3B Instruct", "bartowski/Llama-3.2-3B-Instruct-GGUF",
                 "Llama-3.2-3B-Instruct-Q4_K_M.gguf", 2.0, 5.0, "balanced"),
    CatalogModel("qwen2.5-7b", "Qwen2.5 7B Instruct", "bartowski/Qwen2.5-7B-Instruct-GGUF",
                 "Qwen2.5-7B-Instruct-Q4_K_M.gguf", 4.7, 9.0, "strong · needs ~8 GB RAM"),
)


def hf_url(repo: str, filename: str) -> str:
    return f"https://huggingface.co/{repo}/resolve/main/{filename}"


def models_dir(home: Path | None = None) -> Path:
    home = home or Path(os.environ.get("GENESIS_HOME", Path.home() / ".genesis"))
    return home / "models"


def recommend(memory_total_bytes: int | None) -> CatalogModel:
    """Largest catalogue model whose RAM requirement fits; smallest when unknown."""
    if not memory_total_bytes:
        return CATALOG[0]
    ram_gb = memory_total_bytes / GB
    fitting = [m for m in CATALOG if m.min_ram_gb <= ram_gb]
    return max(fitting, key=lambda m: m.size_gb) if fitting else CATALOG[0]


def resolve_spec(spec: str) -> CatalogModel:
    """Resolve a catalogue number/key or ``hf:owner/repo/file.gguf`` to a model."""
    spec = spec.strip()
    if spec.isdigit() and 1 <= int(spec) <= len(CATALOG):
        return CATALOG[int(spec) - 1]
    for model in CATALOG:
        if spec.lower() == model.key:
            return model
    if spec.lower().startswith("hf:"):
        parts = spec[3:].split("/")
        if len(parts) >= 3 and parts[-1].lower().endswith(".gguf"):
            repo = "/".join(parts[:2])
            filename = "/".join(parts[2:])
            if re.fullmatch(r"[\w.-]+/[\w.-]+", repo) and ".." not in filename:
                return CatalogModel(spec[3:], filename, repo, filename, 0.0, 0.0, "custom")
    raise HubError("Unknown model. Use a number or key from the list, or hf:owner/repo/file.gguf.")


def installed_models(directory: Path | None = None) -> list[Path]:
    directory = directory or models_dir()
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*.gguf") if p.is_file())


def _check_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise HubError("Models can only be downloaded over HTTPS from huggingface.co.")


def format_size(value: float) -> str:
    return f"{value / GB:.2f} GB" if value >= GB else f"{value / 1024 ** 2:.0f} MB"


def download(model: CatalogModel, directory: Path | None = None,
             progress: Callable[[int, int], None] | None = None,
             opener: Callable[..., object] = urlopen, timeout: float = 30.0) -> Path:
    """Download ``model`` (resuming a partial file). Returns the final path."""
    directory = directory or models_dir()
    directory.mkdir(parents=True, exist_ok=True)
    final = directory / Path(model.filename).name
    if final.exists() and final.stat().st_size > 0:
        return final
    _check_url(model.url)
    part = final.with_suffix(final.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0

    headers = {"User-Agent": "genesis-core"}
    if have:
        headers["Range"] = f"bytes={have}-"
    try:
        response = opener(Request(model.url, headers=headers), timeout=timeout)
    except HTTPError as exc:
        if exc.code == 416 and have:  # partial already complete
            part.replace(final)
            return final
        if exc.code in {401, 403}:
            raise HubError("This model requires a Hugging Face login/licence and cannot be downloaded anonymously.") from exc
        if exc.code == 404:
            raise HubError(f"Model file not found on Hugging Face: {model.repo}/{model.filename}") from exc
        raise HubError(f"Download failed: HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise HubError(f"Cannot reach Hugging Face: {exc}") from exc

    with response:
        status = getattr(response, "status", 200)
        length = int(response.headers.get("Content-Length") or 0)
        if status == 206:
            total = have + length
        else:  # server ignored Range: start over
            have, total = 0, length
        needed = max(total - have, 0)
        free = shutil.disk_usage(directory).free
        if needed and free < needed + 256 * 1024 ** 2:
            raise HubError(f"Not enough disk space: need {format_size(needed)}, free {format_size(free)}.")
        mode = "ab" if have else "wb"
        done = have
        try:
            with open(part, mode) as handle:
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    handle.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
        except (URLError, TimeoutError, OSError) as exc:
            raise HubError(f"Download interrupted ({exc}). Run the same command again to resume.") from exc
    if total and done != total:
        raise HubError("Download incomplete. Run the same command again to resume.")
    with open(part, "rb") as handle:
        if handle.read(4) != b"GGUF":
            part.unlink(missing_ok=True)
            raise HubError("Downloaded file is not a GGUF model.")
    part.replace(final)
    return final


def progress_bar(done: int, total: int, started: float, width: int = 24) -> str:
    """One-line progress text: bar, percent, size and speed."""
    elapsed = max(time.monotonic() - started, 0.001)
    speed = done / elapsed
    if total:
        frac = min(done / total, 1.0)
        filled = int(frac * width)
        bar = "█" * filled + "░" * (width - filled)
        return f"{bar} {frac * 100:5.1f}%  {format_size(done)}/{format_size(total)}  {format_size(speed)}/s"
    return f"{format_size(done)}  {format_size(speed)}/s"
