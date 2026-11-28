import io
from contextlib import redirect_stdout

import pytest

from genesis_core import tui


def run_session(monkeypatch, tmp_path, lines):
    monkeypatch.setenv("GENESIS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("GENESIS_MODEL", raising=False)
    monkeypatch.delenv("GENESIS_MODEL_PROVIDER", raising=False)
    monkeypatch.setattr("genesis_core.config.settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(tui, "read_settings", lambda: __import__("json").loads(
        (tmp_path / "settings.json").read_text()) if (tmp_path / "settings.json").exists() else {})
    monkeypatch.setattr(tui, "set_model", lambda p, m, base_url=None: (tmp_path / "settings.json").write_text(
        __import__("json").dumps({"model": {"provider": p, "name": m}})) or tmp_path / "settings.json")
    monkeypatch.setattr(tui, "discover_runtimes", lambda: [])
    answers = iter(lines)
    monkeypatch.setattr("builtins.input", lambda _="": next(answers))
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = tui.run_tui()
    assert code == 0
    return buf.getvalue()


def test_export_and_model_commands(monkeypatch, tmp_path):
    out = run_session(monkeypatch, tmp_path, ["/export", "/model", "/model ollama tiny", "/model", "/quit"])
    assert "Nothing to export yet" in out
    assert "auto-detect" in out
    assert "Primary model set to ollama/tiny" in out
    assert "ollama/tiny" in out.split("Primary model set to")[1]


def test_model_rejects_bad_input(monkeypatch, tmp_path):
    out = run_session(monkeypatch, tmp_path, ["/model 9", "/quit"])
    assert "Use /model <number>" in out


def test_model_install_downloads_starts_engine_and_remembers(monkeypatch, tmp_path):
    import json
    from genesis_core import model_hub

    home = tmp_path / "home"
    settings = tmp_path / "settings.json"
    monkeypatch.setenv("GENESIS_HOME", str(home))
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("GENESIS_MODEL", raising=False)
    monkeypatch.delenv("GENESIS_MODEL_PROVIDER", raising=False)
    monkeypatch.setattr(tui, "read_settings", lambda: json.loads(settings.read_text()) if settings.exists() else {})
    monkeypatch.setattr(tui, "write_settings", lambda data: settings.write_text(json.dumps(data)) or settings)
    monkeypatch.setattr(tui, "discover_runtimes", lambda: [])

    def fake_download(model, directory=None, progress=None, **kw):
        target = model_hub.models_dir(home)
        target.mkdir(parents=True, exist_ok=True)
        path = target / model.filename
        path.write_bytes(b"GGUF" + b"0" * 64)
        progress(len(b"GGUF") + 64, 68)
        return path

    started = []
    monkeypatch.setattr(tui.model_hub, "download", fake_download)
    monkeypatch.setattr(tui.model_hub, "installed_models", lambda *a: sorted((model_hub.models_dir(home)).glob("*.gguf")))
    monkeypatch.setattr(tui, "find_engine", lambda: "/fake/llama-server")
    monkeypatch.setattr(tui, "_activate_native", lambda agent, native, path: started.append(path.name) or f"native/{path.name}")
    answers = iter(["/model install", "", "/model", "/quit"])
    monkeypatch.setattr("builtins.input", lambda _="": next(answers))
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert tui.run_tui() == 0
    out = buf.getvalue()
    assert "recommended for this device" in out
    assert "Ready: native/" in out and started
    assert json.loads(settings.read_text())["native"]["file"] == started[0]
    assert "Downloaded (run by GENESIS)" in out


def test_model_install_reports_missing_engine(monkeypatch, tmp_path):
    out = None
    from genesis_core import model_hub
    import json

    home = tmp_path / "home"
    settings = tmp_path / "settings.json"
    monkeypatch.setenv("GENESIS_HOME", str(home))
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(tui, "read_settings", lambda: json.loads(settings.read_text()) if settings.exists() else {})
    monkeypatch.setattr(tui, "write_settings", lambda data: settings.write_text(json.dumps(data)) or settings)
    monkeypatch.setattr(tui, "discover_runtimes", lambda: [])
    monkeypatch.setattr(tui.model_hub, "download", lambda m, directory=None, progress=None, **kw: (
        (model_hub.models_dir(home).mkdir(parents=True, exist_ok=True)),
        (model_hub.models_dir(home) / m.filename).write_bytes(b"GGUF"),
        model_hub.models_dir(home) / m.filename)[2])
    monkeypatch.setattr(tui, "find_engine", lambda: None)
    answers = iter(["/model install qwen2.5-0.5b", "/quit"])
    monkeypatch.setattr("builtins.input", lambda _="": next(answers))
    buf = io.StringIO()
    with redirect_stdout(buf):
        tui.run_tui()
    assert "engine is missing" in buf.getvalue() and "pkg install llama-cpp" in buf.getvalue()


