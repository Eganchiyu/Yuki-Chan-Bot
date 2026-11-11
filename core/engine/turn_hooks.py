# core/engine/turn_hooks.py
"""TurnHook 协议与内置生命周期钩子（FocusHook / PruneHook / FocusTraceHook / SnapshotHook）。"""
from __future__ import annotations

from typing import Any, Callable, Protocol

from core.engine.turn import PersistDecision, TurnState
from core.focus import (
    FocusExit,
    FocusManager,
    ToolView,
    focus_manager,
    rewrite_in_memory_messages,
)
from modules.debug.context_snapshot import context_snapshot_store
from utils.logger import get_logger

logger = get_logger("engine")


class TurnHook(Protocol):
    """主循环单轮生命周期钩子协议。"""

    def on_turn_start(self, st: TurnState) -> None: ...
    def before_llm(self, st: TurnState) -> None: ...
    def on_model_call(self, st: TurnState, msg: dict, calls: list) -> None: ...
    def classify_persist(self, st: TurnState, msg: dict) -> PersistDecision: ...
    def after_batch(self, st: TurnState, results: list[dict]) -> None: ...
    def on_turn_end(self, st: TurnState) -> None: ...


class BaseTurnHook:
    """提供所有钩子方法的空默认实现，子类按需覆盖。"""

    def on_turn_start(self, st: TurnState) -> None:
        pass

    def before_llm(self, st: TurnState) -> None:
        pass

    def on_model_call(self, st: TurnState, msg: dict, calls: list) -> None:
        pass

    def classify_persist(self, st: TurnState, msg: dict) -> PersistDecision:
        return PersistDecision()

    def after_batch(self, st: TurnState, results: list[dict]) -> None:
        pass

    def on_turn_end(self, st: TurnState) -> None:
        pass


class TurnHookChain:
    """按注册顺序串联调度多个 TurnHook。"""

    def __init__(self, hooks: list[TurnHook] | None = None):
        self.hooks: list[TurnHook] = list(hooks or [])

    def on_turn_start(self, st: TurnState) -> None:
        for h in self.hooks:
            h.on_turn_start(st)

    def before_llm(self, st: TurnState) -> None:
        for h in self.hooks:
            h.before_llm(st)

    def on_model_call(self, st: TurnState, msg: dict, calls: list) -> None:
        for h in self.hooks:
            h.on_model_call(st, msg, calls)

    def classify_persist(self, st: TurnState, msg: dict) -> PersistDecision:
        decision = PersistDecision()
        for h in self.hooks:
            d = h.classify_persist(st, msg)
            if d.action == "drop":
                return d
            if d.focus_work and not decision.focus_work:
                decision.focus_work = d.focus_work
        return decision

    def after_batch(self, st: TurnState, results: list[dict]) -> None:
        for h in self.hooks:
            h.after_batch(st, results)

    def on_turn_end(self, st: TurnState) -> None:
        for h in self.hooks:
            h.on_turn_end(st)


class FocusHook(BaseTurnHook):
    """负责聚焦模式的轮次扩容、工作记录打标、当轮内存覆写与闲置自动退出。"""

    def __init__(
        self,
        history_getter: Callable[[], Any],
        *,
        manager: FocusManager | None = None,
        restore_rounds_on_exit: bool = False,
        gate_exited_writes: bool = True,
    ):
        self._get_history = history_getter
        self._mgr = manager
        self.restore_rounds_on_exit = restore_rounds_on_exit
        self.gate_exited_writes = gate_exited_writes

    @property
    def manager(self) -> FocusManager:
        return self._mgr or focus_manager

    def on_turn_start(self, st: TurnState) -> None:
        active = self.manager.active(st.chat_id)
        if active is not None:
            st.max_rounds = self.manager.max_rounds_for(active.domain, st.max_rounds)

    def before_llm(self, st: TurnState) -> None:
        active = self.manager.active(st.chat_id)
        if active is not None and active.domain not in st.exited_this_turn:
            st.max_rounds = self.manager.max_rounds_for(active.domain, st.max_rounds)

    def on_model_call(self, st: TurnState, msg: dict, calls: list) -> None:
        active = self.manager.active(st.chat_id)
        tool_names = [(c.get("function") or {}).get("name") or "" for c in calls]
        batch_domains = {
            d.name
            for tn in tool_names
            if (d := self.manager.domain_of_tool(tn)) is not None
        }
        if active is not None:
            batch_domains.add(active.domain)
        for dn in batch_domains:
            st.used_domains.add(dn)
            if dn not in st.exited_this_turn:
                st.max_rounds = self.manager.max_rounds_for(dn, st.max_rounds)
        st.batch_focus_domain = (
            active.domain
            if active is not None
            else (next(iter(batch_domains)) if batch_domains else None)
        )

    def classify_persist(self, st: TurnState, msg: dict) -> PersistDecision:
        role = msg.get("role")
        if role == "assistant":
            domain_name = st.batch_focus_domain
        elif role == "tool":
            tool_name = msg.get("name") or ""
            tool_domain = self.manager.domain_of_tool(tool_name)
            active = self.manager.active(st.chat_id)
            domain_name = (
                tool_domain.name
                if tool_domain is not None
                else (active.domain if active is not None else st.batch_focus_domain)
            )
        else:
            domain_name = None

        if self.gate_exited_writes and domain_name and domain_name in st.batch_exited_domains:
            return PersistDecision(action="drop", focus_work=domain_name)
        return PersistDecision(action="write", focus_work=domain_name)

    def collect_batch_exits(self, st: TurnState) -> list[FocusExit]:
        """收集本批次工具执行产生的退出事件（供写入闸门与内存覆写共用）。"""
        exits: list[FocusExit] = list(st.context.metadata.pop("focus_exits", None) or [])
        for d_obj in self.manager.domains():
            legacy_summary = st.context.metadata.pop(f"{d_obj.name}_finish_summary", None)
            if legacy_summary is not None and not any(e.domain == d_obj.name for e in exits):
                exits.append(FocusExit(chat_id=st.chat_id, domain=d_obj.name, summary=legacy_summary))
        if exits:
            st.pending_exits.extend(exits)
            for item in exits:
                st.batch_exited_domains.add(item.domain)
        return exits

    def after_batch(self, st: TurnState, results: list[dict]) -> None:
        self.collect_batch_exits(st)
        while st.pending_exits:
            exit_item = st.pending_exits.pop(0)
            st.exited_this_turn.add(exit_item.domain)
            d_obj = self.manager.get_domain(exit_item.domain)
            if d_obj is not None:
                rewrite_in_memory_messages(st.tool_messages, d_obj, exit_item.summary)
            if self.restore_rounds_on_exit and not self.manager.is_focused(st.chat_id):
                st.max_rounds = max(st.round_idx + 1, st.base_max_rounds)
        st.batch_exited_domains.clear()
        st.batch_focus_domain = None

    def on_turn_end(self, st: TurnState) -> None:
        try:
            self.manager.after_turn(st.chat_id, st.used_domains, history=self._get_history())
        except Exception as exc:
            logger.warning(f"[Focus] 轮次闲置检查失败: {exc}")


