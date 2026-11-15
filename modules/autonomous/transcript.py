# modules/autonomous/transcript.py
"""自主轮的逐轮记录：把双念头交锋 / 复盘 / 工坊步进落到 logs/autonomous/<run_id>.jsonl。

只做一件事：append 一行 JSON。任何写盘异常都吞掉并降级为 debug 日志，
绝不因为它影响自主轮本身（它是观察手段，不是业务链路）。
"""
from __future__ import annotations

import datetime
import json
import os

from utils import BASE_DIR
from utils.logger import get_logger

logger = get_logger("autonomous.transcript")

TRANSCRIPT_DIR = os.path.join(BASE_DIR, "logs", "autonomous")
MAX_CONTENT_CHARS = 4000


def _now_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _truncate(text, limit: int = MAX_CONTENT_CHARS) -> str:
    text = str(text or "")
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


class RunTranscript:
    """单次运行的 JSONL 记录器。`run_id` 为空时静默不写。"""

    def __init__(self, run_id: str, chat_id=None, mode: str = "", directory: str | None = None):
        self.run_id = str(run_id or "").strip()
        self.chat_id = str(chat_id) if chat_id is not None else ""
        self.mode = str(mode or "")
        self.directory = os.path.abspath(directory or TRANSCRIPT_DIR)
        self.path = os.path.join(self.directory, f"{self.run_id}.jsonl") if self.run_id else ""
        self.enabled = bool(self.run_id)
        if self.enabled:
            self.event("run_start", mode=self.mode)

    def _write(self, record: dict) -> None:
        if not self.enabled:
            return
        try:
            os.makedirs(self.directory, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as exc:  # 观察手段不允许影响主流程
            logger.debug(f"[Transcript] 写入失败（已忽略）: {exc}")

    def event(self, kind: str, **fields) -> None:
        record = {"ts": _now_str(), "run_id": self.run_id, "chat_id": self.chat_id, "kind": kind}
        for key, value in fields.items():
            if isinstance(value, str):
                record[key] = _truncate(value)
            else:
                record[key] = value
        self._write(record)

    # ------------------------------------------------------------ 语义化快捷方法
    def debate_step(self, step: int, role: str, content: str, calls=None,
                    results=None, narration: str = "") -> None:
        self.event(
            "debate_step",
            step=step,
            role=role,
            content=content,
            narration=narration,
            calls=_calls_brief(calls),
            tools=_results_brief(results),
        )

    def vote(self, step: int, role: str, agree: bool, verdict: str, note: str = "") -> None:
        self.event("vote", step=step, role=role, agree=bool(agree),
                   verdict=verdict, note=note)

    def reflection(self, payload: dict) -> None:
        self.event(
            "reflection",
            action=payload.get("action"),
            title=payload.get("title"),
            memo=payload.get("memo_content"),
            work_diary_entry=payload.get("work_diary_entry"),
            notebook_pointer=payload.get("notebook_pointer"),
        )

    def workshop_step(self, step: int, content: str, calls=None, results=None,
                      tool_calls_count: int = 0) -> None:
        self.event(
            "workshop_step",
            step=step,
            content=content,
            calls=_calls_brief(calls),
            tools=_results_brief(results),
            tool_calls_count=tool_calls_count,
        )

    def finish(self, outcome: str, **fields) -> None:
        self.event("run_finish", outcome=outcome, **fields)


def _calls_brief(calls) -> list[dict]:
    out = []
    for call in calls or []:
        fn = (call.get("function") or {}) if isinstance(call, dict) else {}
        out.append({
            "name": fn.get("name") or "",
            "args": _truncate(fn.get("arguments") or "", 800),
        })
    return out


def _results_brief(results) -> list[dict]:
    out = []
    for message in results or []:
        if not isinstance(message, dict):
            continue
        payload = {}
        try:
            payload = json.loads(message.get("content") or "{}")
        except (TypeError, ValueError):
            payload = {}
        out.append({
            "name": message.get("name") or "",
            "success": bool(payload.get("success")),
            "content": _truncate(payload.get("content") or "", 600),
        })
    return out


def transcript_for(state, chat_id=None, mode: str = "") -> RunTranscript:
    """从 SandboxState 上取（或挂上）该次运行的记录器。"""
    existing = getattr(state, "transcript", None)
    if isinstance(existing, RunTranscript):
        return existing
    run_id = getattr(state, "run_id", "")
    transcript = RunTranscript(run_id, chat_id=getattr(state, "chat_id", chat_id), mode=mode)
    try:
        state.transcript = transcript
    except Exception:
        pass
    return transcript
