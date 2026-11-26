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


def resource_profile(hardware: dict[str, Any]) -> dict[str, Any]:
    """Classify the host conservatively; this is guidance, not a benchmark."""
    total = hardware.get("memory_total_bytes")
    available = hardware.get("memory_available_bytes")
    cpu = hardware.get("cpu_logical")
    free_disk = hardware.get("disk_free_bytes")
    total_gb = total / GIB if total is not None else None
    available_gb = available / GIB if available is not None else None
    if total_gb is None:
        tier, label = "unknown", "Ressources inconnues"
    elif total_gb < 6 or (cpu is not None and cpu <= 2):
        tier, label = "limited", "Configuration légère"
    elif total_gb < 12:
        tier, label = "balanced", "Configuration équilibrée"
    else:
        tier, label = "capable", "Configuration confortable"
    notes = []
    if cpu is not None and cpu <= 2:
        notes.append("CPU avec peu de cœurs : privilégier les modèles légers et les tâches séquentielles.")
    if available_gb is not None and available_gb < 2:
        notes.append("Peu de RAM disponible actuellement : fermer les applications lourdes avant l'inférence.")
    if free_disk is not None and free_disk < 3 * GIB:
        notes.append("Moins de 3 Go d'espace disque libre : vérifier le stockage avant tout téléchargement.")
    return {
        "tier": tier, "label": label, "memory_total_gb": round(total_gb, 2) if total_gb is not None else None,
        "memory_available_gb": round(available_gb, 2) if available_gb is not None else None,
        "cpu_logical": cpu, "disk_free_gb": round(free_disk / GIB, 2) if free_disk is not None else None,
        "notes": notes,
    }


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
        # Runtime overhead is substantial and varies by quantization/context.
        result["estimated_runtime_gb"] = round(item["download_gb"] * 2.2 + 1.0, 2)
        result["warning"] = None
        if available_gb is not None and available_gb < result["estimated_runtime_gb"]:
            result["warning"] = (
                "RAM actuellement disponible potentiellement insuffisante : "
                "le modèle peut être lent ou ne pas démarrer."
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
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError, RuntimeError) as exc:
        raise RuntimeError(f"Échec du téléchargement de {model}: {exc}") from exc


def print_welcome(*, output: Any = None, hardware: dict[str, Any] | None = None,
                  runtimes: list[Any] | None = None) -> None:
    """Show a compact first-launch overview without changing configuration."""
    output = output or sys.stdout
    hardware = hardware or inspect_hardware()
    runtimes = runtimes if runtimes is not None else discover_runtimes()
    profile = resource_profile(hardware)
    print("\n╔══════════════════════════════════════════════╗", file=output)
    print("║          GENESIS CORE — BIENVENUE            ║", file=output)
    print("╚══════════════════════════════════════════════╝", file=output)
    print(f"Profil de cette machine : {profile['label']}", file=output)
    print(f"RAM : {profile['memory_total_gb'] if profile['memory_total_gb'] is not None else 'inconnue'} Go | "
          f"CPU : {profile['cpu_logical'] or 'inconnu'} cœur(s)", file=output)
    if profile["disk_free_gb"] is not None:
        print(f"Espace disque libre : {profile['disk_free_gb']:.1f} Go", file=output)
    for note in profile["notes"]:
        print(f"Conseil : {note}", file=output)
    print("\nDétection des modèles locaux :", file=output)
    found = False
    for runtime in runtimes:
        state = "EN LIGNE" if runtime.available else "hors ligne"
        print(f"  • {runtime.provider}: {state}", file=output)
        for model in runtime.models:
            found = True
            print(f"      - {model}", file=output)
    if not found:
        print("  Aucun modèle local déjà détecté.", file=output)
    settings = read_settings()
    selected = settings.get("model")
    if selected:
        print(f"Modèle principal configuré : {selected.get('provider')}/{selected.get('name')}", file=output)
    else:
        print("Aucun modèle principal configuré pour le moment.", file=output)
    print("\nUn seul modèle de base suffit. Les autres fournisseurs et modèles restent facultatifs.", file=output)
    print("Commandes : genesis setup | genesis models | genesis tui | genesis studio", file=output)


def _print_recommendations(memory_total: int | None,
                           memory_available: int | None) -> list[dict[str, Any]]:
    suggestions = recommend_models(memory_total, memory_available)
    print("\nModèles recommandés pour cette machine :")
    for index, item in enumerate(suggestions, 1):
        print(f"  {index}. {item['name']} — {item['label']} (~{item['download_gb']:.2f} Go)")
        print(f"     RAM d'exécution estimée : ~{item['estimated_runtime_gb']:.1f} Go (variable selon quantification/contexte)")
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
    profile = resource_profile(hardware)
    print("GENESIS — CONFIGURATION INITIALE", file=output)
    print(f"Profil matériel : {profile['label']}", file=output)
    if hardware["memory_total_bytes"] is not None:
        print(f"RAM détectée : {hardware['memory_total_bytes'] / GIB:.1f} Go", file=output)

    installed = [(runtime, model) for runtime in runtimes
                 if runtime.available for model in runtime.models]
    if installed:
        print("\nModèles déjà détectés :", file=output)
        for index, (runtime, model) in enumerate(installed, 1):
            print(f"  {index}. {runtime.provider}/{model}", file=output)
        if len(installed) == 1:
            choice = input_fn("Un seul modèle trouvé. L'utiliser comme modèle principal ? [O/n] ").strip().lower()
            if choice in {"", "y", "yes", "o", "oui"}:
                runtime, model = installed[0]
                set_model(runtime.provider, model, runtime.base_url)
                settings = read_settings()
                settings["onboarding_completed"] = True
                write_settings(settings)
                print(f"Modèle principal configuré : {runtime.provider}/{model}", file=output)
                return 0
            if choice in {"n", "non", "no"}:
                print("Configuration du modèle ignorée.", file=output)
                return 0
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
        online = [runtime.provider for runtime in runtimes if runtime.available]
        if online:
            print("\nRuntime(s) détecté(s), mais aucun modèle n'est encore chargé : "
                  + ", ".join(online), file=output)
            print("Charge un modèle dans ton runtime, puis relance genesis setup.", file=output)
        else:
            print("\nAucun runtime local n'a été détecté.", file=output)
            print("Installe ou démarre Ollama, llama.cpp ou LM Studio, puis relance genesis setup.", file=output)
        print("GENESIS n'installe pas de runtime automatiquement.", file=output)
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
    if selected["warning"]:
        proceed = input_fn("La mémoire disponible est faible. Continuer malgré le risque ? [y/N] ").strip().lower()
        if proceed not in {"y", "yes", "o", "oui"}:
            print("Téléchargement annulé.", file=output)
            return 0
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
    """Run a guided, one-time welcome when the interactive app first opens."""
    if not sys.stdin.isatty():
        return 0
    settings = read_settings()
    if settings.get("model") or settings.get("onboarding_completed"):
        return 0
    print_welcome()
    answer = input("Lancer la configuration du modèle maintenant ? [O/n] ").strip().lower()
    if answer in {"n", "non", "no"}:
        settings["onboarding_completed"] = True
        write_settings(settings)
        print("Configuration ignorée. Tu pourras lancer genesis setup plus tard.")
        return 0
    return run_setup()
