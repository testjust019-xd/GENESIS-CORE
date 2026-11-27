"""GENESIS Studio: graphical client for the shared local GENESIS state."""

from __future__ import annotations

import json
import queue
import threading

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from genesis_core import __version__
from genesis_core.config import get_search_settings, set_search_settings
from genesis_core.agent import AgentRuntime, ModelError, build_default_tool_executor
from genesis_core.hardware import inspect_hardware
from genesis_core.models import discover_runtimes
from genesis_core.missions import MissionError, MissionStore
from genesis_core.mission_engine import MissionEngine, MissionEngineError
from genesis_core.multi_agent import MultiAgentEngine, MultiAgentError
from genesis_core.memory import MemoryError, MemoryStore
from genesis_core.conversation_memory import ConversationMemoryEngine, ConversationMemoryError
from genesis_core.knowledge import KnowledgeError, KnowledgeStore
from genesis_core.research import ResearchEngine, ResearchError
from genesis_core.research_intelligence import ResearchIntelligence, ResearchIntelligenceError
from genesis_core.learning import LearningEngine, LearningError
from genesis_core.experience import ExperienceError, ExperienceStore
from genesis_core.skills import SkillError, SkillStore
from genesis_core.state import StateStore
from genesis_core.tools import ToolError

app = FastAPI(title="GENESIS CORE Studio", version=__version__)
store = StateStore()
tool_executor, approval_store = build_default_tool_executor(store)
agent = AgentRuntime(store=store, tool_executor=tool_executor)
mission_store = MissionStore(state=store)
multi_agent_engine = MultiAgentEngine(store)
mission_engine = MissionEngine(store, mission_store, agent, multi_agent=multi_agent_engine)
experience_store = ExperienceStore(store)
memory_store = MemoryStore(store)
conversation_memory = ConversationMemoryEngine(store, memory_store)
knowledge_store = KnowledgeStore(store)
research_engine = ResearchEngine(store, knowledge_store)
research_intelligence = ResearchIntelligence(store)
learning_engine = LearningEngine(store)
skill_store = SkillStore(store.database_path, {item['name'] for item in tool_executor.registry.list()})


class CollaborationInput(BaseModel):
    objective: str = Field(min_length=1, max_length=12000)
    roles: list[str] | None = Field(default=None, max_length=4)


class SessionInput(BaseModel):
    title: str = Field(default="New conversation", max_length=120)


class MessageInput(BaseModel):
    content: str = Field(min_length=1, max_length=20000)


class MissionInput(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=10000)
    priority: int = Field(default=3, ge=1, le=5)


class MissionStatusInput(BaseModel):
    status: str


class ExperienceStatusInput(BaseModel):
    status: str = Field(pattern="^(captured|reviewed|archived)$")


class MemoryCandidateDecisionInput(BaseModel):
    decision: str


class KnowledgeDocumentInput(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=1000000)
    source_uri: str = Field(default="", max_length=1000)
    metadata: dict = Field(default_factory=dict)


class KnowledgeSearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=8, ge=1, le=30)


class SearchSettingsInput(BaseModel):
    provider: str = Field(pattern="^(offline|searxng|brave)$")
    searxng_url: str = Field(default="", max_length=1000)


class ResearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=8, ge=1, le=20)


class SkillInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=500)
    instructions: str = Field(min_length=1, max_length=12000)
    allowed_tools: list[str] = Field(default_factory=list, max_length=30)
    checklist: list[str] = Field(default_factory=lambda: ["Review instructions for accuracy and safety"], max_length=20)


class SkillUpdateInput(BaseModel):
    description: str | None = Field(default=None, max_length=500)
    instructions: str | None = Field(default=None, max_length=12000)
    allowed_tools: list[str] | None = Field(default=None, max_length=30)
    checklist: list[str] | None = Field(default=None, max_length=20)


class SkillReviewInput(BaseModel):
    decision: str


class ResearchReviewInput(BaseModel):
    decision: str
    note: str = Field(default="", max_length=1000)


class ResearchReportInput(BaseModel):
    question: str = Field(default="", max_length=2000)


class LearningGoalInput(BaseModel):
    goal: str = Field(min_length=1, max_length=1000)


class LearningAnswerInput(BaseModel):
    answer: str = Field(min_length=1, max_length=12000)


class MemoryInput(BaseModel):
    memory_type: str
    content: str = Field(min_length=1, max_length=4000)
    source_type: str = Field(default="user", min_length=1, max_length=80)
    source_ref: str = Field(default="", max_length=500)
    confidence: float = Field(default=0.8, ge=0, le=1)


@app.get("/api/status")
def status() -> dict:
    return {
        "name": "GENESIS CORE",
        "version": __version__,
        "status": "foundation",
        "interfaces": ["TUI", "Studio"],
        "agent_runtime": "planner_executor_observer",
        "available_tools": [tool["name"] for tool in tool_executor.registry.list()],
        "hardware": inspect_hardware(),
        "model_runtimes": [runtime.to_dict() for runtime in discover_runtimes()],
    }




@app.get("/api/agents/roles")
def list_agent_roles() -> dict:
    return {"roles": multi_agent_engine.roles(), "primary_model_only": True}


@app.post("/api/agents/collaborate")
def collaborate_agents(payload: CollaborationInput) -> dict:
    try:
        return multi_agent_engine.collaborate(payload.objective, payload.roles)
    except MultiAgentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ModelError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/agents/runs")
def list_agent_runs() -> dict:
    return {"runs": multi_agent_engine.list_runs()}


@app.get("/api/agents/runs/{run_id}")
def get_agent_run(run_id: str) -> dict:
    result = multi_agent_engine.get_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Agent collaboration run not found")
    return {"run": result}


@app.get("/api/sessions")
def sessions() -> dict:
    return {"sessions": store.list_sessions()}


@app.post("/api/sessions")
def create_session(payload: SessionInput) -> dict:
    return {"session": store.create_session(payload.title)}


@app.get("/api/sessions/{session_id}/messages")
def messages(session_id: str) -> dict:
    if not store.get_session(session_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"messages": store.list_messages(session_id)}


@app.post("/api/sessions/{session_id}/messages")
def add_message(session_id: str, payload: MessageInput) -> dict:
    try:
        reply = agent.chat(session_id, payload.content)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ModelError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "message": reply.user_message,
        "assistant_message": reply.assistant_message,
        "provider": reply.provider,
        "model": reply.model,
        "agent_runtime": "planner_executor_observer",
        "activity": reply.activity,
    }


@app.post("/api/sessions/{session_id}/messages/stream")
def stream_message(session_id: str, payload: MessageInput):
    if not store.get_session(session_id):
        raise HTTPException(status_code=404, detail="Conversation not found")

    events: queue.Queue = queue.Queue()

    def publish(token: str) -> None:
        events.put({"type": "delta", "content": token})

    def run_agent() -> None:
        try:
            reply = agent.chat(session_id, payload.content, on_token=publish)
            events.put({
                "type": "done",
                "message": reply.user_message,
                "assistant_message": reply.assistant_message,
                "provider": reply.provider,
                "model": reply.model,
                "agent_runtime": "planner_executor_observer",
                "activity": reply.activity,
            })
        except (ModelError, ValueError, KeyError) as exc:
            events.put({"type": "error", "detail": str(exc)})
        except Exception:
            events.put({"type": "error", "detail": "GENESIS encountered an unexpected runtime error."})
        finally:
            events.put(None)

    threading.Thread(target=run_agent, daemon=True).start()

    def event_stream():
        while True:
            event = events.get()
            if event is None:
                break
            yield "data: " + json.dumps(event, ensure_ascii=False) + "\\n\\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/missions")
