# modules/autonomous/inspect.py
"""自主轮的可观测快照：模式/阶段、配额、五层记忆摘要（供 WebUI `/api/autonomous`）。"""
from __future__ import annotations

import datetime
import time

from config import cfg
from modules.autonomous.catchup import DIGEST_MAX_CHARS
from modules.autonomous.storage import (
    daily_memory_store,
    group_name_cache,
    state_store,
    work_diary_store,
    work_session_store,
)

PHASE_LABELS = {
    "debate": "Phase 1 双念头交锋",
    "reflection": "Phase 2 本尊复盘",
    "workshop": "Phase 3 自主工坊",
    "chat": "chat 模式",
}


def _router():
    try:
        from core.modes.router import router

        return router
    except Exception:
        return None


def _ts(value) -> str:
    try:
        ts = float(value or 0)
    except (TypeError, ValueError):
        return ""
    if ts <= 0:
        return ""
    return datetime.datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")


def autonomous_snapshot(limit: int = 10) -> dict:
    """返回可 JSON 序列化的自主轮快照。"""
    state = state_store.load()
    limits = max(1, min(int(limit or 10), 50))
    router = _router()
    run = getattr(router, "global_run", None) if router is not None else None
    frozen = []
    if router is not None:
        for cid, info in (router.frozen_chats() or {}).items():
            frozen.append({
                "chat_id": cid,
                "name": group_name_cache.label(cid),
                "messages": getattr(info, "messages", 0),
                "since": _ts(getattr(info, "since", 0)),
            })

    sessions = []
    for row in work_session_store.list(limit=limits):
        record = work_session_store.load(str(row.get("session_id"))) or {}
        sessions.append({
            "session_id": row.get("session_id"),
            "title": row.get("title"),
            "status": row.get("status"),
            "kind": row.get("kind"),
            "updated_at": _ts(row.get("updated_at")),
            "work_log": record.get("work_log") or row.get("log_head"),
            "artifacts": record.get("artifacts") or [],
        })

    diaries = [
        {"ts": _ts(row.get("ts")), "title": row.get("title"),
         "kind": row.get("kind"), "content": row.get("content")}
        for row in work_diary_store.list(limit=limits)
    ]

    daily = daily_memory_store.load()
    return {
        "now": _ts(time.time()),
        "enabled": bool(cfg.autonomous.enabled),
        "auto_trigger": bool(cfg.autonomous.auto_trigger_enabled),
        "gate": {
            "enabled_groups": list(cfg.autonomous.enabled_groups or []),
            "min_group_idle_minutes": cfg.autonomous.min_group_idle_minutes,
            "min_energy": cfg.autonomous.min_energy,
            "quiet_hours": list(cfg.autonomous.quiet_hours or []),
            "cooldown_minutes": cfg.autonomous.cooldown_minutes,
            "daily_max_runs": cfg.autonomous.daily_max_runs,
        },
        "limits": {
            "debate_max_rounds": cfg.autonomous.debate_max_rounds,
            "workshop_max_tool_calls": cfg.autonomous.workshop_max_tool_calls,
            "zero_tool_max_retries": cfg.autonomous.zero_tool_max_retries,
            "step_timeout_seconds": cfg.autonomous.step_timeout_seconds,
            "max_wall_seconds": cfg.autonomous.max_wall_seconds,
            "catchup_threshold": cfg.autonomous.catchup_summarize_threshold,
            "digest_max_chars": DIGEST_MAX_CHARS,
        },
        "quota": {
            "auto_runs_today": state_store.auto_runs_today(),
            "daily_max_runs": cfg.autonomous.daily_max_runs,
            "last_run_at": _ts(state.get("last_run_at")),
        },
        "run": ({
            "chat_id": run.chat_id,
            "name": group_name_cache.label(run.chat_id),
            "mode": run.mode,
            "phase": PHASE_LABELS.get(run.mode, run.mode),
            "run_id": run.run_id,
            "session_id": run.session_id,
            "elapsed": round(max(0.0, time.time() - run.started_at), 1),
        } if run is not None else None),
        "frozen": frozen,
        "group_overrides": {k: bool(v) for k, v in (state.get("group_overrides") or {}).items()},
        "sessions": sessions,
        "work_diaries": diaries,
        "daily_work_memory": {
            "date": daily.get("date"),
            "text": daily.get("text") or "",
            "entries": len(daily.get("entries") or []),
            "updated_at": _ts(daily.get("updated_at")),
            "archived_at": _ts(daily.get("archived_at")),
        },
        "notebook": _notebook_zones(),
    }


def _notebook_zones() -> dict:
    try:
        from core.notebook import notebook_store

        zones = notebook_store.load_zones()
        return {"daily": zones.get("daily", ""), "plans": zones.get("plans", "")}
    except Exception:
        return {"daily": "", "plans": ""}
