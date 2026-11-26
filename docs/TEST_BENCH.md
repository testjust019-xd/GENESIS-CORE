# GENESIS CORE Test Bench

The Test Bench is a local diagnostic suite for checking the Python environment and
important storage / permission foundations before using GENESIS.

## Commands

```bash
genesis test
genesis test --quick
genesis test --full
genesis test --json-report genesis-diagnostic.json
```

- `genesis test` runs the fast local self-tests.
- `--quick` is an explicit alias for the same safe baseline.
- `--full` additionally probes the default local Ollama, llama.cpp and LM Studio
  model-list endpoints. This is read-only; it does not run inference.
- `--json-report PATH` writes a machine-readable report to the chosen path.

The baseline checks Python >= 3.11, the GENESIS home directory's write access,
SQLite persistence and integrity, memory persistence, knowledge ingestion /
deduplication, and fail-closed tool permission behavior. Storage self-tests use
temporary directories and do not modify the user's GENESIS database.

The default run makes no network requests, does not inspect or download models,
does not invoke a shell, and does not run an LLM. The optional full model probe
only contacts the configured local model-list endpoints and may report a warning
when no runtime is running. A warning is not a failed self-test.

## Install

From a cloned repository, use an isolated virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[web,dev]"
genesis test
```

A local inference runtime and model are needed for actual AI responses, but not
for installation, diagnostics, or the storage self-tests.
