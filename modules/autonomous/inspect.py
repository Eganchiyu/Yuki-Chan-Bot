# modules/autonomous/inspect.py
"""自主轮的可观测快照：模式/阶段、配额、五层记忆摘要（供 WebUI `/api/autonomous`）。"""
from __future__ import annotations

import datetime
import json
import os
import re
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

PHASE_ORDER = ["debate", "reflection", "workshop"]
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


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
    run_payload = None
    if run is not None:
        run_payload = {
            "chat_id": run.chat_id,
            "name": group_name_cache.label(run.chat_id),
            "mode": run.mode,
            "phase": PHASE_LABELS.get(run.mode, run.mode),
            "run_id": run.run_id,
            "session_id": run.session_id,
            "started_at": _ts(run.started_at),
            "started_ts": float(run.started_at or 0.0),
            "elapsed": round(max(0.0, time.time() - run.started_at), 1),
            "progress": _run_progress(run.run_id),
        }

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
        "tuning": {
            "debate_max_tokens": cfg.autonomous.debate_max_tokens,
            "debate_compress_every": cfg.autonomous.debate_compress_every,
            "catchup_enabled": cfg.autonomous.catchup_enabled,
            "catchup_max_messages": cfg.autonomous.catchup_max_messages,
            "diary_local_ratio": cfg.autonomous.diary_local_ratio,
            "daily_memory_ttl_hours": cfg.autonomous.daily_memory_ttl_hours,
            "high_spirits_turns": cfg.autonomous.high_spirits_turns,
            "high_spirits_minutes": cfg.autonomous.high_spirits_minutes,
            "high_spirits_desire_bonus": cfg.autonomous.high_spirits_desire_bonus,
            "high_spirits_followup_window": cfg.autonomous.high_spirits_followup_window,
            "digest_model": cfg.autonomous.digest_model or "（跟随主模型）",
        },
        "quota": {
            "auto_runs_today": state_store.auto_runs_today(),
            "daily_max_runs": cfg.autonomous.daily_max_runs,
            "last_run_at": _ts(state.get("last_run_at")),
            "last_run_at_ts": float(state.get("last_run_at") or 0.0),
        },
        "run": run_payload,
        "frozen": frozen,
        "freeze": {
            "idle": bool(router.is_idle()) if router is not None else True,
            "pending_catchups": ([
                {"chat_id": cid, "name": group_name_cache.label(cid), "messages": getattr(info, "messages", 0)}
                for cid, info in ((router.pending_catchups() or {}).items() if router is not None else [])
            ]),
        },
        "group_overrides": {k: bool(v) for k, v in (state.get("group_overrides") or {}).items()},
        "groups": _group_rows(state, run),
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


