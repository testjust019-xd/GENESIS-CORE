"""Interactive terminal workspace for GENESIS CORE."""

from __future__ import annotations

import json
import os
import shlex
import time
from pathlib import Path
from genesis_core.agent import AgentRuntime, ModelError
from genesis_core import model_hub
from genesis_core.adapters import ModelConfig, create_chat_adapter
from genesis_core.config import read_settings, set_model, write_settings
from genesis_core.hardware import inspect_hardware
from genesis_core.native_runtime import NativeRuntime, NativeRuntimeError, INSTALL_HELP, find_engine
from genesis_core.models import discover_runtimes
from genesis_core.missions import MissionError, MissionStore
from genesis_core.mission_engine import MissionEngine, MissionEngineError
from genesis_core.multi_agent import MultiAgentEngine
from genesis_core.memory import MemoryError, MemoryStore
from genesis_core.conversation_memory import ConversationMemoryEngine, ConversationMemoryError
from genesis_core.knowledge import KnowledgeError, KnowledgeStore
from genesis_core.research import ResearchEngine, ResearchError
from genesis_core.research_intelligence import ResearchIntelligence, ResearchIntelligenceError
from genesis_core.learning import LearningEngine, LearningError
from genesis_core.skills import SkillError, SkillStore
from genesis_core import __version__, ui
from genesis_core.state import StateStore
from genesis_core.tools import ApprovalStore, PermissionManager, ToolExecutor, build_core_registry


def _model_label() -> str:
    """Selected primary model (env overrides settings), or 'auto-detect'."""
    saved = read_settings().get("model") or {}
    provider = os.environ.get("GENESIS_MODEL_PROVIDER") or saved.get("provider")
    name = os.environ.get("GENESIS_MODEL") or saved.get("name")
    native = read_settings().get("native") or {}
    if not (provider or name) and native.get("file"):
        return f"native/{native['file']}"
    return "/".join(filter(None, [provider, name])) or "auto-detect"


def _installed_native() -> list[Path]:
    return model_hub.installed_models()


def _saved_native() -> Path | None:
    name = (read_settings().get("native") or {}).get("file")
    path = model_hub.models_dir() / name if name else None
    return path if path and path.is_file() else None


def _activate_native(agent, native: NativeRuntime, path: Path) -> str:
    """Start the managed engine for ``path`` and point the agent at it."""
    url = native.start(path)
    agent.adapter = create_chat_adapter(ModelConfig("llama_cpp", url, path.name))
    return f"native/{path.name}"


