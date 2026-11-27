"""Run a downloaded GGUF model with GENESIS's own managed llama.cpp server.

GENESIS starts ``llama-server`` (llama.cpp) on a private loopback port, talks to
it through the existing OpenAI-compatible adapter and stops it on exit. No
Ollama or other model manager is involved.
"""

from __future__ import annotations

import atexit
import json
import shutil
import socket
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ENGINE_NAMES = ("llama-server", "llama-server.exe")

INSTALL_HELP = (
    "GENESIS needs the llama.cpp engine (llama-server) to run downloaded models.\n"
    "  Termux : pkg install llama-cpp\n"
    "  Debian/Ubuntu : build from https://github.com/ggml-org/llama.cpp (cmake -B build && cmake --build build -j)\n"
    "  then make sure `llama-server` is on your PATH (or set GENESIS_LLAMA_SERVER=/path/to/llama-server)."
)


class NativeRuntimeError(RuntimeError):
    """Raised when the managed engine cannot be found or started."""


def find_engine(env: dict[str, str] | None = None) -> str | None:
    import os

    env = os.environ if env is None else env
    explicit = env.get("GENESIS_LLAMA_SERVER")
    if explicit and Path(explicit).is_file():
        return explicit
    for name in ENGINE_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def build_command(engine: str, model_path: Path, port: int, context: int = 4096,
                  threads: int | None = None) -> list[str]:
    command = [engine, "-m", str(model_path), "--host", "127.0.0.1", "--port", str(port),
               "-c", str(context)]
    if threads:
        command += ["-t", str(threads)]
    return command


class NativeRuntime:
    """Lifecycle of one managed llama-server process."""

    def __init__(self, engine: str | None = None) -> None:
        self.engine = engine or find_engine()
        self.process: subprocess.Popen | None = None
        self.port: int | None = None
        self.model_path: Path | None = None
        self._registered = False

    @property
    def base_url(self) -> str:
        if self.port is None:
            raise NativeRuntimeError("The native runtime is not running.")
        return f"http://127.0.0.1:{self.port}"

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, model_path: Path, context: int = 4096, ready_timeout: float = 180.0,
              threads: int | None = None) -> str:
        """Start the server for ``model_path`` and wait until it is ready."""
        if not self.engine:
            raise NativeRuntimeError(INSTALL_HELP)
        model_path = Path(model_path)
        if not model_path.is_file():
            raise NativeRuntimeError(f"Model file not found: {model_path}")
        if self.running and self.model_path == model_path:
            return self.base_url
        self.stop()
        self.port = free_port()
        self.model_path = model_path
        self.process = subprocess.Popen(
            build_command(self.engine, model_path, self.port, context, threads),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
        )
        if not self._registered:
            atexit.register(self.stop)
            self._registered = True
        self._wait_ready(ready_timeout)
        return self.base_url

    def _wait_ready(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process is None or self.process.poll() is not None:
                code = self.process.returncode if self.process else "?"
                self.stop()
                raise NativeRuntimeError(f"llama-server exited early (code {code}). The model may not fit in memory.")
            try:
                with urlopen(f"{self.base_url}/health", timeout=2) as response:
                    payload = json.loads(response.read().decode("utf-8") or "{}")
                    if response.status == 200 and payload.get("status", "ok") == "ok":
                        return
            except (URLError, OSError, ValueError, TimeoutError):
                pass  # still loading (503) or not listening yet
            time.sleep(0.5)
        self.stop()
        raise NativeRuntimeError("llama-server did not become ready in time.")

    def stop(self) -> None:
        process, self.process = self.process, None
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        self.port = None
