/* GENESIS Studio — dependency-free, DOM-built (no innerHTML with user content). */
(() => {
'use strict';

// ---------- helpers ----------
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const NS = 'http://www.w3.org/2000/svg';

function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'text') el.textContent = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' }, ...opts,
    body: opts.body && typeof opts.body !== 'string' ? JSON.stringify(opts.body) : opts.body,
  });
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) {
    const detail = data && data.detail;
    throw new Error(typeof detail === 'string' ? detail : (Array.isArray(detail) ? detail.map(d => d.msg).join('; ') : `Request failed (${res.status})`));
  }
  return data;
}

function toast(message, kind = '') {
  const t = h('div', { class: 'toast ' + kind, text: message });
  $('#toasts').append(t);
  setTimeout(() => t.remove(), 4200);
}

function ago(iso) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (isNaN(s)) return '';
  if (s < 60) return 'just now';
  if (s < 3600) return Math.floor(s / 60) + ' min ago';
  if (s < 86400) return Math.floor(s / 3600) + ' h ago';
  return Math.floor(s / 86400) + ' d ago';
}

const store = (() => {
  try { localStorage.setItem('_t', '1'); localStorage.removeItem('_t'); return localStorage; }
  catch { return { getItem: () => null, setItem: () => {} }; }
})();

// ---------- the orb ----------
function orbSVG() {
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 120 120');
  svg.setAttribute('class', 'orb');
  svg.setAttribute('aria-hidden', 'true');
  svg.innerHTML = `
    <circle class="halo" cx="60" cy="60" r="56"/>
    <circle class="shell-fill" cx="60" cy="60" r="44"/>
    <circle class="spin" cx="60" cy="60" r="51"/>
    <g class="eyes-open"><ellipse class="face" cx="46" cy="52" rx="6" ry="8"/><ellipse class="face" cx="74" cy="52" rx="6" ry="8"/></g>
    <g class="eyes-happy"><path class="face" d="M39 55q7-10 14 0"/><path class="face" d="M67 55q7-10 14 0"/></g>
    <g class="eyes-x"><path class="face" d="M40 46l12 12M52 46L40 58M68 46l12 12M80 46L68 58"/></g>
    <path class="face m-flat" d="M53 73h14l-7 9z"/>
    <path class="face m-smile" d="M47 72q13 14 26 0"/>
    <circle class="face m-o" cx="60" cy="77" r="5"/>
    <path class="face m-wave" d="M46 77q4-7 8 0t8 0t8 0"/>`;
  return svg;
}
const root = document.documentElement;
let orbTimer = null;
function setOrb(state, revertMs = 0) {
  clearTimeout(orbTimer);
  root.dataset.state = state;
  if (revertMs) orbTimer = setTimeout(() => setOrb(restingState()), revertMs);
}
function restingState() { return app.approvals.length ? 'alert' : 'idle'; }

// ---------- app state ----------
const app = {
  view: 'chat', sessions: [], activeId: null, busy: false, approvals: [], status: null,
  inspector: false, turnTools: [],
};

