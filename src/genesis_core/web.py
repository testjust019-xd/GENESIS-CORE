"""Optional local web dashboard. Install the 'web' extra to enable it."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from genesis_core import __version__
from genesis_core.hardware import format_bytes, inspect_hardware
from genesis_core.models import discover_runtimes

app = FastAPI(title="GENESIS CORE", version=__version__)


@app.get("/api/status")
def status() -> dict:
    hardware = inspect_hardware()
    return {
        "name": "GENESIS CORE",
        "version": __version__,
        "status": "foundation",
        "implemented": ["CLI", "hardware diagnostics", "local dashboard"],
        "planned": [
            "model adapters",
            "agent runtime",
            "memory and learning",
            "research engine",
            "multimodal tools",
            "training and evolution",
        ],
        "hardware": hardware,
        "model_runtimes": [runtime.to_dict() for runtime in discover_runtimes()],
    }


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    data = inspect_hardware()
    return f"""
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>GENESIS CORE</title>
      <style>
        :root {{ color-scheme: dark; font-family: Inter, system-ui, sans-serif; }}
        body {{ margin: 0; background: #090d16; color: #e8eefc; }}
        main {{ max-width: 980px; margin: 7vh auto; padding: 24px; }}
        .tag {{ color: #72e0bd; letter-spacing: .16em; font-size: .75rem; }}
        h1 {{ font-size: clamp(2.4rem, 7vw, 5rem); margin: .25em 0; }}
        p {{ color: #aab6cc; line-height: 1.6; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(210px,1fr)); gap: 14px; margin-top: 28px; }}
        .card {{ background: #121a2a; border: 1px solid #26334b; border-radius: 14px; padding: 20px; }}
        .label {{ color: #91a1bd; font-size: .8rem; }}
        .value {{ font-size: 1.35rem; margin-top: 8px; }}
        .status {{ display: inline-block; border: 1px solid #246b58; color: #72e0bd; padding: 6px 10px; border-radius: 99px; }}
        code {{ color: #72e0bd; }}
      </style>
    </head>
    <body>
      <main>
        <div class="tag">LOCAL-FIRST AI EVOLUTION FRAMEWORK</div>
        <h1>GENESIS CORE</h1>
        <p>A persistent environment for local models to use tools, build knowledge,
        practice skills and improve through measured evaluation.</p>
        <span class="status">FOUNDATION ONLINE · v{__version__}</span>
        <section class="grid">
          <div class="card"><div class="label">PLATFORM</div><div class="value">{data["system"]} · {data["machine"]}</div></div>
          <div class="card"><div class="label">LOGICAL CPU</div><div class="value">{data["cpu_logical"] or "Unknown"}</div></div>
          <div class="card"><div class="label">TOTAL RAM</div><div class="value">{format_bytes(data["memory_total_bytes"])}</div></div>
          <div class="card"><div class="label">AVAILABLE RAM</div><div class="value">{format_bytes(data["memory_available_bytes"])}</div></div>
          <div class="card"><div class="label">DISK FREE</div><div class="value">{format_bytes(data["disk_free_bytes"])}</div></div>
          <div class="card"><div class="label">ACTIVE MODEL</div><div class="value">Not connected yet</div></div>
        </section>
        <p>Next milestone: select a primary model and introduce the permissioned agent loop.</p>
        <p>Machine-readable status: <code>/api/status</code></p>
      </main>
    </body>
    </html>
    """
