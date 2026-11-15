# modules/debug/webui_server.py
import argparse
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from modules.debug.context_snapshot import context_snapshot_store
from modules.debug.phone_trace import phone_trace_store


WEBUI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webui")
INDEX_HTML_PATH = os.path.join(WEBUI_DIR, "index.html")

_STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".woff2": "font/woff2",
    ".json": "application/json; charset=utf-8",
}


def read_index_html() -> str:
    """读取拆分后的单页入口（assets 走 /static/，入口保持一次读盘便于热改）。"""
    with open(INDEX_HTML_PATH, "r", encoding="utf-8") as fh:
        return fh.read()

_STEP_IMG_RE = re.compile(r"^/api/phone/sessions/([^/]+)/steps/(\d+)/(yuki|raw)\.jpg$")
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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

    def _send_html(self, html_text=None):
        try:
            body = (html_text if html_text is not None else read_index_html()).encode("utf-8")
        except OSError as exc:
            self._send_json({"ok": False, "error": f"webui_missing: {exc}"}, 500)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, rel_path):
        """只允许读取 webui/ 目录内的静态资源（css / js / html）。"""
        clean = os.path.normpath(unquote(rel_path)).lstrip("/\\")
        target = os.path.abspath(os.path.join(WEBUI_DIR, clean))
        if not target.startswith(os.path.abspath(WEBUI_DIR) + os.sep):
            self._send_json({"ok": False, "error": "forbidden"}, 403)
            return
        if not os.path.isfile(target):
            self._send_json({"ok": False, "error": "static_not_found", "path": clean}, 404)
            return
        ctype = _STATIC_TYPES.get(os.path.splitext(target)[1].lower(), "application/octet-stream")
        with open(target, "rb") as fh:
            data = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

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
            if path in ("/", "/analytics", "/analytics/", "/autonomous", "/autonomous/"):
                self._send_html()
            elif path in ("/phone", "/phone/"):
                self._send_html()
            elif path.startswith("/static/"):
                self._send_static(path[len("/static/"):])
            elif path == "/assets/yuki_help.png":
                help_path = os.path.join(_ROOT_DIR, "yuki_help.png")
                if os.path.isfile(help_path):
                    with open(help_path, "rb") as f:
                        self._send_bytes(f.read(), "image/png", 200)
                else:
                    self._send_json({"ok": False, "error": "asset_not_found"}, 404)
            elif path == "/api/health":
                self._send_json({"ok": True})
            elif path == "/api/status":
                self._send_json(context_snapshot_store.status())
            elif path == "/api/analytics":
                self._send_json(context_snapshot_store.analytics())
            elif path == "/api/yuki/state":
                self._send_json(context_snapshot_store.yuki_runtime_state())
            elif path == "/api/autonomous":
                limit = int((query.get("limit") or [10])[0])
                try:
                    from modules.autonomous.inspect import autonomous_snapshot

                    self._send_json(autonomous_snapshot(limit=limit))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, 500)
            elif path == "/api/autonomous/runs":
                limit = int((query.get("limit") or [30])[0])
                try:
                    from modules.autonomous.inspect import autonomous_transcripts

                    self._send_json(autonomous_transcripts(limit=limit))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, 500)
            elif path.startswith("/api/autonomous/runs/"):
                run_id = unquote(path.removeprefix("/api/autonomous/runs/"))
                try:
                    from modules.autonomous.inspect import autonomous_transcript

                    payload = autonomous_transcript(run_id)
                    self._send_json(payload, 200 if payload.get("ok") else 404)
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, 500)
            elif path == "/api/snapshots":
                limit = int((query.get("limit") or [50])[0])
                chat_id = (query.get("chat_id") or [None])[0]
                self._send_json(context_snapshot_store.list_recent(limit=limit, chat_id=chat_id))
            elif path == "/api/latest":
                chat_id = (query.get("chat_id") or [None])[0]
                self._send_json(context_snapshot_store.latest(chat_id) or {})
            elif path.startswith("/api/snapshots/"):
                snapshot_id = unquote(path.removepurb(path) if hasattr(path, "removepurb") else path.removeprefix("/api/snapshots/"))
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
    print(f"Yuki Debug WebUI: http://{host}:{port}/ "
          f"(Autonomous: http://{host}:{port}/autonomous, Phone: http://{host}:{port}/phone)")

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
