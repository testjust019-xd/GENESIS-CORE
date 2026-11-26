import json
from unittest.mock import patch

from genesis_core.adapters import ChatAdapter, ModelConfig


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


def test_ollama_chat_adapter_parses_response():
    config = ModelConfig("ollama", "http://localhost:11434", "tiny-model")
    adapter = ChatAdapter(config)
    response = FakeResponse({"message": {"content": "Hello from Ollama"}})

    with patch("genesis_core.adapters.urlopen", return_value=response):
        answer = adapter.chat([{"role": "user", "content": "Hello"}])

    assert answer == "Hello from Ollama"


def test_openai_compatible_adapter_parses_response():
    config = ModelConfig("llama_cpp", "http://localhost:8080", "tiny-model")
    adapter = ChatAdapter(config)
    response = FakeResponse({
        "choices": [{"message": {"content": "Hello from compatible API"}}]
    })

    with patch("genesis_core.adapters.urlopen", return_value=response):
        answer = adapter.chat([{"role": "user", "content": "Hello"}])

    assert answer == "Hello from compatible API"
