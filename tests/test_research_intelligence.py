from types import SimpleNamespace
import json
import pytest

from genesis_core.research import ResearchStore
from genesis_core.research_intelligence import ResearchIntelligence, ResearchIntelligenceError
from genesis_core.state import StateStore


class FakeAdapter:
    config = SimpleNamespace(provider="fake-local", model="test-model")

    def __init__(self, payload):
        self.payload = payload
        self.messages = None

    def chat(self, messages):
        self.messages = messages
        return json.dumps(self.payload)


def _approved_run(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    store = ResearchStore(state)
    run = store.save_run("renewable energy", "fake", [
        {"title": "Study A", "url": "https://example.org/a", "snippet": "Solar capacity grew."},
        {"title": "Study B", "url": "https://example.org/b", "snippet": "Wind capacity grew."},
    ])
    sources = store.list_sources(run_id=run["id"])
    store.decide_source(sources[0]["id"], "approved")
    store.decide_source(sources[1]["id"], "approved")
    return state, run, sources


def test_research_intelligence_generates_persists_and_lists_cited_report(tmp_path):
    state, run, sources = _approved_run(tmp_path)
    adapter = FakeAdapter({
        "title": "Renewable energy overview",
        "summary": "Both sources describe capacity growth.",
        "claims": [
            {"text": "Solar capacity grew.", "classification": "supported",
             "source_ids": [sources[0]["id"]]},
            {"text": "The trend may continue.", "classification": "inference",
             "source_ids": [sources[0]["id"], sources[1]["id"]]},
            {"text": "The exact global share is unknown.", "classification": "unverified",
             "source_ids": []},
        ],
        "disagreements": [], "open_questions": ["What is the exact global share?"],
    })
    intelligence = ResearchIntelligence(state, adapter)
    report = intelligence.generate(run["id"], "Compare the findings")
    assert report["provider"] == "fake-local"
    assert report["model"] == "test-model"
    assert report["claims"][0]["source_ids"] == [sources[0]["id"]]
    assert intelligence.get(report["id"])["title"] == report["title"]
    assert intelligence.list(run["id"])[0]["id"] == report["id"]
    assert "UNTRUSTED" in adapter.messages[1]["content"]


def test_research_intelligence_excludes_pending_and_rejected_sources(tmp_path):
    state, run, sources = _approved_run(tmp_path)
    ResearchStore(state).decide_source(sources[1]["id"], "rejected")
    adapter = FakeAdapter({
        "title": "One source", "summary": "A limited summary.",
        "claims": [{"text": "Claim.", "classification": "supported",
                    "source_ids": [sources[0]["id"]]}],
        "disagreements": [], "open_questions": [],
    })
    report = ResearchIntelligence(state, adapter).generate(run["id"])
    assert report["source_count"] == 1


def test_research_intelligence_requires_approved_sources(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    store = ResearchStore(state)
    run = store.save_run("query", "fake", [
        {"title": "Pending", "url": "https://example.org/p", "snippet": "Not reviewed."}
    ])
    with pytest.raises(ResearchIntelligenceError, match="no approved sources"):
        ResearchIntelligence(state, FakeAdapter({})).generate(run["id"])


def test_research_intelligence_rejects_forged_source_ids_and_does_not_save(tmp_path):
    state, run, _sources = _approved_run(tmp_path)
    adapter = FakeAdapter({
        "title": "Forged", "summary": "Bad citation.",
        "claims": [{"text": "Claim.", "classification": "supported",
                    "source_ids": ["not-in-this-run"]}],
        "disagreements": [], "open_questions": [],
    })
    intelligence = ResearchIntelligence(state, adapter)
    with pytest.raises(ResearchIntelligenceError, match="outside this reviewed"):
        intelligence.generate(run["id"])
    assert intelligence.list(run["id"]) == []


def test_research_intelligence_requires_citations_for_supported_claims(tmp_path):
    state, run, _sources = _approved_run(tmp_path)
    adapter = FakeAdapter({
        "title": "Missing citation", "summary": "No provenance.",
        "claims": [{"text": "Claim.", "classification": "supported", "source_ids": []}],
        "disagreements": [], "open_questions": [],
    })
    with pytest.raises(ResearchIntelligenceError, match="must cite"):
        ResearchIntelligence(state, adapter).generate(run["id"])


def test_research_intelligence_rejects_invalid_json_without_persisting(tmp_path):
    state, run, _sources = _approved_run(tmp_path)
    adapter = FakeAdapter({})
    adapter.chat = lambda messages: "not json"
    intelligence = ResearchIntelligence(state, adapter)
    with pytest.raises(ResearchIntelligenceError, match="valid JSON"):
        intelligence.generate(run["id"])
    assert intelligence.list(run["id"]) == []