def list_missions(status: str | None = None) -> dict:
    try:
        return {"missions": mission_store.list(status=status)}
    except MissionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/missions")
def create_mission(payload: MissionInput) -> dict:
    try:
        return {"mission": mission_store.create(
            payload.title, payload.description, payload.priority
        )}
    except MissionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.patch("/api/missions/{mission_id}")
def update_mission(mission_id: str, payload: MissionStatusInput) -> dict:
    try:
        return {"mission": mission_store.set_status(mission_id, payload.status)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Mission not found") from exc
    except MissionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc



@app.get("/api/missions/{mission_id}/tasks")
def list_mission_tasks(mission_id: str) -> dict:
    if not mission_store.get(mission_id):
        raise HTTPException(status_code=404, detail="Mission not found")
    return {"tasks": mission_store.list_tasks(mission_id)}


@app.post("/api/missions/{mission_id}/plan")
def plan_mission(mission_id: str) -> dict:
    try:
        return mission_engine.plan(mission_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Mission not found") from exc
    except (MissionError, MissionEngineError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ModelError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/missions/{mission_id}/run")
def run_mission_step(mission_id: str) -> dict:
    try:
        return mission_engine.run_next(mission_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Mission not found") from exc
    except (MissionError, MissionEngineError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ModelError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/missions/{mission_id}/replan")
def replan_mission(mission_id: str, payload: dict | None = None) -> dict:
    reason = ""
    if payload is not None:
        reason = str(payload.get("reason", ""))[:2000]
    try:
        return mission_engine.replan(mission_id, reason)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Mission not found") from exc
    except (MissionError, MissionEngineError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ModelError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/missions/{mission_id}/plan-history")
def mission_plan_history(mission_id: str) -> dict:
    try:
        return {"revisions": mission_engine.plan_history(mission_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Mission not found") from exc


@app.get("/api/experiences")
def list_experiences(
    status: str | None = None,
    outcome: str | None = None,
    limit: int = 50,
) -> dict:
    try:
        items = experience_store.list(status=status, outcome=outcome, limit=limit)
        return {"experiences": items, "count": len(items)}
    except ExperienceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/experiences/{experience_id}")
def get_experience(experience_id: str) -> dict:
    item = experience_store.get(experience_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Experience not found")
    return {"experience": item}


@app.patch("/api/experiences/{experience_id}")
def update_experience_status(
    experience_id: str,
    payload: ExperienceStatusInput,
) -> dict:
    try:
        return {"experience": experience_store.set_status(experience_id, payload.status)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Experience not found") from exc
    except ExperienceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/memories/from-mission/{mission_id}")
def capture_mission_memory(mission_id: str) -> dict:
    try:
        return {"memory": memory_store.capture_completed_mission(mission_store, mission_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Mission not found") from exc
    except MemoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/sessions/{session_id}/memory-extract")
def extract_conversation_memories(session_id: str) -> dict:
    try:
        return {"candidates": conversation_memory.extract(session_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    except ConversationMemoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ModelError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/memory-candidates")
def list_memory_candidates(session_id: str | None = None, status: str = "pending") -> dict:
    try:
        return {"candidates": conversation_memory.list_candidates(session_id, status)}
    except ConversationMemoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/memory-candidates/{candidate_id}")
def review_memory_candidate(candidate_id: str, payload: MemoryCandidateDecisionInput) -> dict:
    try:
        return {"candidate": conversation_memory.decide(candidate_id, payload.decision)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Memory candidate not found") from exc
    except ConversationMemoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/learning/courses")
def list_learning_courses() -> dict:
    return {"courses": learning_engine.list_courses()}


@app.post("/api/learning/courses")
def create_learning_course(payload: LearningGoalInput) -> dict:
    try:
        return {"course": learning_engine.create_course(payload.goal)}
    except LearningError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ModelError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/learning/courses/{course_id}")
def get_learning_course(course_id: str) -> dict:
    try:
        return {"course": learning_engine.get_course(course_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Learning course not found") from exc


@app.post("/api/learning/lessons/{lesson_id}/answer")
def submit_learning_answer(lesson_id: str, payload: LearningAnswerInput) -> dict:
    try:
        return {"assessment": learning_engine.submit_answer(lesson_id, payload.answer)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Learning lesson not found") from exc
    except LearningError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/learning/lessons/{lesson_id}/attempts")
def list_learning_attempts(lesson_id: str) -> dict:
    try:
        return {"attempts": learning_engine.attempts(lesson_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Learning lesson not found") from exc


@app.get("/api/skills")
def list_skills(status: str | None = None) -> dict:
    try:
        return {"skills": skill_store.list(status)}
    except SkillError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/skills")
def create_skill(payload: SkillInput) -> dict:
    try:
        return {"skill": skill_store.create(
            payload.name, payload.description, payload.instructions,
            payload.allowed_tools, payload.checklist,
        )}
    except SkillError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/skills/{skill_id}")
def get_skill(skill_id: str) -> dict:
    item = skill_store.get(skill_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"skill": item}


@app.put("/api/skills/{skill_id}")
def update_skill(skill_id: str, payload: SkillUpdateInput) -> dict:
    try:
        return {"skill": skill_store.update(
            skill_id, description=payload.description, instructions=payload.instructions,
            allowed_tools=payload.allowed_tools, checklist=payload.checklist,
        )}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Skill not found") from exc
    except SkillError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/skills/{skill_id}/submit")
def submit_skill(skill_id: str) -> dict:
    try:
        return {"skill": skill_store.submit(skill_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Skill not found") from exc
    except SkillError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/skills/{skill_id}/review")
def review_skill(skill_id: str, payload: SkillReviewInput) -> dict:
    try:
        return {"skill": skill_store.review(skill_id, payload.decision)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Skill not found") from exc
    except SkillError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/skills/{skill_id}/disable")
def disable_skill(skill_id: str) -> dict:
    try:
        return {"skill": skill_store.disable(skill_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Skill not found") from exc
    except SkillError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/skills/{skill_id}/versions")
def list_skill_versions(skill_id: str) -> dict:
    try:
        return {"versions": skill_store.versions(skill_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Skill not found") from exc


@app.get("/api/skills/{skill_id}/export")
def export_skill(skill_id: str) -> dict:
    try:
        return {"manifest": skill_store.export_manifest(skill_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Skill not found") from exc


@app.post("/api/skills/import")
def import_skill(payload: dict) -> dict:
    try:
        return {"skill": skill_store.import_manifest(payload)}
    except SkillError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/research/config")
def get_research_config() -> dict:
    settings = get_search_settings()
    return {"settings": settings}


@app.put("/api/research/config")
def update_research_config(payload: SearchSettingsInput) -> dict:
    try:
        set_search_settings(payload.provider, payload.searxng_url)
        return {"settings": get_search_settings()}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/research/search")
def search_research(payload: ResearchInput) -> dict:
    try:
        return {"research": research_engine.search(payload.query, payload.limit)}
    except ResearchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/research/runs")
def list_research_runs() -> dict:
    return {"runs": research_engine.store.list_runs()}


@app.post("/api/research/runs/{run_id}/report")
def generate_research_report(run_id: str, payload: ResearchReportInput) -> dict:
    try:
        return {"report": research_intelligence.generate(run_id, payload.question)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Research run not found") from exc
    except ResearchIntelligenceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ModelError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/research/reports")
def list_research_reports(run_id: str | None = None) -> dict:
    return {"reports": research_intelligence.list(run_id)}


@app.get("/api/research/reports/{report_id}")
def get_research_report(report_id: str) -> dict:
    try:
        return {"report": research_intelligence.get(report_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Research report not found") from exc


@app.get("/api/research/sources")
def list_research_sources(run_id: str | None = None, review_status: str | None = None) -> dict:
    try:
        return {"sources": research_engine.list_sources(run_id, review_status)}
    except ResearchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/research/sources/{source_id}/fetch")
def fetch_research_source_page(source_id: str) -> dict:
    try:
        return {"page": research_engine.fetch_source_page(source_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Research source not found") from exc
    except ResearchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/research/sources/{source_id}/page")
def get_research_source_page(source_id: str) -> dict:
    try:
        return {"page": research_engine.get_source_page(source_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Research source not found") from exc


@app.post("/api/research/sources/{source_id}/review")
def review_research_source(source_id: str, payload: ResearchReviewInput) -> dict:
    try:
        return {"source": research_engine.review_source(source_id, payload.decision, payload.note)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Research source not found") from exc
    except ResearchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/knowledge/documents")
def list_knowledge_documents() -> dict:
    return {"documents": knowledge_store.list_documents()}


@app.post("/api/knowledge/documents")
def add_knowledge_document(payload: KnowledgeDocumentInput) -> dict:
    try:
        return {"document": knowledge_store.ingest_text(
            payload.title, payload.content, payload.source_uri, payload.metadata
        )}
    except KnowledgeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/knowledge/documents/{document_id}")
def delete_knowledge_document(document_id: str) -> dict:
    try:
        knowledge_store.delete_document(document_id)
        return {"deleted": document_id}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Knowledge document not found") from exc


@app.post("/api/knowledge/search")
def search_knowledge(payload: KnowledgeSearchInput) -> dict:
    try:
        return {"results": knowledge_store.search(payload.query, payload.limit)}
    except KnowledgeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/memories")
def list_memories(memory_type: str | None = None, status: str = "active") -> dict:
    try:
        return {"memories": memory_store.list(memory_type=memory_type, status=status)}
    except MemoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/memories/search")
def search_memories(q: str) -> dict:
    return {"memories": memory_store.search(q)}


@app.post("/api/memories")
def create_memory(payload: MemoryInput) -> dict:
    try:
        return {"memory": memory_store.add(
            payload.memory_type, payload.content, payload.source_type,
            payload.source_ref, payload.confidence,
        )}
    except MemoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.patch("/api/memories/{memory_id}")
def update_memory(memory_id: str, payload: MissionStatusInput) -> dict:
    try:
        return {"memory": memory_store.set_status(memory_id, payload.status)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Memory not found") from exc
    except MemoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/memories/{memory_id}")
def delete_memory(memory_id: str) -> dict:
    try:
        memory_store.delete(memory_id)
        return {"deleted": memory_id}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Memory not found") from exc


@app.get("/api/approvals")
def list_approvals() -> dict:
    return {"approvals": approval_store.list()}


class ApprovalDecisionInput(BaseModel):
    decision: str


@app.post("/api/approvals/{approval_id}")
def decide_approval(approval_id: str, payload: ApprovalDecisionInput) -> dict:
    if payload.decision not in {"approve", "reject"}:
        raise HTTPException(status_code=422, detail="Decision must be approve or reject")
    try:
        item = approval_store.decide(approval_id, approved=payload.decision == "approve")
        return {"approval": item}
    except ToolError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/", response_class=HTMLResponse)
def studio() -> str:
    return HTML
  

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>GENESIS Studio</title>
<style>
:root{color-scheme:dark;--bg:#080b12;--panel:#0e1420;--panel2:#121b2a;--line:#202c40;--text:#e8eef9;--muted:#8190a8;--mint:#72e0bd;--blue:#8aaeff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px Inter,ui-sans-serif,system-ui,sans-serif;height:100vh;overflow:hidden}
button,input{font:inherit}button{cursor:pointer;color:inherit}.app{height:100vh;display:grid;grid-template-columns:245px minmax(360px,1fr) 290px;grid-template-rows:58px 1fr}
.top{grid-column:1/4;display:flex;align-items:center;justify-content:space-between;padding:0 20px;border-bottom:1px solid var(--line);background:#0b101a}
.brand{display:flex;align-items:center;gap:12px;font-weight:750;letter-spacing:.13em}.mark{width:28px;height:28px;border:1px solid #397e6d;border-radius:9px;display:grid;place-items:center;color:var(--mint);font-weight:900}
.topmeta{display:flex;align-items:center;gap:16px;color:var(--muted);font-size:12px}.pill{border:1px solid #285d50;color:var(--mint);padding:6px 10px;border-radius:99px}
.left,.right{background:var(--panel);min-height:0;padding:18px 14px;overflow:auto}.left{border-right:1px solid var(--line)}.right{border-left:1px solid var(--line)}
.section{font-size:10px;letter-spacing:.16em;color:#71819b;font-weight:700;margin:10px 8px 12px}.new{width:100%;padding:11px;border-radius:9px;border:1px solid #315c57;background:#10251f;color:var(--mint);text-align:left;margin-bottom:18px}
.session{width:100%;border:0;background:transparent;color:#aab7ca;text-align:left;padding:10px;border-radius:8px;margin:2px 0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.session.active,.session:hover{background:#182436;color:#fff}
.center{display:flex;flex-direction:column;min-height:0;background:radial-gradient(ellipse at 50% 0%,#101b2a 0%,#0a0f18 58%)}
.centerhead{height:60px;flex-shrink:0;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 22px}.centerhead strong{font-size:13px}.sub{color:var(--muted);font-size:11px;margin-top:4px}
.messages{flex:1;overflow:auto;padding:28px max(22px,calc((100% - 760px)/2));display:flex;flex-direction:column;gap:16px}
.welcome{margin:auto;text-align:center;max-width:520px}.orb{width:62px;height:62px;border:1px solid #367968;border-radius:20px;margin:0 auto 22px;display:grid;place-items:center;color:var(--mint);font-size:26px;box-shadow:0 0 50px #285c4c33}
.welcome h1{font-size:28px;letter-spacing:.03em;margin:0 0 10px}.welcome p{color:var(--muted);line-height:1.7}
.msg{max-width:82%;padding:13px 15px;border:1px solid var(--line);background:#101827;border-radius:12px;line-height:1.6;white-space:pre-wrap}.msg.user{align-self:flex-end;background:#13251f;border-color:#285b4c}.role{font-size:10px;letter-spacing:.12em;color:var(--mint);margin-bottom:6px}
.composer{padding:16px max(22px,calc((100% - 760px)/2)) 22px;border-top:1px solid var(--line)}.inputbox{display:flex;gap:10px;background:#101827;border:1px solid #2a3850;border-radius:12px;padding:9px}.inputbox input{flex:1;min-width:0;background:transparent;border:0;outline:0;color:var(--text);padding:8px}.send{background:#1b5b4b;color:#d9fff3;border:0;border-radius:8px;padding:0 17px}.hint{color:#65748c;font-size:10px;margin:9px 4px 0}
.card{background:#111a28;border:1px solid var(--line);border-radius:10px;padding:13px;margin-bottom:10px}.card h3{font-size:11px;letter-spacing:.1em;margin:0 0 12px;color:#a9b7cc}.kv{display:flex;justify-content:space-between;gap:8px;font-size:11px;margin:9px 0;color:var(--muted)}.kv b{color:#dce7f8;font-weight:500;text-align:right}.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#67748a;margin-right:6px}.dot.ok{background:var(--mint)}.notice{color:#aab6c9;font-size:11px;line-height:1.6}.mission-row{border-top:1px solid var(--line);padding:9px 0;font-size:11px}.mission-row strong{display:block;color:#dce7f8;font-weight:550;margin-bottom:4px}.mission-row span{color:var(--muted)}.mission-create{display:flex;gap:6px;margin-top:10px}.mission-create input{width:100%;min-width:0;background:#0b111c;border:1px solid var(--line);border-radius:7px;padding:8px;color:var(--text)}.mission-create button{border:0;border-radius:7px;background:#1b5b4b;padding:0 10px;color:#eafff8}.mission-actions{display:flex;gap:6px;margin-top:7px}.mission-actions button{border:1px solid var(--line);background:#172334;color:#c9d7eb;border-radius:6px;padding:5px 8px;font-size:10px}.mission-actions button.primary{background:#174b3e;border-color:#286b58;color:#cffff0}.experience-item{width:100%;display:block;text-align:left;border:1px solid var(--line);background:#0d1522;border-radius:8px;padding:9px;margin:7px 0;color:var(--text)}.experience-item:hover{border-color:#397e6d}.experience-item strong{display:block;font-size:11px;margin-bottom:5px}.experience-item span{font-size:10px;color:var(--muted)}.experience-detail{margin-top:10px;padding:10px;border:1px solid var(--line);border-radius:8px;background:#0b111c}.experience-detail pre{white-space:pre-wrap;overflow-wrap:anywhere;font:11px/1.6 inherit;color:#c5d2e5;max-height:220px;overflow:auto}.experience-filters{display:grid;grid-template-columns:1fr 1fr;gap:6px}.panel-toggle{display:none;border:1px solid var(--line);background:#152234;border-radius:7px;padding:6px 9px;color:var(--text)}.right input,.right select,.right textarea{width:100%;min-width:0;background:#0b111c;border:1px solid var(--line);border-radius:7px;padding:8px;color:var(--text);margin:4px 0}.right textarea{min-height:105px;resize:vertical;line-height:1.5}
@media(max-width:950px){.app{grid-template-columns:210px 1fr}.top{grid-column:1/3}.panel-toggle{display:inline-block}.right{display:none}.right.mobile-open{display:block;position:fixed;z-index:30;top:58px;right:0;bottom:0;width:min(420px,92vw);box-shadow:-18px 0 45px #0009}}
@media(max-width:620px){.app{grid-template-columns:1fr}.top{grid-column:1}.left{display:none}.topmeta .pill{display:none}.centerhead{padding:0 14px}.messages{padding:18px 14px}.composer{padding:12px 14px}.right.mobile-open{width:100%;left:0;right:0}}
</style>
</head>
<body><div class="app">
<header class="top"><div class="brand"><span class="mark">G</span> GENESIS <span style="color:#62738d;font-weight:500">STUDIO</span></div><div class="topmeta"><span id="model-count">Checking runtimes…</span><button class="panel-toggle" id="toggle-panels" aria-expanded="false">Panels ☰</button><span class="pill">LOCAL WORKSPACE</span><span>v<span id="version">…</span></span></div></header>
<aside class="left"><div class="section">WORKSPACE</div><button class="new" id="new-session">＋ &nbsp; New conversation</button><div class="section">CONVERSATIONS</div><div id="sessions"></div><div class="section" style="margin-top:26px">SYSTEM</div><button class="session" id="refresh">↻ &nbsp; Refresh status</button></aside>
<main class="center"><div class="centerhead"><div><strong id="active-title">New conversation</strong><div class="sub" id="active-sub">Shared GENESIS session</div></div><span class="pill">ENGINE FOUNDATION</span></div>
<div class="messages" id="messages"><div class="welcome" id="welcome"><div class="orb">✧</div><h1>GENESIS CORE</h1><p>Your workspace for research, reasoning, tools and evolving skills.<br>Create a conversation to begin building your project context.</p></div></div>
<div class="composer"><div class="inputbox"><input id="message-input" placeholder="Write a message to GENESIS…" autocomplete="off"><button class="send" id="send">Send ↗</button></div><div class="hint">Messages are shared with GENESIS TUI. Connect a supported model runtime to receive AI responses.</div></div></main>
<aside class="right"><div class="section">SYSTEM OVERVIEW</div><div class="card"><h3>AGENT ENGINE</h3><div class="kv"><span>Status</span><b>Foundation only</b></div><div class="kv"><span>Inference</span><b>Agent runtime active</b></div><div class="kv"><span>Sessions</span><b id="session-count">0</b></div></div><div class="card"><h3>MODEL RUNTIMES</h3><div id="runtimes" class="notice">Loading…</div></div><div class="card"><h3>MISSION CONTROL</h3><div id="missions" class="notice">Loading missions…</div><div class="mission-create"><input id="mission-title" placeholder="New mission title"><button id="create-mission">＋</button></div></div><div class="card"><h3>EXPERIENCE ENGINE</h3><p class="notice">Observed mission attempts, preserved as evidence. Review status does not turn an experience into a verified fact.</p><div class="experience-filters"><select id="experience-status"><option value="">All review states</option><option value="captured">Captured</option><option value="reviewed">Reviewed</option><option value="archived">Archived</option></select><select id="experience-outcome"><option value="">All outcomes</option><option value="completed">Completed</option><option value="blocked">Blocked</option><option value="failed">Failed</option></select></div><div class="kv"><span>Loaded experiences</span><b id="experience-count">0</b></div><div id="experiences-list" class="notice">Loading experiences…</div><div id="experience-detail" class="experience-detail notice">Select an experience to inspect its evidence.</div><button id="experience-refresh">↻ Refresh experiences</button></div><div class="card"><h3>CONVERSATION MEMORY REVIEW</h3><p class="notice">Extract suggestions from user messages in the open conversation. Nothing is saved until you accept it.</p><button id="extract-memories" class="primary">Analyze open conversation</button><div id="memory-candidates" class="notice">No proposals loaded.</div></div><div class="card"><h3>SKILLS ENGINE</h3><p class="notice">Create declarative skills, then submit them for review. Only approved skills influence GENESIS.</p><input id="skill-name" placeholder="Skill name"><input id="skill-description" placeholder="Short description"><textarea id="skill-instructions" placeholder="Instructions for GENESIS"></textarea><input id="skill-tools" placeholder="Allowed tool names (comma-separated)"><button id="skill-create" class="primary">Create draft skill</button><div id="skills-list" class="notice">Loading skills…</div></div><div class="card"><h3>LEARNING &amp; EVALUATION</h3><p class="notice">Create a learning path with the primary model, answer short exercises and track measured progress.</p><input id="learning-goal" placeholder="What do you want to learn?"><button id="learning-create" class="primary">Generate curriculum</button><div id="learning-courses" class="notice">Loading learning courses…</div><div id="learning-course-detail" class="notice">Choose or create a course.</div><textarea id="learning-answer" placeholder="Write your answer to the selected lesson"></textarea><button id="learning-submit" disabled>Submit answer</button><div id="learning-feedback" class="notice">Assessment feedback will appear here.</div></div><div class="card"><h3>SEARCH PROVIDER</h3><p class="notice">Use your own SearXNG instance or keep research fully offline.</p><select id="search-provider"><option value="offline">Offline · local knowledge</option><option value="searxng">Self-hosted SearXNG</option><option value="brave">Brave Search</option></select><input id="searxng-url" placeholder="http://127.0.0.1:8080"><button id="search-config-save" class="primary">Save search settings</button><div id="search-config-status" class="notice">Loading search settings…</div></div><div class="card"><h3>RESEARCH ENGINE</h3><input id="research-query" placeholder="What should GENESIS investigate?"><button id="research-search" class="primary">Search sources</button><input id="research-focus" placeholder="Optional focus for the synthesis"><button id="research-report-generate" disabled>Generate cited report</button><div id="research-report" class="notice">Approve at least one source, then generate a report.</div><div id="research-notice" class="notice">External search is optional. Without a provider, GENESIS searches the local Knowledge Base.</div><select id="research-filter"><option value="pending">Pending review</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="">All sources</option></select><div id="research-sources" class="notice">No research sources loaded.</div></div><div class="card"><h3>KNOWLEDGE BASE</h3><input id="knowledge-title" placeholder="Document title"><input id="knowledge-source" placeholder="Source / file reference (optional)"><textarea id="knowledge-content" placeholder="Paste document text or Markdown here"></textarea><button id="knowledge-add" class="primary">Index document</button><input id="knowledge-query" placeholder="Search indexed knowledge"><button id="knowledge-search">Search knowledge</button><div id="knowledge-results" class="notice">No search performed.</div><div id="knowledge-documents" class="notice">Loading documents…</div></div><div class="card"><h3>LONG-TERM MEMORY</h3><select id="memory-type"><option value="semantic">Semantic fact</option><option value="episodic">Episode</option><option value="procedural">Procedure</option></select><input id="memory-content" placeholder="Add a verified memory"><input id="memory-source" placeholder="Source / reference (optional)"><button id="save-memory" class="primary">Save memory</button><div id="memories" class="notice">Loading memories…</div></div><div class="card"><h3>DESIGN PRINCIPLE</h3><p class="notice">Ollama, llama.cpp, LM Studio and remote APIs are interchangeable backends. GENESIS owns the interface, memory, tools, permissions and agent workflow.</p></div></aside>
</div>
<script>
let activeId=null;
let activeResearchRunId=null;
let activeLearningLessonId=null;
let activeExperienceId=null;
const $=id=>document.getElementById(id);
async function api(path,options={}){const response=await fetch(path,{headers:{'Content-Type':'application/json'},...options});if(!response.ok)throw new Error((await response.json()).detail||'Request failed');return response.json()}
function addMessage(m){const box=document.createElement('div');box.className='msg '+(m.role==='user'?'user':'');const role=document.createElement('div');role.className='role';role.textContent=m.role.toUpperCase();const body=document.createElement('div');body.textContent=m.content;box.append(role,body);$('messages').append(box);return box}
async function loadSessions(){const data=await api('/api/sessions');$('sessions').replaceChildren();$('session-count').textContent=data.sessions.length;for(const s of data.sessions){const b=document.createElement('button');b.className='session'+(s.id===activeId?' active':'');b.textContent=s.title;b.onclick=()=>openSession(s.id);$('sessions').append(b)}}
async function openSession(id){activeId=id;const data=await api('/api/sessions/'+id+'/messages');$('messages').replaceChildren();for(const m of data.messages)addMessage(m);if(!data.messages.length){const p=document.createElement('p');p.className='notice';p.textContent='This conversation is ready. Send a message to save it.';$('messages').append(p)}const list=await api('/api/sessions');const s=list.sessions.find(x=>x.id===id);$('active-title').textContent=s?.title||'Conversation';$('active-sub').textContent='Session '+id+' · shared with GENESIS TUI';await loadSessions()}
async function newSession(){const data=await api('/api/sessions',{method:'POST',body:JSON.stringify({title:'New conversation'})});await openSession(data.session.id)}
async function sendMessage(){const input=$('message-input'),button=$('send');const content=input.value.trim();if(!content||button.disabled)return;if(!activeId)await newSession();input.value='';button.disabled=true;button.textContent='Working…';const welcome=$('welcome');if(welcome)welcome.remove();const userBubble=addMessage({role:'user',content});const pending=addMessage({role:'assistant',content:'GENESIS is working…'});$('messages').scrollTop=$('messages').scrollHeight;try{const response=await fetch('/api/sessions/'+activeId+'/messages/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content})});if(!response.ok){const error=await response.json().catch(()=>({}));throw new Error(error.detail||'HTTP '+response.status)}if(!response.body)throw new Error('This browser does not support streamed responses.');const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',completed=null;while(true){const part=await reader.read();buffer+=decoder.decode(part.value||new Uint8Array(),{stream:!part.done});let boundary;while((boundary=buffer.indexOf('\n\n'))>=0){const frame=buffer.slice(0,boundary);buffer=buffer.slice(boundary+2);const line=frame.split('\n').find(x=>x.startsWith('data:'));if(!line)continue;const event=JSON.parse(line.slice(5).trim());if(event.type==='delta'){const body=pending.querySelector('div:last-child');body.textContent+=event.content;$('messages').scrollTop=$('messages').scrollHeight}else if(event.type==='done'){completed=event;pending.querySelector('div:last-child').textContent=event.assistant_message?.content||pending.querySelector('div:last-child').textContent}else if(event.type==='error'){throw new Error(event.detail)}}if(part.done)break}if(!completed)throw new Error('The stream ended before GENESIS returned a final response.');const note=document.createElement('div');note.className='hint';note.textContent='Answered by '+completed.provider+' · '+completed.model;$('messages').append(note);await loadSessions();const s=(await api('/api/sessions')).sessions.find(x=>x.id===activeId);$('active-title').textContent=s?.title||'Conversation'}catch(e){pending.querySelector('div:last-child').textContent='Request failed: '+e.message;throw e}finally{button.disabled=false;button.textContent='Send ↗';$('messages').scrollTop=$('messages').scrollHeight}}
function experienceField(label,value){const line=document.createElement('p');line.className='notice';const strong=document.createElement('strong');strong.textContent=label+': ';line.append(strong,document.createTextNode(value||'—'));return line}
async function showExperience(id){activeExperienceId=id;const data=await api('/api/experiences/'+encodeURIComponent(id));const item=data.experience;const box=$('experience-detail');box.replaceChildren();const heading=document.createElement('strong');heading.textContent=item.title;box.append(heading,experienceField('Outcome',item.outcome),experienceField('Review state',item.status),experienceField('Mission',item.mission_id),experienceField('Task',item.task_id),experienceField('Objective',item.objective),experienceField('Instructions',item.instructions),experienceField('Observer summary',item.observer_summary),experienceField('Confidence (uncalibrated)',String(item.confidence)),experienceField('Captured',new Date(item.created_at).toLocaleString()));const result=document.createElement('pre');result.textContent=item.result;box.append(experienceField('Recorded result',''),result);const actions=document.createElement('div');actions.className='mission-actions';if(item.status==='captured'){const review=document.createElement('button');review.className='primary';review.textContent='Mark reviewed';review.onclick=()=>setExperienceStatus(id,'reviewed');actions.append(review)}if(item.status!=='archived'){const archive=document.createElement('button');archive.textContent='Archive';archive.onclick=()=>setExperienceStatus(id,'archived');actions.append(archive)}if(actions.childNodes.length)box.append(actions)}
async function setExperienceStatus(id,status){try{await api('/api/experiences/'+encodeURIComponent(id),{method:'PATCH',body:JSON.stringify({status})});await loadExperiences();await showExperience(id)}catch(e){alert(e.message)}}
async function loadExperiences(){const status=$('experience-status').value,outcome=$('experience-outcome').value;const params=new URLSearchParams();if(status)params.set('status',status);if(outcome)params.set('outcome',outcome);params.set('limit','100');const data=await api('/api/experiences?'+params.toString());const box=$('experiences-list');box.replaceChildren();$('experience-count').textContent=String(data.count);if(!data.experiences.length){box.textContent='No experiences match these filters yet. Run a mission to capture its first task result.';$('experience-detail').textContent='No experience selected.';return}for(const item of data.experiences){const button=document.createElement('button');button.className='experience-item';const title=document.createElement('strong');title.textContent=item.title;const meta=document.createElement('span');meta.textContent=item.outcome.toUpperCase()+' · '+item.status+' · '+new Date(item.created_at).toLocaleString();button.append(title,meta);button.onclick=()=>showExperience(item.id).catch(e=>alert(e.message));box.append(button)}if(activeExperienceId&&data.experiences.some(item=>item.id===activeExperienceId)){await showExperience(activeExperienceId)}else{await showExperience(data.experiences[0].id)}}
async function loadLearningCourses(){const data=await api('/api/learning/courses');const box=$('learning-courses');box.replaceChildren();if(!data.courses.length){box.textContent='No learning courses yet.';return}for(const course of data.courses){const button=document.createElement('button');button.textContent=course.title+' · '+course.completed_lessons+' completed · '+course.xp+' XP';button.onclick=()=>showLearningCourse(course.id);box.append(button)}}
async function showLearningCourse(id){const data=await api('/api/learning/courses/'+id);const course=data.course;const box=$('learning-course-detail');box.replaceChildren();const heading=document.createElement('strong');heading.textContent=course.title+' · '+course.progress_percent+'% · '+course.xp+' XP';const goal=document.createElement('p');goal.textContent=course.goal;box.append(heading,goal);for(const lesson of course.lessons){const button=document.createElement('button');button.textContent=lesson.position+'. '+lesson.title+' · '+(lesson.completed?'Completed':'Best '+lesson.best_score+'%');button.onclick=()=>{activeLearningLessonId=lesson.id;$('learning-answer').value='';$('learning-submit').disabled=false;$('learning-feedback').textContent=lesson.prompt+(lesson.hints.length?'\nHints: '+lesson.hints.join(' · '):'')};box.append(button)}}
async function createLearningCourse(){const goal=$('learning-goal').value.trim();if(!goal)return;try{const data=await api('/api/learning/courses',{method:'POST',body:JSON.stringify({goal})});$('learning-goal').value='';await loadLearningCourses();await showLearningCourse(data.course.id)}catch(e){alert(e.message)}}
async function submitLearningAnswer(){if(!activeLearningLessonId)return;const answer=$('learning-answer').value.trim();if(!answer)return;try{const data=await api('/api/learning/lessons/'+activeLearningLessonId+'/answer',{method:'POST',body:JSON.stringify({answer})});const a=data.assessment;$('learning-feedback').textContent='Score: '+a.score+'% · best: '+a.best_score+'% · +'+a.xp_awarded+' XP\nMatched: '+a.matched_concepts.join(', ')+'\nTo cover: '+a.missing_concepts.join(', ')+'\n'+a.evaluation_note;await loadLearningCourses();await showLearningCourse(a.course_id) }catch(e){alert(e.message)}}
async function loadSkills(){const data=await api('/api/skills');const box=$('skills-list');box.replaceChildren();if(!data.skills.length){box.textContent='No skills yet.';return}for(const skill of data.skills){const row=document.createElement('div');row.className='mission-row';const body=document.createElement('div');const title=document.createElement('strong');title.textContent='['+skill.status+'] '+skill.name+' · v'+skill.version;const desc=document.createElement('p');desc.textContent=skill.description;const checks=document.createElement('p');checks.textContent='Review checklist: '+skill.checklist.join(' · ');body.append(title,desc,checks);row.append(body);const actions=document.createElement('div');actions.className='mission-actions';if(skill.status==='draft'||skill.status==='disabled'){const submit=document.createElement('button');submit.textContent='Submit';submit.onclick=async()=>{await api('/api/skills/'+skill.id+'/submit',{method:'POST'});await loadSkills()};actions.append(submit)}if(skill.status==='pending'){for(const [label,decision] of [['Approve','approve'],['Reject','reject']]){const button=document.createElement('button');button.textContent=label;button.onclick=async()=>{await api('/api/skills/'+skill.id+'/review',{method:'POST',body:JSON.stringify({decision})});await loadSkills()};actions.append(button)}}if(skill.status==='active'){const disable=document.createElement('button');disable.textContent='Disable';disable.onclick=async()=>{await api('/api/skills/'+skill.id+'/disable',{method:'POST'});await loadSkills()};actions.append(disable)}row.append(actions);box.append(row)}}
async function createSkill(){const name=$('skill-name').value.trim(),description=$('skill-description').value.trim(),instructions=$('skill-instructions').value.trim();if(!name||!description||!instructions)return;const allowed_tools=$('skill-tools').value.split(',').map(x=>x.trim()).filter(Boolean);try{await api('/api/skills',{method:'POST',body:JSON.stringify({name,description,instructions,allowed_tools,checklist:['Review instructions for accuracy and safety','Confirm declared tools are appropriate']})});$('skill-name').value='';$('skill-description').value='';$('skill-instructions').value='';$('skill-tools').value='';await loadSkills()}catch(e){alert(e.message)}}
async function loadResearchSources(){const status=$('research-filter').value;const data=await api('/api/research/sources'+(status?'?review_status='+encodeURIComponent(status):''));renderResearchSources(data.sources)}
function renderResearchSources(sources){const box=$('research-sources');box.replaceChildren();if(!sources.length){box.textContent='No sources in this review filter.';return}for(const source of sources){const row=document.createElement('div');row.className='mission-row';const body=document.createElement('div');const title=document.createElement('strong');title.textContent='['+source.review_status+'] '+source.title;const snippet=document.createElement('p');snippet.textContent=source.snippet;const link=document.createElement('a');link.href=source.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent=source.url;body.append(title,snippet,link);const fetchButton=document.createElement('button');fetchButton.textContent=source.page_fetched_at?'Refresh page text':'Read page';fetchButton.onclick=async()=>{try{fetchButton.disabled=true;const result=await api('/api/research/sources/'+source.id+'/fetch',{method:'POST'});const page=document.createElement('pre');page.className='notice';page.style.whiteSpace='pre-wrap';page.textContent=result.page.text+'\n\n'+result.page.notice;body.append(page)}catch(e){alert(e.message)}finally{fetchButton.disabled=false}};body.append(fetchButton);row.append(body);if(source.review_status==='pending'){const actions=document.createElement('div');actions.className='mission-actions';for(const [label,decision] of [['Approve','approved'],['Reject','rejected']]){const button=document.createElement('button');button.textContent=label;button.onclick=async()=>{try{await api('/api/research/sources/'+source.id+'/review',{method:'POST',body:JSON.stringify({decision})});await loadResearchSources()}catch(e){alert(e.message)}};actions.append(button)}row.append(actions)}box.append(row)}}
async function loadSearchConfig(){const data=await api('/api/research/config');$('search-provider').value=data.settings.provider;$('searxng-url').value=data.settings.searxng_url||'';$('search-config-status').textContent='Active provider: '+data.settings.provider}
async function saveSearchConfig(){try{const settings={provider:$('search-provider').value,searxng_url:$('searxng-url').value.trim()};const data=await api('/api/research/config',{method:'PUT',body:JSON.stringify(settings)});$('search-config-status').textContent='Saved: '+data.settings.provider+' · new research runs will use this provider.'}catch(e){$('search-config-status').textContent='Could not save: '+e.message}}
async function searchResearch(){const query=$('research-query').value.trim();if(!query)return;try{const data=await api('/api/research/search',{method:'POST',body:JSON.stringify({query,limit:8})});const result=data.research;activeResearchRunId=result.id;$('research-report-generate').disabled=false;$('research-report').textContent='Run '+result.id+' created. Approve sources below, then generate the synthesis.';$('research-notice').textContent='Research '+result.id+' · '+result.mode+' · '+result.source_count+' source(s). '+result.notice;renderResearchSources(result.sources);$('research-filter').value='pending'}catch(e){alert(e.message)}}
async function generateResearchReport(){if(!activeResearchRunId)return;const button=$('research-report-generate');button.disabled=true;try{const data=await api('/api/research/runs/'+activeResearchRunId+'/report',{method:'POST',body:JSON.stringify({question:$('research-focus').value})});const report=data.report;const box=$('research-report');box.replaceChildren();const title=document.createElement('strong');title.textContent=report.title+' · '+report.provider+'/'+report.model;const summary=document.createElement('p');summary.textContent=report.summary;box.append(title,summary);for(const claim of report.claims){const row=document.createElement('p');row.textContent='['+claim.classification+'] '+claim.text+(claim.source_ids.length?' · Sources: '+claim.source_ids.join(', '):'');box.append(row)}if(report.disagreements.length){const h=document.createElement('strong');h.textContent='Disagreements';box.append(h);for(const item of report.disagreements){const p=document.createElement('p');p.textContent='• '+item;box.append(p)}}if(report.open_questions.length){const h=document.createElement('strong');h.textContent='Open questions';box.append(h);for(const item of report.open_questions){const p=document.createElement('p');p.textContent='• '+item;box.append(p)}}const notice=document.createElement('p');notice.className='notice';notice.textContent=report.notice;box.append(notice);for(const source of report.sources){const link=document.createElement('a');link.href=source.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent=source.id+' · '+source.title+' ('+source.content_kind+')';box.append(link,document.createElement('br'))}}catch(e){alert(e.message)}finally{button.disabled=false}}

async function loadKnowledgeDocuments(){const data=await api('/api/knowledge/documents');const box=$('knowledge-documents');box.replaceChildren();if(!data.documents.length){box.textContent='No indexed documents.';return}for(const d of data.documents){const row=document.createElement('div');row.className='mission-row';const body=document.createElement('div');body.textContent=d.title+' · '+d.chunk_count+' chunks'+(d.source_uri?' · '+d.source_uri:'');const del=document.createElement('button');del.textContent='Remove';del.onclick=async()=>{if(confirm('Remove this document from the knowledge base?')){await api('/api/knowledge/documents/'+d.id,{method:'DELETE'});await loadKnowledgeDocuments()}};row.append(body,del);box.append(row)}}
async function addKnowledgeDocument(){const title=$('knowledge-title').value.trim(),content=$('knowledge-content').value.trim();if(!title||!content)return;const data=await api('/api/knowledge/documents',{method:'POST',body:JSON.stringify({title,content,source_uri:$('knowledge-source').value})});alert('Indexed '+data.document.chunk_count+' chunk(s).'+(data.document.duplicate?' This content was already indexed.':''));$('knowledge-content').value='';await loadKnowledgeDocuments()}
async function searchKnowledge(){const query=$('knowledge-query').value.trim();if(!query)return;const data=await api('/api/knowledge/search',{method:'POST',body:JSON.stringify({query,limit:8})});const box=$('knowledge-results');box.replaceChildren();if(!data.results.length){box.textContent='No matching knowledge found.';return}for(const result of data.results){const row=document.createElement('div');row.className='mission-row';const body=document.createElement('div');body.textContent=result.excerpt+'\\nSource: '+result.citation.title+' · chunk '+result.citation.chunk+' · '+result.citation.source;row.append(body);box.append(row)}}
async function extractConversationMemories(){if(!activeId){alert('Open a conversation first.');return}try{const data=await api('/api/sessions/'+activeId+'/memory-extract',{method:'POST'});alert('Created '+data.candidates.length+' pending proposal(s). Review them below.');await loadMemoryCandidates()}catch(e){alert(e.message)}}
async function reviewMemoryCandidate(id,decision){try{const data=await api('/api/memory-candidates/'+id,{method:'POST',body:JSON.stringify({decision})});alert('Proposal '+data.candidate.status+'.');await loadMemoryCandidates();await loadMemories()}catch(e){alert(e.message)}}
async function loadMemoryCandidates(){const data=await api('/api/memory-candidates');const box=$('memory-candidates');box.replaceChildren();if(!data.candidates.length){box.textContent='No pending proposals.';return}for(const item of data.candidates){const row=document.createElement('div');row.className='mission-row';const body=document.createElement('div');body.textContent='['+item.memory_type+'] '+item.content+'\\nEvidence: “'+item.evidence+'”';const actions=document.createElement('div');actions.className='mission-actions';const accept=document.createElement('button');accept.textContent='Accept';accept.onclick=()=>reviewMemoryCandidate(item.id,'accept');const reject=document.createElement('button');reject.textContent='Reject';reject.onclick=()=>reviewMemoryCandidate(item.id,'reject');actions.append(accept,reject);row.append(body,actions);box.append(row)}}
async function loadMemories(){const data=await api('/api/memories');$('memories').replaceChildren();if(!data.memories.length){$('memories').textContent='No saved memories.';return}for(const m of data.memories){const row=document.createElement('div');row.className='mission-row';const body=document.createElement('div');body.textContent='['+m.memory_type+'] '+m.content+' · '+m.source_type+' · confidence '+m.confidence;const actions=document.createElement('div');actions.className='mission-actions';const off=document.createElement('button');off.textContent='Deactivate';off.onclick=async()=>{await api('/api/memories/'+m.id,{method:'PATCH',body:JSON.stringify({status:'inactive'})});await loadMemories()};const del=document.createElement('button');del.textContent='Delete';del.onclick=async()=>{if(confirm('Delete this memory permanently?')){await api('/api/memories/'+m.id,{method:'DELETE'});await loadMemories()}};actions.append(off,del);row.append(body,actions);$('memories').append(row)}}
async function saveMemory(){const content=$('memory-content').value.trim();if(!content)return;await api('/api/memories',{method:'POST',body:JSON.stringify({memory_type:$('memory-type').value,content,source_type:'user',source_ref:$('memory-source').value,confidence:0.8})});$('memory-content').value='';$('memory-source').value='';await loadMemories()}
async function loadMissions(){const data=await api('/api/missions');$('missions').replaceChildren();if(!data.missions.length){$('missions').textContent='No missions yet.';return}for(const m of data.missions){const row=document.createElement('div');row.className='mission-row';const title=document.createElement('strong');title.textContent=m.title;const meta=document.createElement('span');meta.textContent=m.status+' · priority '+m.priority;const actions=document.createElement('div');actions.className='mission-actions';const run=document.createElement('button');run.className='primary';run.textContent='Run next step';run.onclick=async()=>{try{const result=await api('/api/missions/'+m.id+'/run',{method:'POST'});const detail=result.task?('Step '+result.task.position+': '+result.task.status+' — '+result.task.title):'Mission '+result.mission.status;alert(detail+(result.task&&result.task.result?'\n\n'+result.task.result:''));await loadMissions()}catch(e){alert(e.message)}};const tasks=document.createElement('button');tasks.textContent='View tasks';tasks.onclick=async()=>{try{const result=await api('/api/missions/'+m.id+'/tasks');alert(result.tasks.length?result.tasks.map(t=>t.position+'. ['+t.status+'] '+t.title+(t.result?'\n'+t.result:'' )).join('\n\n'):'No plan yet. Press Run next step to generate one.')}catch(e){alert(e.message)}};actions.append(run,tasks);if(m.status==='blocked'){const replan=document.createElement('button');replan.textContent='Replan';replan.onclick=async()=>{const reason=prompt('Optional reason or alternative approach:')||'';try{const result=await api('/api/missions/'+m.id+'/replan',{method:'POST',body:JSON.stringify({reason})});alert('New plan proposed. Preserved '+result.preserved_completed+' completed task(s).');await loadMissions()}catch(e){alert(e.message)}};actions.append(replan)}const history=document.createElement('button');history.textContent='Plan history';history.onclick=async()=>{try{const result=await api('/api/missions/'+m.id+'/plan-history');alert(result.revisions.length?result.revisions.map(v=>'Plan v'+v.version+' · '+v.reason+'\n'+JSON.stringify(v.plan.metadata||{})).join('\n\n'):'No plan history yet.')}catch(e){alert(e.message)}};actions.append(history);if(m.status==='completed'){const remember=document.createElement('button');remember.textContent='Save episode';remember.onclick=async()=>{try{const result=await api('/api/memories/from-mission/'+m.id,{method:'POST'});alert('Saved episodic memory '+result.memory.id);await loadMemories()}catch(e){alert(e.message)}};actions.append(remember)}row.append(title,meta,actions);$('missions').append(row)}}
async function createMission(){const input=$('mission-title');const title=input.value.trim();if(!title)return;await api('/api/missions',{method:'POST',body:JSON.stringify({title,priority:3})});input.value='';await loadMissions()}
async function loadStatus(){const s=await api('/api/status');$('version').textContent=s.version;const online=s.model_runtimes.filter(x=>x.available).length;$('model-count').textContent=online+' runtime(s) online';$('runtimes').replaceChildren();for(const r of s.model_runtimes){const row=document.createElement('div');row.className='kv';const name=document.createElement('span');name.textContent=r.provider.replace('_',' ');const state=document.createElement('b');state.innerHTML='<span class="dot '+(r.available?'ok':'')+'"></span>'+ (r.available?'Online':'Offline');row.append(name,state);$('runtimes').append(row)}}
$('toggle-panels').onclick=()=>{const panel=document.querySelector('.right');const open=panel.classList.toggle('mobile-open');$('toggle-panels').setAttribute('aria-expanded',String(open));$('toggle-panels').textContent=open?'Close panels ×':'Panels ☰'};$('experience-status').onchange=()=>loadExperiences().catch(e=>alert(e.message));$('experience-outcome').onchange=()=>loadExperiences().catch(e=>alert(e.message));$('experience-refresh').onclick=()=>loadExperiences().catch(e=>alert(e.message));$('new-session').onclick=()=>newSession();$('learning-create').onclick=()=>createLearningCourse();$('learning-submit').onclick=()=>submitLearningAnswer();$('skill-create').onclick=()=>createSkill();$('send').onclick=()=>sendMessage().catch(e=>alert(e.message));$('message-input').addEventListener('keydown',e=>{if(e.key==='Enter')sendMessage().catch(x=>alert(x.message))});$('refresh').onclick=()=>Promise.all([loadStatus(),loadMissions()]).catch(e=>alert(e.message));$('create-mission').onclick=()=>createMission().catch(e=>alert(e.message));$('save-memory').onclick=()=>saveMemory().catch(e=>alert(e.message));$('research-search').onclick=()=>searchResearch();$('search-config-save').onclick=()=>saveSearchConfig();$('research-report-generate').onclick=()=>generateResearchReport();$('research-filter').onchange=()=>loadResearchSources().catch(e=>alert(e.message));$('knowledge-add').onclick=()=>addKnowledgeDocument().catch(e=>alert(e.message));$('knowledge-search').onclick=()=>searchKnowledge().catch(e=>alert(e.message));$('extract-memories').onclick=()=>extractConversationMemories();$('mission-title').addEventListener('keydown',e=>{if(e.key==='Enter')createMission().catch(x=>alert(x.message))});
Promise.all([loadSessions(),loadStatus(),loadMissions(),loadExperiences(),loadMemories(),loadMemoryCandidates(),loadKnowledgeDocuments(),loadResearchSources(),loadSkills(),loadLearningCourses(),loadSearchConfig()]).then(()=>{}).catch(e=>console.error(e));
</script></body></html>"""
