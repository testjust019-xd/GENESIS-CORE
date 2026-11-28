# Install GENESIS CORE

This guide installs the full local-first GENESIS experience: terminal workspace, browser Studio, tests and optional document ingestion.

## 1. System requirements

- Linux is the primary target (Ubuntu and Debian are the initial supported distributions).
- Python 3.11 or newer.
- Git.
- Internet access for the initial source checkout and Python packages.
- A local model runtime is optional for installation, diagnostics and the Test Bench. It is required for model-powered chat and agent work.
- Keep several GB of free disk space if you plan to download a local model. Model memory requirements depend on quantization, context length and the runtime.

Check your Python version:

```bash
python3 --version
```

If your distribution provides Python 3.10 or older, install Python 3.11+ using its supported package source before continuing. Do not create the virtual environment with an older interpreter.

## 2. Install system packages

Ubuntu / Debian:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
```

On another Linux distribution, install the equivalent Git, Python 3 and venv packages.

Windows users should use a current WSL2 Ubuntu environment for this Linux-first release. Native Windows and macOS behavior is experimental.

## 3. Download and install GENESIS

```bash
git clone https://github.com/testjust019-xd/GENESIS-CORE.git
cd GENESIS-CORE

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e ".[web,dev]"
```

The editable install keeps the checkout connected to the installed `genesis` command, so updates pulled into this folder are used by the environment.

Optional selectable-text PDF ingestion:

```bash
python -m pip install -e ".[web,dev,documents]"
```

## 4. Run the local checks first

```bash
genesis test
genesis doctor
genesis welcome
```

The default Test Bench uses temporary data, makes no network requests, downloads no models and does not modify your normal GENESIS database. For extra local runtime endpoint checks:

```bash
genesis test --full
```

## 5. Initialize your GENESIS workspace

```bash
genesis init
```

This creates the user data directories under `~/.genesis`. Your conversations, settings, memories, research and saved artifacts are kept in the GENESIS data directory, separate from the Git checkout. Set `GENESIS_HOME` before launching if you want to use a different data location.

## 6. Connect a local model (optional, for AI responses)

GENESIS can discover local Ollama, llama.cpp and LM Studio endpoints. Install and start one of those runtimes separately, then check what GENESIS can see:

```bash
genesis models
genesis recommend
genesis setup
```

The setup flow can help select a detected model. It does not silently install a runtime or download a model. If you already have a model loaded, select the exact provider and model ID reported by `genesis models`, for example:

```bash
genesis model set ollama gemma3:1b
genesis model show
```

That model ID is only an example: use a model that is actually installed and suitable for the machine. A local model is not required to open Studio, use the Artifact Engine, or run the offline Test Bench.

## 7. Launch the terminal and browser interfaces

Terminal workspace:

```bash
genesis tui
```

Browser Studio (run this in another terminal):

```bash
genesis studio
```

Open **http://127.0.0.1:8765** in a browser on the same machine. The default bind address is localhost only.

To use another local port:

```bash
genesis studio --port 8766
```

The TUI and Studio use the same local GENESIS database. In Studio, open **Artifacts** from the left navigation to create, edit, preview and save local HTML/CSS/JavaScript experiences.

> **Network safety:** Studio has no built-in user authentication in this release. Keep the default localhost binding. Do not expose it to a public network or bind to `0.0.0.0` unless you have independently added appropriate access controls and network protections.

## 8. Optional web research

Offline local Knowledge Base search is the default. To use a self-hosted SearXNG instance, start SearXNG separately and configure its JSON search format:

```bash
genesis search set searxng --url http://127.0.0.1:8080
genesis search show
```

Return to offline search at any time:

```bash
genesis search set offline
```

See [SEARXNG.md](SEARXNG.md) for details.

## 9. Updating GENESIS

From the cloned repository, with the virtual environment activated:

```bash
git pull
python -m pip install -e ".[web,dev]"
genesis test
```

Stop and restart any running GENESIS Studio or TUI process after updating.

## Troubleshooting

### `genesis: command not found`

Activate the virtual environment from the repository:

```bash
source .venv/bin/activate
```

If it still fails, repeat the editable install command from the repository root.

### Python version is too old

Check `python3 --version`. GENESIS requires Python 3.11+. Recreate `.venv` with a supported interpreter after installing it.

### Studio does not open

- Confirm the terminal reports that the server started.
- Open `http://127.0.0.1:8765` on the same machine.
- If the port is already in use, run `genesis studio --port 8766` and open that port.
- Ensure the web extra was installed with `python -m pip install -e ".[web,dev]"`.

### Studio opens but chat cannot answer

Studio and the Artifact Engine can open without a model, but AI chat requires a supported local model runtime with a model loaded. Run `genesis models` and `genesis model show`, then check that the runtime is running.

### Where is my data?

By default, user data is stored under `~/.genesis`, with the main SQLite database at `~/.genesis/data/genesis.db`. It is not stored inside the repository. Check `GENESIS_HOME` if you configured a custom location.

## Next steps

- [First launch and model setup](FIRST_LAUNCH.md)
- [Artifact Engine](ARTIFACT_ENGINE.md)
- [Test Bench](TEST_BENCH.md)
- [Real-world verification checklist](REAL_WORLD_TEST.md)
- [Project roadmap](../ROADMAP.md)
