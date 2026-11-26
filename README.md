# GENESIS CORE

**An open-source, local-first evolution and agent framework for language models.**

GENESIS CORE is its own agent environment. Local runtimes such as Ollama, llama.cpp and LM Studio are interchangeable inference backends; they do not provide GENESIS's interface or orchestration.

> GENESIS does not magically increase a model's parameter count or native abilities. It improves what the model can accomplish through verified knowledge, external tools, structured workflows and (optionally) actual training.

## Project status

**Early foundation / v0.1.0-dev.** The repository includes two first-party interfaces (**GENESIS TUI** and **GENESIS Studio**), a shared SQLite conversation store, local runtime discovery, initial chat adapters for Ollama and OpenAI-compatible local servers, and a bounded planner/executor/observer agent loop. The agent can request registered tools through a structured chat protocol, execute read-only workspace tools, inspect results, and persist its final reply. Elevated actions remain approval-gated. A persistent mission engine can now generate up to eight ordered tasks, store task results, execute one step at a time, and resume from persisted progress. A separate observer evaluates each task result; invalid or unavailable observer decisions leave the task blocked rather than silently marking it complete. Mission planning and step execution are available through the TUI and Studio API. The initial Memory Engine stores explicit episodic, semantic and procedural records with provenance and confidence, retrieves relevant active records into agent context, and supports listing, searching, deactivation and deletion from TUI and Studio. Completed missions can now be explicitly captured as episodic memories using their persisted task results and observer summaries; capture is idempotent and refuses incomplete missions. Conversation extraction now proposes up to six candidates from user-authored messages only; every candidate requires an exact source quote and explicit user acceptance before it enters long-term memory. Pending proposals can be reviewed or rejected from TUI and Studio. The Knowledge Engine imports UTF-8 TXT, Markdown and reStructuredText files, chunks and indexes them in SQLite FTS5 with a LIKE fallback, deduplicates identical content, and retrieves source-linked excerpts into agent context. Automated tests and CI have been added, and the initial test run passed.

## Principles

- **One GENESIS product:** TUI and Studio are clients of the same engine and persistent state.
- **Local-first:** local models and local data are the default.
- **Model-agnostic:** Ollama, llama.cpp, LM Studio, Hugging Face and remote APIs are backend options.
- **Resource-aware:** inspect hardware and adapt workloads to available resources.
- **Evidence-based evolution:** evaluate skills and model versions instead of treating XP as proof of intelligence.
- **Permissioned autonomy:** tools run with explicit capabilities, isolation and approval boundaries.
- **Extensible:** optional providers, tools and specialist models.

## Requirements

- Linux first (Ubuntu/Debian are the initial targets)
- Python 3.11+
- A local model runtime is required for actual AI replies; the first TUI launch offers a hardware-aware model setup if none is configured

## Install from source

```bash
git clone https://github.com/testjust019-xd/GENESIS-CORE.git
cd GENESIS-CORE
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[web,dev]"
```

For optional selectable-text PDF ingestion, install the document extra with `pip install -e ".[documents]"`.

## Launch GENESIS

```bash
genesis init
genesis tui
```

In another terminal, launch the graphical workspace:

```bash
genesis studio
```

Then open `http://127.0.0.1:8765`. Both interfaces read and write the same local conversation database at `~/.genesis/data/genesis.db` (or under `$GENESIS_HOME`).

Other commands:

```bash
genesis doctor
genesis recommend
genesis setup
genesis models
genesis model show
genesis model set ollama llama3.2
genesis --help
```

The Studio server binds to `127.0.0.1` by default. Runtime discovery checks the default local endpoints for Ollama, llama.cpp and LM Studio. URLs can be overridden with `GENESIS_OLLAMA_URL`, `GENESIS_LLAMA_CPP_URL` and `GENESIS_LM_STUDIO_URL`.