def _remember_native(path: Path) -> None:
    settings = read_settings()
    settings.pop("model", None)  # native choice replaces any explicit runtime choice
    settings["native"] = {"file": path.name}
    write_settings(settings)


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
    research_intelligence = ResearchIntelligence(store)
    learning = LearningEngine(store)
    skills = SkillStore(store.database_path, {item['name'] for item in tool_registry.list()})
    current = None
    sessions = store.list_sessions(limit=1)
    if sessions:
        current = sessions[0]["id"]
    else:
        current = store.create_session()["id"]

    history_path = genesis_home / "tui_history"
    ui.setup_readline(history_path)
    model_label = _model_label()
    native = NativeRuntime()
    print()
    print(ui.welcome_panel(
        __version__,
        (store.get_session(current) or {}).get("title", "New conversation"),
        model_label,
        str(genesis_home / "workspace"),
    ))
    print()

    while True:
        session = store.get_session(current) if current else None
        label = session["title"] if session else "No session"
        try:
            pending = len(approvals.list())
            if pending:
                print(ui.status_line(model_label, len(tool_registry.list()), pending))
            raw = ui.read_multiline(ui.prompt_string(label))
        except EOFError:
            print("\n" + ui.info("Leaving GENESIS TUI."))
            ui.save_history(history_path)
            return 0
        except KeyboardInterrupt:
            print("\n" + ui.paint("Press Ctrl+D or type /quit to exit.", "dim"))
            continue
        if not raw:
            continue
        if not raw.startswith("/"):
            if not current:
                current = store.create_session()["id"]
            if agent.adapter is None and not read_settings().get("model") and _saved_native():
                try:
                    with ui.Spinner("Starting your local model"):
                        model_label = _activate_native(agent, native, _saved_native())
                    print(ui.ok(f"Running {model_label} (managed by GENESIS)."))
                except NativeRuntimeError as exc:
                    print(ui.error(str(exc)))
            print()
            stream = ui.MarkdownStream()
            spinner = ui.Spinner("Thinking")
            started = time.monotonic()
            first_token = True

            def reply_header() -> None:
                print(ui.mini_face("happy") + " " + ui.paint("genesis", "bold", "bright_cyan"))

            def on_token(chunk: str) -> None:
                nonlocal first_token
                if first_token:
                    spinner.stop()
                    reply_header()
                    first_token = False
                stream.feed(chunk)

            def on_activity(event: dict) -> None:
                spinner.stop()
                stream.finish()
                if event.get("type") == "tool_start":
                    print(ui.format_tool_start(event))
                else:
                    line = ui.format_activity(event)
                    if line:
                        print(line)
                spinner.start()

            def on_approval(request: dict) -> bool:
                spinner.stop()
                stream.finish()
                return ui.ask_approval(request)

            try:
                with spinner:
                    reply = agent.chat(
                        current, raw, on_token=on_token,
                        on_activity=on_activity, on_approval=on_approval,
                    )
                spinner.stop()
                stream.finish()
                if first_token and reply.assistant_message["content"]:
                    # Adapter produced no streamed tokens: render the final message.
                    reply_header()
                    stream.feed(reply.assistant_message["content"] + "\n")
                    stream.finish()
                print(ui.reply_footer(reply.provider, reply.model, time.monotonic() - started,
                                      reply.assistant_message["content"]))
                print()
            except KeyboardInterrupt:
                spinner.stop()
                stream.finish()
                print("\n" + ui.mini_face("alert") + " " + ui.warn("Reply cancelled."))
                print()
            except ModelError as exc:
                spinner.stop()
                print(ui.mini_face("error") + " " + ui.error(f"Model unavailable: {exc}"))
                print(ui.paint("  No model yet? Run /model install to download one directly, or start Ollama / LM Studio.", "dim"))
                print()
            continue

        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            print(f"Invalid command: {exc}")
            continue
        command, args = parts[0].lower(), parts[1:]

        if command in {"/quit", "/exit"}:
            print(ui.info("Leaving GENESIS TUI."))
            ui.save_history(history_path)
            return 0
        if command == "/help":
            print(ui.render_help(" ".join(args)))
        elif command == "/clear":
            ui.clear_screen()
        elif command == "/export":
            messages = store.list_messages(current) if current else []
            if not messages:
                print(ui.warn("Nothing to export yet."))
            else:
                title = (store.get_session(current) or {}).get("title", "conversation")
                target = Path(args[0]).expanduser() if args else (
                    genesis_home / "exports" / f"{ui.safe_filename(title)}.md")
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(ui.conversation_to_markdown(title, messages), encoding="utf-8")
                    print(ui.ok(f"Conversation exported to {target}"))
                except OSError as exc:
                    print(ui.error(f"Export failed: {exc}"))
        elif command == "/model" and args and args[0] == "install":
            try:
                hw = inspect_hardware()
                suggested = model_hub.recommend(hw.get("memory_total_bytes"))
                if len(args) >= 2:
                    chosen = model_hub.resolve_spec(" ".join(args[1:]))
                else:
                    print(ui.info("Models you can download (GGUF, run by GENESIS itself):"))
                    for number, item in enumerate(model_hub.CATALOG, 1):
                        star = ui.paint("  ★ recommended for this device", "bright_green") if item.key == suggested.key else ""
                        print(f"  {ui.paint(str(number), 'bright_yellow')}  {item.title:<24} {item.size_gb:>4.1f} GB  {ui.paint(item.note, 'dim')}{star}")
                    print(ui.paint("  Custom: /model install hf:owner/repo/file.gguf", "dim"))
                    choice = input(ui.paint("  Number to install (Enter = recommended, q = cancel) › ", "bright_yellow")).strip().lower()
                    if choice in {"q", "n", "no"}:
                        print(ui.paint("  Cancelled.", "dim"))
                        continue
                    chosen = model_hub.resolve_spec(choice) if choice else suggested
                print(ui.info(f"Downloading {chosen.title} from Hugging Face…"))
                started = time.monotonic()

                def show(done: int, total: int) -> None:
                    print("\r" + ui.paint("  " + model_hub.progress_bar(done, total, started), "bright_cyan") + "\033[K", end="", flush=True)

                path = model_hub.download(chosen, progress=show)
                print()
                print(ui.ok(f"Installed {path.name} ({model_hub.format_size(path.stat().st_size)})."))
                if find_engine():
                    with ui.Spinner("Starting your local model"):
                        model_label = _activate_native(agent, native, path)
                    _remember_native(path)
                    print(ui.ok(f"Ready: {model_label}. You can chat now."))
                else:
                    _remember_native(path)
                    print(ui.warn("Model downloaded, but the llama.cpp engine is missing."))
                    print(ui.paint(INSTALL_HELP, "dim"))
                    print(ui.paint("  Then run /model use to start it.", "dim"))
            except (model_hub.HubError, NativeRuntimeError) as exc:
                print()
                print(ui.error(str(exc)))
            except (EOFError, KeyboardInterrupt):
                print("\n" + ui.paint("  Cancelled. Re-run the command to resume a partial download.", "dim"))
        elif command == "/model" and args and args[0] == "use":
            files = _installed_native()
            try:
                if len(args) >= 2 and args[1].isdigit() and 1 <= int(args[1]) <= len(files):
                    path = files[int(args[1]) - 1]
                elif len(args) >= 2:
                    path = next((f for f in files if f.name == args[1] or f.stem == args[1]), None)
                    if path is None:
                        raise ValueError(f"No installed model named {args[1]}. See /model.")
                elif files:
                    path = _saved_native() or files[0]
                else:
                    raise ValueError("No downloaded model yet. Run /model install.")
                with ui.Spinner("Starting your local model"):
                    model_label = _activate_native(agent, native, path)
                _remember_native(path)
                print(ui.ok(f"Running {model_label} (managed by GENESIS)."))
            except (ValueError, NativeRuntimeError) as exc:
                print(ui.error(str(exc)))
        elif command == "/model":
            runtimes = discover_runtimes()
            choices = [(r.provider, m) for r in runtimes if r.available for m in r.models]
            if not args:
                print(ui.info(f"Primary model: {ui.paint(_model_label(), 'bold')}"))
                if os.environ.get("GENESIS_MODEL") or os.environ.get("GENESIS_MODEL_PROVIDER"):
                    print(ui.paint("  (set by GENESIS_MODEL* environment variables, which override saved settings)", "dim"))
                if not choices:
                    print(ui.paint("  No local model found. Start Ollama, LM Studio or llama.cpp.", "dim"))
                for number, (provider, name) in enumerate(choices, 1):
                    print(f"  {ui.paint(str(number).rjust(2), 'bright_yellow')}  {provider}/{name}")
                if choices:
                    print(ui.paint("  Switch with /model <number> or /model <provider> <name>", "dim"))
                files = _installed_native()
                if files:
                    print(ui.paint("  Downloaded (run by GENESIS):", "bold"))
                    for number, f in enumerate(files, 1):
                        print(f"  {ui.paint(str(number).rjust(2), 'bright_yellow')}  {f.name}  {ui.paint(model_hub.format_size(f.stat().st_size), 'dim')}")
                    print(ui.paint("  Start one with /model use <number>", "dim"))
                else:
                    print(ui.paint("  No model installed? /model install downloads one directly.", "dim"))
            else:
                try:
                    if len(args) == 1 and args[0].isdigit() and 1 <= int(args[0]) <= len(choices):
                        provider, name = choices[int(args[0]) - 1]
                    elif len(args) >= 2:
                        provider, name = args[0], " ".join(args[1:])
                    else:
                        raise ValueError("Use /model <number> from the list, or /model <provider> <name>.")
                    set_model(provider, name)
                    agent.adapter = None  # rebuilt from settings on the next message
                    model_label = _model_label()
                    print(ui.ok(f"Primary model set to {provider}/{name}."))
                    if os.environ.get("GENESIS_MODEL") or os.environ.get("GENESIS_MODEL_PROVIDER"):
                        print(ui.warn("GENESIS_MODEL* environment variables still override this choice."))
                except ValueError as exc:
                    print(ui.error(str(exc)))
        elif command == "/new":
            item = store.create_session(" ".join(args) or "New conversation")
            current = item["id"]
            print(ui.ok(f"Created conversation {current}."))
        elif command == "/sessions":
            items = store.list_sessions()
            if not items:
                print("No conversations yet.")
            for item in items:
                marker = ui.paint("▶", "bright_cyan") if item["id"] == current else " "
                print(f"{marker} {ui.paint(item['id'], 'gray')}  {item['title']}")
        elif command == "/open":
            if not args:
                print("Usage: /open <session-id>")
            elif store.get_session(args[0]):
                current = args[0]
                print(ui.ok(f"Opened conversation {current}."))
            else:
                print("Conversation not found.")
        elif command == "/history":
            for message in store.list_messages(current):
                print(f"{message['role'].upper()}: {message['content']}")
        elif command == "/models":
            for runtime in discover_runtimes():
                status = ui.paint("● ONLINE", "bright_green") if runtime.available else ui.paint("○ OFFLINE", "gray")
                print(f"{ui.paint(runtime.provider, 'bold')}: {status} — {runtime.detail}")
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
                elif len(args) >= 2 and args[0] == "report":
                    report = research_intelligence.generate(args[1], " ".join(args[2:]))
                    print(f"\n{report['title']} · {report['provider']}/{report['model']}")
                    print(report["summary"])
                    for claim in report["claims"]:
                        print(f"  [{claim['classification']}] {claim['text']}")
                        for source_id in claim["source_ids"]:
                            print(f"    Source ID: {source_id}")
                    if report["disagreements"]:
                        print("Disagreements:")
                        for item in report["disagreements"]:
                            print(f"  - {item}")
                    if report["open_questions"]:
                        print("Open questions:")
                        for item in report["open_questions"]:
                            print(f"  - {item}")
                    print(report["notice"])
                elif args and args[0] == "reports":
                    for item in research_intelligence.list(args[1] if len(args) > 1 else None):
                        print(f"{item['id']} · run {item['run_id']} · {item['title']}")
                elif len(args) == 3 and args[0] == "review":
                    decision = {"approve": "approved", "reject": "rejected"}.get(args[2])
                    if not decision:
                        raise ResearchError("Use approve or reject.")
                    source = research.review_source(args[1], decision)
                    print(f"Source {source['id']} is now {source['review_status']}.")
                else:
                    print("Usage: /research search <query> | sources [pending|approved|rejected] | review <id> approve|reject | report <run-id> [focus] | reports [run-id]")
            except (ResearchError, ResearchIntelligenceError, KeyError, ModelError) as exc:
                print(f"Research error: {exc}")
        elif command == "/learn":
            try:
                if len(args) >= 2 and args[0] == "create":
                    course = learning.create_course(" ".join(args[1:]))
                    print(f"Learning course {course['id']}: {course['title']}")
                    print(f"Goal: {course['goal']}")
                    for lesson in course["lessons"]:
                        print(f"  {lesson['position']}. {lesson['id']} — {lesson['title']}")
                        print(f"     {lesson['prompt']}")
                elif len(args) == 1 and args[0] == "list":
                    for course in learning.list_courses():
                        print(f"{course['id']} · {course['title']} · {course['completed_lessons']} lessons completed · {course['xp']} XP")
                elif len(args) == 2 and args[0] == "show":
                    course = learning.get_course(args[1])
                    print(f"{course['title']} · {course['progress_percent']}% · {course['xp']} XP")
                    for lesson in course["lessons"]:
                        state = "completed" if lesson["completed"] else "open"
                        print(f"  {lesson['position']}. [{state}] {lesson['id']} — {lesson['title']} (best {lesson['best_score']}%)")
                        print(f"     {lesson['prompt']}")
                        if lesson["hints"]:
                            print("     Hints: " + " | ".join(lesson["hints"]))
                elif len(args) >= 3 and args[0] == "answer":
                    result = learning.submit_answer(args[1], " ".join(args[2:]))
                    print(f"Score: {result['score']}% · best: {result['best_score']}% · +{result['xp_awarded']} XP")
                    if result["matched_concepts"]:
                        print("Matched: " + ", ".join(result["matched_concepts"]))
                    if result["missing_concepts"]:
                        print("Still to cover: " + ", ".join(result["missing_concepts"]))
                    print(result["evaluation_note"])
                elif len(args) == 2 and args[0] == "attempts":
                    for attempt in learning.attempts(args[1]):
                        print(f"{attempt['created_at']} · {attempt['score']}% · +{attempt['xp_awarded']} XP")
                else:
                    print("Usage: /learn create <goal> | list | show <course-id> | answer <lesson-id> <text> | attempts <lesson-id>")
            except (LearningError, KeyError, ModelError) as exc:
                print(f"Learning error: {exc}")
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
            print(ui.error(f"Unknown command: {command}. Type /help."))

    return 0


if __name__ == "__main__":
    raise SystemExit(run_tui())
