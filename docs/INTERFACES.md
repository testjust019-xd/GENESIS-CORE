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

## GENESIS Studio

The graphical interface is launched locally through a command such as `genesis studio` and opened in the user's browser. It should provide:

- project/file explorer
- central agent conversation
- integrated terminal and editor panels
- mission control and task timeline
- live activity/tool trace
- model and provider management
- memory, research, and skills views
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