class PruneHook(BaseTurnHook):
    """在每轮结束时驱动 ToolHistoryPruner 折叠闲置历史工具输出。"""

    def __init__(
        self,
        pruner_getter: Callable[[], Any],
        *,
        manager: FocusManager | None = None,
        skip_active_focus: bool = False,
    ):
        self._get_pruner = pruner_getter
        self._mgr = manager
        self.skip_active_focus = skip_active_focus

    @property
    def manager(self) -> FocusManager:
        return self._mgr or focus_manager

    def on_turn_end(self, st: TurnState) -> None:
        if self.skip_active_focus and self.manager.is_focused(st.chat_id):
            return
        try:
            self._get_pruner().after_turn(st.chat_id, st.tools_executed)
        except Exception as exc:
            logger.warning(f"[ToolPrune] 折叠失败: {exc}")


class FocusTraceHook(BaseTurnHook):
    """将入站文本、模型调用与最终回复分发给聚焦域的遥测钩子（修复 S3 多出口漏记）。"""

    def __init__(self, *, manager: FocusManager | None = None):
        self._mgr = manager

    @property
    def manager(self) -> FocusManager:
        return self._mgr or focus_manager

    def on_turn_start(self, st: TurnState) -> None:
        for domain in self.manager.domains():
            if domain.on_incoming is not None:
                try:
                    domain.on_incoming(st.chat_id, st.context.combined_text)
                except Exception:
                    pass

    def on_model_call(self, st: TurnState, msg: dict, calls: list) -> None:
        active = self.manager.active(st.chat_id)
        tool_names = [(c.get("function") or {}).get("name") or "" for c in calls]
        target_domains = {
            d.name
            for tn in tool_names
            if (d := self.manager.domain_of_tool(tn)) is not None
        }
        if active is not None:
            target_domains.add(active.domain)
        for dn in target_domains:
            d_obj = self.manager.get_domain(dn)
            if d_obj is not None and d_obj.on_model_call is not None:
                try:
                    d_obj.on_model_call(st.chat_id, msg.get("content") or "", calls)
                except Exception:
                    pass

    def on_turn_end(self, st: TurnState) -> None:
        if st.final is None or st.outcome not in ("reply", "exhausted", "filtered"):
            return
        raw_ans, clean_ans = st.final
        notify_domains = set(st.used_domains)
        active = self.manager.active(st.chat_id)
        if active is not None:
            notify_domains.add(active.domain)
        for dn in notify_domains:
            d_obj = self.manager.get_domain(dn)
            if d_obj is not None and d_obj.on_final_reply is not None:
                try:
                    d_obj.on_final_reply(st.chat_id, raw_ans, clean_ans)
                except Exception:
                    pass


# 兼容简写别名
TraceHook = FocusTraceHook


class SnapshotHook(BaseTurnHook):
    """同步 WebUI 调试快照，并按当前 ToolView 修正 tool_count（S6）。"""

    def __init__(self, *, manager: FocusManager | None = None):
        self._mgr = manager

    @property
    def manager(self) -> FocusManager:
        return self._mgr or focus_manager

    def _sync(self, st: TurnState, *, update_tool_ctx: bool = False) -> None:
        if not st.debug_snap_id:
            return
        try:
            kwargs: dict[str, Any] = {
                "built_messages": st.tool_messages,
                "llm_rounds": st.round_idx,
                "tool_trace": st.tool_trace,
                "tools_used": st.tools_used,
            }
            if update_tool_ctx:
                view = ToolView.resolve(
                    st.active_registry, self.manager, st.chat_id, st.exited_this_turn
                )
                kwargs["tool_context"] = {
                    "tools_enabled": True,
                    "tool_count": len(view.visible),
                    "mode": st.mode,
                    "max_rounds": st.max_rounds,
                }
            context_snapshot_store.update(st.debug_snap_id, **kwargs)
        except Exception:
            pass

    def on_turn_start(self, st: TurnState) -> None:
        self._sync(st, update_tool_ctx=True)

    def after_batch(self, st: TurnState, results: list[dict]) -> None:
        self._sync(st)

    def on_turn_end(self, st: TurnState) -> None:
        self._sync(st)
