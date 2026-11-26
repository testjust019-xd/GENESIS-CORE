from genesis_core.onboarding import recommend_models, resource_profile


GIB = 1024 ** 3


def test_recommendations_are_conservative_for_low_memory():
    suggestions = recommend_models(4 * GIB, 1 * GIB)
    assert suggestions[0]["name"] == "gemma3:1b"
    assert suggestions[0]["warning"] is not None
    assert suggestions[0]["estimated_runtime_gb"] > suggestions[0]["download_gb"]


def test_recommendations_scale_with_memory():
    assert recommend_models(8 * GIB)[0]["name"] == "llama3.2:3b"
    assert recommend_models(16 * GIB)[0]["name"] == "gemma3:4b"


def test_resource_profile_flags_low_cpu_even_with_more_ram():
    profile = resource_profile({
        "memory_total_bytes": 8 * GIB, "memory_available_bytes": 5 * GIB,
        "cpu_logical": 2, "disk_free_bytes": 20 * GIB,
    })
    assert profile["tier"] == "limited"
    assert profile["notes"]


def test_resource_profile_handles_unknown_hardware():
    profile = resource_profile({})
    assert profile["tier"] == "unknown"
    assert profile["memory_total_gb"] is None


def test_resource_profile_warns_about_low_disk():
    profile = resource_profile({
        "memory_total_bytes": 16 * GIB, "memory_available_bytes": 12 * GIB,
        "cpu_logical": 8, "disk_free_bytes": GIB,
    })
    assert any("disque" in note for note in profile["notes"])


def test_pull_ollama_model_streams_progress(monkeypatch):
    import json
    from genesis_core.onboarding import pull_ollama_model

    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def __iter__(self):
            yield (json.dumps({"status": "pulling", "completed": 50, "total": 100}) + "\\n").encode()
            yield (json.dumps({"status": "success"}) + "\\n").encode()

    captured = {}
    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data)
        return FakeResponse()

    monkeypatch.setattr("genesis_core.onboarding.urlopen", fake_urlopen)
    events = []
    pull_ollama_model("http://127.0.0.1:11434", "gemma3:1b", events.append)
    assert captured["url"].endswith("/api/pull")
    assert captured["payload"]["name"] == "gemma3:1b"
    assert len(events) == 2


def test_setup_offers_single_detected_model_as_primary(monkeypatch, tmp_path):
    import io
    from genesis_core.models import RuntimeStatus
    from genesis_core.onboarding import run_setup
    from genesis_core.config import read_settings

    monkeypatch.setenv("GENESIS_HOME", str(tmp_path / "genesis"))
    monkeypatch.setattr("genesis_core.onboarding.inspect_hardware", lambda: {
        "memory_total_bytes": 8 * GIB, "memory_available_bytes": 5 * GIB,
        "cpu_logical": 4, "disk_free_bytes": 20 * GIB,
    })
    monkeypatch.setattr("genesis_core.onboarding.discover_runtimes", lambda: [
        RuntimeStatus("ollama", "http://127.0.0.1:11434", True, ["qwen:1.5b"], "1 model")
    ])
    result = run_setup(input_fn=lambda _prompt: "", output=io.StringIO())
    assert result == 0
    assert read_settings()["model"]["name"] == "qwen:1.5b"
