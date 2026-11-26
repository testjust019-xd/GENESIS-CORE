"""Command-line interface for GENESIS CORE."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from genesis_core import __version__
from genesis_core.hardware import format_bytes, inspect_hardware

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
        DEFAULT_HOME,
        DEFAULT_HOME / "config",
        DEFAULT_HOME / "data",
        DEFAULT_HOME / "memory",
        DEFAULT_HOME / "logs",
        DEFAULT_HOME / "workspace",
        DEFAULT_HOME / "extensions",
        DEFAULT_HOME / "checkpoints",
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    config_file = DEFAULT_HOME / "config" / "settings.json"
    if not config_file.exists():
        config_file.write_text(
            json.dumps(
                {
                    "instance_name": "GENESIS",
                    "autonomy_level": 1,
                    "web_host": "127.0.0.1",
                    "web_port": 8765,
                    "permissions": {
                        "network": False,
                        "shell": False,
                        "workspace_write": True,
                        "install_packages": False,
                        "self_modify": False,
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
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

    serve = subparsers.add_parser("serve", help="start the local web dashboard")
    serve.add_argument("--host", default="127.0.0.1", help="bind address (default: localhost only)")
    serve.add_argument("--port", type=int, default=8765, help="port (default: 8765)")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        _print_hardware()
        return 0
    if args.command == "init":
        return _init()
    if args.command == "serve":
        try:
            import uvicorn
        except ImportError:
            print('Web dependencies missing. Install with: pip install -e ".[web]"', file=sys.stderr)
            return 2
        from genesis_core.web import app

        print(f"GENESIS dashboard: http://{args.host}:{args.port}")
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