// ---------- tiny markdown renderer (safe: builds nodes) ----------
function inline(text) {
  const out = [];
  const re = /(`[^`\n]+`|\*\*[^*\n]+\*\*)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    out.push(tok[0] === '`' ? h('code', { text: tok.slice(1, -1) }) : h('strong', { text: tok.slice(2, -2) }));
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function renderMarkdown(text) {
  const frag = document.createDocumentFragment();
  const lines = text.split('\n');
  let i = 0, para = [];
  const flush = () => { if (para.length) { frag.append(h('p', {}, inline(para.join(' ')))); para = []; } };
  while (i < lines.length) {
    const line = lines[i];
    const fence = line.match(/^\s*```(\w*)/);
    if (fence) {
      flush();
      const code = [];
      i++;
      while (i < lines.length && !/^\s*```/.test(lines[i])) code.push(lines[i++]);
      i++;
      const lang = fence[1] || 'code';
      const body = code.join('\n');
      const copy = h('button', { type: 'button', 'aria-label': 'Copy code', text: 'Copy', onclick: async () => {
        try { await navigator.clipboard.writeText(body); copy.textContent = 'Copied'; setTimeout(() => (copy.textContent = 'Copy'), 1400); }
        catch { toast('Copy is not available here', 'bad'); }
      } });
      frag.append(h('pre', {}, h('div', { class: 'bar' }, h('span', { text: lang }), copy), h('code', { text: body })));
      continue;
    }
    const head = line.match(/^(#{1,4})\s+(.*)/);
    if (head) { flush(); frag.append(h(head[1].length <= 2 ? 'h3' : 'h4', {}, inline(head[2]))); i++; continue; }
    if (/^\s*[-*]\s+/.test(line) || /^\s*\d+\.\s+/.test(line)) {
      flush();
      const ordered = /^\s*\d+\./.test(line);
      const list = h(ordered ? 'ol' : 'ul');
      while (i < lines.length && (/^\s*[-*]\s+/.test(lines[i]) || /^\s*\d+\.\s+/.test(lines[i]))) {
        list.append(h('li', {}, inline(lines[i].replace(/^\s*(?:[-*]|\d+\.)\s+/, ''))));
        i++;
      }
      frag.append(list);
      continue;
    }
    if (!line.trim()) { flush(); i++; continue; }
    para.push(line.trim());
    i++;
  }
  flush();
  return frag;
}

// ---------- navigation ----------
const VIEWS = {
  chat: { title: null, load: () => {} },
  missions: { title: 'Missions', load: renderMissions },
  memory: { title: 'Memory', load: renderMemory },
  skills: { title: 'Skills', load: renderSkills },
  evolution: { title: 'Evolution', load: renderEvolution },
  system: { title: 'System', load: renderSystem },
};

function go(view) {
  if (!VIEWS[view]) return;
  app.view = view;
  for (const v of Object.keys(VIEWS)) $('#view-' + v).hidden = v !== view;
  for (const b of $$('.rail-btn[data-view]')) {
    if (b.dataset.view === view) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
  }
  $('#dock').hidden = view !== 'chat';
  if (view !== 'chat') $('#title').textContent = VIEWS[view].title;
  else updateHeader();
  $('#subtitle').textContent = view === 'chat' ? subtitleText() : 'GENESIS Studio';
  VIEWS[view].load();
  if (view === 'chat') $('#input').focus({ preventScroll: true });
  history.replaceState(null, '', '#' + view);
}

function updateHeader() {
  const s = app.sessions.find(x => x.id === app.activeId);
  $('#title').textContent = s ? s.title : 'New conversation';
}
function subtitleText() {
  const s = app.sessions.find(x => x.id === app.activeId);
  return s ? 'Updated ' + ago(s.updated_at) : 'Not started yet';
}

// ---------- chat ----------
const STARTERS = [
  'Explain what you can do on this device',
  'Help me plan a small project',
  'Summarize what you remember about me',
];

async function loadSessions() {
  try { app.sessions = (await api('/api/sessions')).sessions; } catch (e) { toast(e.message, 'bad'); }
  updateHeader();
}

async function openSession(id) {
  app.activeId = id;
  const { messages } = await api(`/api/sessions/${id}/messages`);
  const thread = $('#thread');
  thread.replaceChildren();
  for (const m of messages) if (m.role === 'user' || m.role === 'assistant') thread.append(turnEl(m.role, m.content));
  showThread(messages.length > 0);
  updateHeader();
  $('#subtitle').textContent = subtitleText();
  scrollDown(true);
}

function newConversation() {
  app.activeId = null;
  $('#thread').replaceChildren();
  showThread(false);
  go('chat');
  updateHeader();
  $('#input').focus();
}

function showThread(on) {
  $('#hero').hidden = on;
  $('#thread').hidden = !on;
}

function turnEl(role, text) {
  const me = role === 'user';
  const bubble = h('div', { class: 'bubble' });
  if (me) bubble.textContent = text; else bubble.append(renderMarkdown(text));
  const who = me ? null : h('div', { class: 'who' }, miniOrb(), 'GENESIS');
  return h('div', { class: 'turn ' + (me ? 'me' : 'ai') }, who, bubble);
}
function miniOrb() { const w = h('span', { class: 'orb-wrap' }); w.append(orbSVG()); w.firstChild.style.cssText = 'width:22px;height:22px'; return w; }

function scrollDown(force) {
  const v = $('#view-chat');
  if (force || v.scrollHeight - v.scrollTop - v.clientHeight < 160) v.scrollTop = v.scrollHeight;
}

function toolChip(ev) {
  const status = ev.status || ev.type || '';
  const cls = /ok|completed|success/.test(status) ? 'ok' : /deni|fail|error|block/.test(status) ? 'bad' : /pending|approval/.test(status) ? 'wait' : '';
  const glyph = cls === 'ok' ? '✔' : cls === 'bad' ? '✖' : cls === 'wait' ? '?' : '•';
  return h('span', { class: 'tool ' + cls, title: status }, `${glyph} ${ev.tool || ev.type}`);
}

async function send(text) {
  if (app.busy || !text.trim()) return;
  app.busy = true;
  $('#send').disabled = true;
  if (!app.activeId) {
    const { session } = await api('/api/sessions', { method: 'POST', body: { title: 'New conversation' } });
    app.activeId = session.id;
    app.sessions.unshift(session);
  }
  showThread(true);
  const thread = $('#thread');
  thread.append(turnEl('user', text));
  const bubble = h('div', { class: 'bubble' });
  const typing = h('div', { class: 'typing', 'aria-label': 'GENESIS is thinking' }, h('i'), h('i'), h('i'));
  const aiTurn = h('div', { class: 'turn ai' }, h('div', { class: 'who' }, miniOrb(), 'GENESIS'), typing);
  thread.append(aiTurn);
  scrollDown(true);
  app.turnTools = [];
  renderTurnTools();
  setOrb('thinking');

  let acc = '', toolsRow = null, rafPending = false, finalState = 'happy';
  const paint = () => {
    rafPending = false;
    bubble.replaceChildren(renderMarkdown(acc));
    scrollDown(false);
  };
  const addTool = ev => {
    if (!toolsRow) { toolsRow = h('div', { class: 'tools' }); aiTurn.append(toolsRow); }
    toolsRow.append(toolChip(ev));
    app.turnTools.push(ev);
    renderTurnTools();
  };

  try {
    const res = await fetch(`/api/sessions/${app.activeId}/messages/stream`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content: text }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `Request failed (${res.status})`);
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const chunk = buf.slice(0, idx); buf = buf.slice(idx + 2);
        if (!chunk.startsWith('data: ')) continue;
        const ev = JSON.parse(chunk.slice(6));
        if (ev.type === 'delta') {
          if (typing.isConnected) { typing.replaceWith(bubble); setOrb('working'); }
          acc += ev.content;
          if (!rafPending) { rafPending = true; requestAnimationFrame(paint); }
        } else if (ev.type === 'activity') {
          addTool(ev.event);
        } else if (ev.type === 'done') {
          if (typing.isConnected) typing.replaceWith(bubble);
          acc = (ev.assistant_message && ev.assistant_message.content) || acc;
          paint();
          const known = new Set(app.turnTools.map(t => (t.tool || '') + (t.status || '')));
          for (const a of ev.activity || []) if (a.type === 'tool' && !known.has((a.tool || '') + (a.status || ''))) addTool(a);
          const needs = (ev.activity || []).some(a => /approval/.test(a.status || ''));
          if (needs) {
            aiTurn.append(h('div', { class: 'notice' }, h('p', { text: 'GENESIS needs your approval to continue.' }),
              h('small', { text: 'Approve it in the activity panel, then ask again.' })));
            finalState = 'alert';
            await refreshApprovals();
            openInspector(true);
          }
          aiTurn.append(h('div', { class: 'who', style: 'padding-inline-start:30px;font-size:12px' }, `${ev.provider}/${ev.model}`));
        } else if (ev.type === 'error') {
          throw new Error(ev.detail);
        }
      }
    }
  } catch (e) {
    typing.remove();
    aiTurn.append(h('div', { class: 'notice err' }, h('p', { text: 'GENESIS could not answer.' }), h('small', { text: String(e.message || e) })));
    finalState = 'error';
  } finally {
    app.busy = false;
    $('#send').disabled = !$('#input').value.trim();
    if (!bubble.isConnected && !aiTurn.querySelector('.notice')) aiTurn.append(bubble);
    setOrb(finalState, finalState === 'alert' ? 0 : 3200);
    loadSessions().then(() => { $('#subtitle').textContent = subtitleText(); });
    scrollDown(false);
  }
}

