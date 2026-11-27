"""Dependency-free terminal presentation helpers for the GENESIS TUI.

Everything here uses only the standard library so the TUI stays usable on
modest machines (Termux, SSH, minimal containers). Colour is disabled
automatically when output is not a terminal or ``NO_COLOR`` is set.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Iterable, TextIO

try:  # readline is unavailable on some platforms
    import readline  # type: ignore
except ImportError:  # pragma: no cover - platform dependent
    readline = None  # type: ignore

# --------------------------------------------------------------------------- #
# Colour
# --------------------------------------------------------------------------- #

_CODES = {
    "reset": "0", "bold": "1", "dim": "2", "italic": "3", "underline": "4",
    "red": "31", "green": "32", "yellow": "33", "blue": "34", "magenta": "35",
    "cyan": "36", "gray": "90", "bright_cyan": "96", "bright_green": "92",
    "bright_yellow": "93", "bright_red": "91", "bright_magenta": "95",
}

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def color_enabled(stream: TextIO | None = None) -> bool:
    """Return True when ANSI colour should be emitted for ``stream``."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    stream = stream or sys.stdout
    return bool(getattr(stream, "isatty", lambda: False)()) and os.environ.get("TERM") != "dumb"


def paint(text: str, *styles: str, enabled: bool | None = None) -> str:
    """Wrap ``text`` in ANSI styles (no-op when colour is disabled)."""
    if enabled is None:
        enabled = color_enabled()
    if not enabled or not styles or not text:
        return text
    prefix = "".join(f"\033[{_CODES[s]}m" for s in styles if s in _CODES)
    return f"{prefix}{text}\033[0m"


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def visible_len(text: str) -> int:
    return len(strip_ansi(text))


def term_width(default: int = 80) -> int:
    return max(40, min(shutil.get_terminal_size((default, 24)).columns, 120))


def _truncate(text: str, width: int) -> str:
    """Truncate to ``width`` visible characters (ANSI-aware enough for our use)."""
    if visible_len(text) <= width:
        return text
    plain = strip_ansi(text)
    return plain[: max(0, width - 1)] + "…"


# --------------------------------------------------------------------------- #
# Boxes and header
# --------------------------------------------------------------------------- #

def box(lines: Iterable[str], title: str = "", width: int | None = None,
        style: str = "bright_cyan", enabled: bool | None = None) -> str:
    """Render ``lines`` inside a rounded box with an optional title."""
    width = width or term_width()
    inner = width - 4
    out: list[str] = []
    head = f" {title} " if title else ""
    top = "╭─" + head + "─" * max(0, width - 3 - len(head)) + "╮"
    out.append(paint(top, style, enabled=enabled))
    for line in lines:
        line = _truncate(line, inner)
        pad = " " * (inner - visible_len(line))
        out.append(paint("│", style, enabled=enabled) + f" {line}{pad} " + paint("│", style, enabled=enabled))
    out.append(paint("╰" + "─" * (width - 2) + "╯", style, enabled=enabled))
    return "\n".join(out)


BACKSLASH = "\\"  # kept out of f-string expressions (invalid before Python 3.12)

AVATAR_ART = (
    " ╭─────╮ ",
    " │ {e} {e} │ ",
    " │  {m}  │ ",
    " ╰─┬─┬─╯ ",
)

# state -> (eyes, mouth)
FACES = {
    "idle": ("◉", "▾"),
    "thinking": ("◔", "~"),
    "happy": ("◕", "‿"),
    "alert": ("◉", "o"),
    "error": ("✖", "▾"),
}


def avatar_lines(state: str = "idle", enabled: bool | None = None) -> list[str]:
    """The GENESIS mascot as four lines, 9 columns wide."""
    eyes, mouth = FACES.get(state, FACES["idle"])
    style = "bright_yellow" if state == "alert" else "bright_red" if state == "error" else "bright_cyan"
    rows = []
    for row in AVATAR_ART:
        row = row.format(e=eyes, m=mouth)
        rows.append(paint(row, style, enabled=enabled))
    return rows


def mini_face(state: str = "idle", enabled: bool | None = None) -> str:
    """One-glyph-wide-ish face used beside replies: ``(◉▾◉)``."""
    eyes, mouth = FACES.get(state, FACES["idle"])
    style = "bright_yellow" if state == "alert" else "bright_red" if state == "error" else "bright_cyan"
    return paint(f"({eyes}{mouth}{eyes})", style, enabled=enabled)