def test_eval_and_evolve_commands(monkeypatch, tmp_path):
    import json
    from types import SimpleNamespace
    from genesis_core import agent as agent_module

    class Fake:
        config = SimpleNamespace(provider="fake", model="tiny")

        def chat(self, messages):
            prompt = messages[-1]["content"]
            return "43" if "17 + 26" in prompt else "wrong"

    settings = tmp_path / "settings.json"
    monkeypatch.setenv("GENESIS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(tui, "read_settings", lambda: json.loads(settings.read_text()) if settings.exists() else {})
    monkeypatch.setattr(tui, "discover_runtimes", lambda: [])
    monkeypatch.setattr(agent_module, "create_chat_adapter", lambda: Fake())
    monkeypatch.setattr("genesis_core.evaluation.create_chat_adapter", lambda: Fake())
    answers = iter(["/evolve", "/eval", "/eval run", "/eval history", "/eval skill nope", "/evolve", "/quit"])
    monkeypatch.setattr("builtins.input", lambda _="": next(answers))
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert tui.run_tui() == 0
    out = buf.getvalue()
    assert "No baseline yet" in out
    assert "core-basics" in out
    import re
    assert re.search(r"Score \d+%\s+\(\d+/10 tasks passed", out)
    assert "arith-1" in out
    assert "fake/tiny" in out
    assert "Skill nope not found" in out
    assert re.search(r"Baseline score\s+\S+\s+\d+% → \d+%\s+\(1 run\(s\)", out)


def test_avatar_command_persists_style(monkeypatch, tmp_path):
    import json

    settings = tmp_path / "settings.json"
    monkeypatch.setenv("GENESIS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(tui, "read_settings", lambda: json.loads(settings.read_text()) if settings.exists() else {})
    monkeypatch.setattr(tui, "write_settings", lambda data: settings.write_text(json.dumps(data)) or settings)
    monkeypatch.setattr(tui, "discover_runtimes", lambda: [])
    answers = iter(["/avatar", "/avatar owl", "/avatar dragon", "/quit"])
    monkeypatch.setattr("builtins.input", lambda _="": next(answers))
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            assert tui.run_tui() == 0
    finally:
        tui.ui.set_avatar_style(None)
    out = buf.getvalue()
    assert "Current avatar: orb" in out and "Avatar set to owl." in out
    assert "Unknown style 'dragon'" in out
    assert json.loads(settings.read_text())["avatar"]["style"] == "owl"


def test_approve_always_skips_next_prompt(monkeypatch, tmp_path):
    import json
    from types import SimpleNamespace

    from genesis_core import agent as agent_module
    from genesis_core.tools import ToolRegistry, ToolSpec

    calls = []
    registry_holder = {}
    real_build = tui.build_core_registry

    def build(workspace):
        registry = real_build(workspace)
        registry.register(ToolSpec(
            "write_note", "Write a note", {"type": "object", "properties": {}, "additionalProperties": False},
            lambda _a: calls.append(1) or {"ok": True},
            capabilities=frozenset({"workspace_write"}), risk="write"))
        return registry

    class Fake:
        config = SimpleNamespace(provider="fake", model="m")

        def __init__(self):
            self.turn = 0

        def chat(self, messages):
            self.turn += 1
            if self.turn in (1, 3):
                return json.dumps({"action": "tool", "tool": "write_note", "arguments": {}})
            return json.dumps({"action": "final", "message": "done"})

    home = tmp_path / "home"
    (home / "config").mkdir(parents=True)
    monkeypatch.setenv("GENESIS_HOME", str(home))
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(tui, "build_core_registry", build)
    monkeypatch.setattr(tui, "discover_runtimes", lambda: [])
    monkeypatch.setattr(agent_module, "create_chat_adapter", lambda: Fake())
    answers = iter(["first request", "a", "second request", "/quit"])
    prompts = []

    def fake_input(prompt=""):
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr("builtins.input", fake_input)
    buf = io.StringIO()
    with redirect_stdout(buf):
        tui.run_tui()
    out = buf.getvalue()
    assert calls == [1, 1], out
    assert "auto-approved for this session" in out
    assert sum("Allow?" in p for p in prompts) == 1