// ---------- composer + slash commands ----------
const COMMANDS = [
  { cmd: '/new', desc: 'Start a new conversation', run: () => newConversation() },
  { cmd: '/missions', desc: 'Open missions', run: () => go('missions') },
  { cmd: '/memory', desc: 'Open memory', run: () => go('memory') },
  { cmd: '/skills', desc: 'Open skills', run: () => go('skills') },
  { cmd: '/evolution', desc: 'See how GENESIS is progressing', run: () => go('evolution') },
  { cmd: '/system', desc: 'Models, hardware and approvals', run: () => go('system') },
  { cmd: '/theme', desc: 'Switch light or dark', run: () => toggleTheme() },
];
let slashIndex = 0;
function slashMatches() {
  const v = $('#input').value;
  if (!v.startsWith('/') || v.includes(' ')) return [];
  return COMMANDS.filter(c => c.cmd.startsWith(v.toLowerCase()));
}
function renderSlash() {
  const menu = $('#slash-menu'), items = slashMatches();
  menu.hidden = !items.length;
  menu.replaceChildren();
  slashIndex = Math.min(slashIndex, Math.max(0, items.length - 1));
  items.forEach((c, i) => menu.append(h('button', {
    type: 'button', role: 'option', 'aria-selected': String(i === slashIndex),
    onmousedown: e => { e.preventDefault(); runSlash(c); },
  }, h('b', { text: c.cmd }), h('span', { text: c.desc }))));
}
function runSlash(c) { $('#input').value = ''; autosize(); renderSlash(); c.run(); }
function autosize() {
  const t = $('#input');
  t.style.height = 'auto';
  t.style.height = Math.min(t.scrollHeight, 180) + 'px';
  $('#send').disabled = app.busy || !t.value.trim();
}

