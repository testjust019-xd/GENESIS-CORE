"""GENESIS Studio: graphical client for the shared local GENESIS state."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from genesis_core import __version__
from genesis_core.agent import AgentRuntime, ModelError, build_default_tool_executor
from genesis_core.hardware import inspect_hardware
from genesis_core.models import discover_runtimes
from genesis_core.missions import MissionError, MissionStore
from genesis_core.mission_engine import MissionEngine, MissionEngineError
from genesis_core.memory import MemoryError, MemoryStore
from genesis_core.conversation_memory import ConversationMemoryEngine, ConversationMemoryError
from genesis_core.knowledge import KnowledgeError, KnowledgeStore
from genesis_core.research import ResearchEngine, ResearchError
from genesis_core.state import StateStore
from genesis_core.tools import ToolError

app = FastAPI(title="GENESIS CORE Studio", version=__version__)
store = StateStore()
tool_executor, approval_store = build_default_tool_executor(store)
agent = AgentRuntime(store=store, tool_executor=tool_executor)
mission_store = MissionStore(state=store)
mission_engine = MissionEngine(store, mission_store, agent)
memory_store = MemoryStore(store)
conversation_memory = ConversationMemoryEngine(store, memory_store)
knowledge_store = KnowledgeStore(store)
research_engine = ResearchEngine(store, knowledge_store)


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


class ResearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=8, ge=1, le=20)


class ResearchReviewInput(BaseModel):
    decision: str
    note: str = Field(default="", max_length=1000)


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


@app.post("/api/research/search")
def search_research(payload: ResearchInput) -> dict:
    try:
        return {"research": research_engine.search(payload.query, payload.limit)}
    except ResearchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/research/runs")
def list_research_runs() -> dict:
    return {"runs": research_engine.store.list_runs()}


@app.get("/api/research/sources")
def list_research_sources(run_id: str | None = None, review_status: str | None = None) -> dict:
    try:
        return {"sources": research_engine.list_sources(run_id, review_status)}
    except ResearchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
.card{background:#111a28;border:1px solid var(--line);border-radius:10px;padding:13px;margin-bottom:10px}.card h3{font-size:11px;letter-spacing:.1em;margin:0 0 12px;color:#a9b7cc}.kv{display:flex;justify-content:space-between;gap:8px;font-size:11px;margin:9px 0;color:var(--muted)}.kv b{color:#dce7f8;font-weight:500;text-align:right}.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#67748a;margin-right:6px}.dot.ok{background:var(--mint)}.notice{color:#aab6c9;font-size:11px;line-height:1.6}.mission-row{border-top:1px solid var(--line);padding:9px 0;font-size:11px}.mission-row strong{display:block;color:#dce7f8;font-weight:550;margin-bottom:4px}.mission-row span{color:var(--muted)}.mission-create{display:flex;gap:6px;margin-top:10px}.mission-create input{width:100%;min-width:0;background:#0b111c;border:1px solid var(--line);border-radius:7px;padding:8px;color:var(--text)}.mission-create button{border:0;border-radius:7px;background:#1b5b4b;padding:0 10px;color:#eafff8}.mission-actions{display:flex;gap:6px;margin-top:7px}.mission-actions button{border:1px solid var(--line);background:#172334;color:#c9d7eb;border-radius:6px;padding:5px 8px;font-size:10px}.mission-actions button.primary{background:#174b3e;border-color:#286b58;color:#cffff0}.right input,.right select,.right textarea{width:100%;min-width:0;background:#0b111c;border:1px solid var(--line);border-radius:7px;padding:8px;color:var(--text);margin:4px 0}.right textarea{min-height:105px;resize:vertical;line-height:1.5}
@media(max-width:950px){.app{grid-template-columns:210px 1fr}.top{grid-column:1/3}.right{display:none}}
@media(max-width:620px){.app{grid-template-columns:1fr}.top{grid-column:1}.left{display:none}.topmeta .pill{display:none}.centerhead{padding:0 14px}.messages{padding:18px 14px}.composer{padding:12px 14px}}
</style>
</head>
<body><div class="app">
<header class="top"><div class="brand"><span class="mark">G</span> GENESIS <span style="color:#62738d;font-weight:500">STUDIO</span></div><div class="topmeta"><span id="model-count">Checking runtimes…</span><span class="pill">LOCAL WORKSPACE</span><span>v<span id="version">…</span></span></div></header>
<aside class="left"><div class="section">WORKSPACE</div><button class="new" id="new-session">＋ &nbsp; New conversation</button><div class="section">CONVERSATIONS</div><div id="sessions"></div><div class="section" style="margin-top:26px">SYSTEM</div><button class="session" id="refresh">↻ &nbsp; Refresh status</button></aside>
<main class="center"><div class="centerhead"><div><strong id="active-title">New conversation</strong><div class="sub" id="active-sub">Shared GENESIS session</div></div><span class="pill">ENGINE FOUNDATION</span></div>
<div class="messages" id="messages"><div class="welcome" id="welcome"><div class="orb">✧</div><h1>GENESIS CORE</h1><p>Your workspace for research, reasoning, tools and evolving skills.<br>Create a conversation to begin building your project context.</p></div></div>
<div class="composer"><div class="inputbox"><input id="message-input" placeholder="Write a message to GENESIS…" autocomplete="off"><button class="send" id="send">Send ↗</button></div><div class="hint">Messages are shared with GENESIS TUI. Connect a supported model runtime to receive AI responses.</div></div></main>
<aside class="right"><div class="section">SYSTEM OVERVIEW</div><div class="card"><h3>AGENT ENGINE</h3><div class="kv"><span>Status</span><b>Foundation only</b></div><div class="kv"><span>Inference</span><b>Agent runtime active</b></div><div class="kv"><span>Sessions</span><b id="session-count">0</b></div></div><div class="card"><h3>MODEL RUNTIMES</h3><div id="runtimes" class="notice">Loading…</div></div><div class="card"><h3>MISSION CONTROL</h3><div id="missions" class="notice">Loading missions…</div><div class="mission-create"><input id="mission-title" placeholder="New mission title"><button id="create-mission">＋</button></div></div><div class="card"><h3>CONVERSATION MEMORY REVIEW</h3><p class="notice">Extract suggestions from user messages in the open conversation. Nothing is saved until you accept it.</p><button id="extract-memories" class="primary">Analyze open conversation</button><div id="memory-candidates" class="notice">No proposals loaded.</div></div><div class="card"><h3>RESEARCH ENGINE</h3><input id="research-query" placeholder="What should GENESIS investigate?"><button id="research-search" class="primary">Search sources</button><div id="research-notice" class="notice">External search is optional. Without a provider, GENESIS searches the local Knowledge Base.</div><select id="research-filter"><option value="pending">Pending review</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="">All sources</option></select><div id="research-sources" class="notice">No research sources loaded.</div></div><div class="card"><h3>KNOWLEDGE BASE</h3><input id="knowledge-title" placeholder="Document title"><input id="knowledge-source" placeholder="Source / file reference (optional)"><textarea id="knowledge-content" placeholder="Paste document text or Markdown here"></textarea><button id="knowledge-add" class="primary">Index document</button><input id="knowledge-query" placeholder="Search indexed knowledge"><button id="knowledge-search">Search knowledge</button><div id="knowledge-results" class="notice">No search performed.</div><div id="knowledge-documents" class="notice">Loading documents…</div></div><div class="card"><h3>LONG-TERM MEMORY</h3><select id="memory-type"><option value="semantic">Semantic fact</option><option value="episodic">Episode</option><option value="procedural">Procedure</option></select><input id="memory-content" placeholder="Add a verified memory"><input id="memory-source" placeholder="Source / reference (optional)"><button id="save-memory" class="primary">Save memory</button><div id="memories" class="notice">Loading memories…</div></div><div class="card"><h3>DESIGN PRINCIPLE</h3><p class="notice">Ollama, llama.cpp, LM Studio and remote APIs are interchangeable backends. GENESIS owns the interface, memory, tools, permissions and agent workflow.</p></div></aside>
</div>
<script>
let activeId=null;
const $=id=>document.getElementById(id);
async function api(path,options={}){const response=await fetch(path,{headers:{'Content-Type':'application/json'},...options});if(!response.ok)throw new Error((await response.json()).detail||'Request failed');return response.json()}
function addMessage(m){const box=document.createElement('div');box.className='msg '+(m.role==='user'?'user':'');const role=document.createElement('div');role.className='role';role.textContent=m.role.toUpperCase();const body=document.createElement('div');body.textContent=m.content;box.append(role,body);$('messages').append(box)}
async function loadSessions(){const data=await api('/api/sessions');$('sessions').replaceChildren();$('session-count').textContent=data.sessions.length;for(const s of data.sessions){const b=document.createElement('button');b.className='session'+(s.id===activeId?' active':'');b.textContent=s.title;b.onclick=()=>openSession(s.id);$('sessions').append(b)}}
async function openSession(id){activeId=id;const data=await api('/api/sessions/'+id+'/messages');$('messages').replaceChildren();for(const m of data.messages)addMessage(m);if(!data.messages.length){const p=document.createElement('p');p.className='notice';p.textContent='This conversation is ready. Send a message to save it.';$('messages').append(p)}const list=await api('/api/sessions');const s=list.sessions.find(x=>x.id===id);$('active-title').textContent=s?.title||'Conversation';$('active-sub').textContent='Session '+id+' · shared with GENESIS TUI';await loadSessions()}
async function newSession(){const data=await api('/api/sessions',{method:'POST',body:JSON.stringify({title:'New conversation'})});await openSession(data.session.id)}
async function sendMessage(){const input=$('message-input');const content=input.value.trim();if(!content)return;if(!activeId)await newSession();input.value='';const data=await api('/api/sessions/'+activeId+'/messages',{method:'POST',body:JSON.stringify({content})});const welcome=$('welcome');if(welcome)welcome.remove();addMessage(data.message);if(data.assistant_message){addMessage(data.assistant_message);const note=document.createElement('div');note.className='hint';note.textContent='Answered by '+data.provider+' · '+data.model;$('messages').append(note)}$('messages').scrollTop=$('messages').scrollHeight;await loadSessions();const s=(await api('/api/sessions')).sessions.find(x=>x.id===activeId);$('active-title').textContent=s?.title||'Conversation'}
async function loadResearchSources(){const status=$('research-filter').value;const data=await api('/api/research/sources'+(status?'?review_status='+encodeURIComponent(status):''));renderResearchSources(data.sources)}
function renderResearchSources(sources){const box=$('research-sources');box.replaceChildren();if(!sources.length){box.textContent='No sources in this review filter.';return}for(const source of sources){const row=document.createElement('div');row.className='mission-row';const body=document.createElement('div');const title=document.createElement('strong');title.textContent='['+source.review_status+'] '+source.title;const snippet=document.createElement('p');snippet.textContent=source.snippet;const link=document.createElement('a');link.href=source.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent=source.url;body.append(title,snippet,link);row.append(body);if(source.review_status==='pending'){const actions=document.createElement('div');actions.className='mission-actions';for(const [label,decision] of [['Approve','approved'],['Reject','rejected']]){const button=document.createElement('button');button.textContent=label;button.onclick=async()=>{try{await api('/api/research/sources/'+source.id+'/review',{method:'POST',body:JSON.stringify({decision})});await loadResearchSources()}catch(e){alert(e.message)}};actions.append(button)}row.append(actions)}box.append(row)}}
async function searchResearch(){const query=$('research-query').value.trim();if(!query)return;try{const data=await api('/api/research/search',{method:'POST',body:JSON.stringify({query,limit:8})});const result=data.research;$('research-notice').textContent='Research '+result.id+' · '+result.mode+' · '+result.source_count+' source(s). '+result.notice;renderResearchSources(result.sources);$('research-filter').value='pending'}catch(e){alert(e.message)}}
async function loadKnowledgeDocuments(){const data=await api('/api/knowledge/documents');const box=$('knowledge-documents');box.replaceChildren();if(!data.documents.length){box.textContent='No indexed documents.';return}for(const d of data.documents){const row=document.createElement('div');row.className='mission-row';const body=document.createElement('div');body.textContent=d.title+' · '+d.chunk_count+' chunks'+(d.source_uri?' · '+d.source_uri:'');const del=document.createElement('button');del.textContent='Remove';del.onclick=async()=>{if(confirm('Remove this document from the knowledge base?')){await api('/api/knowledge/documents/'+d.id,{method:'DELETE'});await loadKnowledgeDocuments()}};row.append(body,del);box.append(row)}}
async function addKnowledgeDocument(){const title=$('knowledge-title').value.trim(),content=$('knowledge-content').value.trim();if(!title||!content)return;const data=await api('/api/knowledge/documents',{method:'POST',body:JSON.stringify({title,content,source_uri:$('knowledge-source').value})});alert('Indexed '+data.document.chunk_count+' chunk(s).'+(data.document.duplicate?' This content was already indexed.':''));$('knowledge-content').value='';await loadKnowledgeDocuments()}
async function searchKnowledge(){const query=$('knowledge-query').value.trim();if(!query)return;const data=await api('/api/knowledge/search',{method:'POST',body:JSON.stringify({query,limit:8})});const box=$('knowledge-results');box.replaceChildren();if(!data.results.length){box.textContent='No matching knowledge found.';return}for(const result of data.results){const row=document.createElement('div');row.className='mission-row';const body=document.createElement('div');body.textContent=result.excerpt+'\\nSource: '+result.citation.title+' · chunk '+result.citation.chunk+' · '+result.citation.source;row.append(body);box.append(row)}}
async function extractConversationMemories(){if(!activeId){alert('Open a conversation first.');return}try{const data=await api('/api/sessions/'+activeId+'/memory-extract',{method:'POST'});alert('Created '+data.candidates.length+' pending proposal(s). Review them below.');await loadMemoryCandidates()}catch(e){alert(e.message)}}
async function reviewMemoryCandidate(id,decision){try{const data=await api('/api/memory-candidates/'+id,{method:'POST',body:JSON.stringify({decision})});alert('Proposal '+data.candidate.status+'.');await loadMemoryCandidates();await loadMemories()}catch(e){alert(e.message)}}
async function loadMemoryCandidates(){const data=await api('/api/memory-candidates');const box=$('memory-candidates');box.replaceChildren();if(!data.candidates.length){box.textContent='No pending proposals.';return}for(const item of data.candidates){const row=document.createElement('div');row.className='mission-row';const body=document.createElement('div');body.textContent='['+item.memory_type+'] '+item.content+'\\nEvidence: “'+item.evidence+'”';const actions=document.createElement('div');actions.className='mission-actions';const accept=document.createElement('button');accept.textContent='Accept';accept.onclick=()=>reviewMemoryCandidate(item.id,'accept');const reject=document.createElement('button');reject.textContent='Reject';reject.onclick=()=>reviewMemoryCandidate(item.id,'reject');actions.append(accept,reject);row.append(body,actions);box.append(row)}}
async function loadMemories(){const data=await api('/api/memories');$('memories').replaceChildren();if(!data.memories.length){$('memories').textContent='No saved memories.';return}for(const m of data.memories){const row=document.createElement('div');row.className='mission-row';const body=document.createElement('div');body.textContent='['+m.memory_type+'] '+m.content+' · '+m.source_type+' · confidence '+m.confidence;const actions=document.createElement('div');actions.className='mission-actions';const off=document.createElement('button');off.textContent='Deactivate';off.onclick=async()=>{await api('/api/memories/'+m.id,{method:'PATCH',body:JSON.stringify({status:'inactive'})});await loadMemories()};const del=document.createElement('button');del.textContent='Delete';del.onclick=async()=>{if(confirm('Delete this memory permanently?')){await api('/api/memories/'+m.id,{method:'DELETE'});await loadMemories()}};actions.append(off,del);row.append(body,actions);$('memories').append(row)}}
async function saveMemory(){const content=$('memory-content').value.trim();if(!content)return;await api('/api/memories',{method:'POST',body:JSON.stringify({memory_type:$('memory-type').value,content,source_type:'user',source_ref:$('memory-source').value,confidence:0.8})});$('memory-content').value='';$('memory-source').value='';await loadMemories()}
async function loadMissions(){const data=await api('/api/missions');$('missions').replaceChildren();if(!data.missions.length){$('missions').textContent='No missions yet.';return}for(const m of data.missions){const row=document.createElement('div');row.className='mission-row';const title=document.createElement('strong');title.textContent=m.title;const meta=document.createElement('span');meta.textContent=m.status+' · priority '+m.priority;const actions=document.createElement('div');actions.className='mission-actions';const run=document.createElement('button');run.className='primary';run.textContent='Run next step';run.onclick=async()=>{try{const result=await api('/api/missions/'+m.id+'/run',{method:'POST'});const detail=result.task?('Step '+result.task.position+': '+result.task.status+' — '+result.task.title):'Mission '+result.mission.status;alert(detail+(result.task&&result.task.result?'\\n\\n'+result.task.result:''));await loadMissions()}catch(e){alert(e.message)}};const tasks=document.createElement('button');tasks.textContent='View tasks';tasks.onclick=async()=>{try{const result=await api('/api/missions/'+m.id+'/tasks');alert(result.tasks.length?result.tasks.map(t=>t.position+'. ['+t.status+'] '+t.title+(t.result?'\\n'+t.result:'' )).join('\\n\\n'):'No plan yet. Press Run next step to generate one.')}catch(e){alert(e.message)}};actions.append(run,tasks);if(m.status==='completed'){const remember=document.createElement('button');remember.textContent='Save episode';remember.onclick=async()=>{try{const result=await api('/api/memories/from-mission/'+m.id,{method:'POST'});alert('Saved episodic memory '+result.memory.id);await loadMemories()}catch(e){alert(e.message)}};actions.append(remember)}row.append(title,meta,actions);$('missions').append(row)}}
async function createMission(){const input=$('mission-title');const title=input.value.trim();if(!title)return;await api('/api/missions',{method:'POST',body:JSON.stringify({title,priority:3})});input.value='';await loadMissions()}
async function loadStatus(){const s=await api('/api/status');$('version').textContent=s.version;const online=s.model_runtimes.filter(x=>x.available).length;$('model-count').textContent=online+' runtime(s) online';$('runtimes').replaceChildren();for(const r of s.model_runtimes){const row=document.createElement('div');row.className='kv';const name=document.createElement('span');name.textContent=r.provider.replace('_',' ');const state=document.createElement('b');state.innerHTML='<span class="dot '+(r.available?'ok':'')+'"></span>'+ (r.available?'Online':'Offline');row.append(name,state);$('runtimes').append(row)}}
$('new-session').onclick=()=>newSession();$('send').onclick=()=>sendMessage().catch(e=>alert(e.message));$('message-input').addEventListener('keydown',e=>{if(e.key==='Enter')sendMessage().catch(x=>alert(x.message))});$('refresh').onclick=()=>Promise.all([loadStatus(),loadMissions()]).catch(e=>alert(e.message));$('create-mission').onclick=()=>createMission().catch(e=>alert(e.message));$('save-memory').onclick=()=>saveMemory().catch(e=>alert(e.message));$('research-search').onclick=()=>searchResearch();$('research-filter').onchange=()=>loadResearchSources().catch(e=>alert(e.message));$('knowledge-add').onclick=()=>addKnowledgeDocument().catch(e=>alert(e.message));$('knowledge-search').onclick=()=>searchKnowledge().catch(e=>alert(e.message));$('extract-memories').onclick=()=>extractConversationMemories();$('mission-title').addEventListener('keydown',e=>{if(e.key==='Enter')createMission().catch(x=>alert(x.message))});
Promise.all([loadSessions(),loadStatus(),loadMissions(),loadMemories(),loadMemoryCandidates(),loadKnowledgeDocuments(),loadResearchSources()]).then(()=>{}).catch(e=>console.error(e));
</script></body></html>"""
