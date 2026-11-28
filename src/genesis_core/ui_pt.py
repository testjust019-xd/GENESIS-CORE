"""Optional prompt_toolkit front-end: live slash-command menu and a status bar.

``prompt_toolkit`` is an optional dependency (``pip install "genesis-core[pro]"``).
Without it, or when stdin/stdout is not a terminal, GENESIS keeps the plain
readline prompt, so nothing here is required to use the TUI.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable

from genesis_core import ui


def available() -> bool:
    try:
        import prompt_toolkit  # noqa: F401
    except ImportError:
        return False
    return True


def should_use() -> bool:
    """Use the rich prompt only on a real terminal and when not disabled."""
    return (not os.environ.get("GENESIS_NO_PT") and sys.stdin.isatty() and sys.stdout.isatty()
            and available())


def build_session(history_path: Path | None, toolbar: Callable[[], str]):
    """Create the PromptSession (live slash menu, status bar, Alt+Enter newline)."""
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.history import FileHistory, InMemoryHistory
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.styles import Style

    class SlashCompleter(Completer):
        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            word = text.split(" ")[-1]
            for insert, meta in ui.completion_items(text):
                yield Completion(insert, start_position=-len(word), display_meta=meta)

    bindings = KeyBindings()

    @bindings.add("escape", "enter")
    def _newline(event) -> None:  # Alt+Enter inserts a new line
        event.current_buffer.insert_text("\n")

    history = InMemoryHistory()
    if history_path is not None:
        try:
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history = FileHistory(str(history_path))
        except OSError:
            pass
    return PromptSession(
        history=history,
        completer=SlashCompleter(),
        complete_while_typing=True,
        bottom_toolbar=lambda: toolbar(),
        key_bindings=bindings,
        style=Style.from_dict({
            "bottom-toolbar": "noreverse bg:#1e1e2e #9399b2",
            "completion-menu.completion": "bg:#313244 #cdd6f4",
            "completion-menu.completion.current": "bg:#74c7ec #11111b",
            "completion-menu.meta.completion": "bg:#313244 #9399b2",
            "completion-menu.meta.completion.current": "bg:#74c7ec #11111b",
        }),
    )



def make_input(history_path: Path | None, toolbar: Callable[[], str]) -> Callable[[str], str]:
    """Return an ``input()``-compatible function backed by a PromptSession."""
    from prompt_toolkit.formatted_text import ANSI

    session = build_session(history_path, toolbar)

    def read(prompt: str) -> str:
        return session.prompt(ANSI(prompt))

    return read