function initComposer() {
  const input = $('#input');
  input.addEventListener('input', () => { slashIndex = 0; autosize(); renderSlash(); });
  input.addEventListener('keydown', e => {
    const items = slashMatches();
    if (items.length) {
      if (e.key === 'ArrowDown') { e.preventDefault(); slashIndex = (slashIndex + 1) % items.length; renderSlash(); return; }
      if (e.key === 'ArrowUp') { e.preventDefault(); slashIndex = (slashIndex - 1 + items.length) % items.length; renderSlash(); return; }
      if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); runSlash(items[slashIndex]); return; }
      if (e.key === 'Escape') { input.value = ''; autosize(); renderSlash(); return; }
    }
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); submit(); }
  });
  $('#send').addEventListener('click', submit);
  const starters = $('#starters');
  for (const s of STARTERS) starters.append(h('button', { class: 'starter', type: 'button', text: s, onclick: () => send(s) }));
}
function submit() {
  const input = $('#input'), text = input.value.trim();
  if (!text) return;
  input.value = '';
  autosize();
  send(text);
}

// ---------- overlays: palette + conversations ----------
function openSheet(build) {
  const overlay = $('#overlay'), sheet = $('#sheet');
  sheet.replaceChildren();
  build(sheet);
  overlay.hidden = false;
  const first = $('input', sheet);
  if (first) first.focus();
}
function closeSheet() { $('#overlay').hidden = true; }

function listSheet(label, groups, placeholder) {
  openSheet(sheet => {
    sheet.setAttribute('aria-label', label);
    const input = h('input', { type: 'text', placeholder, 'aria-label': placeholder, autocomplete: 'off' });
    const list = h('div', { class: 'list', role: 'listbox' });
    let flat = [], sel = 0;
    const draw = () => {
      const q = input.value.trim().toLowerCase();
      list.replaceChildren(); flat = [];
      for (const g of groups()) {
        const items = g.items.filter(i => !q || i.label.toLowerCase().includes(q) || (i.hint || '').toLowerCase().includes(q));
        if (!items.length) continue;
        if (g.title) list.append(h('div', { class: 'group', text: g.title }));
        for (const it of items) {
          const idx = flat.push(it) - 1;
          list.append(h('button', { class: 'item', type: 'button', role: 'option', 'aria-selected': String(idx === sel), onclick: () => { closeSheet(); it.run(); } },
            h('span', { text: it.label }), it.hint ? h('small', { text: it.hint }) : null));
        }
      }
      if (!flat.length) list.append(h('div', { class: 'empty', text: 'Nothing matches.' }));
    };
    input.addEventListener('input', () => { sel = 0; draw(); });
    input.addEventListener('keydown', e => {
      if (e.key === 'ArrowDown') { e.preventDefault(); sel = Math.min(sel + 1, flat.length - 1); draw(); $('[aria-selected=true]', list)?.scrollIntoView({ block: 'nearest' }); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); sel = Math.max(sel - 1, 0); draw(); $('[aria-selected=true]', list)?.scrollIntoView({ block: 'nearest' }); }
      else if (e.key === 'Enter' && flat[sel]) { e.preventDefault(); closeSheet(); flat[sel].run(); }
    });
    sheet.append(input, list);
    draw();
  });
}

function openPalette() {
  listSheet('Command palette', () => [
    { title: 'Go to', items: [
      { label: 'Chat', run: () => go('chat') }, { label: 'Missions', run: () => go('missions') },
      { label: 'Memory', run: () => go('memory') }, { label: 'Skills', run: () => go('skills') },
      { label: 'Evolution', run: () => go('evolution') }, { label: 'System', run: () => go('system') },
      { label: 'Classic Studio', hint: 'Knowledge, research, learning', run: () => { location.href = '/classic'; } },
    ] },
    { title: 'Do', items: [
      { label: 'New conversation', run: newConversation },
      { label: 'Switch conversation', run: openConversations },
      { label: 'Toggle activity panel', run: () => openInspector() },
      { label: 'Switch light or dark theme', run: toggleTheme },
    ] },
  ], 'Search commands');
}

function openConversations() {
  listSheet('Conversations', () => [{ title: 'Conversations', items: [
    { label: '＋ New conversation', run: newConversation },
    ...app.sessions.map(s => ({ label: s.title, hint: ago(s.updated_at), run: () => { go('chat'); openSession(s.id); } })),
  ] }], 'Find a conversation');
}