def welcome_panel(version: str, session_title: str, model: str, workspace: str,
                  enabled: bool | None = None, width: int | None = None) -> str:
    """Compact Claude-Code-style welcome panel with the GENESIS avatar."""
    b = lambda s: paint(s, "bold", enabled=enabled)  # noqa: E731
    d = lambda s: paint(s, "dim", enabled=enabled)  # noqa: E731
    c = lambda s: paint(s, "bright_cyan", "bold", enabled=enabled)  # noqa: E731
    info_rows = [
        f"{c('GENESIS CORE')}  {d('v' + version)}",
        f"{d('session')}    {b(session_title)}",
        f"{d('model')}      {b(model)}",
        f"{d('workspace')}  {workspace}",
    ]
    width = width or term_width()
    if width >= 60:
        art = avatar_lines("idle", enabled)
        top = [f"{left} {right}" for left, right in zip(art, info_rows)]
    else:
        top = info_rows
    tips = [
        "",
        d("Tips"),
        f"  {c('/help')} commands   {c('/new')} conversation   {c('/models')} runtimes",
        f"  {c('Tab')} complete   {c('↑/↓')} history   {c(BACKSLASH)} new line   {c('Ctrl+C')} stop   {c('Ctrl+D')} quit",
    ]
    return box(top + tips, width=width, enabled=enabled)


def approval_card(request: dict, enabled: bool | None = None, width: int | None = None) -> str:
    """Boxed description of a gated tool call, shown before asking y/n."""
    import json as _json

    args = request.get("arguments") or {}
    try:
        rendered = _json.dumps(args, ensure_ascii=False)
    except (TypeError, ValueError):
        rendered = str(args)
    lines = [
        f"{paint('Tool', 'dim', enabled=enabled)}    {paint(str(request.get('tool', '?')), 'bold', enabled=enabled)}",
        f"{paint('Args', 'dim', enabled=enabled)}    {rendered}",
    ]
    if request.get("reason"):
        lines.append(f"{paint('Why', 'dim', enabled=enabled)}     {request['reason']}")
    return box(lines, title="Approval needed", width=width, style="bright_yellow", enabled=enabled)


def ask_approval(request: dict, input_fn=None, out: TextIO | None = None,
                 enabled: bool | None = None) -> bool:
    """Show an approval card and ask ``[y/N]``. Anything but yes (or EOF) declines."""
    input_fn = input_fn or input
    out = out or sys.stdout
    out.write("\n" + approval_card(request, enabled=enabled) + "\n")
    out.flush()
    try:
        answer = input_fn(paint("  Allow this action? [y/N] ", "bright_yellow", enabled=enabled)).strip().lower()
    except (EOFError, KeyboardInterrupt):
        out.write("\n")
        return False
    return answer in {"y", "yes", "o", "oui"}


def format_tool_start(event: dict, enabled: bool | None = None) -> str:
    """Live line printed while a tool is running."""
    args = event.get("arguments") or {}
    brief = ", ".join(f"{k}={str(v)[:40]!r}" for k, v in list(args.items())[:2])
    return (paint("  ⚙ ", "bright_cyan", enabled=enabled)
            + paint(str(event.get("tool", "tool")), "bold", enabled=enabled)
            + (paint(f"  {brief}", "dim", enabled=enabled) if brief else ""))


# --------------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------------- #

def prompt_string(session_title: str, enabled: bool | None = None) -> str:
    """Prompt with zero-width markers so readline measures the width correctly."""
    if enabled is None:
        enabled = color_enabled()
    label = session_title[:28]
    if not enabled:
        return f"genesis [{label}] › "

    def w(code: str) -> str:  # wrap non-printing sequences for readline
        return f"\001\033[{code}m\002"

    return (f"{w('1;96')}genesis{w('0')} {w('90')}[{label}]{w('0')} {w('96')}›{w('0')} ")


def status_line(model_label: str, tools: int, pending_approvals: int,
                enabled: bool | None = None) -> str:
    """One-line footer shown above the prompt."""
    base = paint(f"  {model_label} · {tools} tools", "dim", enabled=enabled)
    if pending_approvals:
        base += paint(f" · {pending_approvals} approval(s) pending (/approvals)", "bright_yellow", enabled=enabled)
    return base


