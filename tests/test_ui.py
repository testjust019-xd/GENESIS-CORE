import io

from genesis_core import ui


def test_paint_disabled_is_plain():
    assert ui.paint("hi", "bold", enabled=False) == "hi"
    assert ui.paint("hi", "bold", enabled=True) == "\033[1mhi\033[0m"


def test_no_color_env_disables(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert ui.color_enabled(io.StringIO()) is False


def test_box_lines_have_equal_visible_width():
    out = ui.box(["short", "a much longer line of text"], title="T", width=40, enabled=False)
    widths = {len(line) for line in out.splitlines()}
    assert widths == {40}


def test_welcome_panel_mentions_session_and_model():
    out = ui.welcome_panel("1.2.3", "My chat", "ollama/llama3", "/ws", enabled=False)
    assert "My chat" in out and "ollama/llama3" in out and "v1.2.3" in out


def test_prompt_plain_without_color():
    assert ui.prompt_string("Chat", enabled=False) == "genesis [Chat] › "
    assert "\001" in ui.prompt_string("Chat", enabled=True)


def test_markdown_stream_handles_code_fences_across_chunks():
    out = io.StringIO()
    md = ui.MarkdownStream(out=out, enabled=False)
    for chunk in ["# Ti", "tle\n- item **b**\n``", "`py\nx = `1`\n```\nend"]:
        md.feed(chunk)
    md.finish()
    text = out.getvalue()
    assert "  Title\n" in text
    assert "  • item b\n" in text
    assert "┌ py" in text and "│ x = `1`" in text  # no inline formatting inside code
    assert "  end\n" in text


def test_format_activity():
    line = ui.format_activity({"type": "tool", "tool": "read_file", "status": "ok"}, enabled=False)
    assert "read_file" in line and "ok" in line
    assert ui.format_activity({"type": "other"}) is None
    assert "boom" in ui.format_activity({"type": "error", "detail": "boom"}, enabled=False)


def test_help_grouped_and_filtered():
    full = ui.render_help(enabled=False)
    assert "Missions" in full and "/mission plan <id>" in full
    only = ui.render_help("approval", enabled=False)
    assert "/approvals" in only and "/mission plan" not in only
    assert "No command matches" in ui.render_help("zzzz", enabled=False)


def test_completion():
    assert "/mission " in ui.complete_line("/mi", "/mi")
    assert "/missions " in ui.complete_line("/mi", "/mi")
    assert ui.complete_line("/mission p", "p") == ["plan "]
    assert ui.complete_line("/mission plan x", "x") == []


def test_spinner_silent_when_not_tty():
    buf = io.StringIO()
    with ui.Spinner("x", stream=buf):
        pass
    assert buf.getvalue() == ""


def test_avatar_states_and_widths():
    for state in ("idle", "thinking", "happy", "alert", "error"):
        lines = ui.avatar_lines(state, enabled=False)
        assert len(lines) == 4 and {len(l) for l in lines} == {9}
    assert "◉" in "".join(ui.avatar_lines("idle", enabled=False))
    assert ui.mini_face("happy", enabled=False) == "(◕‿◕)"


def test_welcome_panel_shows_avatar_only_when_wide():
    wide = ui.welcome_panel("1", "S", "m", "/w", enabled=False, width=80)
    narrow = ui.welcome_panel("1", "S", "m", "/w", enabled=False, width=50)
    assert "╰─┬─┬─╯" in wide and "╰─┬─┬─╯" not in narrow
    assert {len(l) for l in wide.splitlines()} == {80}


def test_ask_approval_yes_no_and_eof():
    req = {"id": "a1", "tool": "write_note", "arguments": {"text": "x"}, "reason": "needs write"}
    out = io.StringIO()
    assert ui.ask_approval(req, input_fn=lambda _: "y", out=out, enabled=False) is True
    assert "Approval needed" in out.getvalue() and "write_note" in out.getvalue()
    assert ui.ask_approval(req, input_fn=lambda _: "", out=io.StringIO(), enabled=False) is False

    def eof(_):
        raise EOFError

    assert ui.ask_approval(req, input_fn=eof, out=io.StringIO(), enabled=False) is False


def test_spinner_can_restart():
    sp = ui.Spinner("x", stream=io.StringIO())
    sp.start()
    sp.stop()
    sp.start()
    sp.stop()
