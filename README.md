# GENESIS CORE

**An open-source, local-first evolution and agent framework for language models.**

GENESIS CORE gives a locally hosted model a persistent workspace, tools, memory, research workflows, evaluations and a controlled path toward skill development and model training.

> GENESIS does not magically increase a model's parameter count or native abilities. It improves what the model can accomplish through verified knowledge, external tools, structured workflows and (optionally) actual training.

## Project status

**Early foundation / v0.1.0-dev.** This repository is being built incrementally. The current version provides the initial Python package, CLI, hardware inspection and an optional local web status server. Agent execution, model adapters, memory, research, multimodal processing and training are planned modules, not implemented features yet.

## Principles

- **Local-first:** local models and local data are the default.
- **Model-agnostic:** adapters for Ollama, llama.cpp, LM Studio and Hugging Face are planned.
- **CLI + Web:** terminal controls and a local browser interface.
- **Resource-aware:** inspect hardware and adapt workloads to available resources.
- **Evidence-based evolution:** evaluate skills and model versions instead of treating XP as proof of intelligence.
- **Permissioned autonomy:** tools run with explicit capabilities, isolation and approval boundaries.
- **Extensible:** optional providers, tools and specialist models.

## Requirements

- Linux first (Ubuntu/Debian are the initial targets)
- Python 3.11+
- A local model runtime is optional for the initial foundation

## Install from source

```bash
git clone https://github.com/testjust019-xd/GENESIS-CORE.git
cd GENESIS-CORE
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
```

Optional web interface:

```bash
pip install -e ".[web]"
```

## First commands

```bash
genesis --help
genesis doctor
genesis init
genesis serve
```

The web server binds to `127.0.0.1` by default. Open `http://127.0.0.1:8765`.

## Planned architecture

| Component | Responsibility | Status |
|---|---|---|
| Core / CLI | Lifecycle and commands | Initial |
| Hardware Monitor | CPU, RAM, disk and platform detection | Initial |
| Local Web UI | Local status dashboard | Initial |
| Model Adapters | Ollama, llama.cpp, LM Studio, Transformers, APIs | Planned |
| Agent Runtime | Planning, tool selection and execution loop | Planned |
| Memory | Session, episodic and semantic knowledge | Planned |
| Research Engine | Search, source capture and verification | Planned |
| Tool System | Permissioned tools and extensions | Planned |
| Multimodal | Image, audio, video and document pipelines | Planned |
| Skill & XP Engine | Track practice and demonstrated competencies | Planned |
| Evaluation Lab | Repeatable benchmarks and regression tests | Planned |
| Training Lab | Optional LoRA / fine-tuning workflows | Planned |
| Evolution Engine | Version, compare and roll back model improvements | Planned |
| Background Scheduler | User-configured maintenance and learning tasks | Planned |

## Safety model

Autonomy will be configurable. Network access, shell commands, file writes, package installation, model training and self-modification must use scoped permissions. New or modified tools will be tested in an isolated workspace before activation. GENESIS will never silently grant itself broader permissions.

## Development

See [ROADMAP.md](ROADMAP.md) for milestones. Contributions and issue reports are welcome.

## License

MIT. See [LICENSE](LICENSE).