# --------------------------------------------------------------------------- #
# Messages
# --------------------------------------------------------------------------- #

def info(text: str, enabled: bool | None = None) -> str:
    return paint("● ", "bright_cyan", enabled=enabled) + text


def ok(text: str, enabled: bool | None = None) -> str:
    return paint("✔ ", "bright_green", enabled=enabled) + text


def warn(text: str, enabled: bool | None = None) -> str:
    return paint("▲ ", "bright_yellow", enabled=enabled) + text


def error(text: str, enabled: bool | None = None) -> str:
    return paint("✖ ", "bright_red", enabled=enabled) + text


_STATUS_STYLE = {
    "ok": ("✔", "bright_green"), "success": ("✔", "bright_green"), "completed": ("✔", "bright_green"),
    "pending_approval": ("?", "bright_yellow"), "denied": ("✖", "bright_red"),
    "error": ("✖", "bright_red"), "failed": ("✖", "bright_red"), "blocked": ("▲", "bright_yellow"),
}


def format_activity(event: dict, enabled: bool | None = None) -> str | None:
    """Format one agent activity event as a tool-trace line (None to skip)."""
    kind = event.get("type")
    if kind == "tool":
        status = str(event.get("status", ""))
        glyph, style = _STATUS_STYLE.get(status, ("•", "bright_cyan"))
        return (paint(f"  {glyph} ", style, enabled=enabled)
                + paint(str(event.get("tool", "tool")), "bold", enabled=enabled)
                + paint(f"  {status}", "dim", enabled=enabled))
    if kind in {"tool_error", "error", "limit", "loop_guard"}:
        detail = str(event.get("detail", kind))
        return paint("  ▲ ", "bright_yellow", enabled=enabled) + paint(detail, "dim", enabled=enabled)
    return None


# --------------------------------------------------------------------------- #
# Lightweight markdown rendering (line oriented so it can stream)
# --------------------------------------------------------------------------- #

_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_BOLD = re.compile(r"\*\*([^*\n]+)\*\*")


def render_inline(text: str, enabled: bool | None = None) -> str:
    text = _INLINE_CODE.sub(lambda m: paint(m.group(1), "bright_yellow", enabled=enabled), text)
    text = _BOLD.sub(lambda m: paint(m.group(1), "bold", enabled=enabled), text)
    return text


class MarkdownStream:
    """Incremental line-based markdown renderer.

    Feed raw token chunks with :meth:`feed`; complete lines are rendered and
    written immediately. Call :meth:`finish` to flush a trailing partial line.
    Fenced code blocks get a dim gutter and are never inline-formatted.
    """

    def __init__(self, out: TextIO | None = None, enabled: bool | None = None, indent: str = "  "):
        self.out = out or sys.stdout
        self.enabled = color_enabled(self.out) if enabled is None else enabled
        self.indent = indent
        self._buffer = ""
        self._in_code = False
        self.wrote = False

    def feed(self, chunk: str) -> None:
        self._buffer += chunk
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._emit(line)

    def finish(self) -> None:
        if self._buffer:
            self._emit(self._buffer)
            self._buffer = ""

    def _emit(self, line: str) -> None:
        self.wrote = True
        e = self.enabled
        stripped = line.strip()
        if stripped.startswith("```"):
            if not self._in_code:
                lang = stripped[3:].strip()
                self._in_code = True
                label = paint(f"┌ {lang}" if lang else "┌", "gray", enabled=e)
                self.out.write(f"{self.indent}{label}\n")
            else:
                self._in_code = False
                self.out.write(f"{self.indent}{paint('└', 'gray', enabled=e)}\n")
        elif self._in_code:
            self.out.write(f"{self.indent}{paint('│', 'gray', enabled=e)} {paint(line, 'bright_green', enabled=e)}\n")
        elif stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            self.out.write(f"{self.indent}{paint(title, 'bold', 'bright_cyan', enabled=e)}\n")
        elif re.match(r"^\s*[-*]\s+", line):
            body = re.sub(r"^\s*[-*]\s+", "", line)
            lead = len(line) - len(line.lstrip())
            self.out.write(f"{self.indent}{' ' * lead}{paint('•', 'cyan', enabled=e)} {render_inline(body, e)}\n")
        elif stripped.startswith(">"):
            self.out.write(f"{self.indent}{paint('▎', 'gray', enabled=e)} {paint(stripped.lstrip('> '), 'italic', enabled=e)}\n")
        else:
            self.out.write(f"{self.indent}{render_inline(line, e)}\n")
        self.out.flush()


