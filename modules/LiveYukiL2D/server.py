from __future__ import annotations

import asyncio
import base64
import ctypes
import ctypes.wintypes
import json
import mimetypes
import socket
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote

try:
    from .liveyuki_l2d.events import error_event
    from .liveyuki_l2d.protocol import set_model_message
except ImportError:
    from liveyuki_l2d.events import error_event
    from liveyuki_l2d.protocol import set_model_message

try:
    from aiohttp import web, WSMsgType
except ImportError as exc:
    raise SystemExit(
        "缺少 aiohttp。先运行：uv add aiohttp 或 pip install aiohttp"
    ) from exc

ROOT = Path(__file__).resolve().parent
MODELS_DIR = ROOT / "models"
FRONTEND_DIR = ROOT / "frontend" / "minimal" / "dist"
CONFIG_PATH = ROOT / "config.json"
HISTORY_PATH = ROOT / "data" / "conversation.json"
HOST = "127.0.0.1"
PORT = 18765
MAX_AUDIO_BYTES = 10 * 1024 * 1024
MAX_AUDIO_BASE64_LENGTH = 14 * 1024 * 1024

CLIENTS: set[web.WebSocketResponse] = set()
SERVER_LOOP: Any | None = None

DEFAULT_CONFIG: dict[str, Any] = {
    "desktopPet": {
        "enabled": True,
        "width": 420,
        "height": 640,
        "x": None,
        "y": None,
        "transparent": True,
        "frameless": True,
        "alwaysOnTop": True,
        "resizable": True,
        "mousePassthrough": True,
        "lookAtMouse": True,
    },
    "model": {
        "kScale": 1.0,
        "scrollToResize": True,
    },
    "llm": {
        "baseUrl": "",
        "apiKey": "",
        "model": "",
        "timeoutSeconds": 60,
        "systemPrompt": "你是 Yuki，一个友善、简洁的桌面 Live2D 助手。请用中文回答。",
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"config.json 格式错误：{exc}") from exc
    return deep_merge(DEFAULT_CONFIG, data)


def public_config() -> dict[str, Any]:
    config = json.loads(json.dumps(load_config(), ensure_ascii=False))
    llm_config = config.get("llm")
    if isinstance(llm_config, dict) and llm_config.get("apiKey"):
        llm_config["apiKey"] = "***"
    return config


def get_yuki_model_info() -> dict[str, Any]:
    config = load_config()
    model_config = config.get("model", {})
    pet_config = config.get("desktopPet", {})
    return {
        "name": "Yuki",
        "url": f"http://{HOST}:{PORT}/models/Yuki/Yuki.model3.json",
        "kScale": model_config.get("kScale", 1.0),
        "initialXshift": 0,
        "initialYshift": 0,
        "idleMotionGroupName": "Idle",
        "defaultEmotion": 0,
        "emotionMap": {"neutral": 0},
        "tapMotions": {},
        "pointerInteractive": True,
        "scrollToResize": model_config.get("scrollToResize", True),
        "lookAtMouse": pet_config.get("lookAtMouse", True),
        "desktopPet": pet_config,
    }


def json_response(data: Any, status: int = 200) -> web.Response:
    return web.Response(
        text=json.dumps(data, ensure_ascii=False, indent=2),
        status=status,
        content_type="application/json",
    )


def safe_join(base: Path, rel: str) -> Path:
    rel = unquote(rel).replace("\\", "/").lstrip("/")
    path = (base / rel).resolve()
    try:
        path.relative_to(base.resolve())
    except ValueError:
        raise web.HTTPForbidden(text="invalid path")
    return path


async def index(_: web.Request) -> web.Response:
    path = FRONTEND_DIR / "index.html"
    return web.FileResponse(path)


async def frontend_static(request: web.Request) -> web.StreamResponse:
    rel = request.match_info.get("path", "")
    path = safe_join(FRONTEND_DIR, rel)
    if path.is_dir():
        path = path / "index.html"
    if not path.exists():
        raise web.HTTPNotFound(text=f"not found: {rel}")
    return web.FileResponse(path)


async def model_static(request: web.Request) -> web.StreamResponse:
    rel = request.match_info.get("path", "")
    path = safe_join(MODELS_DIR, rel)
    if not path.exists() or not path.is_file():
        raise web.HTTPNotFound(text=f"not found: {rel}")

    ctype, _ = mimetypes.guess_type(str(path))
    if path.suffix == ".moc3":
        ctype = "application/octet-stream"
    elif path.name.endswith(".model3.json") or path.suffix == ".json":
        ctype = "application/json"
    elif path.suffix == ".png":
        ctype = "image/png"
    return web.FileResponse(path, headers={"Content-Type": ctype or "application/octet-stream"})


async def _broadcast_on_server_loop(message: dict[str, Any]) -> None:
    dead: list[web.WebSocketResponse] = []
    text = json.dumps(message, ensure_ascii=False)
    for ws in tuple(CLIENTS):
        if ws.closed:
            dead.append(ws)
            continue
        try:
            await ws.send_str(text)
        except Exception:
            dead.append(ws)
    for ws in dead:
        CLIENTS.discard(ws)


async def broadcast(message: dict[str, Any]) -> None:
    current_loop = asyncio.get_running_loop()
    if SERVER_LOOP is None or current_loop is SERVER_LOOP:
        await _broadcast_on_server_loop(message)
        return

    future = asyncio.run_coroutine_threadsafe(_broadcast_on_server_loop(message), SERVER_LOOP)
    await asyncio.wrap_future(future)


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    CLIENTS.add(ws)
    print(f"[ws] client connected, total={len(CLIENTS)}")

    await ws.send_str(json.dumps(set_model_message(get_yuki_model_info()), ensure_ascii=False))
    await ws.send_str(json.dumps({"type": "say", "text": "Yuki 模型加载中..."}, ensure_ascii=False))

    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            try:
                data = json.loads(msg.data)
            except json.JSONDecodeError:
                await ws.send_str(json.dumps(error_event("消息不是有效 JSON"), ensure_ascii=False))
                continue
            if not isinstance(data, dict):
                await ws.send_str(json.dumps(error_event("消息必须是 JSON 对象"), ensure_ascii=False))
                continue
            message_type = data.get("type")
            pipeline = request.app.get("session_pipeline")
            try:
                if message_type == "user-input":
                    text = data.get("text")
                    if not isinstance(text, str) or not text.strip():
                        raise ValueError("请输入文本")
                    text = text.strip()
                    if len(text) > 4000:
                        raise ValueError("输入不能超过 4000 个字符")
                    if pipeline is None:
                        raise RuntimeError("桌宠聊天需要从 YukiV6 主程序启动。")
                    message_obj = {
                        "name": "桌宠主人",
                        "content": f'【"桌宠主人"】说: {text}',
                        "raw_text": text,
                        "is_bot": False,
                        "user_id": 0,
                        "message_id": None,
                    }
                    pipeline_loop = request.app.get("pipeline_loop")
                    coro = pipeline.enqueue_message(
                        "desktop_pet",
                        "desktop_pet",
                        message_obj=message_obj,
                        debounce_flag=False,
                        force_reply=True,
                    )
                    if pipeline_loop is None:
                        await coro
                    else:
                        future = asyncio.run_coroutine_threadsafe(coro, pipeline_loop)
                        await asyncio.wrap_future(future)
                elif message_type == "cancel":
                    await ws.send_str(json.dumps(error_event("桌宠管线暂未支持中断当前回复"), ensure_ascii=False))
                elif message_type == "clear-history":
                    await ws.send_str(json.dumps({"type": "say", "text": "桌宠历史清理会在后续接入。"}, ensure_ascii=False))
                else:
                    await ws.send_str(json.dumps(error_event(f"未知消息类型：{message_type}"), ensure_ascii=False))
            except Exception as exc:
                await ws.send_str(json.dumps(error_event(str(exc)), ensure_ascii=False))
        elif msg.type == WSMsgType.ERROR:
            print("[ws] error:", ws.exception())

    CLIENTS.discard(ws)
    print(f"[ws] client disconnected, total={len(CLIENTS)}")
    return ws


async def api_config(_: web.Request) -> web.Response:
    return json_response(public_config())


async def api_model(_: web.Request) -> web.Response:
    model_info = get_yuki_model_info()
    await broadcast(set_model_message(model_info))
    return json_response({"ok": True, "model_info": model_info, "clients": len(CLIENTS)})


async def api_say(request: web.Request) -> web.Response:
    text = request.query.get("text", "你好，我是 Yuki")
    expr_raw = request.query.get("expression")
    expression: int | str | None = None
    if expr_raw is not None:
        try:
            expression = int(expr_raw)
        except ValueError:
            expression = expr_raw

    msg = {"type": "say", "text": text}
    if expression is not None:
        msg["expression"] = expression
    await broadcast(msg)
    return json_response({"ok": True, "sent": msg, "clients": len(CLIENTS)})


async def api_cursor(_: web.Request) -> web.Response:
    point = ctypes.wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    return json_response({"x": point.x, "y": point.y})


async def api_audio(request: web.Request) -> web.Response:
    if request.content_length and request.content_length > MAX_AUDIO_BASE64_LENGTH:
        return json_response({"ok": False, "error": "audio payload too large"}, 413)
    data = await request.json()
    audio_path = data.get("path")
    text = data.get("text", "")
    expression = data.get("expression")
    audio_b64 = data.get("audio", "")
    if not isinstance(audio_b64, str):
        return json_response({"ok": False, "error": "audio must be base64 string"}, 400)
    if len(audio_b64) > MAX_AUDIO_BASE64_LENGTH:
        return json_response({"ok": False, "error": "audio payload too large"}, 413)

    if audio_path and not audio_b64:
        try:
            path = safe_join(ROOT, str(audio_path))
        except web.HTTPException:
            return json_response({"ok": False, "error": "invalid audio path"}, 403)
        if not path.is_file() or path.suffix.lower() != ".wav":
            return json_response({"ok": False, "error": "audio file not found or unsupported"}, 404)
        if path.stat().st_size > MAX_AUDIO_BYTES:
            return json_response({"ok": False, "error": "audio file too large"}, 413)
        audio_b64 = base64.b64encode(path.read_bytes()).decode("ascii")

    msg: dict[str, Any] = {
        "type": "audio",
        "audio": audio_b64,
        "volumes": [],
        "slice_length": 0,
        "display_text": {"text": text, "name": "Yuki", "avatar": ""},
        "actions": {},
    }
    if expression is not None:
        msg["actions"]["expressions"] = [expression]

    await broadcast(msg)
    return json_response({"ok": True, "sent_text": text, "has_audio": bool(audio_b64), "clients": len(CLIENTS)})


def create_app(
    session_pipeline: Any | None = None,
    pipeline_loop: asyncio.AbstractEventLoop | None = None,
) -> web.Application:
    app = web.Application()
    app["session_pipeline"] = session_pipeline
    app["pipeline_loop"] = pipeline_loop

    async def remember_server_loop(_: web.Application) -> None:
        global SERVER_LOOP
        SERVER_LOOP = asyncio.get_running_loop()

    app.on_startup.append(remember_server_loop)
    app.router.add_get("/", index)
    app.router.add_get("/ws", websocket_handler)
    app.router.add_get("/api/config", api_config)
    app.router.add_get("/api/model", api_model)
    app.router.add_get("/api/say", api_say)
    app.router.add_get("/api/cursor", api_cursor)
    app.router.add_post("/api/audio", api_audio)
    app.router.add_get("/models/{path:.*}", model_static)
    app.router.add_get("/{path:.*}", frontend_static)
    return app


def is_server_running() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((HOST, PORT)) == 0


def main(
    handle_signals: bool = True,
    session_pipeline: Any | None = None,
    pipeline_loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    print(f"LiveYukiL2D server: http://{HOST}:{PORT}")
    print(f"Serving model: {get_yuki_model_info()['url']}")
    app = create_app(session_pipeline, pipeline_loop)
    web.run_app(app, host=HOST, port=PORT, handle_signals=handle_signals, access_log=None)


def start_background_server(
    session_pipeline: Any | None = None,
    pipeline_loop: asyncio.AbstractEventLoop | None = None,
) -> threading.Thread | None:
    if is_server_running():
        print(f"LiveYukiL2D server already running: http://{HOST}:{PORT}")
        return None

    server_thread = threading.Thread(
        target=main,
        kwargs={
            "handle_signals": False,
            "session_pipeline": session_pipeline,
            "pipeline_loop": pipeline_loop,
        },
        daemon=True,
    )
    server_thread.start()

    for _ in range(30):
        if is_server_running():
            return server_thread
        time.sleep(0.1)

    raise RuntimeError(f"服务启动超时：http://{HOST}:{PORT}")


if __name__ == "__main__":
    main()