def _group_rows(state: dict, run) -> list[dict]:
    """准入看板：把所有相关群号汇总成一行一行的「为什么能/不能跑」。"""
    overrides = {str(k): bool(v) for k, v in (state.get("group_overrides") or {}).items()}
    config_groups = {str(g) for g in (cfg.autonomous.enabled_groups or [])}
    targets = {str(g) for g in (cfg.TARGET_GROUPS or [])}
    cached = {}
    try:
        with open(group_name_cache.path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            cached = {str(k): str(v) for k, v in data.items()}
    except OSError:
        cached = {}
    except ValueError:
        cached = {}

    gids = set(cached) | config_groups | set(overrides) | targets
    if run is not None:
        gids.add(str(run.chat_id))

    rows = []
    for gid in sorted(gids):
        override = overrides.get(gid)
        in_target = not targets or gid in targets
        in_config = gid in config_groups
        enabled = in_target and (override if override is not None
                                 else (bool(cfg.autonomous.enabled) and in_config))
        if not in_target:
            reason = "不属于目标群（TARGET_GROUPS）"
        elif override is True:
            reason = "已开启（运行时覆盖 /自主轮 开）"
        elif override is False:
            reason = "已关闭（运行时覆盖 /自主轮 关）"
        elif not cfg.autonomous.enabled:
            reason = "未开启（总开关关闭，可用 /自主轮 开 单独开启）"
        elif in_config:
            reason = "已开启（配置白名单）"
        else:
            reason = "未开启（不在 enabled_groups）"
        rows.append({
            "chat_id": gid,
            "name": cached.get(gid) or group_name_cache.label(gid),
            "enabled": bool(enabled),
            "reason": reason,
            "override": ("on" if override is True else "off" if override is False else ""),
            "in_config": in_config,
            "in_target": in_target,
            "running": bool(run is not None and str(run.chat_id) == gid),
        })
    rows.sort(key=lambda r: (not r["running"], not r["enabled"], r["name"]))
    return rows


# ---------------------------------------------------------------- 逐轮记录 API
def _transcript_dir() -> str:
    from modules.autonomous.transcript import TRANSCRIPT_DIR

    return TRANSCRIPT_DIR


def _safe_run_id(run_id: str) -> str:
    rid = str(run_id or "").strip()
    return rid if _RUN_ID_RE.match(rid) else ""


def _read_events(run_id: str, limit: int = 0) -> list[dict]:
    rid = _safe_run_id(run_id)
    if not rid:
        return []
    path = os.path.join(_transcript_dir(), f"{rid}.jsonl")
    events = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if isinstance(record, dict):
                    events.append(record)
    except OSError:
        return []
    if limit and len(events) > limit:
        events = events[-int(limit):]
    return events


def _run_progress(run_id: str) -> dict:
    events = _read_events(run_id, limit=4000)
    progress = {
        "events": len(events),
        "debate_steps": 0,
        "workshop_steps": 0,
        "votes": 0,
        "tool_calls": 0,
        "last_kind": "",
        "last_ts": "",
        "phase": "",
    }
    for ev in events:
        kind = ev.get("kind") or ""
        progress["last_kind"] = kind
        progress["last_ts"] = str(ev.get("ts") or "")
        if kind == "debate_step":
            progress["debate_steps"] += 1
        elif kind == "workshop_step":
            progress["workshop_steps"] += 1
            try:  # tool_calls_count 是累计值，取最大而不是求和
                progress["tool_calls"] = max(progress["tool_calls"], int(ev.get("tool_calls_count") or 0))
            except (TypeError, ValueError):
                pass
        elif kind == "vote":
            progress["votes"] += 1
        elif kind == "phase":
            progress["phase"] = str(ev.get("phase") or "")
    if not progress["phase"]:
        progress["phase"] = "debate" if progress["workshop_steps"] == 0 else "workshop"
    return progress


def autonomous_transcripts(limit: int = 30) -> dict:
    """最近若干次自主轮的逐轮记录清单（logs/autonomous/*.jsonl）。"""
    limits = max(1, min(int(limit or 30), 200))
    directory = _transcript_dir()
    rows = []
    try:
        entries = []
        for name in os.listdir(directory):
            if not name.endswith(".jsonl"):
                continue
            rid = name[: -len(".jsonl")]
            if not _safe_run_id(rid):
                continue
            path = os.path.join(directory, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            entries.append((stat.st_mtime, rid, stat.st_size))
        entries.sort(reverse=True)
    except OSError:
        return {"ok": True, "runs": [], "dir": directory}

    for mtime, rid, size in entries[:limits]:
        events = _read_events(rid, limit=4000)
        chat_id = ""
        mode = ""
        outcome = ""
        started_at = ""
        ended_at = ""
        for ev in events:
            if not chat_id and ev.get("chat_id"):
                chat_id = str(ev.get("chat_id"))
            kind = ev.get("kind")
            if kind == "run_start":
                mode = str(ev.get("mode") or "")
                started_at = str(ev.get("ts") or "")
            elif kind == "run_finish":
                outcome = str(ev.get("outcome") or "")
                ended_at = str(ev.get("ts") or "")
        progress = {
            "events": len(events),
            "debate_steps": sum(1 for ev in events if ev.get("kind") == "debate_step"),
            "workshop_steps": sum(1 for ev in events if ev.get("kind") == "workshop_step"),
            "votes": sum(1 for ev in events if ev.get("kind") == "vote"),
            "tool_calls": max([int(ev.get("tool_calls_count") or 0)
                               for ev in events if ev.get("kind") == "workshop_step"] or [0]),
        }
        rows.append({
            "run_id": rid,
            "chat_id": chat_id,
            "name": group_name_cache.label(chat_id) if chat_id else "",
            "mode": mode,
            "outcome": outcome,
            "started_at": started_at,
            "ended_at": ended_at,
            "updated_at": _ts(mtime),
            "size": size,
            **progress,
        })
    return {"ok": True, "runs": rows, "dir": directory}


def autonomous_transcript(run_id: str, limit: int = 1200) -> dict:
    """单次自主轮的完整事件流（供 WebUI 逐轮回放）。"""
    rid = _safe_run_id(run_id)
    if not rid:
        return {"ok": False, "error": "invalid_run_id"}
    events = _read_events(rid, limit=limit)
    if not events:
        return {"ok": False, "error": "run_not_found", "run_id": rid}
    chat_id = str(next((ev.get("chat_id") for ev in events if ev.get("chat_id")), "") or "")
    return {
        "ok": True,
        "run_id": rid,
        "chat_id": chat_id,
        "name": group_name_cache.label(chat_id) if chat_id else "",
        "events": events,
        "truncated": len(events) >= int(limit),
    }


def _notebook_zones() -> dict:
    try:
        from core.notebook import notebook_store

        zones = notebook_store.load_zones()
        return {"daily": zones.get("daily", ""), "plans": zones.get("plans", "")}
    except Exception:
        return {"daily": "", "plans": ""}