# --------------------------------------------------------------------------- #
# Spinner
# --------------------------------------------------------------------------- #

class Spinner:
    """Animated "thinking" indicator written to stderr; silent when not a TTY."""

    FRAMES = ("(◔▾◔)", "(◔~◔)", "(◑▾◑)", "(◕~◕)", "(◕▾◕)", "(◑~◑)")

    def __init__(self, label: str = "Thinking", stream: TextIO | None = None):
        self.label = label
        self.stream = stream or sys.stderr
        self.active = bool(getattr(self.stream, "isatty", lambda: False)()) and os.environ.get("TERM") != "dumb"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._start = 0.0
        self._lock = threading.Lock()
        self._visible = False

    def start(self) -> None:
        """(Re)start the animation. Safe after :meth:`stop`."""
        if self.active and self._thread is None:
            self._stop = threading.Event()
            self._start = time.monotonic()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def __enter__(self) -> "Spinner":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def _run(self) -> None:
        i = 0
        while not self._stop.is_set():
            elapsed = time.monotonic() - self._start
            frame = self.FRAMES[i % len(self.FRAMES)]
            text = f"\r{paint(frame, 'bright_cyan', enabled=True)} {paint(self.label + '…', 'dim', enabled=True)} {paint(f'{elapsed:0.0f}s · Ctrl+C to stop', 'gray', enabled=True)}"
            with self._lock:
                if not self._stop.is_set():
                    self.stream.write(text)
                    self.stream.flush()
                    self._visible = True
            i += 1
            self._stop.wait(0.22)

    def stop(self) -> None:
        """Stop and erase the spinner line. Safe to call repeatedly."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
            self._thread = None
        with self._lock:
            if self._visible:
                self.stream.write("\r\033[2K")
                self.stream.flush()
                self._visible = False


# --------------------------------------------------------------------------- #
# Slash-command registry, grouped help and tab completion
# --------------------------------------------------------------------------- #

HELP_SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Conversations", [
        ("/new [title]", "Create a conversation"),
        ("/sessions", "List shared conversations"),
        ("/open <id>", "Switch conversation"),
        ("/history", "Show current conversation"),
        ("/clear", "Clear the screen"),
        ("/export [path]", "Save this conversation as Markdown"),
    ]),
    ("Models & tools", [
        ("/models", "Inspect local model runtimes"),
        ("/model [n | provider name]", "Show or switch the primary model"),
        ("/model install [n | hf:repo/file]", "Download a model directly (no Ollama)"),
        ("/model use [n | file]", "Start a downloaded model"),
        ("/tools", "List available agent tools"),
        ("/tool <name> [json]", "Run one tool directly"),
        ("/approvals", "List pending tool approvals"),
        ("/approval <id> approve|reject", "Decide a pending approval"),
    ]),
    ("Memory & knowledge", [
        ("/memory list [type]", "List active memories"),
        ("/memory search <text>", "Search active memories"),
        ("/memory add <type> <text>", "Save an explicit memory"),
        ("/memory mission <id>", "Capture a completed mission as an episode"),
        ("/memory extract [session-id]", "Propose conversation memories"),
        ("/memory candidates [session-id]", "List pending proposals"),
        ("/memory candidate <id> accept|reject", "Review a proposal"),
        ("/memory off|delete <id>", "Deactivate or delete a memory"),
        ("/knowledge add <path>", "Import UTF-8 text or selectable-text PDF"),
        ("/knowledge search <query>", "Search indexed documents"),
        ("/knowledge list|delete <id>", "Manage indexed documents"),
    ]),
    ("Research & learning", [
        ("/research search <query>", "Search web or local knowledge"),
        ("/research sources [state]", "List saved sources"),
        ("/research review <id> approve|reject", "Review a source"),
        ("/research report <run-id> [focus]", "Generate a cited synthesis"),
        ("/research reports [run-id]", "List saved research reports"),
        ("/learn create <goal>", "Create a learning curriculum"),
        ("/learn list | show <course-id>", "Browse curricula"),
        ("/learn answer <lesson-id> <text>", "Submit a lesson answer"),
        ("/learn attempts <lesson-id>", "Show practice attempts"),
    ]),
    ("Evolution Lab", [
        ("/eval run [suite]", "Measure the model on a fixed benchmark suite"),
        ("/eval skill <id> [suite]", "Test a skill: baseline vs with the skill"),
        ("/eval compare <run-a> <run-b>", "Compare two runs"),
        ("/eval show <run-id> | history", "Inspect runs"),
        ("/evolve", "Progress report: scores over time, skills, memory"),
    ]),
    ("Missions", [
        ("/missions", "List missions"),
        ("/mission new <title>", "Create a mission"),
        ("/mission status <id> <status>", "Update mission status"),
        ("/mission plan <id>", "Generate a task plan"),
        ("/mission run <id>", "Execute the next task"),
        ("/mission tasks <id>", "Show mission tasks"),
        ("/mission replan <id> [reason]", "Propose a revised plan after a blocker"),
        ("/mission history <id>", "Show saved plan revisions"),
    ]),
    ("General", [
        ("/help [filter]", "Show this help (optionally filtered)"),
        ("/quit", "Exit"),
    ]),
]

SLASH_COMMANDS: list[str] = sorted({
    "/new", "/sessions", "/open", "/history", "/clear", "/export", "/model", "/models", "/tools", "/tool",
    "/approvals", "/approval", "/memory", "/knowledge", "/research", "/learn",
    "/missions", "/mission", "/eval", "/evolve", "/help", "/quit", "/exit",
})

SUBCOMMANDS: dict[str, list[str]] = {
    "/memory": ["list", "search", "add", "mission", "extract", "candidates", "candidate", "off", "delete"],
    "/knowledge": ["add", "search", "list", "delete"],
    "/research": ["search", "sources", "review", "report", "reports"],
    "/learn": ["create", "list", "show", "answer", "attempts"],
    "/model": ["install", "use"],
    "/eval": ["run", "skill", "compare", "show", "history"],
    "/mission": ["new", "status", "plan", "run", "tasks", "replan", "history"],
    "/approval": [],
}


def render_help(filter_text: str = "", enabled: bool | None = None) -> str:
    """Grouped help text, optionally filtered by a substring."""
    needle = filter_text.strip().lower()
    out: list[str] = []
    for section, rows in HELP_SECTIONS:
        rows = [r for r in rows if not needle or needle in r[0].lower() or needle in r[1].lower()]
        if not rows:
            continue
        out.append("")
        out.append(paint(section, "bold", "bright_cyan", enabled=enabled))
        width = max(len(cmd) for cmd, _ in rows)
        for cmd, desc in rows:
            out.append(f"  {paint(cmd.ljust(width), 'bright_yellow', enabled=enabled)}  {paint(desc, 'dim', enabled=enabled)}")
    if not out:
        return warn(f"No command matches '{filter_text}'.", enabled)
    return "\n".join(out) + "\n"


def complete_line(buffer: str, text: str) -> list[str]:
    """Pure completion function (testable without readline)."""
    parts = buffer.lstrip().split(" ")
    if len(parts) <= 1:
        return [c + " " for c in SLASH_COMMANDS if c.startswith(text)]
    command = parts[0].lower()
    if len(parts) == 2:
        return [s + " " for s in SUBCOMMANDS.get(command, []) if s.startswith(text)]
    return []


def setup_readline(history_path: Path | None = None) -> None:
    """Enable history persistence and Tab completion for slash commands."""
    if readline is None:
        return
    try:
        readline.set_completer_delims(" \t\n")
        matches: list[str] = []

        def completer(text: str, state: int) -> str | None:
            nonlocal matches
            if state == 0:
                matches = complete_line(readline.get_line_buffer(), text)
            return matches[state] if state < len(matches) else None

        readline.set_completer(completer)
        readline.parse_and_bind("tab: complete")
        if history_path:
            history_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                readline.read_history_file(str(history_path))
            except (FileNotFoundError, OSError):
                pass
            readline.set_history_length(1000)
    except Exception:  # pragma: no cover - never let UI niceties break the TUI
        return


def save_history(history_path: Path | None) -> None:
    if readline is None or history_path is None:
        return
    try:
        readline.write_history_file(str(history_path))
    except Exception:  # pragma: no cover
        pass


def read_multiline(prompt: str, input_fn=None, continuation: str = "… ") -> str:
    """Read one logical input; a trailing backslash continues on the next line."""
    input_fn = input_fn or input  # resolved at call time so it can be patched
    lines: list[str] = []
    text = input_fn(prompt)
    while text.rstrip().endswith("\\"):
        lines.append(text.rstrip()[:-1].rstrip())
        text = input_fn(paint(continuation, "gray") if continuation else "")
    lines.append(text)
    return "\n".join(lines).strip()


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 characters per token); always labelled approximate."""
    return max(1, round(len(text) / 4)) if text else 0


