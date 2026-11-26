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
from genesis_core.multi_agent import MultiAgentEngine
from genesis_core.memory import MemoryError, MemoryStore
from genesis_core.conversation_memory import ConversationMemoryEngine, ConversationMemoryError
from genesis_core.knowledge import KnowledgeError, KnowledgeStore
from genesis_core.research import ResearchEngine, ResearchError
from genesis_core.skills import SkillError, SkillStore
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
    multi_agent = MultiAgentEngine(store)
    mission_engine = MissionEngine(store, missions, agent, multi_agent=multi_agent)
    memories = MemoryStore(store)
    conversation_memory = ConversationMemoryEngine(store, memories)
    knowledge = KnowledgeStore(store)
    research = ResearchEngine(store, knowledge)
    skills = SkillStore(store.database_path, {item['name'] for item in tool_registry.list()})
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
                "  /memory list [type]  List active memories\n"
                "  /memory search <text> Search active memories\n"
                "  /memory add <type> <text> Save an explicit memory\n"
                "  /memory mission <id> Capture a completed mission as an episode\n"
                "  /memory extract [session-id] Propose conversation memories\n"
                "  /memory candidates [session-id] List pending proposals\n"
                "  /memory candidate <id> accept|reject Review a proposal\n"
                "  /memory off|delete <id> Deactivate or delete a memory\n"
                "  /knowledge add <path> Import UTF-8 text or selectable-text PDF\n"
                "  /knowledge search <query> Search indexed documents\n"
                "  /knowledge list|delete <id> Manage indexed documents\n"
                "  /research search <query> Search web or local knowledge\n"
                "  /research sources [pending|approved|rejected] List saved sources\n"
                "  /research review <id> approve|reject Review a source\n"
                "  /missions          List missions\n"
                "  /mission new <title>  Create a mission\n"
                "  /mission status <id> <status>  Update mission status\n"
                "  /mission plan <id>  Generate a task plan\n"
                "  /mission run <id>   Execute the next task\n"
                "  /mission tasks <id> Show mission tasks\n"
                "  /mission replan <id> [reason] Propose a revised plan after a blocker\n"
                "  /mission history <id> Show saved plan revisions\n"
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
        elif command == "/memory":
            try:
                if args and args[0] == "add" and len(args) >= 3:
                    item = memories.add(args[1], " ".join(args[2:]), source_type="user")
                    print(f"Saved {item['memory_type']} memory: {item['id']}")
                elif args and args[0] == "extract":
                    target = args[1] if len(args) > 1 else current
                    items = conversation_memory.extract(target)
                    print(f"Created {len(items)} pending memory proposal(s). Review with /memory candidates.")
                    for item in items:
                        print(f"  {item['id']} [{item['memory_type']}] {item['content']}")
                elif args and args[0] == "candidates":
                    target = args[1] if len(args) > 1 else None
                    for item in conversation_memory.list_candidates(session_id=target):
                        print(f"{item['id']} [{item['memory_type']}] {item['content']}\n  Evidence: {item['evidence']}")
                elif len(args) == 3 and args[0] == "candidate":
                    item = conversation_memory.decide(args[1], args[2])
                    print(f"Candidate {item['id']}: {item['status']}" +
                          (f" → memory {item['memory_id']}" if item.get("memory_id") else ""))
                elif len(args) == 2 and args[0] == "mission":
                    item = memories.capture_completed_mission(missions, args[1])
                    print(f"Captured completed mission as episodic memory: {item['id']}")
                elif args and args[0] == "list":
                    items = memories.list(memory_type=args[1] if len(args) > 1 else None)
                    for item in items:
                        print(f"{item['id']} [{item['memory_type']}] ({item['confidence']:.2f}) {item['content']}")
                elif args and args[0] == "search" and len(args) >= 2:
                    for item in memories.search(" ".join(args[1:])):
                        print(f"{item['id']} [{item['memory_type']}] {item['content']}")
                elif len(args) == 2 and args[0] == "off":
                    memories.set_status(args[1], "inactive")
                    print(f"Memory {args[1]} deactivated.")
                elif len(args) == 2 and args[0] == "delete":
                    memories.delete(args[1])
                    print(f"Memory {args[1]} deleted.")
                else:
                    print("Usage: /memory list [type] | search <text> | add <episodic|semantic|procedural> <text> | mission <id> | extract [session-id] | candidates [session-id] | candidate <id> accept|reject | off|delete <id>")
            except (MemoryError, ConversationMemoryError, KeyError, ModelError) as exc:
                print(f"Memory error: {exc}")
        elif command == "/skills":
            try:
                status = args[1] if len(args) > 1 else None
                for item in skills.list(status):
                    print(f"[{item['status']}] {item['id']} v{item['version']} — {item['name']}: {item['description']}")
                if not skills.list(status):
                    print("No skills found.")
            except SkillError as exc:
                print(f"Skills error: {exc}")
        elif command == "/skill":
            try:
                if args and args[0] == "create":
                    raw_value = raw[len("/skill create"):].strip()
                    parts_value = [part.strip() for part in raw_value.split("|", 2)]
                    if len(parts_value) != 3:
                        raise SkillError("Usage: /skill create <name> | <description> | <instructions>")
                    item = skills.create(parts_value[0], parts_value[1], parts_value[2],
                                         checklist=["Review instructions for accuracy and safety"])
                    print(f"Draft skill created: {item['id']} — {item['name']}. Submit it for review.")
                elif len(args) == 2 and args[0] == "submit":
                    item = skills.submit(args[1])
                    print(f"Skill {item['id']} is pending review.")
                elif len(args) == 3 and args[0] == "review":
                    item = skills.review(args[1], args[2])
                    print(f"Skill {item['id']} is now {item['status']}.")
                elif len(args) == 2 and args[0] == "disable":
                    item = skills.disable(args[1])
                    print(f"Skill {item['id']} disabled.")
                elif len(args) == 2 and args[0] == "versions":
                    for version in skills.versions(args[1]):
                        print(f"v{version['version']} · {version['created_at']} — {version['manifest']['name']}")
                else:
                    print("Usage: /skill create <name> | <description> | <instructions> | submit <id> | review <id> approve|reject | disable <id> | versions <id>")
            except (SkillError, KeyError) as exc:
                print(f"Skill error: {exc}")
        elif command == "/research":
            try:
                if len(args) >= 2 and args[0] == "search":
                    result = research.search(" ".join(args[1:]))
                    print(f"Research {result['id']} · {result['mode']} · {result['source_count']} source(s)")
                    print(result["notice"])
                    for source in result["sources"]:
                        print(f"  [{source['review_status']}] {source['title']}")
                        print(f"    {source['url']}")
                        if source["snippet"]:
                            print(f"    {source['snippet'][:260]}")
                elif args and args[0] == "sources":
                    status = args[1] if len(args) > 1 else None
                    for source in research.list_sources(review_status=status):
                        print(f"[{source['review_status']}] {source['id']} — {source['title']}")
                        print(f"  {source['url']}")
                elif len(args) == 3 and args[0] == "review":
                    decision = {"approve": "approved", "reject": "rejected"}.get(args[2])
                    if not decision:
                        raise ResearchError("Use approve or reject.")
                    source = research.review_source(args[1], decision)
                    print(f"Source {source['id']} is now {source['review_status']}.")
                else:
                    print("Usage: /research search <query> | sources [pending|approved|rejected] | review <id> approve|reject")
            except (ResearchError, KeyError) as exc:
                print(f"Research error: {exc}")
        elif command == "/knowledge":
            try:
                if len(args) >= 2 and args[0] == "add":
                    item = knowledge.ingest_file(" ".join(args[1:]))
                    status = "already indexed" if item["duplicate"] else "indexed"
                    print(f"Document {status}: {item['id']} — {item['chunk_count']} chunk(s)")
                elif len(args) >= 2 and args[0] == "search":
                    results = knowledge.search(" ".join(args[1:]))
                    if not results:
                        print("No matching knowledge found.")
                    for item in results:
                        citation = item["citation"]
                        print(f"[{citation['title']} · chunk {citation['chunk']}] {item['excerpt']}")
                        print(f"  Source: {citation['source']}")
                elif len(args) == 1 and args[0] == "list":
                    for item in knowledge.list_documents():
                        print(f"{item['id']} — {item['title']} ({item['chunk_count']} chunks)")
                elif len(args) == 2 and args[0] == "delete":
                    knowledge.delete_document(args[1])
                    print(f"Knowledge document {args[1]} removed.")
                else:
                    print("Usage: /knowledge add <path> | search <query> | list | delete <id>")
            except (KnowledgeError, KeyError, OSError) as exc:
                print(f"Knowledge error: {exc}")
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
                elif len(args) >= 2 and args[0] == "replan":
                    result = mission_engine.replan(args[1], " ".join(args[2:]))
                    print(f"Revised plan proposed. Preserved {result['preserved_completed']} completed task(s).")
                    for task in result["tasks"]:
                        print(f"  {task['position']}. [{task['status']}] {task['title']}")
                elif len(args) == 2 and args[0] == "history":
                    for revision in mission_engine.plan_history(args[1]):
                        print(f"Plan v{revision['version']} · {revision['created_at']} · {revision['reason']}")
                        print(json.dumps(revision["plan"].get("metadata", {}), ensure_ascii=False))
                elif len(args) == 2 and args[0] == "tasks":
                    for task in missions.list_tasks(args[1]):
                        print(f"  {task['position']}. [{task['status']}] {task['title']}")
                        if task["result"]:
                            print(f"     {task['result'][:240]}")
                else:
                    print("Usage: /mission new <title> | plan|run|tasks|history <id> | replan <id> [reason] | status <id> <status>")
            except (MissionError, MissionEngineError, KeyError, ModelError) as exc:
                print(f"Mission error: {exc}")
        else:
            print(f"Unknown command: {command}. Type /help.")

    return 0


if __name__ == "__main__":
    raise SystemExit(run_tui())
