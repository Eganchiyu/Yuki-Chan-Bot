# modules/debug/webui_server.py
import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from modules.debug.context_snapshot import context_snapshot_store


HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Yuki Context Debug WebUI</title>
  <style>
    :root{color-scheme:dark;--bg:#070b18;--card:rgba(255,255,255,.08);--line:rgba(255,255,255,.14);--text:#eef4ff;--muted:#aab7d4;--cyan:#65e4ff;--purple:#c084fc;--green:#8bf5c2;--yellow:#fde68a;--red:#fca5a5;--blue:#7aa7ff}
    *{box-sizing:border-box}body{margin:0;min-height:100vh;font-family:"Microsoft YaHei","Segoe UI",system-ui,sans-serif;color:var(--text);background:radial-gradient(circle at 12% 8%,rgba(101,228,255,.2),transparent 34%),radial-gradient(circle at 82% 16%,rgba(192,132,252,.18),transparent 32%),var(--bg)}
    .page{width:min(1600px,calc(100vw - 32px));margin:0 auto;padding:24px 0 36px}.hero,.card{border:1px solid var(--line);background:var(--card);box-shadow:0 24px 80px rgba(0,0,0,.32);backdrop-filter:blur(18px)}.hero{border-radius:26px;padding:24px}.top{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}.actions{display:flex;gap:8px;flex-wrap:wrap}button{border:1px solid var(--line);border-radius:12px;background:rgba(255,255,255,.08);color:var(--text);padding:9px 12px;cursor:pointer}button:hover{border-color:rgba(101,228,255,.45)}h1{margin:0 0 10px;font-size:34px}.sub,.muted{color:var(--muted)}.pill{display:inline-flex;align-items:center;gap:8px;padding:7px 10px;border:1px solid var(--line);border-radius:999px;background:rgba(255,255,255,.07);font-size:13px;color:var(--muted);margin:4px 6px 0 0}.dot{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 16px var(--green)}
    .layout{display:grid;grid-template-columns:290px minmax(0,1fr) 360px;gap:16px;margin-top:16px}.card{border-radius:22px;padding:16px;min-width:0}h2{font-size:16px;margin:0 0 14px}.sessions{display:grid;gap:10px;max-height:72vh;overflow:auto}.session{padding:12px;border:1px solid var(--line);border-radius:16px;background:rgba(255,255,255,.05);cursor:pointer}.session.active{border-color:var(--cyan);box-shadow:0 0 0 1px rgba(101,228,255,.25) inset}.session b{display:block;margin-bottom:6px}.preview{font-size:12px;color:var(--muted);line-height:1.5;word-break:break-all}.messages{display:grid;gap:12px}.msg{border:1px solid var(--line);border-radius:16px;overflow:hidden;background:rgba(0,0,0,.16)}.msg summary{cursor:pointer;padding:12px 14px;display:flex;gap:10px;align-items:center}.role{padding:3px 8px;border-radius:999px;font-size:12px;background:rgba(122,167,255,.18);color:#dbe7ff}.role.system{background:rgba(192,132,252,.18);color:#f1ddff}.role.user{background:rgba(101,228,255,.16);color:#d8f7ff}.role.assistant{background:rgba(139,245,194,.16);color:#d9ffec}.role.tool{background:rgba(253,230,138,.16);color:#fff5c9}.content{white-space:pre-wrap;word-break:break-word;line-height:1.65;color:#eaf2ff;padding:0 14px 14px;max-height:420px;overflow:auto}.panel{display:grid;gap:12px}.json{white-space:pre-wrap;word-break:break-word;max-height:300px;overflow:auto;font-size:12px;line-height:1.55;color:#d8e8ff;background:rgba(0,0,0,.18);border-radius:14px;padding:12px}.mem{padding:10px;border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.04);font-size:13px;line-height:1.55}.timeline{display:grid;grid-template-columns:repeat(8,1fr);gap:8px;margin-top:16px}.step{border:1px solid var(--line);border-radius:14px;padding:10px;background:rgba(255,255,255,.05);font-size:12px;color:var(--muted)}.step.done{border-color:rgba(139,245,194,.35);color:#d5ffe9}.empty{padding:40px;text-align:center;color:var(--muted)}@media(max-width:1100px){.layout{grid-template-columns:1fr}.timeline{grid-template-columns:repeat(2,1fr)}}
  </style>
</head>
<body><main class="page">
  <section class="hero"><div class="top"><div><h1>Yuki Context Debug WebUI</h1><div class="sub">本地只读调试页面，展示 LLM messages、RAG 与 Yuki-Memory 召回快照。</div><div id="status"></div></div><div class="actions"><button onclick="refreshAll()">刷新</button><button onclick="togglePause()" id="pauseBtn">暂停自动刷新</button><button onclick="copySnapshot()">复制当前上下文</button><button onclick="downloadSnapshot()">导出 snapshot JSON</button></div></div></section>
  <section class="layout"><aside class="card"><h2>最近会话</h2><div id="sessions" class="sessions"></div></aside><section class="card"><h2>完整构建上下文</h2><div id="messages" class="messages empty">暂无 snapshot</div></section><aside class="card panel"><div><h2>记忆召回</h2><div id="memories"></div></div><div><h2>Snapshot JSON</h2><div id="snapshotJson" class="json">{}</div></div></aside></section>
  <section class="card"><h2>Pipeline 阶段时间线</h2><div id="timeline" class="timeline"></div></section>
</main><script>
let selectedId=null,current=null,paused=false;const stages=['prepare_message_batch','normalize_incoming_content','prepare_chat_context','decide_reply_action','retrieve_memories','generate_reply','send_reply','finalize_conversation'];
async function api(path){const r=await fetch(path);return await r.json()}function esc(s){return String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function meta(){return current?`chat_id=${current.chat_id||''} · stage=${current.stage||''} · tokens≈${current.token_estimate?.estimated_tokens||0}`:'等待数据'}
async function refreshAll(){const [status,list]=await Promise.all([api('/api/status'),api('/api/snapshots?limit=80')]);document.getElementById('status').innerHTML=`<span class="pill"><i class="dot"></i>online</span><span class="pill">刷新 ${status.generated_at}</span><span class="pill">snapshots ${status.snapshot_count}</span><span class="pill">${meta()}</span>`;renderSessions(list);if(!selectedId&&status.latest_snapshot_id)selectedId=status.latest_snapshot_id;if(selectedId)await loadSnapshot(selectedId)}
function renderSessions(list){document.getElementById('sessions').innerHTML=list.length?list.map(x=>`<div class="session ${x.snapshot_id===selectedId?'active':''}" onclick="selectSnapshot('${x.snapshot_id}')"><b>${esc(x.chat_id||'-')}</b><div class="preview">${esc(x.mode||'')} · ${esc(x.stage||'')} · ${esc(x.updated_at||x.created_at||'')}</div><div class="preview">${esc(x.combined_text_preview||'')}</div><div class="preview">messages ${x.built_message_count||0} · tokens≈${x.estimated_tokens||0}</div></div>`).join(''):'<div class="empty">暂无 snapshot</div>'}
async function selectSnapshot(id){selectedId=id;await loadSnapshot(id);await refreshAll()}async function loadSnapshot(id){current=await api('/api/snapshots/'+encodeURIComponent(id));renderSnapshot()}
function renderSnapshot(){document.getElementById('snapshotJson').textContent=JSON.stringify(current,null,2);const messages=current.built_messages||[];document.getElementById('messages').className=messages.length?'messages':'messages empty';document.getElementById('messages').innerHTML=messages.length?messages.map((m,i)=>{const c=typeof m.content==='string'?m.content:JSON.stringify(m.content,null,2);return `<details class="msg" ${i<3?'open':''}><summary><span class="role ${esc(m.role)}">${esc(m.role||'unknown')}</span><span class="muted">#${i+1} · chars ${c.length} · tokens≈${Math.max(1,Math.floor(c.length/2))}</span><button onclick="event.stopPropagation();navigator.clipboard.writeText(${JSON.stringify(c)})">复制</button></summary><div class="content">${esc(c)}</div></details>`}).join(''):'暂无完整 messages';renderMemories();renderTimeline()}
function renderMemories(){const old=current.relevant_diaries||[];let html=`<h2>RAG 回忆</h2>${old.length?old.map(x=>`<div class="mem">${esc(typeof x==='string'?x:JSON.stringify(x,null,2))}</div>`).join(''):'<div class="muted">无</div>'}`;document.getElementById('memories').innerHTML=html}
function renderTimeline(){const latency=current.latency||{};const stage=current.stage||'';document.getElementById('timeline').innerHTML=stages.map(s=>`<div class="step ${(latency[s]||stage===s)?'done':''}"><b>${s}</b><br>${latency[s]??''}</div>`).join('')}
function togglePause(){paused=!paused;document.getElementById('pauseBtn').textContent=paused?'恢复自动刷新':'暂停自动刷新'}function copySnapshot(){if(current)navigator.clipboard.writeText(JSON.stringify(current,null,2))}function downloadSnapshot(){if(!current)return;const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(current,null,2)],{type:'application/json'}));a.download=(current.snapshot_id||'snapshot')+'.json';a.click()}setInterval(()=>{if(!paused)refreshAll()},2000);refreshAll();
</script></body></html>"""


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

    def _send_html(self):
        body = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            if path == "/":
                self._send_html()
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
            else:
                self._send_json({"ok": False, "error": "not_found"}, 404)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, 500)


def run_server(host="127.0.0.1", port=8777):
    server = ThreadingHTTPServer((host, port), ContextDebugRequestHandler)
    print(f"Yuki Context Debug WebUI: http://{host}:{port}/")
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
