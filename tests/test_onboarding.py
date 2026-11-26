import json

from genesis_core.onboarding import recommend_models, pull_ollama_model


def test_recommendations_are_conservative_for_low_memory():
    suggestions = recommend_models(4 * 1024**3, 2 * 1024**3)
    assert suggestions[0]["name"] == "gemma3:1b"
    assert suggestions[0]["warning"] is not None


def test_recommendations_scale_with_memory():
    assert recommend_models(8 * 1024**3)[0]["name"] == "llama3.2:3b"
    assert recommend_models(16 * 1024**3)[0]["name"] == "gemma3:4b"


def test_pull_ollama_model_streams_progress(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def __iter__(self):
            yield (json.dumps({"status": "pulling", "completed": 50, "total": 100}) + "\n").encode()
            yield (json.dumps({"status": "success"}) + "\n").encode()

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
