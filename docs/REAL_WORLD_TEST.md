# First real-world verification

This checklist separates automated orchestration tests from a real inference test. CI uses mock adapters and temporary SQLite databases; it does not download models, contact search engines, or prove the quality of a particular model.

## 1. Install and run safe diagnostics

```bash
git clone https://github.com/testjust019-xd/GENESIS-CORE.git
cd GENESIS-CORE
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[web,dev]"
genesis test
```

## 2. Connect one local model

Start Ollama, LM Studio, or llama.cpp separately, then select a model GENESIS can discover:

```bash
genesis models
genesis model set ollama gemma3:1b
genesis model show
```

Use the provider and model identifier actually installed on the machine. The example above is not a required model choice.

## 3. Test the Studio chat

```bash
genesis studio
```

Open `http://127.0.0.1:8765` and verify:

- Create a conversation and send a prompt.
- Assistant text appears incrementally when the selected provider supports streaming.
- The final message is present in the conversation history after refreshing.
- The same session is visible from the TUI.
- A missing or stopped model produces an explicit error rather than a fabricated answer.

## 4. Test SearXNG

Start your own SearXNG instance and ensure its JSON search format is enabled. Then configure GENESIS:

```bash
genesis search set searxng --url http://127.0.0.1:8080
genesis search show
```

Run a search from Studio. Review the returned sources before asking GENESIS to synthesize them. To verify offline behavior, switch back:

```bash
genesis search set offline
```

The local Knowledge Base remains available without SearXNG or Internet access.

## 5. Verify persistent context and permissions

- Add a local document to the Knowledge Base and ask a question that uses it.
- Save a memory, open a new session, and ask a related question.
- Try a tool that is outside the active permission profile and confirm that it is rejected or requires approval.
- Create a mission, inspect its plan, and confirm that blocked or unverified steps are not reported as completed.

## 6. Record resource usage

Run a short, normal conversation first. Observe memory and CPU usage with the operating system's process monitor. Avoid stress tests on low-memory machines. Model size, quantization, context length and other running applications materially affect resource use.

## What passing CI means

Automated tests validate persistence, provider parsing, source review, permissions, bounded agent orchestration and the Studio streaming protocol with mocks. A real local-model test is still required to assess inference latency, response quality, provider-specific compatibility and actual hardware usage.
