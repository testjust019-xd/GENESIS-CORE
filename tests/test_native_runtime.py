import stat
import sys

import pytest

from genesis_core import native_runtime as nr

FAKE_SERVER = '''#!{python}
import sys, json
from http.server import BaseHTTPRequestHandler, HTTPServer
port = int(sys.argv[sys.argv.index("--port") + 1])
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({{"status": "ok"}}).encode())
    def log_message(self, *a): pass
HTTPServer(("127.0.0.1", port), H).serve_forever()
'''


def make_engine(tmp_path, body=None):
    script = tmp_path / "llama-server"
    script.write_text(body or FAKE_SERVER.format(python=sys.executable))
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def test_find_engine_prefers_explicit_env(tmp_path):
    engine = make_engine(tmp_path)
    assert nr.find_engine({"GENESIS_LLAMA_SERVER": engine}) == engine
    assert nr.find_engine({"GENESIS_LLAMA_SERVER": str(tmp_path / "missing")}) in (None, nr.shutil.which("llama-server"))


def test_build_command_binds_loopback_only(tmp_path):
    cmd = nr.build_command("/bin/llama-server", tmp_path / "m.gguf", 9999, context=2048, threads=4)
    assert cmd[:3] == ["/bin/llama-server", "-m", str(tmp_path / "m.gguf")]
    assert "127.0.0.1" in cmd and "9999" in cmd and "2048" in cmd and "-t" in cmd


def test_start_waits_for_health_then_stops(tmp_path):
    model = tmp_path / "m.gguf"
    model.write_bytes(b"GGUF")
    runtime = nr.NativeRuntime(engine=make_engine(tmp_path))
    url = runtime.start(model, ready_timeout=20)
    assert url.startswith("http://127.0.0.1:") and runtime.running
    assert runtime.start(model) == url  # idempotent for the same model
    runtime.stop()
    assert not runtime.running


def test_missing_engine_and_model_give_clear_errors(tmp_path):
    runtime = nr.NativeRuntime(engine=None)
    runtime.engine = None
    with pytest.raises(nr.NativeRuntimeError, match="pkg install llama-cpp"):
        runtime.start(tmp_path / "m.gguf")
    runtime = nr.NativeRuntime(engine=make_engine(tmp_path))
    with pytest.raises(nr.NativeRuntimeError, match="not found"):
        runtime.start(tmp_path / "nope.gguf")


def test_engine_crash_is_reported(tmp_path):
    model = tmp_path / "m.gguf"
    model.write_bytes(b"GGUF")
    crash = make_engine(tmp_path, "#!/bin/sh\nexit 3\n")
    with pytest.raises(nr.NativeRuntimeError, match="exited early"):
        nr.NativeRuntime(engine=crash).start(model, ready_timeout=10)