// ---------- inspector + approvals ----------
function openInspector(force) {
  app.inspector = force === true ? true : !app.inspector;
  $('#inspector').hidden = !app.inspector;
  $('#shell').classList.toggle('inspecting', app.inspector);
  $('#inspector-btn').setAttribute('aria-pressed', String(app.inspector));
  if (app.inspector) refreshApprovals();
}

function renderTurnTools() {
  const box = $('#insp-tools');
  box.replaceChildren(...app.turnTools.map(toolChip));
  $('#insp-empty').hidden = app.turnTools.length > 0;
}

function parseArgs(raw) { try { return JSON.stringify(typeof raw === 'string' ? JSON.parse(raw) : raw, null, 2); } catch { return String(raw); } }

function approvalCard(a, onDone) {
  const decide = async decision => {
    try {
      await api(`/api/approvals/${a.id}`, { method: 'POST', body: { decision } });
      toast(decision === 'approve' ? 'Approved. Ask again to run it.' : 'Rejected.', decision === 'approve' ? 'good' : '');
      await refreshApprovals();
      onDone && onDone();
    } catch (e) { toast(e.message, 'bad'); }
  };
  return h('div', { class: 'appr' },
    h('strong', { text: a.tool_name }), a.reason ? h('div', { class: 'sub', style: 'color:var(--dusk);font-size:13px', text: a.reason }) : null,
    h('code', { text: parseArgs(a.arguments) }),
    h('div', { class: 'acts' },
      h('button', { class: 'btn primary', type: 'button', text: 'Approve', onclick: () => decide('approve') }),
      h('button', { class: 'btn danger', type: 'button', text: 'Reject', onclick: () => decide('reject') })));
}

async function refreshApprovals() {
  try { app.approvals = (await api('/api/approvals')).approvals; } catch { return; }
  const n = app.approvals.length;
  const badge = $('#appr-badge');
  badge.hidden = n === 0; badge.textContent = n;
  const box = $('#insp-approvals');
  box.replaceChildren(...(n ? app.approvals.map(a => approvalCard(a)) : [h('p', { style: 'color:var(--dusk);font-size:14px;margin:0', text: 'Nothing is waiting for approval.' })]));
  if (!app.busy) setOrb(restingState());
  if (app.view === 'system') renderSystem();
}

// ---------- views ----------
function pageShell(title, lead) {
  return h('div', { class: 'col page' }, h('h2', { text: title }), h('p', { class: 'lead', text: lead }));
}
function empty(title, text) { return h('div', { class: 'empty' }, h('b', { text: title }), text); }
async function guard(btn, fn) {
  btn.disabled = true;
  try { await fn(); } catch (e) { toast(e.message, 'bad'); } finally { btn.disabled = false; }
}

async function renderMissions() {
  const view = $('#view-missions');
  const page = pageShell('Missions', 'Break a goal into tasks, then let GENESIS work through them one step at a time.');
  const title = h('input', { id: 'm-title', placeholder: 'What should GENESIS achieve?', maxlength: 160, 'aria-label': 'Mission title' });
  const desc = h('textarea', { rows: 2, placeholder: 'Details (optional)', 'aria-label': 'Mission details' });
  const add = h('button', { class: 'btn primary', type: 'button', text: 'Create mission', onclick: () => guard(add, async () => {
    if (!title.value.trim()) { title.focus(); throw new Error('Give the mission a title.'); }
    await api('/api/missions', { method: 'POST', body: { title: title.value.trim(), description: desc.value.trim(), priority: 3 } });
    toast('Mission created', 'good'); renderMissions();
  }) });
  page.append(h('div', { class: 'form' }, title, desc, h('div', {}, add)));
  const rows = h('div', { class: 'rows' });
  page.append(rows);
  view.replaceChildren(page);
  let missions = [];
  try { missions = (await api('/api/missions')).missions; } catch (e) { toast(e.message, 'bad'); }
  if (!missions.length) { rows.replaceWith(empty('No missions yet', 'Create one above and GENESIS will plan the steps.')); return; }
  for (const m of missions) {
    const more = h('div', { class: 'more' }); more.hidden = true;
    const showTasks = async () => {
      if (!more.hidden) { more.hidden = true; return; }
      const { tasks } = await api(`/api/missions/${m.id}/tasks`);
      more.replaceChildren(tasks.length ? h('ol', { style: 'margin:8px 0 0;padding-inline-start:1.2em;color:var(--dusk)' }, tasks.map(t => h('li', {}, `${t.title} `, h('span', { class: 'pill', text: t.status })))) : h('p', { style: 'color:var(--dusk);margin:8px 0 0', text: 'No tasks yet. Plan the mission first.' }));
      more.hidden = false;
    };
    const planBtn = h('button', { class: 'btn', type: 'button', text: 'Plan', onclick: () => guard(planBtn, async () => { await api(`/api/missions/${m.id}/plan`, { method: 'POST' }); toast('Plan ready', 'good'); more.hidden = true; await showTasks(); }) });
    const runBtn = h('button', { class: 'btn primary', type: 'button', text: 'Run next step', onclick: () => guard(runBtn, async () => { setOrb('working'); try { await api(`/api/missions/${m.id}/run`, { method: 'POST' }); toast('Step finished', 'good'); } finally { setOrb(restingState()); } more.hidden = true; await showTasks(); renderMissions(); }) });
    rows.append(h('div', { class: 'row' },
      h('span', { class: 'lamp ' + m.status }), h('span', { class: 't', text: m.title }),
      h('div', { class: 'acts' }, h('button', { class: 'btn', type: 'button', text: 'Tasks', onclick: () => guard(planBtn, showTasks) }), planBtn, runBtn),
      h('span', { class: 'm' }, h('span', { class: 'pill', text: m.status }), m.description || 'No description'), more));
  }
}

