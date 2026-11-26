"""Command-line interface for GENESIS CORE."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from genesis_core import __version__
from genesis_core.config import read_settings, set_model
from genesis_core.hardware import format_bytes, inspect_hardware
from genesis_core.models import discover_runtimes
from genesis_core.onboarding import recommend_models, run_first_start_if_needed, run_setup

DEFAULT_HOME = Path(os.environ.get("GENESIS_HOME", Path.home() / ".genesis"))


def _print_hardware() -> None:
    data = inspect_hardware()
    print("GENESIS CORE — SYSTEM DIAGNOSTICS")
    print(f"Platform:          {data['system']} {data['release']} ({data['machine']})")
    print(f"Python:            {data['python']}")
    print(f"Logical CPUs:      {data['cpu_logical'] or 'unknown'}")
    print(f"RAM total:         {format_bytes(data['memory_total_bytes'])}")
    print(f"RAM available:     {format_bytes(data['memory_available_bytes'])}")
    print(f"Disk total:        {format_bytes(data['disk_total_bytes'])}")
    print(f"Disk free:         {format_bytes(data['disk_free_bytes'])}")
    print(f"GENESIS home:      {DEFAULT_HOME}")
    if data["system"] != "Linux":
        print("Note: Linux is the first supported platform; other platforms are experimental.")


def _init() -> int:
    directories = [
        DEFAULT_HOME, DEFAULT_HOME / "config", DEFAULT_HOME / "data",
        DEFAULT_HOME / "memory", DEFAULT_HOME / "logs", DEFAULT_HOME / "workspace",
        DEFAULT_HOME / "extensions", DEFAULT_HOME / "checkpoints",
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    config_file = DEFAULT_HOME / "config" / "settings.json"
    if not config_file.exists():
        config_file.write_text(json.dumps({
            "instance_name": "GENESIS", "autonomy_level": 1,
            "web_host": "127.0.0.1", "web_port": 8765,
            "permissions": {"network": False, "shell": False, "workspace_write": True,
                            "install_packages": False, "self_modify": False},
        }, indent=2) + "\n", encoding="utf-8")
    print(f"GENESIS workspace initialized at: {DEFAULT_HOME}")
    print(f"Configuration: {config_file}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="genesis",
        description="GENESIS CORE — local-first AI agent and evolution framework",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("doctor", help="inspect host resources and runtime environment")
    subparsers.add_parser("init", help="create the local GENESIS data directory")
    subparsers.add_parser("setup", help="configure and optionally download a recommended local model")
    subparsers.add_parser("recommend", help="recommend local models for this machine")
    subparsers.add_parser("models", help="discover local model runtimes and available models")
    test = subparsers.add_parser("test", help="run local GENESIS diagnostics and self-tests")
    test.add_argument("--quick", action="store_true", help="run safe local self-tests (default)")
    test.add_argument("--full", action="store_true", help="also probe local model runtime endpoints")
    test.add_argument("--json-report", metavar="PATH", help="write a JSON diagnostic report")
    model = subparsers.add_parser("model", help="view or configure the primary model")
    model_sub = model.add_subparsers(dest="model_action")
    model_sub.add_parser("show", help="show the selected primary model")
    model_set = model_sub.add_parser("set", help="select the primary model")
    model_set.add_argument("provider", choices=["ollama", "llama_cpp", "lm_studio"])
    model_set.add_argument("name", help="model identifier reported by the provider")
    model_set.add_argument("--url", help="custom provider base URL")
    subparsers.add_parser("tui", help="open the interactive GENESIS terminal workspace")
    serve = subparsers.add_parser("studio", aliases=["serve"], help="open GENESIS Studio in your browser")
    serve.add_argument("--host", default="127.0.0.1", help="bind address (default: localhost only)")
    serve.add_argument("--port", type=int, default=8765, help="port (default: 8765)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "tui":
        run_first_start_if_needed()
        from genesis_core.tui import run_tui
        return run_tui()
    if args.command == "doctor":
        _print_hardware()
        return 0
    if args.command == "test":
        from genesis_core.diagnostics import format_report, run_test_bench
        report = run_test_bench(DEFAULT_HOME, include_models=args.full)
        print(format_report(report))
        if args.json_report:
            target = Path(args.json_report).expanduser()
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                                  encoding="utf-8")
                print(f"JSON report: {target}")
            except OSError as exc:
                print(f"Could not write JSON report: {exc}", file=sys.stderr)
                return 2
        return 1 if report["overall"] == "fail" else 0
    if args.command == "init":
        return _init()
    if args.command == "setup":
        return run_setup()
    if args.command == "recommend":
        hardware = inspect_hardware()
        total, available = hardware["memory_total_bytes"], hardware["memory_available_bytes"]
        print("GENESIS — RECOMMANDATIONS DE MODÈLES")
        print(f"RAM totale : {format_bytes(total)}")
        print(f"RAM disponible : {format_bytes(available)}")
        for index, item in enumerate(recommend_models(total, available), 1):
            print(f"  {index}. {item['name']} — {item['label']} (~{item['download_gb']:.2f} Go)")
            print(f"     {item['description']}")
            if item["warning"]:
                print(f"     ATTENTION : {item['warning']}")
        print("La mémoire nécessaire à l'exécution dépasse la seule taille du téléchargement.")
        print("Lancer genesis setup pour choisir et installer un modèle via Ollama.")
        return 0
    if args.command == "model":
        if args.model_action == "set":
            try:
                path = set_model(args.provider, args.name, args.url)
            except ValueError as exc:
                print(f"Configuration error: {exc}", file=sys.stderr)
                return 2
            print(f"Primary model saved to {path}: {args.provider}/{args.name}")
            return 0
        selected = read_settings().get("model")
        if selected:
            print(f"Primary model: {selected.get('provider')}/{selected.get('name')}")
            print(f"Base URL: {selected.get('base_url', 'provider default')}")
        else:
            print("No primary model selected. GENESIS will auto-detect a local model.")
        return 0
    if args.command == "models":
        print("GENESIS CORE — LOCAL MODEL RUNTIMES")
        for runtime in discover_runtimes():
            print(f"\n{runtime.provider}: {'ONLINE' if runtime.available else 'OFFLINE'} — {runtime.base_url}")
            print(f"  {runtime.detail}")
            for item in runtime.models:
                print(f"  • {item}")
        return 0
    if args.command in {"studio", "serve"}:
        run_first_start_if_needed()
        try:
            import uvicorn
        except ImportError:
            print('Web dependencies missing. Install with: pip install -e ".[web]"', file=sys.stderr)
            return 2
        from genesis_core.web import app
        print(f"GENESIS Studio: http://{args.host}:{args.port}")
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