**Current limitation:** the initial planner/executor/observer loop is deliberately bounded (four tool steps by default) and uses a JSON action protocol over ordinary chat adapters, not provider-native tool calling. It currently exposes only time and read-only workspace tools. Write, network and system actions are not enabled by default; sensitive actions require an approval workflow. Once an action is approved, repeat the original request to let GENESIS resume it; the approval is bound to the exact tool arguments and consumed once. Mission execution is currently user-triggered and advances one task per call; it does not run in the background or browse the web. Knowledge documents are local and user-selected; retrieved excerpts are treated as untrusted data and must not override system instructions. The initial index is lexical rather than embedding-based, and selectable-text PDF extraction is available through the optional `documents` extra; scanned-PDF OCR and Office extraction are not included yet. Conversation memory extraction is user-triggered and uses only user-authored messages. The model creates pending suggestions with exact quote evidence; users must accept each suggestion before it becomes long-term memory. Assistant messages are not used as evidence, and extraction never saves candidates automatically. If no local model is reachable, GENESIS reports a provider error rather than simulating an answer. On first TUI launch, an optional setup wizard detects available runtimes, recommends small Ollama models based on RAM, and downloads a model only after explicit confirmation. Run genesis recommend to preview suggestions or genesis setup to configure one later.

Mission commands in the TUI: `/mission new <title>`, `/mission plan <id>`, `/mission run <id>`, and `/mission tasks <id>`. Each `/mission run` advances at most one planned task. The observer must explicitly confirm completion; uncertain results remain blocked for review. Studio exposes `POST /api/missions/{id}/plan`, `POST /api/missions/{id}/run`, and `GET /api/missions/{id}/tasks`. Memory is managed with `/memory list`, `/memory search <text>`, `/memory add <type> <text>`, `/memory off <id>`, `/memory delete <id>`, and `/memory mission <id>` to capture a fully completed mission as an episode, `/memory extract [session-id]` to propose conversation memories, `/memory candidates [session-id]` to review pending proposals, and `/memory candidate <id> accept|reject` to decide each proposal. Studio exposes `POST /api/memories/from-mission/{id}` for the same explicit action, alongside the `/api/memories` endpoints. Conversation proposals use `POST /api/sessions/{id}/memory-extract`, `GET /api/memory-candidates`, and `POST /api/memory-candidates/{candidate_id}` to accept or reject each suggestion. Knowledge documents can be imported with `/knowledge add <path>` (UTF-8 `.txt`, `.md`, `.markdown`, `.rst` or selectable-text `.pdf`), searched with `/knowledge search <query>`, listed with `/knowledge list` and removed with `/knowledge delete <id>`. Studio offers a paste-and-index panel and source-linked search results. The API provides `POST /api/knowledge/documents`, `GET /api/knowledge/documents`, `POST /api/knowledge/search` and `DELETE /api/knowledge/documents/{id}`.

## Architecture

See [docs/INTERFACES.md](docs/INTERFACES.md) for the TUI/Studio contract and [docs/MODEL_CORE.md](docs/MODEL_CORE.md) for runtime discovery.

| Component | Responsibility | Status |
|---|---|---|
| Shared state | SQLite sessions and messages | Initial |
| GENESIS TUI | Interactive terminal workspace | Initial |
| GENESIS Studio | Graphical local workspace and API | Initial |
| Hardware Monitor | CPU, RAM, disk and platform detection | Initial |
| Model Discovery | Detect local runtimes and models | Initial |
| Model Adapters | Ollama and OpenAI-compatible local chat adapters | Initial |
| Agent Runtime | Bounded planner / executor / observer loop over chat adapters | Initial |
| First-Run Setup | Hardware-aware model recommendations and opt-in Ollama download | Initial |
| Mission Control | Persistent goals, task plans, step results and resumable execution | Initial |
| Memory Engine | Provenance-aware records, retrieval, verified mission capture and user-reviewed conversation extraction | Initial |
| Knowledge Engine | Local document ingestion, chunking, SQLite full-text search and source-linked agent context | Initial |
| Research Engine | Search, source capture and verification | Planned |
| Tool System | Schema-validated tools, workspace confinement, approval queue and agent integration | Initial foundation |
| Multimodal | Image, audio, video and document pipelines | Planned |
| Skill & Evaluation | Practice, competencies and repeatable benchmarks | Planned |
| Training Lab | Optional LoRA / fine-tuning workflows | Planned |
| Evolution Engine | Version, compare and roll back model improvements | Planned |

## Safety model

Autonomy will be configurable. Network access, shell commands, file writes, package installation, model training and self-modification must use scoped permissions. New or modified tools will be tested in an isolated workspace before activation. GENESIS will never silently grant itself broader permissions.

## Development

See [ROADMAP.md](ROADMAP.md) for milestones. Contributions and issue reports are welcome.

## License

MIT. See [LICENSE](LICENSE).