async function renderMemory() {
  const view = $('#view-memory');
  const page = pageShell('Memory', 'What GENESIS keeps between conversations. You decide what stays.');
  let filter = '';
  const type = h('select', { 'aria-label': 'Memory type' }, ['semantic', 'episodic', 'procedural'].map(t => h('option', { value: t, text: t })));
  const text = h('textarea', { rows: 2, placeholder: 'Something GENESIS should remember', 'aria-label': 'Memory text' });
  const save = h('button', { class: 'btn primary', type: 'button', text: 'Save memory', onclick: () => guard(save, async () => {
    if (!text.value.trim()) { text.focus(); throw new Error('Write what GENESIS should remember.'); }
    await api('/api/memories', { method: 'POST', body: { memory_type: type.value, content: text.value.trim() } });
    toast('Saved', 'good'); text.value = ''; draw();
  }) });
  const seg = h('div', { class: 'seg', role: 'group', 'aria-label': 'Filter by type' });
  for (const [val, label] of [['', 'All'], ['semantic', 'Facts'], ['episodic', 'Events'], ['procedural', 'How-to']]) {
    seg.append(h('button', { type: 'button', 'aria-pressed': String(val === filter), text: label, onclick: e => { filter = val; $$("button", seg).forEach(b => b.setAttribute("aria-pressed", String(b === e.currentTarget))); draw(); } }));
  }
  const rows = h('div', { class: 'rows' });
  page.append(h('div', { class: 'form' }, h('label', {}, 'Type', type), text, h('div', {}, save)), h('div', { class: 'bar' }, seg), rows);
  view.replaceChildren(page);
  async function draw() {
    rows.replaceChildren();
    let list = [];
    try { list = (await api('/api/memories' + (filter ? '?memory_type=' + filter : ''))).memories; } catch (e) { toast(e.message, 'bad'); }
    if (!list.length) { rows.append(empty('Nothing saved yet', 'Add a memory above, or let GENESIS propose some after a conversation.')); return; }
    for (const m of list) rows.append(h('div', { class: 'row' },
      h('span', { class: 'lamp active' }), h('span', { class: 't', text: m.content }),
      h('div', { class: 'acts' }, h('button', { class: 'btn danger', type: 'button', 'aria-label': 'Forget this memory', text: 'Forget', onclick: async () => { try { await api('/api/memories/' + m.id, { method: 'DELETE' }); draw(); } catch (e) { toast(e.message, 'bad'); } } })),
      h('span', { class: 'm' }, h('span', { class: 'pill', text: m.memory_type }), `${Math.round(m.confidence * 100)}% sure · ${ago(m.updated_at)}`)));
  }
  draw();
}

