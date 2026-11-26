# Model Core — first milestone

Model Core is the provider-discovery and compatibility layer for GENESIS CORE.

## Initial providers

| Provider | Default address | Discovery endpoint | Status |
|---|---|---|---|
| Ollama | http://127.0.0.1:11434 | GET /api/tags | Initial discovery |
| llama.cpp server | http://127.0.0.1:8080 | GET /v1/models | OpenAI-compatible discovery |
| LM Studio | http://127.0.0.1:1234 | GET /v1/models | OpenAI-compatible discovery |

The base URLs can be overridden with:

- `GENESIS_OLLAMA_URL`
- `GENESIS_LLAMA_CPP_URL`
- `GENESIS_LM_STUDIO_URL`

The `genesis models` command performs read-only discovery. It does not launch runtimes,
download models, or send prompts.

## Next steps

1. Add a common chat-completion interface and provider-specific request handling.
2. Add explicit model selection and a persisted primary-model profile.
3. Add capability checks and safe connection tests.
4. Add optional remote API providers with secret storage.
5. Add specialist-model routing without replacing the primary decision-maker.

Provider discovery is not the same as model capability verification. GENESIS must test
capabilities with explicit user consent before relying on them.
