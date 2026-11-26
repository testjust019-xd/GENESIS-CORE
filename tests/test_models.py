import json
import unittest
from unittest.mock import patch

from genesis_core.models import discover_runtimes, inspect_runtime


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class ModelDiscoveryTests(unittest.TestCase):
    @patch("genesis_core.models.urlopen")
    def test_ollama_model_names(self, mocked_urlopen):
        mocked_urlopen.return_value = FakeResponse(
            {"models": [{"name": "qwen:1.5b"}, {"name": "llama3:8b"}]}
        )
        result = inspect_runtime("ollama", "http://127.0.0.1:11434/")
        self.assertTrue(result.available)
        self.assertEqual(result.models, ["qwen:1.5b", "llama3:8b"])
        mocked_urlopen.assert_called_once()

    @patch("genesis_core.models.urlopen")
    def test_openai_compatible_model_ids(self, mocked_urlopen):
        mocked_urlopen.return_value = FakeResponse(
            {"data": [{"id": "local-model"}]}
        )
        result = inspect_runtime("lm_studio", "http://127.0.0.1:1234")
        self.assertTrue(result.available)
        self.assertEqual(result.models, ["local-model"])

    @patch("genesis_core.models.urlopen", side_effect=OSError("offline"))
    def test_unavailable_runtime_does_not_crash(self, _mocked_urlopen):
        result = inspect_runtime("llama_cpp", "http://127.0.0.1:8080")
        self.assertFalse(result.available)
        self.assertEqual(result.models, [])

    @patch("genesis_core.models.urlopen", side_effect=OSError("offline"))
    def test_discovery_checks_all_default_providers(self, _mocked_urlopen):
        results = discover_runtimes(timeout=0.01)
        self.assertEqual([item.provider for item in results], [
            "ollama", "llama_cpp", "lm_studio"
        ])


if __name__ == "__main__":
    unittest.main()
