# modules/debug/phone_trace.py
"""手机操作轨迹与实时画面监控存储（内存 + data/phone_traces/ 持久化）。"""
from __future__ import annotations

import copy
import datetime
import io
import json
import os
import re
import subprocess
import threading
import time
import uuid
from collections import deque
from typing import Any, Optional

from config import cfg
from utils.logger import get_logger

logger = get_logger("tools")

_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _now_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _default_base_dir() -> str:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "data", "phone_traces")


class PhoneTraceStore:
    """记录手机聚焦会话、每步耗时、Yuki 视角截图（标注图/原图）以及收发原文本。"""

    def __init__(self, base_dir: Optional[str] = None, max_sessions: int = 80):
        self._is_default_dir = base_dir is None
        self.base_dir = base_dir or _default_base_dir()
        self.max_sessions = max_sessions
        self._lock = threading.RLock()
        self._sessions: deque[dict[str, Any]] = deque(maxlen=max_sessions)
        self._by_id: dict[str, dict[str, Any]] = {}
        self._active_by_chat: dict[str, str] = {}
        self._pending_turn_context: dict[str, dict[str, Any]] = {}
        # 实时画面短缓存（避免前端高频轮询压垮 adb screencap）
        self._live_lock = threading.Lock()
        self._live_jpeg: bytes = b""
        self._live_ts: float = 0.0
        self._live_elapsed_ms: int = 0
        self._live_error: str = ""
        self._load_existing()

    def _load_existing(self) -> None:
        try:
            if not os.path.isdir(self.base_dir):
                return
            entries = []
            for name in os.listdir(self.base_dir):
                sdir = os.path.join(self.base_dir, name)
                sfile = os.path.join(sdir, "session.json")
                if os.path.isdir(sdir) and os.path.isfile(sfile):
                    try:
                        entries.append((os.path.getmtime(sfile), sfile))
                    except OSError:
                        continue
            entries.sort(key=lambda x: x[0])
            for _, sfile in entries[-self.max_sessions:]:
                try:
                    with open(sfile, encoding="utf-8") as f:
                        data = json.load(f)
                    sid = str(data.get("session_id") or "")
                    if sid:
                        self._sessions.append(data)
                        self._by_id[sid] = data
                except Exception as exc:
                    logger.debug(f"[PhoneTrace] 读取历史轨迹失败 {sfile}: {exc}")
        except Exception as exc:
            logger.debug(f"[PhoneTrace] 初始化历史目录失败: {exc}")

    def _session_dir(self, session_id: str) -> str:
        safe = _SAFE_ID_RE.sub("_", str(session_id)).strip("_") or "default"
        return os.path.join(self.base_dir, safe)

    def _should_persist(self) -> bool:
        return not (self._is_default_dir and "PYTEST_CURRENT_TEST" in os.environ)

    def _persist_session(self, session: dict[str, Any]) -> None:
        if not self._should_persist():
            return
        try:
            sdir = self._session_dir(session["session_id"])
            os.makedirs(sdir, exist_ok=True)
            tmp_path = os.path.join(sdir, "session.json.tmp")
            final_path = os.path.join(sdir, "session.json")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(session, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, final_path)
        except Exception as exc:
            logger.debug(f"[PhoneTrace] 持久化 session 失败: {exc}")

    # ---------------- 会话与上下文关联 ----------------

    def set_turn_incoming(self, chat_id: str, incoming_text: str) -> None:
        """在每轮对话进入工具链时记录 Yuki 收到的原始用户文本。"""
        cid = str(chat_id)
        text = (incoming_text or "").strip()
        with self._lock:
            ctx = self._pending_turn_context.setdefault(cid, {})
            ctx["incoming_text"] = text
            ctx["incoming_at"] = _now_str()
            sid = self._active_by_chat.get(cid)
            if sid and sid in self._by_id and text:
                sess = self._by_id[sid]
                msgs = sess.setdefault("incoming_messages", [])
                if not msgs or msgs[-1].get("text") != text:
                    msgs.append({"time": _now_str(), "text": text})
                    sess["updated_at"] = _now_str()
                    self._persist_session(sess)

    def set_pending_model_call(self, chat_id: str, thought_text: str, tool_calls: list[dict]) -> None:
        """在模型发起手机工具调用前，记录模型输出的原文本（思考/过渡回复 + tool_calls）。"""
        cid = str(chat_id)
        formatted_calls = []
        for c in tool_calls or []:
            fn = c.get("function") or {}
            formatted_calls.append({
                "name": fn.get("name") or "",
                "arguments": fn.get("arguments") or "",
            })
        parts = []
        if (thought_text or "").strip():
            parts.append((thought_text or "").strip())
        for fc in formatted_calls:
            parts.append(f"[调用 {fc['name']}] {fc['arguments']}")
        raw_reply = "\n".join(parts)

        with self._lock:
            ctx = self._pending_turn_context.setdefault(cid, {})
            ctx["last_model_reply"] = raw_reply
            ctx["last_thought"] = (thought_text or "").strip()
            ctx["last_tool_calls"] = formatted_calls
            sid = self._active_by_chat.get(cid)
            if sid and sid in self._by_id and (thought_text or "").strip():
                sess = self._by_id[sid]
                out = sess.setdefault("outgoing_messages", [])
                out.append({
                    "time": _now_str(),
                    "kind": "thought",
                    "text": (thought_text or "").strip(),
                })
                sess["updated_at"] = _now_str()
                self._persist_session(sess)

    def record_turn_final_reply(self, chat_id: str, raw_reply: str, clean_reply: str = "") -> None:
        """记录 Yuki 在本轮结束时的最终回复原文本。"""
        cid = str(chat_id)
        text = (raw_reply or clean_reply or "").strip()
        if not text:
            return
        with self._lock:
            sid = self._active_by_chat.get(cid)
            # 若刚在同轮退出聚焦，找最近一个属于该 chat_id 的会话写入最终回复
            target_sess = self._by_id.get(sid) if sid else None
            if target_sess is None and self._sessions:
                for item in reversed(self._sessions):
                    if str(item.get("chat_id")) == cid:
                        target_sess = item
                        break
            if target_sess is not None:
                out = target_sess.setdefault("outgoing_messages", [])
                out.append({
                    "time": _now_str(),
                    "kind": "final",
                    "text": text,
                })
                target_sess["last_final_reply"] = text
                target_sess["updated_at"] = _now_str()
                if target_sess.get("steps"):
                    last_step = target_sess["steps"][-1]
                    if not last_step.get("yuki_final_reply"):
                        last_step["yuki_final_reply"] = text
                self._persist_session(target_sess)

    def start_session(self, chat_id: str, goal: str = "") -> str:
        """开启或复用当前 chat_id 的手机操作轨迹会话。"""
        cid = str(chat_id)
        with self._lock:
            existing_id = self._active_by_chat.get(cid)
            if existing_id and existing_id in self._by_id:
                sess = self._by_id[existing_id]
                if sess.get("status") == "running":
                    if goal and not sess.get("goal"):
                        sess["goal"] = goal
                    return existing_id

            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            short = uuid.uuid4().hex[:6]
            session_id = f"{ts}_{_SAFE_ID_RE.sub('_', cid)}_{short}"
            pending = self._pending_turn_context.get(cid) or {}
            incoming_text = pending.get("incoming_text") or ""
            incoming_msgs = (
                [{"time": pending.get("incoming_at") or _now_str(), "text": incoming_text}]
                if incoming_text
                else []
            )
            session = {
                "session_id": session_id,
                "chat_id": cid,
                "goal": (goal or "").strip(),
                "status": "running",
                "created_at": _now_str(),
                "updated_at": _now_str(),
                "total_elapsed_ms": 0,
                "step_count": 0,
                "last_incoming_text": incoming_text,
                "last_final_reply": "",
                "summary": "",
                "incoming_messages": incoming_msgs,
                "outgoing_messages": [],
                "steps": [],
            }
            self._sessions.append(session)
            self._by_id[session_id] = session
            self._active_by_chat[cid] = session_id
            self._persist_session(session)
            return session_id

    def finish_session(self, chat_id: str, summary: str = "", status: str = "finished") -> None:
        cid = str(chat_id)
        with self._lock:
            sid = self._active_by_chat.pop(cid, None)
            if not sid or sid not in self._by_id:
                return
            sess = self._by_id[sid]
            sess["status"] = status
            if summary:
                sess["summary"] = summary
            sess["updated_at"] = _now_str()
            self._persist_session(sess)

    def record_step(
        self,
        chat_id: str,
        *,
        tool_name: str = "phone_action",
        action: str = "",
        target: Any = None,
        text: str = "",
        note: str = "",
        step_display: str = "",
        package: str = "",
        node_count: int = 0,
        success: bool = True,
        error: str = "",
        elapsed_ms: int = 0,
        timing_breakdown: Optional[dict[str, int]] = None,
        tool_result_text: str = "",
        raw_png_bytes: Optional[bytes] = None,
        annotated_jpeg_bytes: Optional[bytes] = None,
    ) -> dict[str, Any]:
        """记录单步手机操作轨迹并保存原图与标注图。"""
        cid = str(chat_id)
        with self._lock:
            sid = self._active_by_chat.get(cid)
            if not sid or sid not in self._by_id:
                sid = self.start_session(cid, goal=note or action)
            sess = self._by_id[sid]
            step_index = len(sess["steps"]) + 1
            pending = self._pending_turn_context.get(cid) or {}
            incoming_text = pending.get("incoming_text") or sess.get("last_incoming_text") or ""
            if incoming_text:
                sess["last_incoming_text"] = incoming_text
            model_reply = pending.get("last_model_reply") or ""

            raw_url = ""
            yuki_url = ""

            if self._should_persist():
                sdir = self._session_dir(sid)
                os.makedirs(sdir, exist_ok=True)
                if raw_png_bytes:
                    try:
                        raw_jpg = self._png_to_jpeg(raw_png_bytes)
                        raw_file = os.path.join(sdir, f"step_{step_index:03d}_raw.jpg")
                        with open(raw_file, "wb") as f:
                            f.write(raw_jpg)
                        raw_url = f"/api/phone/sessions/{sid}/steps/{step_index}/raw.jpg"
                    except Exception as exc:
                        logger.debug(f"[PhoneTrace] 保存原始截图失败: {exc}")

                if annotated_jpeg_bytes:
                    try:
                        yuki_file = os.path.join(sdir, f"step_{step_index:03d}_yuki.jpg")
                        with open(yuki_file, "wb") as f:
                            f.write(annotated_jpeg_bytes)
                        yuki_url = f"/api/phone/sessions/{sid}/steps/{step_index}/yuki.jpg"
                    except Exception as exc:
                        logger.debug(f"[PhoneTrace] 保存标注截图失败: {exc}")

            step_item = {
                "step_index": step_index,
                "timestamp": _now_str(),
                "tool_name": tool_name,
                "action": action,
                "target": "" if target is None else str(target),
                "text": text or "",
                "note": note or "",
                "step_display": step_display or action,
                "package": package or "",
                "node_count": int(node_count or 0),
                "success": bool(success),
                "error": error or "",
                "elapsed_ms": int(elapsed_ms or 0),
                "timing_breakdown": dict(timing_breakdown or {}),
                "user_incoming_text": incoming_text,
                "yuki_received_text": tool_result_text or "",
                "yuki_replied_text": model_reply,
                "yuki_final_reply": "",
                "raw_image_url": raw_url,
                "yuki_image_url": yuki_url or raw_url,
            }
            sess["steps"].append(step_item)
            sess["step_count"] = len(sess["steps"])
            sess["total_elapsed_ms"] = sum(int(s.get("elapsed_ms") or 0) for s in sess["steps"])
            sess["updated_at"] = _now_str()
            self._persist_session(sess)
            return copy.deepcopy(step_item)

    @staticmethod
    def _png_to_jpeg(img_bytes: bytes, max_width: int = 720, quality: int = 75) -> bytes:
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            w, h = img.size
            if max_width and w > max_width:
                img = img.resize((max_width, int(h * max_width / w)))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            return buf.getvalue()
        except Exception:
            return img_bytes

    def get_step_image(self, session_id: str, step_index: int, kind: str = "yuki") -> Optional[bytes]:
        sdir = self._session_dir(session_id)
        suffix = "yuki" if kind == "yuki" else "raw"
        path = os.path.join(sdir, f"step_{int(step_index):03d}_{suffix}.jpg")
        if not os.path.isfile(path) and suffix == "yuki":
            path = os.path.join(sdir, f"step_{int(step_index):03d}_raw.jpg")
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "rb") as f:
                return f.read()
        except OSError:
            return None

    # ---------------- 实时手机画面抓拍 ----------------

    def capture_live_jpeg(self, force: bool = False) -> tuple[bytes, int, str]:
        """同步抓取当前手机实时画面（带 0.4s 节流缓存），供 HTTP 线程直接调用。"""
        now = time.monotonic()
        if not force and self._live_jpeg and (now - self._live_ts) < 0.4:
            return self._live_jpeg, self._live_elapsed_ms, self._live_error

        with self._live_lock:
            now = time.monotonic()
            if not force and self._live_jpeg and (now - self._live_ts) < 0.4:
                return self._live_jpeg, self._live_elapsed_ms, self._live_error

            t0 = time.monotonic()
            tools_cfg = getattr(cfg, "tools", None)
            adb_bin = getattr(tools_cfg, "adb_path", "adb") or "adb"
            serial = (getattr(tools_cfg, "adb_serial", "") or "").strip()
            cmd = [adb_bin]
            if serial:
                cmd += ["-s", serial]
            cmd += ["exec-out", "screencap", "-p"]
            try:
                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8.0)
                if proc.returncode != 0 or not proc.stdout:
                    err = (proc.stderr or b"").decode("utf-8", "replace").strip() or f"rc={proc.returncode}"
                    self._live_error = err
                    return self._live_jpeg, self._live_elapsed_ms, err
                jpeg = self._png_to_jpeg(proc.stdout, max_width=720, quality=75)
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                self._live_jpeg = jpeg
                self._live_ts = time.monotonic()
                self._live_elapsed_ms = elapsed_ms
                self._live_error = ""
                return jpeg, elapsed_ms, ""
            except Exception as exc:
                self._live_error = str(exc)
                return self._live_jpeg, self._live_elapsed_ms, str(exc)

    # ---------------- 查询接口 ----------------

    def status(self) -> dict[str, Any]:
        with self._lock:
            sessions = list(self._sessions)
            active = dict(self._active_by_chat)
        latest = sessions[-1] if sessions else None
        return {
            "ok": True,
            "generated_at": _now_str(),
            "session_count": len(sessions),
            "active_chats": active,
            "latest_session_id": latest.get("session_id") if latest else None,
            "latest_updated_at": latest.get("updated_at") if latest else None,
            "live_elapsed_ms": self._live_elapsed_ms,
            "live_error": self._live_error,
        }

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or 50), 100))
        with self._lock:
            items = list(self._sessions)
        out = []
        for s in reversed(items):
            out.append({
                "session_id": s.get("session_id"),
                "chat_id": s.get("chat_id"),
                "goal": s.get("goal") or "",
                "status": s.get("status") or "running",
                "created_at": s.get("created_at"),
                "updated_at": s.get("updated_at"),
                "step_count": s.get("step_count", len(s.get("steps") or [])),
                "total_elapsed_ms": s.get("total_elapsed_ms", 0),
                "last_incoming_text": (s.get("last_incoming_text") or "")[:120],
                "last_final_reply": (s.get("last_final_reply") or "")[:120],
                "summary": (s.get("summary") or "")[:120],
            })
            if len(out) >= limit:
                break
        return out

    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            sess = self._by_id.get(str(session_id))
            return copy.deepcopy(sess) if sess else None


phone_trace_store = PhoneTraceStore()
