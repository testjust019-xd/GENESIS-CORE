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
    for style in ui.AVATAR_STYLES:
        for state in ui.FACES:
            lines = ui.avatar_lines(state, enabled=False, style=style)
            assert len(lines) == 4 and len({len(l) for l in lines}) == 1, (style, state)
    assert "◉" in "".join(ui.avatar_lines("idle", enabled=False, style="robot"))
    assert "─" in ui.avatar_lines("blink", enabled=False, style="orb")[1]
    assert ui.mini_face("happy", enabled=False) == "(◕‿◕)"


def test_avatar_style_selection_and_fallback():
    try:
        assert ui.set_avatar_style("owl") == "owl" and ui.get_avatar_style() == "owl"
        assert ui.set_avatar_style("nope") == ui.DEFAULT_AVATAR == "orb"
        assert ui.set_avatar_style(None) == "orb"
    finally:
        ui.set_avatar_style(None)


def test_welcome_panel_shows_avatar_only_when_wide():
    wide = ui.welcome_panel("1", "S", "m", "/w", enabled=False, width=80)
    narrow = ui.welcome_panel("1", "S", "m", "/w", enabled=False, width=50)
    assert "╲_____╱" in wide and "╲_____╱" not in narrow
    assert {len(l) for l in wide.splitlines()} == {80}
    for style in ui.AVATAR_STYLES:
        ui.set_avatar_style(style)
        assert {len(l) for l in ui.welcome_panel("1", "S", "m", "/w", enabled=False, width=80).splitlines()} == {80}
    ui.set_avatar_style(None)


def test_play_intro_single_draw_when_not_tty():
    out = io.StringIO()
    states = []
    ui.play_intro(lambda st: states.append(st) or "PANEL", out=out, sleep=lambda s: None)
    assert out.getvalue() == "PANEL\n" and states == ["idle"]


def test_play_intro_animates_on_tty(monkeypatch):
    class TTY(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("GENESIS_NO_ANIMATION", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    out, states, pauses = TTY(), [], []
    ui.play_intro(lambda st: states.append(st) or "L1\nL2", out=out, sleep=pauses.append)
    # first render is a height probe, then one render per frame
    assert states[1:] == ["blink", "idle", "blink", "happy", "idle"]
    assert out.getvalue().count("\033[2A") == 4 and len(pauses) == 5
    monkeypatch.setenv("GENESIS_NO_ANIMATION", "1")
    quiet = TTY()
    ui.play_intro(lambda st: "X", out=quiet, sleep=pauses.append)
    assert quiet.getvalue() == "X\n"


def test_event_faces():
    assert "(◐▾◐)" in ui.format_tool_start({"tool": "t"}, enabled=False)


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


def test_read_multiline_joins_backslash_continuations():
    answers = iter(["line one \\", "line two \\", "line three"])
    assert ui.read_multiline("> ", input_fn=lambda _: next(answers)) == "line one\nline two\nline three"
    assert ui.read_multiline("> ", input_fn=lambda _: "single") == "single"


def test_reply_footer_and_token_estimate():
    assert ui.estimate_tokens("") == 0 and ui.estimate_tokens("abcdefgh") == 2
    footer = ui.reply_footer("ollama", "q", 2.345, "x" * 40, enabled=False)
    assert "ollama/q" in footer and "2.3s" in footer and "~10 tokens" in footer


def test_conversation_markdown_and_filename():
    md = ui.conversation_to_markdown("Chat", [
        {"role": "user", "content": "hi"}, {"role": "system", "content": "skip"},
        {"role": "assistant", "content": "hello"},
    ])
    assert md.startswith("# Chat") and "## You\n\nhi" in md and "## GENESIS\n\nhello" in md and "skip" not in md
    assert ui.safe_filename("Salut / ça va?") == "Salut-ça-va"
    assert ui.safe_filename("///") == "conversation"


def test_sparkline_and_renderers():
    assert ui.sparkline([0, 0.5, 1]) == "▁▅█" and ui.sparkline([]) == ""
    run = {"id": "r1", "suite": "s", "label": "baseline", "provider": "p", "model": "m", "score": 0.5,
           "passed": 1, "total": 2, "errors": 0, "duration": 3.0,
           "results": [{"task_id": "a", "passed": True}, {"task_id": "b", "passed": False, "error": None}]}
    text = ui.render_run(run, enabled=False)
    assert "Score 50%" in text and "a" in text and "b" in text
    comp = {"verdict": "improved", "delta": 0.3, "base_score": 0.5, "candidate_score": 0.8,
            "improved": ["a"], "regressed": [], "caveat": "noisy"}
    out = ui.render_comparison(comp, enabled=False)
    assert "IMPROVED" in out and "+30 pts" in out and "now pass: a" in out and "noisy" in out