async function renderSkills() {
  const view = $('#view-skills');
  const page = pageShell('Skills', 'Reusable know-how you review before GENESIS may use it. Test a skill in the terminal with /eval skill, and the evidence shows up here.');
  const name = h('input', { placeholder: 'Skill name', 'aria-label': 'Skill name', maxlength: 100 });
  const desc = h('input', { placeholder: 'What it is for', 'aria-label': 'Skill description', maxlength: 500 });
  const ins = h('textarea', { rows: 3, placeholder: 'Instructions GENESIS should follow', 'aria-label': 'Skill instructions' });
  const add = h('button', { class: 'btn primary', type: 'button', text: 'Create draft', onclick: () => guard(add, async () => {
    if (![name, desc, ins].every(f => f.value.trim())) throw new Error('Fill in the name, purpose and instructions.');
    await api('/api/skills', { method: 'POST', body: { name: name.value.trim(), description: desc.value.trim(), instructions: ins.value.trim() } });
    toast('Draft created. Submit it for review when ready.', 'good'); renderSkills();
  }) });
  const rows = h('div', { class: 'rows' });
  page.append(h('div', { class: 'form' }, name, desc, ins, h('div', {}, add)), rows);
  view.replaceChildren(page);
  let skills = [];
  try { skills = (await api('/api/skills')).skills; } catch (e) { toast(e.message, 'bad'); }
  if (!skills.length) { rows.replaceWith(empty('No skills yet', 'Write one above. It stays a draft until you approve it.')); return; }
  for (const s of skills) {
    const act = (label, path, body, cls = '') => h('button', { class: 'btn ' + cls, type: 'button', text: label, onclick: e => guard(e.currentTarget, async () => { await api(`/api/skills/${s.id}/${path}`, { method: 'POST', body }); renderSkills(); }) });
    const acts = h('div', { class: 'acts' });
    if (s.status === 'draft') acts.append(act('Submit for review', 'submit', undefined, 'primary'));
    if (s.status === 'pending') acts.append(act('Approve', 'review', { decision: 'approve' }, 'primary'), act('Reject', 'review', { decision: 'reject' }, 'danger'));
    if (s.status === 'active') acts.append(act('Disable', 'disable', undefined, 'danger'));
    const ev = h('span', { class: 'evidence' });
    rows.append(h('div', { class: 'row' }, h('span', { class: 'lamp ' + s.status }), h('span', { class: 't', text: s.name }), acts,
      h('span', { class: 'm' }, h('span', { class: 'pill', text: s.status }), h('span', { class: 'pill', text: 'v' + s.version }), s.description, ' ', ev)));
    api(`/api/skills/${s.id}/evidence`).then(d => {
      const e = d.evidence;
      if (!e) { ev.textContent = 'Not tested yet.'; return; }
      ev.textContent = `Benchmark: ${e.verdict} (${e.delta >= 0 ? '+' : ''}${Math.round(e.delta * 100)} pts)`;
      ev.className = 'evidence ' + (/improved/.test(e.verdict) ? 'good' : e.verdict === 'no change' ? '' : e.verdict === 'mixed' ? 'mixed' : 'bad');
    }).catch(() => {});
  }
}

