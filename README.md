# GENESIS CORE

**An open-source, local-first evolution and agent framework for language models.**

GENESIS CORE is its own agent environment. Local runtimes such as Ollama, llama.cpp and LM Studio are interchangeable inference backends; they do not provide GENESIS's interface or orchestration.

> GENESIS does not magically increase a model's parameter count or native abilities. It improves what the model can accomplish through verified knowledge, external tools, structured workflows and (optionally) actual training.

## Project status

**Early foundation / v0.1.0-dev.** The repository includes two first-party interfaces (**GENESIS TUI** and **GENESIS Studio**), a shared SQLite conversation store, local runtime discovery, initial chat adapters for Ollama and OpenAI-compatible local servers, and a first agent loop. The agent can now send conversation context to a selected local model and persist its reply. A persistent mission queue is also available in the TUI and Studio. Multi-step planning, tool execution, long-term memory, research, and training remain future milestones. Automated tests and CI have been added, and the initial test run passed.

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

**Current limitation:** the first agent loop supports direct chat only. It does not yet plan multi-step missions, call tools, browse the web, or perform background learning. If no local model is reachable, GENESIS reports a provider error rather than simulating an answer. On first TUI launch, an optional setup wizard detects available runtimes, recommends small Ollama models based on RAM, and downloads a model only after explicit confirmation. Run genesis recommend to preview suggestions or genesis setup to configure one later.

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
| Agent Runtime | Context-aware direct chat loop; planner and tools pending | Initial |
| First-Run Setup | Hardware-aware model recommendations and opt-in Ollama download | Initial |
| Mission Control | Persistent goals, priorities and status transitions | Initial |
| Memory | Episodic and semantic knowledge | Planned |
| Research Engine | Search, source capture and verification | Planned |
| Tool System | Permissioned tools and extensions | Initial foundation |
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
