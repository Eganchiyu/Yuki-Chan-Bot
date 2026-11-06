# modules/debug/webui_server.py
import argparse
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from modules.debug.context_snapshot import context_snapshot_store
from modules.debug.phone_trace import phone_trace_store


HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Yuki Context Debug WebUI</title>
  <style>
    :root{color-scheme:dark;--bg:#070b18;--card:rgba(255,255,255,.08);--line:rgba(255,255,255,.14);--text:#eef4ff;--muted:#aab7d4;--cyan:#65e4ff;--purple:#c084fc;--green:#8bf5c2;--yellow:#fde68a;--red:#fca5a5;--blue:#7aa7ff}
    *{box-sizing:border-box}body{margin:0;min-height:100vh;font-family:"Microsoft YaHei","Segoe UI",system-ui,sans-serif;color:var(--text);background:radial-gradient(circle at 12% 8%,rgba(101,228,255,.2),transparent 34%),radial-gradient(circle at 82% 16%,rgba(192,132,252,.18),transparent 32%),var(--bg)}
    .page{width:min(1600px,calc(100vw - 32px));margin:0 auto;padding:24px 0 36px}.hero,.card{border:1px solid var(--line);background:var(--card);box-shadow:0 24px 80px rgba(0,0,0,.32);backdrop-filter:blur(18px)}.hero{border-radius:26px;padding:24px}.top{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}.actions{display:flex;gap:8px;flex-wrap:wrap}button,a.btn{border:1px solid var(--line);border-radius:12px;background:rgba(255,255,255,.08);color:var(--text);padding:9px 12px;cursor:pointer;text-decoration:none;font-size:14px;display:inline-flex;align-items:center;gap:6px}button:hover,a.btn:hover{border-color:rgba(101,228,255,.45)}a.btn.primary{border-color:var(--cyan);background:rgba(101,228,255,.16);color:#d8f7ff;font-weight:600}h1{margin:0 0 10px;font-size:34px}.sub,.muted{color:var(--muted)}.pill{display:inline-flex;align-items:center;gap:8px;padding:7px 10px;border:1px solid var(--line);border-radius:999px;background:rgba(255,255,255,.07);font-size:13px;color:var(--muted);margin:4px 6px 0 0}.dot{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 16px var(--green)}
    .layout{display:grid;grid-template-columns:290px minmax(0,1fr) 360px;gap:16px;margin-top:16px}.card{border-radius:22px;padding:16px;min-width:0}h2{font-size:16px;margin:0 0 14px}.sessions{display:grid;gap:10px;max-height:72vh;overflow:auto}.session{padding:12px;border:1px solid var(--line);border-radius:16px;background:rgba(255,255,255,.05);cursor:pointer}.session.active{border-color:var(--cyan);box-shadow:0 0 0 1px rgba(101,228,255,.25) inset}.session b{display:block;margin-bottom:6px}.preview{font-size:12px;color:var(--muted);line-height:1.5;word-break:break-all}.messages{display:grid;gap:12px}.msg{border:1px solid var(--line);border-radius:16px;overflow:hidden;background:rgba(0,0,0,.16)}.msg summary{cursor:pointer;padding:12px 14px;display:flex;gap:10px;align-items:center}.role{padding:3px 8px;border-radius:999px;font-size:12px;background:rgba(122,167,255,.18);color:#dbe7ff}.role.system{background:rgba(192,132,252,.18);color:#f1ddff}.role.user{background:rgba(101,228,255,.16);color:#d8f7ff}.role.assistant{background:rgba(139,245,194,.16);color:#d9ffec}.role.tool{background:rgba(253,230,138,.16);color:#fff5c9}.content{white-space:pre-wrap;word-break:break-word;line-height:1.65;color:#eaf2ff;padding:0 14px 14px;max-height:420px;overflow:auto}.panel{display:grid;gap:12px}.json{white-space:pre-wrap;word-break:break-word;max-height:300px;overflow:auto;font-size:12px;line-height:1.55;color:#d8e8ff;background:rgba(0,0,0,.18);border-radius:14px;padding:12px}.mem{padding:10px;border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.04);font-size:13px;line-height:1.55}.timeline{display:grid;grid-template-columns:repeat(8,1fr);gap:8px;margin-top:16px}.step{border:1px solid var(--line);border-radius:14px;padding:10px;background:rgba(255,255,255,.05);font-size:12px;color:var(--muted)}.step.done{border-color:rgba(139,245,194,.35);color:#d5ffe9}.empty{padding:40px;text-align:center;color:var(--muted)}@media(max-width:1100px){.layout{grid-template-columns:1fr}.timeline{grid-template-columns:repeat(2,1fr)}}
  </style>
</head>
<body><main class="page">
  <section class="hero"><div class="top"><div><h1>Yuki Context Debug WebUI</h1><div class="sub">本地只读调试页面，展示 LLM messages、RAG 与 Yuki-Memory 召回快照。</div><div id="status"></div></div><div class="actions"><a class="btn primary" href="/phone">📱 手机实时监控 &amp; 轨迹回放</a><button onclick="refreshAll()">刷新</button><button onclick="togglePause()" id="pauseBtn">暂停自动刷新</button><button onclick="copySnapshot()">复制当前上下文</button><button onclick="downloadSnapshot()">导出 snapshot JSON</button></div></div></section>
  <section class="layout"><aside class="card"><h2>最近会话</h2><div id="sessions" class="sessions"></div></aside><section class="card"><h2>完整构建上下文</h2><div id="messages" class="messages empty">暂无 snapshot</div></section><aside class="card panel"><div><h2>记忆召回</h2><div id="memories"></div></div><div><h2>Snapshot JSON</h2><div id="snapshotJson" class="json">{}</div></div></aside></section>
  <section class="card"><h2>Pipeline 阶段时间线</h2><div id="timeline" class="timeline"></div></section>
</main><script>
let selectedId=null, current=null, paused=false;
let lastListUpdate=null;
const stages=['prepare_message_batch','normalize_incoming_content','prepare_chat_context','decide_reply_action','retrieve_memories','generate_reply','send_reply','finalize_conversation'];
async function api(path){const r=await fetch(path);return await r.json()}
function esc(s){return String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function meta(){return current?`chat_id=${current.chat_id||''} · stage=${current.stage||''} · tokens≈${current.token_estimate?.estimated_tokens||0}`:'等待数据'}

async function refreshAll(){
  const [status,list]=await Promise.all([api('/api/status'),api('/api/snapshots?limit=80')]);
  document.getElementById('status').innerHTML=`<span class="pill"><i class="dot"></i>online</span><span class="pill">刷新 ${status.generated_at}</span><span class="pill">snapshots ${status.snapshot_count}</span><span class="pill">${meta()}</span>`;

  if(status.latest_snapshot_at !== lastListUpdate || !lastListUpdate){
    renderSessions(list);
    lastListUpdate = status.latest_snapshot_at;
  }

  if(!selectedId && status.latest_snapshot_id) {
    selectedId=status.latest_snapshot_id;
    lastListUpdate=null;
  }

  if(selectedId){
    const freshData = await api('/api/snapshots/'+encodeURIComponent(selectedId));
    if(!current || current.snapshot_id !== freshData.snapshot_id || current.updated_at !== freshData.updated_at){
      current = freshData;
      renderSnapshot();
    }
  }
}

function renderSessions(list){
  document.getElementById('sessions').innerHTML=list.length?list.map(x=>`<div class="session ${x.snapshot_id===selectedId?'active':''}" onclick="selectSnapshot('${x.snapshot_id}')"><b>${esc(x.chat_id||'-')}</b><div class="preview">${esc(x.mode||'')} · ${esc(x.stage||'')} · ${esc(x.updated_at||x.created_at||'')}</div><div class="preview">${esc(x.combined_text_preview||'')}</div><div class="preview">messages ${x.built_message_count||0} · tokens≈${x.estimated_tokens||0}</div></div>`).join(''):'<div class="empty">暂无 snapshot</div>';
}

async function selectSnapshot(id){
  selectedId=id;
  current=null;
  lastListUpdate=null;
  await refreshAll();
}

function renderSnapshot(){
  document.getElementById('snapshotJson').textContent=JSON.stringify(current,null,2);
  const messages=current.built_messages||[];
  document.getElementById('messages').className=messages.length?'messages':'messages empty';
  document.getElementById('messages').innerHTML=messages.length?messages.map((m,i)=>{
    const c=typeof m.content==='string'?m.content:JSON.stringify(m.content,null,2);
    return `<details class="msg" ${i<3?'open':''}><summary><span class="role ${esc(m.role)}">${esc(m.role||'unknown')}</span><span class="muted">#${i+1} · chars ${c.length} · tokens≈${Math.max(1,Math.floor(c.length/2))}</span><button onclick="event.stopPropagation();navigator.clipboard.writeText(${JSON.stringify(c).replace(/"/g, '&quot;')})">复制</button></summary><div class="content">${esc(c)}</div></details>`;
  }).join(''):'暂无完整 messages';
  renderMemories();
  renderTimeline();
}

function renderMemories(){
  const old=current.relevant_diaries||[];
  let html=`<h2>RAG 回忆</h2>${old.length?old.map(x=>`<div class="mem">${esc(typeof x==='string'?x:JSON.stringify(x,null,2))}</div>`).join(''):'<div class="muted">无</div>'}`;
  document.getElementById('memories').innerHTML=html;
}

function renderTimeline(){
  const latency=current.latency||{};const stage=current.stage||'';
  document.getElementById('timeline').innerHTML=stages.map(s=>`<div class="step ${(latency[s]||stage===s)?'done':''}"><b>${s}</b><br>${latency[s]??''}</div>`).join('');
}

function togglePause(){
  paused=!paused;
  document.getElementById('pauseBtn').textContent=paused?'恢复自动刷新':'暂停自动刷新';
}

function copySnapshot(){if(current)navigator.clipboard.writeText(JSON.stringify(current,null,2))}

function downloadSnapshot(){
  if(!current)return;
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([JSON.stringify(current,null,2)],{type:'application/json'}));
  a.download=(current.snapshot_id||'snapshot')+'.json';
  a.click();
}

setInterval(()=>{if(!paused)refreshAll()},2000);
refreshAll();
</script></body></html>"""


PHONE_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Yuki 手机实时监控 & 轨迹回放 WebUI</title>
  <style>
    :root{color-scheme:dark;--bg:#060a15;--card:rgba(255,255,255,.07);--line:rgba(255,255,255,.14);--text:#eef4ff;--muted:#9fb0cf;--cyan:#65e4ff;--purple:#c084fc;--green:#8bf5c2;--yellow:#fde68a;--red:#fca5a5;--blue:#7aa7ff}
    *{box-sizing:border-box}
    body{margin:0;min-height:100vh;font-family:"Microsoft YaHei","Segoe UI",system-ui,sans-serif;color:var(--text);background:radial-gradient(circle at 10% 6%,rgba(101,228,255,.18),transparent 34%),radial-gradient(circle at 86% 12%,rgba(192,132,252,.16),transparent 32%),var(--bg)}
    .page{width:min(1760px,calc(100vw - 28px));margin:0 auto;padding:18px 0 32px}
    .hero,.card{border:1px solid var(--line);background:var(--card);box-shadow:0 20px 60px rgba(0,0,0,.35);backdrop-filter:blur(16px)}
    .hero{border-radius:22px;padding:18px 22px}
    .top{display:flex;justify-content:space-between;gap:16px;align-items:center;flex-wrap:wrap}
    .actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
    button,a.btn{border:1px solid var(--line);border-radius:11px;background:rgba(255,255,255,.08);color:var(--text);padding:8px 12px;cursor:pointer;text-decoration:none;font-size:13px;display:inline-flex;align-items:center;gap:6px}
    button:hover,a.btn:hover{border-color:rgba(101,228,255,.5)}
    button.active{border-color:var(--cyan);background:rgba(101,228,255,.18);color:#d8f7ff}
    h1{margin:0 0 6px;font-size:26px}
    h2{font-size:15px;margin:0 0 10px;display:flex;justify-content:space-between;align-items:center}
    .sub,.muted{color:var(--muted);font-size:13px}
    .pill{display:inline-flex;align-items:center;gap:7px;padding:5px 10px;border:1px solid var(--line);border-radius:999px;background:rgba(255,255,255,.06);font-size:12px;color:var(--muted);margin:6px 6px 0 0}
    .dot{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 12px var(--green)}
    .dot.warn{background:var(--yellow);box-shadow:0 0 12px var(--yellow)}
    .layout{display:grid;grid-template-columns:340px minmax(0,1fr) 460px;gap:14px;margin-top:14px;align-items:start}
    .card{border-radius:20px;padding:14px;min-width:0}
    .list-box{display:grid;gap:8px;max-height:33vh;overflow:auto;padding-right:2px}
    .step-list-box{display:grid;gap:8px;max-height:44vh;overflow:auto;padding-right:2px}
    .item{padding:10px 12px;border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.04);cursor:pointer;transition:border-color .15s}
    .item:hover{border-color:rgba(101,228,255,.4)}
    .item.active{border-color:var(--cyan);background:rgba(101,228,255,.11);box-shadow:0 0 0 1px rgba(101,228,255,.22) inset}
    .item-head{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:4px}
    .badge{padding:2px 7px;border-radius:999px;font-size:11px;font-weight:600;background:rgba(122,167,255,.18);color:#dbe7ff}
    .badge.running{background:rgba(139,245,194,.2);color:#d9ffec}
    .badge.finished{background:rgba(192,132,252,.2);color:#f3e1ff}
    .badge.time{background:rgba(253,230,138,.18);color:#fef08a}
    .badge.err{background:rgba(252,165,165,.22);color:#fecaca}
    .screens{display:grid;grid-template-columns:1fr 1fr;gap:14px}
    .screen-card{border:1px solid var(--line);border-radius:16px;padding:12px;background:rgba(0,0,0,.22);display:flex;flex-direction:column;align-items:center}
    .screen-card .head{width:100%;display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;gap:8px;flex-wrap:wrap}
    .img-wrap{width:100%;min-height:480px;max-height:68vh;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.35);border-radius:12px;overflow:hidden;position:relative}
    .img-wrap img{max-width:100%;max-height:66vh;object-fit:contain;cursor:zoom-in;border-radius:8px}
    .timing-bar{width:100%;margin-top:10px;display:flex;gap:6px;flex-wrap:wrap;font-size:12px;color:var(--muted)}
    .timing-chip{padding:4px 8px;border-radius:8px;background:rgba(255,255,255,.06);border:1px solid var(--line)}
    .text-panel{display:grid;gap:12px}
    .box{border:1px solid var(--line);border-radius:14px;background:rgba(0,0,0,.22);padding:12px}
    .box h3{margin:0 0 8px;font-size:13px;color:var(--cyan);display:flex;justify-content:space-between;align-items:center}
    .pre{white-space:pre-wrap;word-break:break-word;font-size:12.5px;line-height:1.6;color:#eaf2ff;max-height:240px;overflow:auto;font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
    .empty{padding:28px;text-align:center;color:var(--muted);font-size:13px}
    .modal{position:fixed;inset:0;background:rgba(0,0,0,.85);display:none;align-items:center;justify-content:center;z-index:999;padding:24px}
    .modal img{max-width:95vw;max-height:92vh;object-fit:contain;border-radius:12px}
    @media(max-width:1300px){.layout{grid-template-columns:1fr}.screens{grid-template-columns:1fr}}
  </style>
</head>
<body>
<main class="page">
  <section class="hero">
    <div class="top">
      <div>
        <h1>📱 Yuki 手机实时监控 &amp; 操作轨迹回放</h1>
        <div class="sub">实时手机投屏 · 当步 Yuki 视角标注画面 · Yuki 收发原文本 · 每步耗时分解与历史轨迹翻阅（键盘 ← / → 快速翻步）</div>
        <div id="statusPills"></div>
      </div>
      <div class="actions">
        <a class="btn" href="/">🧠 返回 Context Debug</a>
        <button id="followBtn" class="active" onclick="toggleFollow()">🎯 自动跟随最新步</button>
        <button id="liveBtn" class="active" onclick="toggleLive()">🟢 实时画面流: 开启</button>
        <button onclick="refreshLiveImage(true)">📸 立即抓屏</button>
        <button onclick="refreshData()">🔄 刷新轨迹</button>
      </div>
    </div>
  </section>

  <section class="layout">
    <!-- 左栏：历史轨迹会话 + 步骤列表 -->
    <aside class="card" style="display:grid;gap:14px">
      <div>
        <h2><span>🗂️ 手机操作轨迹列表</span><span class="muted" id="sessCount">0 条</span></h2>
        <div id="sessionList" class="list-box"><div class="empty">暂无手机操作轨迹</div></div>
      </div>
      <div>
        <h2>
          <span>⏱️ 步骤时间轴 (点击回翻)</span>
          <span style="display:flex;gap:4px">
            <button style="padding:3px 8px;font-size:12px" onclick="stepDelta(-1)">◀ 上一步</button>
            <button style="padding:3px 8px;font-size:12px" onclick="stepDelta(1)">下一步 ▶</button>
          </span>
        </h2>
        <div id="stepList" class="step-list-box"><div class="empty">请选择轨迹会话</div></div>
      </div>
    </aside>

    <!-- 中栏：实时画面 vs Yuki 看到的原画面 -->
    <section class="card">
      <div class="screens">
        <div class="screen-card">
          <div class="head">
            <b>📡 当前手机实时画面 (Live)</b>
            <span class="badge time" id="liveMeta">等待抓拍...</span>
          </div>
          <div class="img-wrap">
            <img id="liveImg" alt="当前手机实时画面" onclick="openModal(this.src)" />
          </div>
          <div class="timing-bar">
            <span class="timing-chip" id="liveHint">每 1.2s 自动从 ADB 实时拉取当前屏幕</span>
          </div>
        </div>

        <div class="screen-card">
          <div class="head">
            <b id="stepScreenTitle">👁️ Yuki 看到的原画面</b>
            <span style="display:flex;gap:6px;align-items:center">
              <button id="viewModeBtn" style="padding:3px 8px;font-size:11px" onclick="toggleStepImgMode()">切换: 红框标注图</button>
              <span class="badge time" id="stepElapsedBadge">- ms</span>
            </span>
          </div>
          <div class="img-wrap">
            <img id="yukiImg" alt="Yuki 看到的画面" onclick="openModal(this.src)" />
          </div>
          <div class="timing-bar" id="stepTimingBar">
            <span class="timing-chip">选择左侧步骤查看当步耗时分解</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 右栏：Yuki 收到的原文本 & Yuki 回复的原文本 -->
    <aside class="card text-panel">
      <div class="box">
        <h3>
          <span>📥 Yuki 收到的用户触发原文本</span>
          <button style="padding:2px 7px;font-size:11px" onclick="copyText('userIncomingText')">复制</button>
        </h3>
        <div id="userIncomingText" class="pre">暂无</div>
      </div>

      <div class="box">
        <h3>
          <span>📤 Yuki 回复的原文本 (当步思考/调用 + 最终回复)</span>
          <button style="padding:2px 7px;font-size:11px" onclick="copyText('yukiReplyText')">复制</button>
        </h3>
        <div id="yukiReplyText" class="pre">暂无</div>
      </div>

      <div class="box">
        <h3>
          <span>🌲 当步回传给 Yuki 的控件树 / 工具原文本</span>
          <button style="padding:2px 7px;font-size:11px" onclick="copyText('toolResultText')">复制</button>
        </h3>
        <div id="toolResultText" class="pre" style="max-height:310px">暂无</div>
      </div>
    </aside>
  </section>
</main>

<div id="imgModal" class="modal" onclick="this.style.display='none'">
  <img id="modalImg" src="" alt="preview" />
</div>

<script>
let selectedSessionId = null;
let selectedStepIndex = null;
let currentSession = null;
let followLatest = true;
let liveEnabled = true;
let showAnnotated = true;
let liveBusy = false;

function esc(s){return String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function fmtMs(ms){
  const n = Number(ms||0);
  return n >= 1000 ? (n/1000).toFixed(2)+'s ('+n+'ms)' : n+'ms';
}
async function api(path){const r=await fetch(path);return await r.json()}

function openModal(src){
  if(!src)return;
  document.getElementById('modalImg').src = src;
  document.getElementById('imgModal').style.display = 'flex';
}

function copyText(id){
  const el = document.getElementById(id);
  if(el) navigator.clipboard.writeText(el.textContent || '');
}

function toggleFollow(){
  followLatest = !followLatest;
  const btn = document.getElementById('followBtn');
  btn.className = followLatest ? 'active' : '';
  btn.textContent = followLatest ? '🎯 自动跟随最新步' : '📌 已锁定当前步';
  if(followLatest) refreshData();
}

function toggleLive(){
  liveEnabled = !liveEnabled;
  const btn = document.getElementById('liveBtn');
  btn.className = liveEnabled ? 'active' : '';
  btn.textContent = liveEnabled ? '🟢 实时画面流: 开启' : '⏸️ 实时画面流: 暂停';
}

function toggleStepImgMode(){
  showAnnotated = !showAnnotated;
  document.getElementById('viewModeBtn').textContent = showAnnotated ? '切换: 红框标注图' : '切换: 无框原图';
  renderSelectedStep();
}

function refreshLiveImage(force=false){
  if(liveBusy && !force) return;
  liveBusy = true;
  const img = document.getElementById('liveImg');
  const t0 = performance.now();
  const url = '/api/phone/live.jpg?t=' + Date.now() + (force ? '&force=1' : '');
  const loader = new Image();
  loader.onload = () => {
    img.src = url;
    const cost = Math.round(performance.now() - t0);
    document.getElementById('liveMeta').textContent = '实时帧 ' + cost + 'ms';
    liveBusy = false;
  };
  loader.onerror = () => {
    document.getElementById('liveMeta').textContent = '设备未就绪或抓屏失败';
    liveBusy = false;
  };
  loader.src = url;
}

async function refreshData(){
  try {
    const [status, sessions] = await Promise.all([
      api('/api/phone/status'),
      api('/api/phone/sessions?limit=60')
    ]);
    const activeChats = Object.keys(status.active_chats || {});
    document.getElementById('statusPills').innerHTML = `
      <span class="pill"><i class="dot ${status.live_error?'warn':''}"></i>${status.live_error ? 'ADB: '+esc(status.live_error) : 'ADB 在线'}</span>
      <span class="pill">聚焦中会话: ${activeChats.length ? esc(activeChats.join(',')) : '无'}</span>
      <span class="pill">历史轨迹数: ${status.session_count || 0}</span>
      <span class="pill">刷新: ${esc(status.generated_at || '')}</span>
    `;
    document.getElementById('sessCount').textContent = `${sessions.length} 条`;

    if((followLatest && status.latest_session_id) || (!selectedSessionId && sessions.length)){
      selectedSessionId = (followLatest && status.latest_session_id) ? status.latest_session_id : sessions[0].session_id;
    }

    renderSessionList(sessions);

    if(selectedSessionId){
      const detail = await api('/api/phone/sessions/' + encodeURIComponent(selectedSessionId));
      if(detail && detail.session_id){
        currentSession = detail;
        const steps = currentSession.steps || [];
        if(followLatest || !selectedStepIndex || selectedStepIndex > steps.length){
          selectedStepIndex = steps.length ? steps[steps.length - 1].step_index : null;
        }
        renderStepList();
        renderSelectedStep();
      }
    }
  } catch (e) {
    console.error(e);
  }
}

function renderSessionList(sessions){
  const el = document.getElementById('sessionList');
  if(!sessions.length){
    el.innerHTML = '<div class="empty">暂无手机操作轨迹</div>';
    return;
  }
  el.innerHTML = sessions.map(s => `
    <div class="item ${s.session_id===selectedSessionId?'active':''}" onclick="selectSession('${esc(s.session_id)}')">
      <div class="item-head">
        <b>${esc(s.goal || '手机操作')}</b>
        <span class="badge ${s.status==='running'?'running':'finished'}">${esc(s.status)}</span>
      </div>
      <div class="sub">chat: ${esc(s.chat_id)} · ${s.step_count||0} 步 · 总耗时 ${fmtMs(s.total_elapsed_ms)}</div>
      <div class="sub">${esc(s.updated_at || s.created_at || '')}</div>
    </div>
  `).join('');
}

async function selectSession(sid){
  selectedSessionId = sid;
  selectedStepIndex = null;
  followLatest = false;
  document.getElementById('followBtn').className = '';
  document.getElementById('followBtn').textContent = '📌 已锁定当前步';
  await refreshData();
}

function selectStep(idx){
  selectedStepIndex = idx;
  followLatest = false;
  document.getElementById('followBtn').className = '';
  document.getElementById('followBtn').textContent = '📌 已锁定当前步';
  renderStepList();
  renderSelectedStep();
}

function stepDelta(delta){
  if(!currentSession || !(currentSession.steps||[]).length) return;
  const total = currentSession.steps.length;
  const cur = selectedStepIndex || total;
  const next = Math.max(1, Math.min(total, cur + delta));
  selectStep(next);
}

function renderStepList(){
  const el = document.getElementById('stepList');
  const steps = (currentSession && currentSession.steps) || [];
  if(!steps.length){
    el.innerHTML = '<div class="empty">该会话暂无步骤记录</div>';
    return;
  }
  el.innerHTML = steps.map(st => `
    <div class="item ${st.step_index===selectedStepIndex?'active':''}" onclick="selectStep(${st.step_index})">
      <div class="item-head">
        <b>#${st.step_index} ${esc(st.step_display || st.action)}</b>
        <span class="badge ${st.success?'time':'err'}">${fmtMs(st.elapsed_ms)}</span>
      </div>
      <div class="sub">${esc(st.note || '')}</div>
      <div class="sub">${esc(st.package || '未知包名')} · 节点 ${st.node_count||0} · ${esc(st.timestamp||'')}</div>
    </div>
  `).join('');
}

function renderSelectedStep(){
  if(!currentSession) return;
  const steps = currentSession.steps || [];
  const step = steps.find(s => s.step_index === selectedStepIndex) || steps[steps.length - 1];

  // 1) 用户触发原文本
  const incomingList = (currentSession.incoming_messages || []).map(m => `[${m.time}] ${m.text}`).join('\n---\n');
  const stepIncoming = step ? (step.user_incoming_text || '') : '';
  document.getElementById('userIncomingText').textContent =
    incomingList || stepIncoming || currentSession.last_incoming_text || '暂无';

  if(!step){
    document.getElementById('yukiReplyText').textContent = currentSession.last_final_reply || '暂无';
    document.getElementById('toolResultText').textContent = '暂无步骤';
    return;
  }

  // 2) 当步画面与耗时分解
  document.getElementById('stepScreenTitle').textContent =
    `👁️ 第 #${step.step_index} 步 Yuki 看到的画面 (${step.action})`;
  document.getElementById('stepElapsedBadge').textContent = fmtMs(step.elapsed_ms);

  const imgUrl = showAnnotated ? (step.yuki_image_url || step.raw_image_url) : (step.raw_image_url || step.yuki_image_url);
  const yukiImg = document.getElementById('yukiImg');
  if(imgUrl){
    yukiImg.src = imgUrl;
  } else {
    yukiImg.removeAttribute('src');
  }

  const tb = step.timing_breakdown || {};
  const chips = [`<span class="timing-chip"><b>总用时</b>: ${fmtMs(step.elapsed_ms)}</span>`];
  if(tb.dump_before_ms != null) chips.push(`<span class="timing-chip">动作前Dump: ${tb.dump_before_ms}ms</span>`);
  if(tb.exec_ms != null) chips.push(`<span class="timing-chip">ADB执行: ${tb.exec_ms}ms</span>`);
  if(tb.wait_ms != null) chips.push(`<span class="timing-chip">等待稳定: ${tb.wait_ms}ms</span>`);
  if(tb.dump_after_ms != null) chips.push(`<span class="timing-chip">动作后Dump: ${tb.dump_after_ms}ms</span>`);
  if(tb.screenshot_ms != null) chips.push(`<span class="timing-chip">截图+标注: ${tb.screenshot_ms}ms</span>`);
  document.getElementById('stepTimingBar').innerHTML = chips.join('');

  // 3) Yuki 回复的原文本
  const replyParts = [];
  if(step.yuki_replied_text){
    replyParts.push(`【第 #${step.step_index} 步模型思考 & 调用原文】\n${step.yuki_replied_text}`);
  }
  if(step.yuki_final_reply || currentSession.last_final_reply){
    replyParts.push(`【本轮最终回复原文】\n${step.yuki_final_reply || currentSession.last_final_reply}`);
  }
  if(currentSession.summary){
    replyParts.push(`【聚焦退出总结】\n${currentSession.summary}`);
  }
  document.getElementById('yukiReplyText').textContent = replyParts.join('\n\n====================\n\n') || '（本步无附加文本）';

  // 4) 当步工具返回给 Yuki 的原文本
  document.getElementById('toolResultText').textContent = step.yuki_received_text || '暂无';
}

document.addEventListener('keydown', e => {
  if(e.key === 'ArrowLeft') stepDelta(-1);
  if(e.key === 'ArrowRight') stepDelta(1);
  if(e.key === 'Escape') document.getElementById('imgModal').style.display = 'none';
});

setInterval(() => { if(liveEnabled) refreshLiveImage(false); }, 1200);
setInterval(() => { refreshData(); }, 1800);
refreshLiveImage(true);
refreshData();
</script>
</body>
</html>"""


_STEP_IMG_RE = re.compile(r"^/api/phone/sessions/([^/]+)/steps/(\d+)/(yuki|raw)\.jpg$")


class ContextDebugRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_text=HTML):
        body = html_text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, data: bytes, content_type: str = "image/jpeg", status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            if path == "/":
                self._send_html(HTML)
            elif path in ("/phone", "/phone/"):
                self._send_html(PHONE_HTML)
            elif path == "/api/health":
                self._send_json({"ok": True})
            elif path == "/api/status":
                self._send_json(context_snapshot_store.status())
            elif path == "/api/snapshots":
                limit = int((query.get("limit") or [50])[0])
                chat_id = (query.get("chat_id") or [None])[0]
                self._send_json(context_snapshot_store.list_recent(limit=limit, chat_id=chat_id))
            elif path == "/api/latest":
                chat_id = (query.get("chat_id") or [None])[0]
                self._send_json(context_snapshot_store.latest(chat_id) or {})
            elif path.startswith("/api/snapshots/"):
                snapshot_id = unquote(path.removeprefix("/api/snapshots/"))
                item = context_snapshot_store.get(snapshot_id)
                self._send_json(item or {"ok": False, "error": "snapshot_not_found"}, 200 if item else 404)
            # ---------- 手机监控与轨迹 API ----------
            elif path == "/api/phone/status":
                self._send_json(phone_trace_store.status())
            elif path == "/api/phone/sessions":
                limit = int((query.get("limit") or [50])[0])
                self._send_json(phone_trace_store.list_sessions(limit=limit))
            elif path == "/api/phone/live.jpg":
                force = (query.get("force") or ["0"])[0] in ("1", "true")
                jpeg, _, _ = phone_trace_store.capture_live_jpeg(force=force)
                if jpeg:
                    self._send_bytes(jpeg, "image/jpeg", 200)
                else:
                    self._send_json({"ok": False, "error": "live_screencap_unavailable"}, 503)
            elif path.startswith("/api/phone/sessions/"):
                m = _STEP_IMG_RE.match(path)
                if m:
                    sid = unquote(m.group(1))
                    step_idx = int(m.group(2))
                    kind = m.group(3)
                    img_bytes = phone_trace_store.get_step_image(sid, step_idx, kind=kind)
                    if img_bytes:
                        self._send_bytes(img_bytes, "image/jpeg", 200)
                    else:
                        self._send_json({"ok": False, "error": "image_not_found"}, 404)
                else:
                    sid = unquote(path.removeprefix("/api/phone/sessions/"))
                    sess = phone_trace_store.get_session(sid)
                    self._send_json(sess or {"ok": False, "error": "session_not_found"}, 200 if sess else 404)
            else:
                self._send_json({"ok": False, "error": "not_found"}, 404)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, 500)


def run_server(host="127.0.0.1", port=8777):
    server = ThreadingHTTPServer((host, port), ContextDebugRequestHandler)
    print(f"Yuki Debug WebUI: http://{host}:{port}/ (Phone: http://{host}:{port}/phone)")
    server.serve_forever()


def start_background_server(host="127.0.0.1", port=8777):
    """在主程序进程内后台启动 Debug WebUI，共享内存 snapshot store。"""
    thread = threading.Thread(
        target=run_server,
        kwargs={"host": host, "port": port},
        name="context-debug-webui",
        daemon=True,
    )
    thread.start()
    return thread


def main():
    parser = argparse.ArgumentParser(description="启动 Yuki Context Debug WebUI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8777)
    args = parser.parse_args()
    run_server(args.host, args.port)


if __name__ == "__main__":
    main()