function chart(points) {
  const W = 700, H = 190, P = { l: 34, r: 12, t: 12, b: 24 };
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('class', 'chart'); svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', 'Benchmark score over time: ' + points.map(p => Math.round(p.score * 100) + '%').join(', '));
  const x = i => P.l + (points.length === 1 ? (W - P.l - P.r) / 2 : i * (W - P.l - P.r) / (points.length - 1));
  const y = v => P.t + (1 - v) * (H - P.t - P.b);
  let html = '';
  for (const g of [0, .25, .5, .75, 1]) html += `<line class="grid" x1="${P.l}" x2="${W - P.r}" y1="${y(g)}" y2="${y(g)}"/><text x="4" y="${y(g) + 4}">${Math.round(g * 100)}%</text>`;
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(p.score).toFixed(1)}`).join(' ');
  if (points.length > 1) html += `<path class="area" d="${d} L${x(points.length - 1)} ${y(0)} L${x(0)} ${y(0)}Z"/>`;
  html += `<path class="line" d="${d}"/>` + points.map((p, i) => `<circle class="pt" cx="${x(i).toFixed(1)}" cy="${y(p.score).toFixed(1)}" r="4"/>`).join('');
  svg.innerHTML = html;
  return svg;
}

async function renderEvolution() {
  const view = $('#view-evolution');
  const page = pageShell('Evolution', 'GENESIS does not change the model itself. It gets better through what you teach it, and this page measures whether that is really working.');
  view.replaceChildren(page);
  let d;
  try { d = await api('/api/evolution'); } catch (e) { page.append(empty('Could not load progress', e.message)); return; }
  const c = d.counts;
  page.append(h('p', { style: 'margin:0 0 18px;color:var(--dusk)' }, `${c.skills_active} active ${c.skills_active === 1 ? 'skill' : 'skills'} · ${c.memories} ${c.memories === 1 ? 'memory' : 'memories'} · ${c.documents} ${c.documents === 1 ? 'document' : 'documents'}`));
  if (!d.timeline.length) {
    page.append(empty('No baseline yet', 'Run /eval run in the terminal to measure where GENESIS starts. The score curve appears here.'));
    return;
  }
  const last = d.timeline[d.timeline.length - 1], first = d.timeline[0];
  page.append(h('h3', { style: 'margin:0', text: `Baseline score: ${Math.round(last.score * 100)}%` }),
    h('p', { style: 'margin:2px 0 6px;color:var(--dusk);font-size:14px', text: `${d.timeline.length} run${d.timeline.length > 1 ? 's' : ''}, from ${Math.round(first.score * 100)}% on ${last.model}. Rule-based tasks only: this shows measured behaviour, not general intelligence.` }),
    chart(d.timeline));
  const body = h('tbody', {}, d.runs.map(r => h('tr', {}, h('td', { text: ago(r.created_at) }), h('td', { text: r.label }), h('td', { text: r.suite }), h('td', { text: Math.round(r.score * 100) + '%' }), h('td', { text: `${r.passed}/${r.total}` }))));
  page.append(h('h3', { text: 'Recent runs' }), h('div', { class: 'tbl-wrap' }, h('table', { class: 'tbl' },
    h('thead', {}, h('tr', {}, ['When', 'Condition', 'Suite', 'Score', 'Passed'].map(t => h('th', { text: t })))), body)));
}

async function renderSystem() {
  const view = $('#view-system');
  const page = pageShell('System', 'Everything runs on this device. Here is what GENESIS can use right now.');
  view.replaceChildren(page);
  let s;
  try { s = await api('/api/status'); } catch (e) { page.append(empty('Could not reach GENESIS', e.message)); return; }
  app.status = s;
  page.append(h('h3', { text: 'Model runtimes' }));
  const rows = h('div', { class: 'rows' });
  for (const r of s.model_runtimes) rows.append(h('div', { class: 'row' },
    h('span', { class: 'lamp ' + (r.available ? 'active' : '') }), h('span', { class: 't', text: r.provider }),
    h('span'), h('span', { class: 'm', text: r.available ? `${(r.models || []).length} model(s) · ${r.detail || ''}` : (r.detail || 'Not running') })));
  page.append(rows);
  if (!s.model_runtimes.some(r => r.available)) page.append(h('p', { style: 'color:var(--dusk)', text: 'No model is running. In the terminal, /model install downloads one directly.' }));
  page.append(h('h3', { style: 'margin-top:26px', text: 'Waiting for your approval' }));
  page.append(app.approvals.length ? h('div', {}, app.approvals.map(a => approvalCard(a))) : h('p', { style: 'color:var(--dusk)', text: 'Nothing is waiting.' }));
  page.append(h('h3', { style: 'margin-top:26px', text: 'Tools' }), h('div', { class: 'tools', style: 'padding:0' }, s.available_tools.map(t => h('span', { class: 'tool', text: t }))));
  page.append(h('p', { style: 'margin-top:26px;color:var(--dusk);font-size:13px', text: `GENESIS CORE ${s.version}` }));
}

async function refreshModelChip() {
  try {
    const s = await api('/api/status');
    app.status = s;
    const on = s.model_runtimes.filter(r => r.available);
    $('#model-led').classList.toggle('on', on.length > 0);
    $('#model-text').textContent = on.length ? on.map(r => r.provider).join(', ') + ' online' : 'No model running';
  } catch { $('#model-text').textContent = 'Offline'; }
}

// ---------- theme ----------
function toggleTheme() {
  const dark = matchMedia('(prefers-color-scheme: dark)').matches;
  const cur = root.dataset.theme || (dark ? 'dark' : 'light');
  const next = cur === 'dark' ? 'light' : 'dark';
  root.dataset.theme = next;
  store.setItem('genesis-theme', next);
}

// ---------- boot ----------
function boot() {
  const saved = store.getItem('genesis-theme');
  if (saved) root.dataset.theme = saved;
  setOrb('idle');
  $('#logo').append(orbSVG()); $('#head-orb').append(orbSVG()); $('#hero-orb').append(orbSVG());
  $('#head-orb').firstChild.style.cssText = 'width:36px;height:36px';
  $('#logo').firstChild.style.cssText = 'width:44px;height:44px';
  for (const b of $$('.rail-btn[data-view]')) b.addEventListener('click', () => go(b.dataset.view));
  $('#more-btn').addEventListener('click', openPalette);
  $('#title-btn').addEventListener('click', openConversations);
  $('#palette-btn').addEventListener('click', openPalette);
  $('#theme-btn').addEventListener('click', toggleTheme);
  $('#inspector-btn').addEventListener('click', () => openInspector());
  $('#overlay').addEventListener('mousedown', e => { if (e.target.id === 'overlay') closeSheet(); });
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); $('#overlay').hidden ? openPalette() : closeSheet(); }
    else if (e.key === 'Escape' && !$('#overlay').hidden) closeSheet();
  });
  initComposer();
  Promise.all([loadSessions(), refreshApprovals(), refreshModelChip()]).then(() => {
    const target = (location.hash || '#chat').slice(1);
    go(VIEWS[target] ? target : 'chat');
    if (app.sessions.length && !app.activeId) openSession(app.sessions[0].id).catch(() => {});
  });
  setInterval(() => { if (!document.hidden) { refreshApprovals(); refreshModelChip(); } }, 10000);
}
boot();
})();
