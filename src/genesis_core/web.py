"""GENESIS Studio: graphical client for the shared local GENESIS state."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from genesis_core import __version__
from genesis_core.agent import AgentRuntime, ModelError
from genesis_core.hardware import inspect_hardware
from genesis_core.models import discover_runtimes
from genesis_core.missions import MissionError, MissionStore
from genesis_core.state import StateStore

app = FastAPI(title="GENESIS CORE Studio", version=__version__)
store = StateStore()
agent = AgentRuntime(store=store)
mission_store = MissionStore(state=store)


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


@app.get("/api/status")
def status() -> dict:
    return {
        "name": "GENESIS CORE",
        "version": __version__,
        "status": "foundation",
        "interfaces": ["TUI", "Studio"],
        "agent_runtime": "ready",
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
        "agent_runtime": "ready",
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
.card{background:#111a28;border:1px solid var(--line);border-radius:10px;padding:13px;margin-bottom:10px}.card h3{font-size:11px;letter-spacing:.1em;margin:0 0 12px;color:#a9b7cc}.kv{display:flex;justify-content:space-between;gap:8px;font-size:11px;margin:9px 0;color:var(--muted)}.kv b{color:#dce7f8;font-weight:500;text-align:right}.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#67748a;margin-right:6px}.dot.ok{background:var(--mint)}.notice{color:#aab6c9;font-size:11px;line-height:1.6}
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
<aside class="right"><div class="section">SYSTEM OVERVIEW</div><div class="card"><h3>AGENT ENGINE</h3><div class="kv"><span>Status</span><b>Foundation only</b></div><div class="kv"><span>Inference</span><b>Agent runtime active</b></div><div class="kv"><span>Sessions</span><b id="session-count">0</b></div></div><div class="card"><h3>MODEL RUNTIMES</h3><div id="runtimes" class="notice">Loading…</div></div><div class="card"><h3>DESIGN PRINCIPLE</h3><p class="notice">Ollama, llama.cpp, LM Studio and remote APIs are interchangeable backends. GENESIS owns the interface, memory, tools, permissions and agent workflow.</p></div></aside>
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
async function loadStatus(){const s=await api('/api/status');$('version').textContent=s.version;const online=s.model_runtimes.filter(x=>x.available).length;$('model-count').textContent=online+' runtime(s) online';$('runtimes').replaceChildren();for(const r of s.model_runtimes){const row=document.createElement('div');row.className='kv';const name=document.createElement('span');name.textContent=r.provider.replace('_',' ');const state=document.createElement('b');state.innerHTML='<span class="dot '+(r.available?'ok':'')+'"></span>'+ (r.available?'Online':'Offline');row.append(name,state);$('runtimes').append(row)}}
$('new-session').onclick=()=>newSession();$('send').onclick=()=>sendMessage().catch(e=>alert(e.message));$('message-input').addEventListener('keydown',e=>{if(e.key==='Enter')sendMessage().catch(x=>alert(x.message))});$('refresh').onclick=()=>loadStatus().catch(e=>alert(e.message));
Promise.all([loadSessions(),loadStatus()]).then(()=>{}).catch(e=>console.error(e));
</script></body></html>"""
