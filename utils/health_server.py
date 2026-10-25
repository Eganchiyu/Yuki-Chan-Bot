"""极简健康探针：给宿主 supervisor 判断「新进程真的活了」。

为什么不用 aiohttp：探针必须能在事件循环还没跑起来、或者循环被卡住时响应，
所以用独立线程 + 标准库 http.server，不占 asyncio 循环。

契约（宿主 deploy/supervisor.py 依赖）：
    GET /health -> 200 {"status":"ok",   "ready":true,  ...}
                   503 {"status":"starting","ready":false,...}
    POST /notify -> 由容器内的回调处理，用于「告诉她即将重启」这类需要用到
                    Yuki 自己的 NapCat 连接才能做的事（supervisor 在宿主，
                    没有 WS 连接，只有这个端口）。
    ready 由 main.py 在初始化完成后置 True，napcat 在线状态由探针回调实时读取。
"""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_HEALTH_PORT = 8778

_started_at = time.time()
_ready = False
_detail = {}
_probe = None
_notifier = None
_server = None
_lock = threading.Lock()


def set_ready(value: bool = True, **detail) -> None:
    """初始化完成后调用，标记可以对流量负责了。"""
    global _ready, _detail
    _ready = bool(value)
    if detail:
        _detail.update(detail)


def set_notifier(fn) -> None:
    """注册 POST /notify 的处理函数：fn(payload) -> (ok, detail)。

    它在 HTTP 线程里被调用，实现方负责把协程安全地调度回事件循环并等结果，
    这样调用方（supervisor）能确认消息真的发出去了再动手重启。
    """
    global _notifier
    _notifier = fn


def set_probe(fn) -> None:
    """注册状态回调，每次 /health 请求时调用，返回 dict 合并进响应。"""
    global _probe
    _probe = fn


def _snapshot() -> dict:
    payload = {
        "status": "ok" if _ready else "starting",
        "ready": _ready,
        "pid": os.getpid(),
        "uptime": round(time.time() - _started_at, 1),
        "dry_run": _is_dry_run(),
    }
    payload.update(_detail)
    if _probe is not None:
        try:
            extra = _probe()
            if isinstance(extra, dict):
                payload.update(extra)
        except Exception as e:
            payload["probe_error"] = str(e)
    return payload


def _is_dry_run() -> bool:
    return os.getenv("YUKI_DRY_RUN", "").strip().lower() in {"1", "true", "yes", "on"}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - 标准库约定
        if self.path.split("?")[0] not in {"/health", "/"}:
            self.send_response(404)
            self.end_headers()
            return
        payload = _snapshot()
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200 if payload["ready"] else 503)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802 - 标准库约定
        if self.path.split("?")[0] != "/notify":
            self.send_response(404)
            self.end_headers()
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw or b"{}")
        except Exception as e:
            self._reply(400, {"ok": False, "detail": f"payload 无法解析: {e}"})
            return
        if _notifier is None:
            self._reply(503, {"ok": False, "detail": "容器内未注册通知处理函数"})
            return
        try:
            result = _notifier(payload)
            ok, detail = result if isinstance(result, tuple) else (bool(result), "")
        except Exception as e:
            self._reply(500, {"ok": False, "detail": f"处理通知失败: {e}"})
            return
        self._reply(200 if ok else 500, {"ok": bool(ok), "detail": str(detail)})

    def _reply(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # 探针不刷日志
        return


def start_health_server(host: str = None, port: int = None) -> bool:
    """启动探针服务（幂等）。返回是否成功持有端口。"""
    global _server
    with _lock:
        if _server is not None:
            return True
        host = host or os.getenv("YUKI_HEALTH_HOST", "0.0.0.0")
        try:
            port = int(port or os.getenv("YUKI_HEALTH_PORT", DEFAULT_HEALTH_PORT))
        except Exception:
            port = DEFAULT_HEALTH_PORT
        try:
            server = ThreadingHTTPServer((host, port), _Handler)
        except OSError as e:
            print(f"[Health] 探针端口 {host}:{port} 不可用: {e}")
            return False
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, name="yuki-health", daemon=True)
        thread.start()
        _server = server
        return True
