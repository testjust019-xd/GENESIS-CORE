from __future__ import annotations

import pytest

from genesis_core.evolution import EvolutionEngine, EvolutionError
from genesis_core.experience import ExperienceStore
from genesis_core.skills import SkillStore
from genesis_core.state import StateStore


def setup_engine(tmp_path):
    state = StateStore(tmp_path / "genesis.db")
    experiences = ExperienceStore(state)
    skills = SkillStore(state.database_path, set())
    return state, experiences, skills, EvolutionEngine(state, experiences)


def capture(store, *, task_id, outcome="completed", objective="Check local model setup",
            instructions="Inspect the configured runtime and report its status.",
            summary="The observer verified the result."):
    return store.capture_task_result(
        mission_id=f"mission-{task_id}",
        task_id=task_id,
        title="Inspect local model setup",
        objective=objective,
        instructions=instructions,
        outcome=outcome,
        result="Recorded task result.",
        observer_summary=summary,
        confidence=0.9,
    )


def test_repeated_experiences_create_one_evidence_proposal(tmp_path):
    _, experiences, _, engine = setup_engine(tmp_path)
    first = capture(experiences, task_id="one")
    second = capture(experiences, task_id="two", outcome="blocked")

    result = engine.analyze()
    assert result["created"] == 1
    proposal = result["proposals"][0]
    assert proposal["evidence_count"] == 2
    assert proposal["completed_count"] == 1
    assert proposal["blocked_count"] == 1
    assert set(proposal["evidence_ids"]) == {first["id"], second["id"]}

    repeated = engine.analyze()
    assert repeated["created"] == 0
    assert repeated["updated"] == 1
    assert len(engine.list(status="pending")) == 1


def test_contexts_are_not_semantically_guessed_or_archived(tmp_path):
    _, experiences, _, engine = setup_engine(tmp_path)
    capture(experiences, task_id="one")
    capture(experiences, task_id="two", objective="Check another unrelated thing")
    archived = capture(experiences, task_id="three")
    experiences.set_status(archived["id"], "archived")

    result = engine.analyze()
    assert result["created"] == 0
    assert result["proposals"] == []


def test_proposal_requires_review_and_only_creates_skill_draft(tmp_path):
    _, experiences, skills, engine = setup_engine(tmp_path)
    capture(experiences, task_id="one")
    capture(experiences, task_id="two")
    proposal = engine.analyze()["proposals"][0]

    with pytest.raises(EvolutionError, match="accepted"):
        engine.promote_to_skill_draft(proposal["id"], skills)

    accepted = engine.decide(proposal["id"], "accept", "Evidence reviewed.")
    assert accepted["status"] == "accepted"

    skill = engine.promote_to_skill_draft(proposal["id"], skills)
    assert skill["status"] == "draft"
    assert "Source observations" in skill["instructions"]
    assert engine.promote_to_skill_draft(proposal["id"], skills)["id"] == skill["id"]

    with pytest.raises(EvolutionError, match="Only pending"):
        engine.decide(proposal["id"], "reject")


def test_rejected_proposal_cannot_be_promoted(tmp_path):
    _, experiences, skills, engine = setup_engine(tmp_path)
    capture(experiences, task_id="one")
    capture(experiences, task_id="two")
    proposal = engine.analyze()["proposals"][0]
    engine.decide(proposal["id"], "reject")
    with pytest.raises(EvolutionError, match="accepted"):
        engine.promote_to_skill_draft(proposal["id"], skills)


@pytest.mark.parametrize("kwargs", [
    {"min_support": 1},
    {"min_support": 21},
    {"limit": 0},
    {"min_support": True},
])
def test_analyze_validates_bounds(tmp_path, kwargs):
    _, _, _, engine = setup_engine(tmp_path)
    with pytest.raises(EvolutionError):
        engine.analyze(**kwargs)


def test_skill_store_must_share_database(tmp_path):
    _, experiences, _, engine = setup_engine(tmp_path)
    capture(experiences, task_id="one")
    capture(experiences, task_id="two")
    proposal = engine.analyze()["proposals"][0]
    engine.decide(proposal["id"], "accept")
    other = SkillStore(tmp_path / "other.db", set())
    with pytest.raises(EvolutionError, match="share the same database"):
        engine.promote_to_skill_draft(proposal["id"], other)
