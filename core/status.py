# core/status.py
"""Yuki 运行状态快照：给 `/查询` 指令用的关键词式简报。

设计约束：
1. 输出要短 —— 一行关键词，最多两行，不做长段落；
2. 分层脱敏 —— 普通群友只看模式/精力/静默，模型与主备线路只给主人看；
3. 可扩展 —— 未来的模式系统（chat / debate / workshop）通过
   `register_mode_provider()` 注入"当前模式"描述，本模块不需要提前知道它们。
"""
from __future__ import annotations

import re
import time
from typing import Callable, Optional

from config import cfg
from core.focus import focus_manager

# 进程启动时间：用于"运行时长"
_START_TS = time.time()

# 当前模式描述提供者：签名 (chat_id) -> str | None。
# 模式系统落地后由 modules/autonomous 注册；返回 None 表示交回默认推断。
_mode_providers: list[Callable[[str], Optional[str]]] = []


def register_mode_provider(provider: Callable[[str], Optional[str]]) -> None:
    """注册"当前模式"描述提供者（后者优先）。"""
    if provider not in _mode_providers:
        _mode_providers.append(provider)


def reset_mode_providers() -> None:
    """测试用：清空模式提供者。"""
    _mode_providers.clear()


def uptime_seconds() -> float:
    return max(0.0, time.time() - _START_TS)


def _human_duration(seconds: float) -> str:
    """把秒数压成极短的中文时长（30s / 12m / 3h / 2d）。"""
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"


def current_mode(chat_id, group_active: bool = True) -> str:
    """优先问模式提供者；否则按聚焦域 / 休眠 / 群聊推断。"""
    cid = str(chat_id)
    for provider in reversed(_mode_providers):
        try:
            text = provider(cid)
        except Exception:
            text = None
        if text:
            return text
    state = focus_manager.active(cid)
    if state is not None:
        domain = focus_manager.get_domain(state.domain)
        return (domain.title if domain else state.domain)
    if not group_active:
        return "休眠"
    return "群聊"


def route_state() -> dict:
    """主备线路状态（降级与否），读不到时回落为正常。"""
    try:
        from utils.llm_client import get_route_state

        return get_route_state()
    except Exception:
        return {"is_degraded": False, "recovery_seconds": 120.0, "last_fail_time": 0.0}


def build_status_text(yuki, chat_id, *, group_active: bool = True, is_master: bool = False,
                      now: Optional[float] = None) -> str:
    """生成 `/查询` 的简报文本（关键词式，一行主信息 + 可选第二行）。"""
    cid = str(chat_id)
    now = time.time() if now is None else now

    mode_text = current_mode(cid, group_active)

    # 精力：优先读现有值，避免为了查状态而改动状态
    energy = None
    try:
        if cid in getattr(yuki, "energy", {}):
            energy = float(yuki.energy[cid])
        else:
            energy = float(cfg.INITIAL_ENERGY)
    except Exception:
        energy = None

    parts = [f"模式 {mode_text}"]
    if energy is not None:
        parts.append(f"精力 {energy:.0f}/{cfg.MAX_ENERGY}")

    last_ts = getattr(yuki, "last_message_time", {}).get(cid)
    if last_ts:
        parts.append(f"静默 {_human_duration(now - float(last_ts))}")

    if is_master:
        activity = float(getattr(yuki, "group_activity", {}).get(cid, 0.0) or 0.0)
        desire = float(getattr(yuki, "desire_to_start_topic", {}).get(cid, 0.0) or 0.0)
        parts.append(f"活跃 {activity:.1f}")
        parts.append(f"欲 {desire:.0f}%")

        state = route_state()
        line = "备用线路" if state.get("is_degraded") else "主线"
        parts.append(f"{line} {cfg.LLM_MODEL}")

        queue = getattr(yuki, "maid_task_queue", None)
        try:
            queued = queue.qsize() if queue is not None else 0
        except Exception:
            queued = 0
        running = len(getattr(yuki, "maid_current_tasks", {}) or {})
        parts.append(f"小女仆 {queued}排/{running}跑")

        parts.append(f"在线 {_human_duration(uptime_seconds())}")

    return " | ".join(parts)


# ---------------------------------------------------------------
# 指令正则：/查询、/状态、/status（全量快照）
# ---------------------------------------------------------------

STATUS_CMD_RE = re.compile(r"^/(?:查询|状态|status)\s*$", re.IGNORECASE)

# 强制关闭：第一次提示确认，第二次（60 秒内）执行
FORCE_CLOSE_CMD_RE = re.compile(r"^/强制(?:关闭|关)(?:\s*(?:确认|confirm|确认关闭))?\s*$", re.IGNORECASE)
FORCE_CLOSE_CONFIRM_SECONDS = 60.0

_pending_force_close: dict[str, float] = {}


def match_status_command(raw_text: str) -> bool:
    return bool(STATUS_CMD_RE.match(str(raw_text or "").strip()))


def match_force_close_command(raw_text: str) -> bool:
    return bool(FORCE_CLOSE_CMD_RE.match(str(raw_text or "").strip()))


def is_force_close_confirmed(chat_id, now: Optional[float] = None) -> bool:
    """检查该会话是否已在本轮二次确认窗口内发过 /强制关闭。"""
    cid = str(chat_id)
    now = time.time() if now is None else now
    pending = _pending_force_close.get(cid)
    if pending is None:
        return False
    if now - pending > FORCE_CLOSE_CONFIRM_SECONDS:
        _pending_force_close.pop(cid, None)
        return False
    return True


def mark_force_close_pending(chat_id, now: Optional[float] = None) -> None:
    _pending_force_close[str(chat_id)] = time.time() if now is None else now


def clear_force_close(chat_id) -> None:
    _pending_force_close.pop(str(chat_id), None)


def reset_force_close_state() -> None:
    """测试用：清空所有待确认状态。"""
    _pending_force_close.clear()
