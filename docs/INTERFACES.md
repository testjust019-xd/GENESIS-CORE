# GENESIS CORE Interfaces

## Decision

GENESIS CORE provides two first-party interfaces:

1. **GENESIS TUI** — an interactive terminal workspace, designed for keyboard-first use.
2. **GENESIS Studio** — a graphical local workspace with an IDE-like layout.

They are two clients of the same GENESIS engine. Neither interface is a wrapper around Ollama, LM Studio, llama.cpp, or another model runtime.

## Shared engine

Both interfaces use the same application services and persistent state:

- conversation and session management
- agent loop, planning, and mission queue
- model selection and provider adapters
- memory and knowledge retrieval
- tools, extensions, and permission checks
- autonomy settings and approval requests
- research, skills, evaluation, and evolution workflows
- activity events, logs, and checkpoints

A task started in the TUI must be visible in Studio, and vice versa. There must not be two separate agent implementations.

## GENESIS TUI

The terminal interface is launched with `genesis`. It should provide:

- interactive conversations and streaming responses
- mission/task creation and progress
- visible tool activity and approval prompts
- model/runtime selection and status
- project and workspace navigation
- command palette and keyboard shortcuts
- session history and resume
- configuration and diagnostics

The TUI should remain usable over SSH and on modest Linux machines.

### Terminal experience (`genesis_core/ui.py`)

The TUI uses a dependency-free presentation layer (standard library only, so it works on Termux, SSH and minimal containers):

- welcome panel with session, model and workspace
- streamed replies rendered as lightweight markdown (headings, bullets, `inline code`, fenced code blocks)
- animated "thinking" indicator; **Ctrl+C** cancels a reply and returns to the prompt, **Ctrl+D** quits
- tool-activity trace after each reply and a pending-approvals notice above the prompt
- Tab completion for slash commands and sub-commands, persistent input history (`~/.genesis/tui_history`)
- the GENESIS avatar (idle/thinking/happy/alert/error faces) in the welcome panel, spinner and replies
- live tool trace while the agent works and inline `[y/N]` approval of gated tools (`on_activity` / `on_approval` callbacks on `AgentRuntime.chat`; clients without them keep the approval queue)
- multi-line input (end a line with `\`), reply footer with duration and an approximate token count
- `/model` to list and switch the primary model, `/export` to save a conversation as Markdown
- **native models, no Ollama needed:** `/model install` recommends a GGUF model for the device's RAM, downloads it from Hugging Face (resumable, size-checked, HTTPS to huggingface.co only) into `~/.genesis/models`, and GENESIS starts and stops its own `llama-server` (llama.cpp) on a loopback port. `/model use` starts a downloaded model; with no other model configured it starts automatically on the first message. The engine itself must be installed once (`pkg install llama-cpp` on Termux; or set `GENESIS_LLAMA_SERVER`)
- **Evolution Lab:** `/eval run` measures the model on a fixed rule-based suite, `/eval skill <id>` compares baseline vs with-skill and stores the evidence (shown when you approve a skill), `/evolve` reports the score timeline, skills and memory. Add suites as JSON in `~/.genesis/evals`. Scores are measured behaviour on that suite, not weight changes
- grouped, filterable help (`/help <text>`) and `/clear`
- colour is disabled automatically when output is not a terminal or `NO_COLOR` is set

## GENESIS Studio

The graphical interface is launched locally through a command such as `genesis studio` and opened in the user's browser. It should provide:

- project/file explorer
- central agent conversation with server-sent-event token streaming
- integrated terminal and editor panels
- mission control and task timeline
- live activity/tool trace
- model and provider management
- memory, research, and skills views
- an Experience Engine view with mission-attempt filters, evidence details and a captured/reviewed/archived workflow
- responsive access to Studio's right-side panels on narrow screens
- permissions and autonomy controls
- settings, logs, and checkpoints

Studio is a first-party GENESIS interface, not the model provider's UI.

## Shared local API

The interfaces communicate with the same local engine through a versioned API and event stream. The API is an internal boundary first; it may later be documented for external integrations.

## Model providers are backends

Ollama, llama.cpp, LM Studio, Hugging Face runtimes, and remote APIs are interchangeable model backends. They supply inference only. GENESIS owns the user experience, agent orchestration, memory, tools, permissions, and workflows.

## Implementation principles

- Linux-first, local-first, and offline-capable where possible.
- One engine and one source of truth for state.
- Provider-neutral interfaces and adapters.
- Resource-aware defaults for modest hardware.
- Explicit permissions, sandboxing, approvals, and rollback for consequential actions.
- Do not present simulated progress or accumulated activity as proof that model weights or intelligence have improved.

## Delivery order

1. Define stable engine services, session state, and event contracts.
2. Build the TUI as the first usable client.
3. Build Studio against the same contracts.
4. Add parity tests so shared tasks and state behave consistently in both clients.
