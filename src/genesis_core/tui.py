"""Interactive terminal workspace for GENESIS CORE."""

from __future__ import annotations

import shlex
from genesis_core.agent import AgentRuntime, ModelError
from genesis_core.models import discover_runtimes
from genesis_core.state import StateStore


BANNER = r"""
   ____ _____ _   _ _____ ____ ___ ____  
  / ___| ____| \ | | ____/ ___|_ _/ ___| 
 | |  _|  _| |  \| |  _| \___ \| | |     
 | |_| | |___| |\  | |___ ___) | | |___  
  \____|_____|_| \_|_____|____/___\____| 
"""


def run_tui() -> int:
    store = StateStore()
    agent = AgentRuntime(store=store)
    current = None
    sessions = store.list_sessions(limit=1)
    if sessions:
        current = sessions[0]["id"]
    else:
        current = store.create_session()["id"]

    print(BANNER)
    print("GENESIS CORE · TERMINAL WORKSPACE")
    print("Shared local sessions · type /help for commands · /quit to exit")
    print("GENESIS agent runtime enabled · connect a supported model runtime to chat.")
    print()

    while True:
        session = store.get_session(current) if current else None
        label = session["title"] if session else "No session"
        try:
            raw = input(f"\033[96mGENESIS\033[0m [{label[:28]}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nLeaving GENESIS TUI.")
            return 0
        if not raw:
            continue
        if not raw.startswith("/"):
            if not current:
                current = store.create_session()["id"]
            try:
                reply = agent.chat(current, raw)
                print(f"\nGENESIS [{reply.provider}/{reply.model}]")
                print(reply.assistant_message["content"])
                print()
            except ModelError as exc:
                print(f"\nModel unavailable: {exc}")
                print("Start a local model runtime or configure GENESIS_MODEL_PROVIDER / GENESIS_MODEL.\n")
            continue

        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            print(f"Invalid command: {exc}")
            continue
        command, args = parts[0].lower(), parts[1:]

        if command in {"/quit", "/exit"}:
            print("Leaving GENESIS TUI.")
            return 0
        if command == "/help":
            print(
                "\nCommands:\n"
                "  /new [title]       Create a conversation\n"
                "  /sessions          List shared conversations\n"
                "  /open <id>         Switch conversation\n"
                "  /history           Show current conversation\n"
                "  /models            Inspect local model runtimes\n"
                "  /help              Show this help\n"
                "  /quit              Exit\n"
            )
        elif command == "/new":
            item = store.create_session(" ".join(args) or "New conversation")
            current = item["id"]
            print(f"Created conversation {current}.")
        elif command == "/sessions":
            items = store.list_sessions()
            if not items:
                print("No conversations yet.")
            for item in items:
                marker = "*" if item["id"] == current else " "
                print(f"{marker} {item['id']}  {item['title']}")
        elif command == "/open":
            if not args:
                print("Usage: /open <session-id>")
            elif store.get_session(args[0]):
                current = args[0]
                print(f"Opened conversation {current}.")
            else:
                print("Conversation not found.")
        elif command == "/history":
            for message in store.list_messages(current):
                print(f"{message['role'].upper()}: {message['content']}")
        elif command == "/models":
            for runtime in discover_runtimes():
                status = "ONLINE" if runtime.available else "OFFLINE"
                print(f"{runtime.provider}: {status} — {runtime.detail}")
                for model in runtime.models:
                    print(f"  • {model}")
        else:
            print(f"Unknown command: {command}. Type /help.")

    return 0


if __name__ == "__main__":
    raise SystemExit(run_tui())
