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