def reply_footer(provider: str, model: str, seconds: float, reply_text: str,
                 enabled: bool | None = None) -> str:
    """Footer under a reply: model, duration and an approximate token count."""
    tokens = estimate_tokens(reply_text)
    return paint(f"  {provider}/{model} · {seconds:.1f}s · ~{tokens} tokens", "gray", enabled=enabled)


def conversation_to_markdown(title: str, messages: list[dict]) -> str:
    """Render a conversation as a Markdown transcript."""
    out = [f"# {title}", ""]
    for message in messages:
        role = str(message.get("role", "")).lower()
        if role not in {"user", "assistant"}:
            continue
        who = "You" if role == "user" else "GENESIS"
        out += [f"## {who}", "", str(message.get("content", "")).strip(), ""]
    return "\n".join(out).rstrip() + "\n"


def safe_filename(title: str, default: str = "conversation") -> str:
    slug = re.sub(r"[^\w.-]+", "-", title).strip("-._")[:60]
    return slug or default


SPARK = "▁▂▃▄▅▆▇█"


def sparkline(values: list[float], lo: float = 0.0, hi: float = 1.0) -> str:
    """Tiny trend chart for values in [lo, hi]."""
    if not values:
        return ""
    span = (hi - lo) or 1.0
    return "".join(SPARK[min(len(SPARK) - 1, max(0, int((v - lo) / span * (len(SPARK) - 1) + 0.5)))] for v in values)


