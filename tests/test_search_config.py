from __future__ import annotations

import pytest

from genesis_core.config import get_search_settings, set_search_settings
from genesis_core.research import ResearchEngine, SearXNGProvider


def test_search_settings_persist_in_genesis_home(tmp_path, monkeypatch):
    monkeypatch.setenv("GENESIS_HOME", str(tmp_path))
    path = set_search_settings("searxng", "http://127.0.0.1:8080/")
    assert path.exists()
    assert get_search_settings() == {
        "provider": "searxng",
        "searxng_url": "http://127.0.0.1:8080",
    }


def test_research_engine_uses_persisted_searxng_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("GENESIS_HOME", str(tmp_path))
    monkeypatch.delenv("GENESIS_SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("GENESIS_SEARXNG_URL", raising=False)
    set_search_settings("searxng", "http://localhost:8080")
    provider = ResearchEngine.configured_provider()
    assert isinstance(provider, SearXNGProvider)
    assert provider.base_url == "http://localhost:8080"


def test_environment_overrides_persisted_search_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("GENESIS_HOME", str(tmp_path))
    set_search_settings("searxng", "http://localhost:8080")
    monkeypatch.setenv("GENESIS_SEARCH_PROVIDER", "offline")
    assert ResearchEngine.configured_provider() is None


@pytest.mark.parametrize("provider", ["unknown", "", "google"])
def test_search_settings_reject_unknown_provider(tmp_path, monkeypatch, provider):
    monkeypatch.setenv("GENESIS_HOME", str(tmp_path))
    with pytest.raises(ValueError):
        set_search_settings(provider)


def test_remote_searxng_requires_https(tmp_path, monkeypatch):
    monkeypatch.setenv("GENESIS_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="HTTPS"):
        set_search_settings("searxng", "http://search.example.org")


def test_searxng_requires_a_valid_url(tmp_path, monkeypatch):
    monkeypatch.setenv("GENESIS_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="HTTP"):
        set_search_settings("searxng", "file:///etc/passwd")
