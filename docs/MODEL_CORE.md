# Model Core — initial connectivity

Model Core is GENESIS CORE's provider-neutral inference layer. It separates model inference from the GENESIS interface, conversation state and agent orchestration.

## Supported local chat providers

| Provider | Default address | Discovery endpoint | Chat endpoint | Current support |
|---|---|---|---|---|
| Ollama | http://127.0.0.1:11434 | GET /api/tags | POST /api/chat | Initial native adapter |
| llama.cpp server | http://127.0.0.1:8080 | GET /v1/models | POST /v1/chat/completions | Initial OpenAI-compatible adapter |
| LM Studio | http://127.0.0.1:1234 | GET /v1/models | POST /v1/chat/completions | Initial OpenAI-compatible adapter |

The base URLs can be overridden with `GENESIS_OLLAMA_URL`, `GENESIS_LLAMA_CPP_URL`, and `GENESIS_LM_STUDIO_URL`.

## Select the primary model

GENESIS can auto-select the first discovered local model. To select one explicitly:

```bash
genesis models
genesis model set ollama llama3.2
genesis model show
```

Other providers:

```bash
genesis model set llama_cpp my-model
genesis model set lm_studio local-model
```

A custom OpenAI-compatible local endpoint can be supplied with `--url`. Environment variables can override the selection:

- `GENESIS_MODEL_PROVIDER`
- `GENESIS_MODEL`
- `GENESIS_MODEL_URL`
- `GENESIS_MODEL_API_KEY`

The persistent selection is stored in `$GENESIS_HOME/config/settings.json`. Do not share that file if it contains credentials. Environment variables are preferable for secrets.

## Agent integration

The first agent runtime sends the system instruction and recent conversation messages to the selected adapter, then stores the assistant reply in the shared SQLite conversation. Both TUI and Studio use this same runtime and database.

This is a direct chat loop, not yet a planning or tool-using autonomous agent. It does not execute shell commands, access files, browse the web, or claim those abilities.

## Known limitations and next steps

1. Run automated tests on supported Python versions and verify provider behavior against real local runtimes.
2. Add streaming, cancellation, token/context limits and capability inspection.
3. Add optional Hugging Face and remote mentor adapters.
4. Add provider health diagnostics and secure credential handling.
5. Add specialist routing without replacing the primary decision-maker.

Provider discovery is not the same as model capability verification. GENESIS must test capabilities with explicit user consent before relying on them.
