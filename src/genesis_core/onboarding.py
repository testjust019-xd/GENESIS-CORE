"""Hardware-aware first-run model onboarding for GENESIS CORE."""
from __future__ import annotations

import json
import sys
from typing import Any, Callable
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from genesis_core.config import read_settings, set_model, write_settings
from genesis_core.hardware import inspect_hardware
from genesis_core.models import discover_runtimes


GIB = 1024 ** 3

# Approximate Ollama download sizes; runtime memory use is higher.
MODEL_CATALOG = (
    {"name": "gemma3:1b", "download_gb": 0.81, "label": "Ultra léger",
     "description": "Petit modèle généraliste pour les machines modestes."},
    {"name": "llama3.2:1b", "download_gb": 1.3, "label": "Alternative légère",
     "description": "Petit modèle de chat pour démarrer."},
    {"name": "llama3.2:3b", "download_gb": 2.0, "label": "Équilibré",
     "description": "Plus capable, mais demande davantage de mémoire."},
    {"name": "gemma3:4b", "download_gb": 3.4, "label": "Plus capable",
     "description": "Modèle généraliste plus lourd, avec entrée d'images."},
)


def recommend_models(memory_total_bytes: int | None,
                     memory_available_bytes: int | None = None) -> list[dict[str, Any]]:
    """Return conservative suggestions based on total and currently free RAM."""
    total_gb = memory_total_bytes / GIB if memory_total_bytes is not None else 0
    if total_gb < 6:
        selected = [MODEL_CATALOG[0], MODEL_CATALOG[1]]
    elif total_gb < 12:
        selected = [MODEL_CATALOG[2], MODEL_CATALOG[0]]
    else:
        selected = [MODEL_CATALOG[3], MODEL_CATALOG[2]]

    available_gb = memory_available_bytes / GIB if memory_available_bytes is not None else None
    results = []
    for item in selected:
        result = dict(item)
        result["warning"] = None
        if available_gb is not None and available_gb < item["download_gb"] * 1.8:
            result["warning"] = (
                "Mémoire actuellement disponible faible : le modèle peut manquer "
                "de RAM une fois chargé."
            )
        results.append(result)
    return results


def pull_ollama_model(base_url: str, model: str,
                      progress: Callable[[dict[str, Any]], None] | None = None) -> None:
    """Download a model through the local Ollama pull API."""
    payload = json.dumps({"name": model, "stream": True}).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}/api/pull", data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/x-ndjson"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as response:
            for raw_line in response:
                if not raw_line.strip():
                    continue
                event = json.loads(raw_line.decode("utf-8"))
                if event.get("error"):
                    raise RuntimeError(str(event["error"]))
                if progress:
                    progress(event)
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Échec du téléchargement de {model}: {exc}") from exc


def _print_recommendations(memory_total: int | None,
                           memory_available: int | None) -> list[dict[str, Any]]:
    suggestions = recommend_models(memory_total, memory_available)
    print("\nModèles recommandés pour cette machine :")
    for index, item in enumerate(suggestions, 1):
        print(f"  {index}. {item['name']} — {item['label']} (~{item['download_gb']:.2f} Go)")
        print(f"     {item['description']}")
        if item["warning"]:
            print(f"     ATTENTION : {item['warning']}")
    print("La taille du téléchargement ne représente pas toute la RAM nécessaire au fonctionnement.")
    return suggestions


def run_setup(*, input_fn: Callable[[str], str] = input, output: Any = None) -> int:
    """Interactive setup; downloads only after explicit confirmation."""
    output = output or sys.stdout
    hardware = inspect_hardware()
    runtimes = discover_runtimes()
    print("GENESIS — CONFIGURATION DU MODÈLE", file=output)
    if hardware["memory_total_bytes"] is not None:
        print(f"RAM détectée : {hardware['memory_total_bytes'] / GIB:.1f} Go", file=output)

    installed = [(runtime, model) for runtime in runtimes
                 if runtime.available for model in runtime.models]
    if installed:
        print("\nModèles déjà détectés :", file=output)
        for index, (runtime, model) in enumerate(installed, 1):
            print(f"  {index}. {runtime.provider}/{model}", file=output)
        choice = input_fn("Choisir un modèle (numéro, Entrée pour annuler) : ").strip()
        if not choice:
            return 0
        try:
            runtime, model = installed[int(choice) - 1]
        except (ValueError, IndexError):
            print("Sélection invalide.", file=output)
            return 2
        set_model(runtime.provider, model, runtime.base_url)
        settings = read_settings()
        settings["onboarding_completed"] = True
        write_settings(settings)
        print(f"Modèle principal configuré : {runtime.provider}/{model}", file=output)
        return 0

    ollama = next((runtime for runtime in runtimes
                   if runtime.provider == "ollama" and runtime.available), None)
    if ollama is None:
        print("\nAucun runtime local n'a été détecté.", file=output)
        print("Installe Ollama depuis https://ollama.com/download/linux, puis relance genesis setup.", file=output)
        print("Commande officielle Linux : curl -fsSL https://ollama.com/install.sh | sh", file=output)
        return 1

    suggestions = _print_recommendations(
        hardware["memory_total_bytes"], hardware["memory_available_bytes"]
    )
    choice = input_fn("Modèle à télécharger (numéro, Entrée pour annuler) : ").strip()
    if not choice:
        return 0
    try:
        selected = suggestions[int(choice) - 1]
    except (ValueError, IndexError):
        print("Sélection invalide.", file=output)
        return 2

    confirmation = input_fn(
        f"Télécharger {selected['name']} (~{selected['download_gb']:.2f} Go) ? [y/N] "
    ).strip().lower()
    if confirmation not in {"y", "yes", "o", "oui"}:
        print("Téléchargement annulé.", file=output)
        return 0

    def show_progress(event: dict[str, Any]) -> None:
        status = event.get("status", "Téléchargement…")
        total, completed = event.get("total"), event.get("completed")
        if total and completed is not None:
            print(f"  {status}: {completed * 100 / total:.1f}%", file=output)
        else:
            print(f"  {status}", file=output)

    try:
        pull_ollama_model(ollama.base_url, selected["name"], show_progress)
    except RuntimeError as exc:
        print(str(exc), file=output)
        return 1

    set_model("ollama", selected["name"], ollama.base_url)
    settings = read_settings()
    settings["onboarding_completed"] = True
    write_settings(settings)
    print(f"Modèle installé et configuré : ollama/{selected['name']}", file=output)
    return 0


def run_first_start_if_needed() -> int:
    """Run onboarding once when no model has been configured."""
    settings = read_settings()
    if settings.get("model") or settings.get("onboarding_completed"):
        return 0
    answer = input("Aucun modèle n'est configuré. Lancer la configuration initiale ? [O/n] ").strip().lower()
    if answer in {"n", "non", "no"}:
        settings["onboarding_completed"] = True
        write_settings(settings)
        print("Configuration ignorée. Tu pourras lancer genesis setup plus tard.")
        return 0
    return run_setup()
