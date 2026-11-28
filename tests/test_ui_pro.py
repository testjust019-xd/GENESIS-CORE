import io

import pytest

from genesis_core import ui


def test_highlight_code_colours_tokens():
    line = 'def run(x): return "a" + 3  # note'
    out = ui.highlight_code(line, "python", enabled=True)
    assert ui.strip_ansi(out) == line
    assert "\033[95mdef\033[0m" in out and "\033[92m\"a\"\033[0m" in out
    assert "\033[93m3\033[0m" in out and "\033[90m# note\033[0m" in out
    assert ui.highlight_code(line, "python", enabled=False) == line
    assert ui.strip_ansi(ui.highlight_code("x = 1", "unknownlang", enabled=True)) == "x = 1"
    assert ui.highlight_code("", "python", enabled=True) == ""


def test_markdown_stream_highlights_by_fence_language():
    out = io.StringIO()
    md = ui.MarkdownStream(out=out, enabled=True)
    md.feed("```bash\nif true; then echo 'hi'\n```\n")
    md.finish()
    text = out.getvalue()
    assert "\033[95mif\033[0m" in text and ui.strip_ansi(text).count("hi") == 1


def test_render_diff_colours_additions_and_removals():
    out = ui.render_diff("a\nb\n", "a\nc\n", enabled=False)
    assert "-b" in out and "+c" in out
    assert "\033[92m+c\033[0m" in ui.render_diff("a\nb\n", "a\nc\n", enabled=True)
    assert "no changes" in ui.render_diff("same", "same", enabled=False)
    big = ui.render_diff("", "\n".join(str(i) for i in range(200)), enabled=False, max_lines=10)
    assert "more line(s)" in big


def test_build_write_diff_is_confined_to_workspace(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "notes.md").write_text("old\n")
    diff = ui.build_write_diff({"path": "notes.md", "content": "new\n"}, ws, enabled=False)
    assert "-old" in diff and "+new" in diff
    fresh = ui.build_write_diff({"path": "sub/new.txt", "text": "hello\n"}, ws, enabled=False)
    assert "+hello" in fresh
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET")
    assert ui.build_write_diff({"path": "../secret.txt", "content": "x"}, ws) is None
    assert ui.build_write_diff({"path": str(secret), "content": "x"}, ws) is None
    assert ui.build_write_diff({"query": "x"}, ws) is None


@pytest.mark.parametrize("answer,expected", [
    ("y", "yes"), ("OUI", "yes"), ("a", "always"), ("always", "always"), ("", "no"), ("maybe", "no")])
def test_approval_choice(answer, expected):
    out = io.StringIO()
    req = {"tool": "write_note", "arguments": {}, "diff": "+added line"}
    assert ui.ask_approval_choice(req, input_fn=lambda _: answer, out=out, enabled=False) == expected
    assert "+added line" in out.getvalue()


def test_approval_choice_eof_and_bool_wrapper():
    def eof(_):
        raise EOFError

    assert ui.ask_approval_choice({"tool": "t"}, input_fn=eof, out=io.StringIO(), enabled=False) == "no"
    assert ui.ask_approval({"tool": "t"}, input_fn=lambda _: "a", out=io.StringIO(), enabled=False) is True
    assert ui.ask_approval({"tool": "t"}, input_fn=lambda _: "n", out=io.StringIO(), enabled=False) is False


def test_completion_items_with_descriptions():
    items = dict(ui.completion_items("/mi"))
    assert "/mission" in items and "/missions" in items and items["/missions"]
    assert ui.completion_items("hello") == []
    assert [i for i, _ in ui.completion_items("/mission pl")] == ["plan"]
    assert ui.completion_items("/mission plan x") == []
    descriptions = ui.command_descriptions()
    assert descriptions["/new"] and descriptions["/avatar"] and descriptions["/eval"]


def test_toolbar_text():
    text = ui.toolbar_text("native/qwen", "My chat", 5, 0, 0.8)
    assert "native/qwen" in text and "5 tools" in text and "bench 80%" in text and "pending" not in text
    assert "2 approval(s) pending" in ui.toolbar_text("m", "s", 1, 2)
    assert "bench" not in ui.toolbar_text("m", "s", 1, 0, None)


def test_prompt_markers_optional():
    assert "\001" in ui.prompt_string("Chat", enabled=True, markers=True)
    assert "\001" not in ui.prompt_string("Chat", enabled=True, markers=False)


def test_pt_front_end_not_used_without_terminal(monkeypatch):
    from genesis_core import ui_pt

    monkeypatch.setattr("sys.stdin", io.StringIO())
    assert ui_pt.should_use() is False
    monkeypatch.setenv("GENESIS_NO_PT", "1")
    assert ui_pt.should_use() is False


def test_pt_session_completer_and_toolbar(tmp_path):
    pytest.importorskip("prompt_toolkit")
    from prompt_toolkit.document import Document

    from genesis_core import ui_pt

    session = ui_pt.build_session(tmp_path / "hist", lambda: "status!")
    completions = list(session.completer.get_completions(Document("/mi"), None))
    texts = {c.text for c in completions}
    assert {"/mission", "/missions"} <= texts
    assert all(c.start_position == -3 for c in completions)
    meta = {c.text: c.display_meta_text for c in completions}
    assert meta["/missions"]
    sub = list(session.completer.get_completions(Document("/mission pl"), None))
    assert [c.text for c in sub] == ["plan"] and sub[0].start_position == -2
    assert session.complete_while_typing
