# First Launch Experience

GENESIS shows a welcome overview the first time an interactive TUI or Studio session
starts without a configured primary model. It summarizes hardware, detects local
Ollama / llama.cpp / LM Studio endpoints and lists discovered model IDs. The overview
does not change settings or download anything.

## Commands

```bash
genesis welcome
genesis doctor
genesis models
genesis recommend
genesis setup
```

The resource profile is a conservative hint based on available RAM, total RAM, logical
CPU count and free disk. It is not a performance benchmark. Model runtime memory
estimates are approximate: quantization, context length, runtime overhead and other
applications change actual requirements.

If exactly one local model is discovered, setup offers to select it as the primary
model. With multiple models, you choose one. If no model exists but Ollama is online,
setup offers a recommended download; downloading still requires a separate explicit
confirmation. If another supported runtime is online but has no loaded model, setup
explains that a model must be loaded there first. GENESIS never installs a runtime
automatically.

A single primary model is enough for the core GENESIS experience. Multiple models and
providers are optional.
