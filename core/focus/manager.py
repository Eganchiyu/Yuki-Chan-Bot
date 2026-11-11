# core/focus/manager.py
"""多域聚焦状态机：每个 chat_id 同一时刻最多处于 1 个活跃聚焦域。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from config import cfg
from core.focus.domain import FocusDomain
from core.focus.rewrite import (
    build_summary_message,
    message_focus_domain,
    rewrite_in_memory_messages,
    rewrite_persistent_session,
)
from utils.logger import get_logger

logger = get_logger("tools")

DEFAULT_MAX_IDLE_TURNS = 5


@dataclass
class FocusState:
    """单个会话在某个聚焦域下的运行状态。"""

    chat_id: str
    domain: str = "phone"
    goal: str = ""
    started_at: float = field(default_factory=time.time)
    idle_turns: int = 0
    trace: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FocusExit:
    """一次聚焦退出的结果描述。"""

    chat_id: str
    domain: str
    summary: str
    reason: str = "finish"  # "finish" | "idle" | "switch" | "orphan"


class FocusManager:
    """多域聚焦模式状态机。"""

    def __init__(self, max_idle_turns: int = DEFAULT_MAX_IDLE_TURNS):
        self.max_idle_turns = max(1, int(max_idle_turns or DEFAULT_MAX_IDLE_TURNS))
        self._domains: dict[str, FocusDomain] = {}
        self._tool_to_domain: dict[str, FocusDomain] = {}
        self._states: dict[str, FocusState] = {}

    # ---------------- 域注册与查询 ----------------

    def register(self, domain: FocusDomain) -> None:
        self._domains[domain.name] = domain
        for tool_name in domain.work_tools:
            self._tool_to_domain[tool_name] = domain

    def domain(self, name: str) -> FocusDomain:
        if name not in self._domains:
            raise KeyError(f"未注册的聚焦域: {name}")
        return self._domains[name]

    def get_domain(self, name: str) -> FocusDomain | None:
        return self._domains.get(name)

    def domains(self) -> list[FocusDomain]:
        return list(self._domains.values())

    def domain_of_tool(self, tool_name: str) -> FocusDomain | None:
        if not tool_name:
            return None
        return self._tool_to_domain.get(tool_name)

    # ---------------- 会话状态管理 ----------------

    def active(self, chat_id: Any) -> FocusState | None:
        return self._states.get(str(chat_id))

    def is_focused(self, chat_id: Any, domain: str | None = None) -> bool:
        state = self._states.get(str(chat_id))
        if state is None:
            return False
        if domain is None:
            return True
        return state.domain == domain

    def enter(
        self,
        chat_id: Any,
        domain: str,
        goal: str = "",
        *,
        history: Any = None,
    ) -> FocusState:
        cid = str(chat_id)
        d = self.domain(domain)
        state = self._states.get(cid)

        # 若当前已在其他域，先自动退出旧域并写入兜底总结
        if state is not None and state.domain != d.name:
            self.exit(cid, history=history, reason="switch")
            state = None

        if state is None:
            state = FocusState(chat_id=cid, domain=d.name, goal=(goal or "").strip())
            self._states[cid] = state
            logger.info(f"[Focus:{d.name}] {cid} 进入{d.title}聚焦模式 goal={state.goal or '无'}")
            if d.on_enter is not None:
                try:
                    d.on_enter(cid, state.goal)
                except Exception as exc:
                    logger.debug(f"[Focus:{d.name}] on_enter 钩子异常: {exc}")
        else:
            if goal and not state.goal:
                state.goal = goal.strip()
            state.idle_turns = 0
        return state

    def abort(self, chat_id: Any, domain: str | None = None) -> None:
        """进入失败（如设备未就绪）时回滚聚焦状态，不写总结。"""
        cid = str(chat_id)
        state = self._states.get(cid)
        if state is None:
            return
        if domain is None or state.domain == domain:
            self._states.pop(cid, None)

    def record_step(
        self,
        chat_id: Any,
        step_desc: str,
        note: str = "",
        *,
        domain: str | None = None,
    ) -> None:
        """记录聚焦期间的一步操作，并将闲置轮数清零。"""
        cid = str(chat_id)
        state = self._states.get(cid)
        if state is None:
            target_domain = domain or ("phone" if "phone" in self._domains else next(iter(self._domains), "phone"))
            state = self.enter(cid, target_domain)
        state.idle_turns = 0
        d = self._domains.get(state.domain)
        max_trace = d.max_trace if d else 20

        desc = (step_desc or "").strip()
        note_str = (note or "").strip()
        entry = f"{desc} ({note_str})" if (desc and note_str) else (desc or note_str)
        if entry:
            state.trace.append(entry[:80])
            if len(state.trace) > max_trace:
                del state.trace[:-max_trace]

    def build_fallback_summary(
        self,
        state: FocusState | None,
        custom_summary: str = "",
        *,
        domain: str | None = None,
    ) -> str:
        text = (custom_summary or "").strip()
        if text:
            return text
        d_name = (state.domain if state else None) or domain or "phone"
        d = self._domains.get(d_name)
        title = d.title if d else d_name
        default_fb = (d.default_fallback if d and d.default_fallback else f"已完成{title}操作。")
        empty_fb = (d.empty_trace_fallback if d and d.empty_trace_fallback else f"已进入{title}查看并完成操作。")

        if state is None:
            return default_fb
        parts: list[str] = []
        if state.goal:
            parts.append(f"目标：{state.goal}")
        if state.trace:
            parts.append("执行步骤：" + " → ".join(state.trace[-8:]))
        if not parts:
            return empty_fb
        return "；".join(parts)

    def exit(
        self,
        chat_id: Any,
        *,
        history: Any = None,
        summary: str = "",
        reason: str = "finish",
        domain: str | None = None,
        tool_messages: list[dict] | None = None,
    ) -> FocusExit | None:
        """退出聚焦模式，清除持久化历史中的工作过程记录并以 USER 身份注入总结。"""
        cid = str(chat_id)
        state = self._states.pop(cid, None)
        d_name = (state.domain if state else None) or domain
        if not d_name:
            return None
        d = self._domains.get(d_name)
        if d is None:
            return None

        final_summary = self.build_fallback_summary(state, summary, domain=d.name)

        if history is not None:
            try:
                session = history.get_session(cid)
                filtered = rewrite_persistent_session(session, d, final_summary)
                history.replace_session(cid, filtered)
            except Exception as exc:
                logger.warning(f"[Focus:{d.name}] 覆写会话历史失败 {cid}: {exc}")

        if tool_messages is not None:
            rewrite_in_memory_messages(tool_messages, d, final_summary)

        if d.on_exit is not None:
            try:
                d.on_exit(cid, final_summary, reason)
            except Exception as exc:
                logger.debug(f"[Focus:{d.name}] on_exit 钩子异常: {exc}")

        logger.info(f"[Focus:{d.name}] {cid} 已退出{d.title}聚焦模式 (reason={reason})，注入总结: {final_summary[:80]}")
        return FocusExit(chat_id=cid, domain=d.name, summary=final_summary, reason=reason)

    def _idle_limit_for(self, domain: FocusDomain) -> int:
        if domain.idle_turns_key:
            val = getattr(getattr(cfg, "tools", None), domain.idle_turns_key, None)
            if val:
                return max(1, int(val))
        return self.max_idle_turns

    def max_rounds_for(self, domain_name: str, default_rounds: int = 4) -> int:
        d = self._domains.get(domain_name)
        if d is None:
            return default_rounds
        configured = 100
        if d.max_rounds_key:
            val = getattr(getattr(cfg, "tools", None), d.max_rounds_key, None)
            if val:
                configured = int(val)
        return max(default_rounds, configured)

    def after_turn(
        self,
        chat_id: Any,
        used_domains: set[str] | bool,
        *,
        history: Any = None,
    ) -> FocusExit | None:
        """每轮对话结束时更新闲置计数；连续闲置超过阈值时自动退出并写入兜底总结。"""
        cid = str(chat_id)
        state = self._states.get(cid)
        if state is None:
            return None

        if isinstance(used_domains, bool):
            domain_used = used_domains
        else:
            domain_used = state.domain in used_domains

        if domain_used:
            state.idle_turns = 0
            return None

        state.idle_turns += 1
        d = self._domains.get(state.domain)
        limit = self._idle_limit_for(d) if d else self.max_idle_turns
        if state.idle_turns > limit:
            auto_note = self.build_fallback_summary(state)
            logger.info(
                f"[Focus:{state.domain}] {cid} 连续 {state.idle_turns} 轮未操作（>{limit}轮），自动退出聚焦模式"
            )
            return self.exit(cid, history=history, summary=auto_note, reason="idle")
        return None

    def sweep_orphans(self, history: Any) -> int:
        """清扫所有无活跃聚焦状态的孤儿 focus_work 历史片段（B5）。"""
        if history is None or not hasattr(history, "load"):
            return 0
        try:
            all_sessions = history.load(copy_result=True)
        except Exception as exc:
            logger.warning(f"[Focus] 读取历史以清扫孤儿记录失败: {exc}")
            return 0
        if not isinstance(all_sessions, dict):
            return 0

        total_swept = 0
        for cid, session in all_sessions.items():
            if not isinstance(session, list) or not session:
                continue
            active_state = self.active(cid)
            active_domain = active_state.domain if active_state else None

            new_session: list[dict] = []
            segment_domain: str | None = None
            segment_thoughts: list[str] = []
            segment_tools: list[str] = []
            segment_interleaved: list[dict] = []
            swept_in_chat = 0

            def _flush_segment():
                nonlocal segment_domain, segment_thoughts, segment_tools, segment_interleaved
                if not segment_domain:
                    return
                d = self._domains.get(segment_domain)
                new_session.extend(segment_interleaved)
                parts: list[str] = []
                if segment_thoughts:
                    parts.append("；".join(segment_thoughts[:3]))
                if segment_tools:
                    parts.append("步骤：" + " → ".join(segment_tools[:6]))
                fallback = "；".join(parts) if parts else (
                    d.default_fallback if d and d.default_fallback else "操作中断"
                )
                summary_text = f"（重启前未正常结束）{fallback}"
                if d is not None:
                    new_session.append(build_summary_message(d, summary_text))
                else:
                    new_session.append({
                        "role": "user",
                        "content": f"【{segment_domain}总结】{summary_text}",
                        "is_focus_summary": True,
                        "focus_domain": segment_domain,
                    })
                segment_domain = None
                segment_thoughts = []
                segment_tools = []
                segment_interleaved = []

            for msg in session:
                msg_domain = message_focus_domain(msg, self.domain_of_tool)
                if msg_domain and msg_domain != active_domain:
                    if segment_domain and segment_domain != msg_domain:
                        _flush_segment()
                    segment_domain = msg_domain
                    swept_in_chat += 1
                    if msg.get("role") == "assistant" and msg.get("content"):
                        segment_thoughts.append(str(msg.get("content")).strip()[:60])
                    elif msg.get("role") == "tool" and msg.get("name"):
                        segment_tools.append(str(msg.get("name")))
                else:
                    if segment_domain is not None:
                        # 处于孤儿工作片段期间：普通 user 插话暂存进 segment_interleaved，
                        # 遇到非 tool_thought 的正常 assistant 最终回复说明该轮已结束，先闭合片段
                        if msg.get("role") == "user" and not msg.get("is_focus_summary") and not msg.get("is_phone_summary"):
                            segment_interleaved.append(msg)
                        else:
                            _flush_segment()
                            new_session.append(msg)
                    else:
                        new_session.append(msg)

            if segment_domain is not None:
                _flush_segment()

            if swept_in_chat > 0:
                total_swept += swept_in_chat
                try:
                    history.replace_session(cid, new_session)
                except Exception as exc:
                    logger.warning(f"[Focus] 写回清扫后的会话失败 {cid}: {exc}")

        if total_swept > 0:
            logger.info(f"[Focus] 启动清扫完成：共清理 {total_swept} 条孤儿聚焦工作记录")
        return total_swept


focus_manager = FocusManager()


def register_domain(domain: FocusDomain) -> FocusDomain:
    focus_manager.register(domain)
    return domain
