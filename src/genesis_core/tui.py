"""Interactive terminal workspace for GENESIS CORE."""

from __future__ import annotations

import json
import os
import shlex
from pathlib import Path
from genesis_core.agent import AgentRuntime, ModelError
from genesis_core.models import discover_runtimes
from genesis_core.missions import MissionError, MissionStore
from genesis_core.mission_engine import MissionEngine, MissionEngineError
from genesis_core.state import StateStore
from genesis_core.tools import ApprovalStore, PermissionManager, ToolExecutor, build_core_registry


BANNER = r"""
   ____ _____ _   _ _____ ____ ___ ____  
  / ___| ____| \ | | ____/ ___|_ _/ ___| 
 | |  _|  _| |  \| |  _| \___ \| | |     
 | |_| | |___| |\  | |___ ___) | | |___  
  \____|_____|_| \_|_____|____/___\____| 
"""


def run_tui() -> int:
    store = StateStore()
    missions = MissionStore(state=store)
    genesis_home = Path(os.environ.get("GENESIS_HOME", Path.home() / ".genesis"))
    approvals = ApprovalStore(store.database_path)
    tool_registry = build_core_registry(genesis_home / "workspace")
    tool_executor = ToolExecutor(tool_registry, PermissionManager(), approvals)
    agent = AgentRuntime(store=store, tool_executor=tool_executor)
    mission_engine = MissionEngine(store, missions, agent)
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
                for event in reply.activity:
                    if event["type"] == "tool":
                        print(f"  [EXECUTOR] {event['tool']} -> {event['status']}")
                    elif event["type"] in {"tool_error", "error", "limit", "loop_guard"}:
                        print(f"  [OBSERVER] {event.get('detail', event['type'])}")
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
                "  /tools             List available agent tools\n"
                "  /approvals         List pending tool approvals\n"
                "  /approval <id> approve|reject  Decide a pending approval\n"
                "  /missions          List missions\n"
                "  /mission new <title>  Create a mission\n"
                "  /mission status <id> <status>  Update mission status\n"
                "  /mission plan <id>  Generate a task plan\n"
                "  /mission run <id>   Execute the next task\n"
                "  /mission tasks <id> Show mission tasks\n"
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
        elif command == "/tool":
            try:
                raw_parts = raw.split(maxsplit=2)
                if len(raw_parts) < 2:
                    print("Usage: /tool <name> [JSON arguments]")
                    continue
                tool_name = raw_parts[1]
                tool_arguments = json.loads(raw_parts[2]) if len(raw_parts) == 3 else {}
                result = tool_executor.execute(tool_name, tool_arguments)
                print(json.dumps({
                    "tool": result.tool, "status": result.status,
                    "output": result.output, "approval_id": result.approval_id,
                    "reason": result.reason,
                }, indent=2, ensure_ascii=False))
            except Exception as exc:
                print(f"Tool error: {exc}")
        elif command == "/tools":
            for tool in tool_registry.list():
                print(f"{tool['name']} [{tool['risk']}] — {tool['description']}")
        elif command == "/approvals":
            pending = approvals.list()
            if not pending:
                print("No pending tool approvals.")
            for request in pending:
                print(f"{request['id']} — {request['tool_name']} — {request['reason']}")
        elif command == "/approval":
            if len(args) != 2 or args[1] not in {"approve", "reject"}:
                print("Usage: /approval <id> approve|reject")
            else:
                try:
                    item = approvals.decide(args[0], approved=args[1] == "approve")
                    print(f"Approval {item['id']}: {item['status']}.")
                except Exception as exc:
                    print(f"Approval error: {exc}")
        elif command == "/missions":
            for mission in missions.list():
                print(
                    f"{mission['id']} [{mission['status']}] "
                    f"P{mission['priority']} — {mission['title']}"
                )
        elif command == "/mission":
            try:
                if len(args) >= 2 and args[0] == "new":
                    mission = missions.create(" ".join(args[1:]))
                    print(f"Mission created: {mission['id']} — {mission['title']}")
                elif len(args) == 3 and args[0] == "status":
                    mission = missions.set_status(args[1], args[2])
                    print(f"Mission {mission['id']} is now {mission['status']}.")
                elif len(args) == 2 and args[0] == "plan":
                    result = mission_engine.plan(args[1])
                    print(f"Plan ready: {len(result['tasks'])} task(s).")
                    for task in result["tasks"]:
                        print(f"  {task['position']}. [{task['status']}] {task['title']}")
                elif len(args) == 2 and args[0] == "run":
                    result = mission_engine.run_next(args[1])
                    if result.get("task"):
                        print(f"Task {result['task']['position']}: {result['task']['status']}")
                        print(result["task"]["result"])
                    else:
                        print(f"Mission status: {result['mission']['status']}")
                elif len(args) == 2 and args[0] == "tasks":
                    for task in missions.list_tasks(args[1]):
                        print(f"  {task['position']}. [{task['status']}] {task['title']}")
                        if task["result"]:
                            print(f"     {task['result'][:240]}")
                else:
                    print("Usage: /mission new <title> | /mission plan|run|tasks <id> | /mission status <id> <status>")
            except (MissionError, MissionEngineError, KeyError, ModelError) as exc:
                print(f"Mission error: {exc}")
        else:
            print(f"Unknown command: {command}. Type /help.")

    return 0


if __name__ == "__main__":
    raise SystemExit(run_tui())