def render_run(run: dict, enabled: bool | None = None) -> str:
    """Per-task results of one evaluation run."""
    lines = [info(f"Run {paint(run['id'], 'bold', enabled=enabled)} · {run['suite']} · {run['label']} · "
                  f"{run['provider']}/{run['model']}", enabled)]
    for r in run.get("results", []):
        mark = ok("", enabled) if r["passed"] else (error("", enabled) if not r.get("error") else warn("", enabled))
        lines.append(f"  {mark}{r['task_id']}")
    lines.append(f"  Score {run['score'] * 100:.0f}%  ({run['passed']}/{run['total']} tasks passed, "
                 f"{run['errors']} error(s), {run['duration']:.0f}s)")
    return "\n".join(lines)


def render_comparison(comp: dict, enabled: bool | None = None) -> str:
    """Baseline vs candidate summary with an honest caveat."""
    style = {"improved": "bright_green", "slightly improved": "bright_green", "regressed": "bright_red",
             "mixed": "bright_yellow"}.get(comp["verdict"], "gray")
    delta = comp["delta"] * 100
    lines = [
        info(f"Baseline {comp['base_score'] * 100:.0f}%  →  candidate {comp['candidate_score'] * 100:.0f}%  "
             f"({delta:+.0f} pts)  verdict: {paint(comp['verdict'].upper(), 'bold', style, enabled=enabled)}", enabled),
    ]
    if comp["improved"]:
        lines.append(f"  {ok('', enabled)}now pass: {', '.join(comp['improved'])}")
    if comp["regressed"]:
        lines.append(f"  {error('', enabled)}now fail: {', '.join(comp['regressed'])}")
    lines.append(paint(f"  {comp['caveat']}", "dim", enabled=enabled))
    return "\n".join(lines)


def clear_screen(stream: TextIO | None = None) -> None:
    stream = stream or sys.stdout
    if getattr(stream, "isatty", lambda: False)():
        stream.write("\033[2J\033[H")
        stream.flush()
