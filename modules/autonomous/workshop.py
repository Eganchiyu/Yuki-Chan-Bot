# modules/autonomous/workshop.py
"""workshop 模式：自主执行工坊（≤60 次工具调用、零工具追问、熔断、随时暂停接续）。"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from config import cfg
from core.tool_markup import strip_tool_call_markup
from modules.autonomous import prompts as sb_prompts
from modules.autonomous.sandbox_loop import (
    AdaptorHistory,
    SandboxDeps,
    SandboxLoop,
    SilentSender,
    build_tool_context,
    run_step_with_timeout,
)
from modules.autonomous.storage import WORK_LOG_MAX_CHARS, truncate_chars, work_session_store
from modules.autonomous.tools import SandboxState, build_registry
from modules.autonomous.transcript import transcript_for
from utils.logger import get_logger

logger = get_logger("autonomous.workshop")

WORKSHOP_SANDBOX_TOOLS = [
    "inspect_work_session",
    "list_recent_work_sessions",
    "write_work_diary",
    "publish_to_corner",
    "save_inspiration",
    "wait_maid_tasks",
    "work_finish",
]
# 收尾与上架工具永不被裁剪，保证任何子模式下都能收尾和发布
WORKSHOP_PINNED = set(WORKSHOP_SANDBOX_TOOLS)

ZERO_TOOL_NUDGE = (
    "你这一轮想做的事情完成了吗？想要回到群里吗？"
    "如果已经完成（或者打算先暂停留到下次再接续），请调用 work_finish 写下不超过 512 字的工作日志"
    "，最好包含产物路径（如果有的话）；如果还没做完，请继续调用工具推进。"
)
BUDGET_REMINDER_TEMPLATE = (
    "\n\n[系统提醒：本轮自主工具调用已达 {used}/{limit} 次上限，请尽快整理当前进度并调用 work_finish 保存工作日志]"
)
INNER_EVENT_TEMPLATE = "【内部消息·小女仆汇报】{content}"


@dataclass
class WorkshopOutcome:
    status: str = "paused"              # completed | paused | fuse | timeout | empty
    session_id: str = ""
    work_log: str = ""
    artifacts: list[str] = field(default_factory=list)
    steps: int = 0
    tool_calls: int = 0
    notes: list[str] = field(default_factory=list)


class Workshop:
    """工坊主循环：一步一次 LLM，直到 work_finish / 预算耗尽 / 熔断。"""

    def __init__(
        self,
        *,
        chat_id,
        chat_label: str,
        state: SandboxState,
        deps: SandboxDeps,
        goal: str = "",
        stop_check=None,
    ):
        self.chat_id = str(chat_id)
        self.chat_label = chat_label or f"群 {self.chat_id}"
        self.state = state
        self.deps = deps
        self.goal = str(goal or "")
        self.stop_check = stop_check or (lambda: False)
        self.max_tool_calls = max(1, int(cfg.autonomous.workshop_max_tool_calls))
        self.zero_tool_max_retries = max(0, int(cfg.autonomous.zero_tool_max_retries))
        self.inner_events: list[dict] = []
        self._inner_event_signal = asyncio.Event()

        self.history = AdaptorHistory(self.chat_id)
        self.sender = SilentSender(self.chat_id)
        self.registry = build_registry(
            deps.main_registry,
            WORKSHOP_SANDBOX_TOOLS,
            main_tool_names=set(_main_tool_names(deps.main_registry)),
        )
        self.context = build_tool_context(
            chat_id=self.chat_id,
            yuki=deps.yuki,
            sender=self.sender,
            history=self.history,
            image_store=deps.image_store,
            metadata={
                "sandbox": state,
                "workshop": self,
                "stop_check": self.stop_check,
                "is_autonomous": True,
                "is_autonomous_work": True,
                "history_manager": self.history,     # 子聚焦退出只覆写内存流
                "process_callback": deps.process_callback,
            },
        )
        self.loop = SandboxLoop(
            chat_id=self.chat_id,
            registry=self.registry,
            context=self.context,
            history=self.history,
            max_steps=self.max_tool_calls + self.zero_tool_max_retries + 5,
            max_tokens=cfg.autonomous.workshop_max_tokens,
            temperature=0.9,
            pinned=WORKSHOP_PINNED,
            debug_tag="workshop",
        )

    # ------------------------------------------------------------ 内部事件
    def queue_inner_event(self, event: dict) -> None:
        if event:
            self.inner_events.append(event)
            self._inner_event_signal.set()

    def pop_inner_events(self) -> list[dict]:
        events, self.inner_events = self.inner_events, []
        self._inner_event_signal.clear()
        return events

    # ------------------------------------------------------------ 主循环
    async def run(self) -> WorkshopOutcome:
        outcome = WorkshopOutcome(session_id=self.state.session_id)
        resume_hint = ""
        record = work_session_store.load(self.state.session_id) if self.state.session_id else None
        if record and record.get("work_log"):
            resume_hint = f"{record.get('work_log')}（产物：{', '.join(record.get('artifacts') or []) or '暂无'}）"

        goal = (record or {}).get("title") or self.goal
        memo = (self.state.reflection or {}).get("memo_content", "")
        messages = [
            {"role": "system", "content": sb_prompts.workshop_system(
                self.chat_label, self.state.session_id, resume_hint)},
            {"role": "user", "content": sb_prompts.workshop_user_block(
                goal, memo,
            )},
        ]

        transcript = transcript_for(self.state, mode="workshop")
        transcript.event("workshop_start", session_id=self.state.session_id, goal=goal,
                         resume_hint=resume_hint)
        zero_streak = 0
        step_no = 0
        while True:
            step_no += 1
            if self.stop_check():
                outcome.status = "timeout"
                logger.warning(f"[Workshop] {self.chat_id} 收到停止请求，收尾")
                break
            self._drain_inner_events(messages)
            budget_left = self.max_tool_calls - self.loop.tool_calls_count
            if budget_left <= 0:
                visible = {"work_finish"}          # 预算耗尽：只留收尾工具，逼模型归档
            else:
                visible = None                     # None = 按子聚焦状态自动算

            try:
                msg, _ = await run_step_with_timeout(self.loop.call_model(messages, visible))
            except asyncio.TimeoutError:
                outcome.status = "timeout"
                logger.warning(f"[Workshop] {self.chat_id} LLM 单步超时")
                break
            except Exception as exc:
                logger.error(f"[Workshop] {self.chat_id} LLM 失败: {exc}")
                outcome.status = "empty"
                break

            content = strip_tool_call_markup(msg.get("content") or "").strip()
            calls = self.loop.extract_calls(msg, visible)
            transcript.workshop_step(step_no, content, calls, None,
                                     self.loop.tool_calls_count)
            if not calls:
                zero_streak += 1
                messages.append({"role": "assistant", "content": msg.get("content") or ""})
                if zero_streak <= self.zero_tool_max_retries:
                    messages.append({"role": "user", "content": ZERO_TOOL_NUDGE})
                    logger.info(f"[Workshop] {self.chat_id} 零工具返回，追问 {zero_streak}/"
                                f"{self.zero_tool_max_retries}")
                    continue
                outcome.status = "fuse"
                logger.warning(f"[Workshop] {self.chat_id} 连续零工具，触发熔断")
                break

            zero_streak = 0
            messages.append(msg)
            try:
                results = await run_step_with_timeout(
                    self.loop.execute_calls(
                        calls, visible, finish_reason=msg.get("_finish_reason") or "",
                    )
                )
            except asyncio.TimeoutError:
                outcome.status = "timeout"
                logger.warning(f"[Workshop] {self.chat_id} 工具批次超时")
                break

            messages.extend(results)
            transcript.workshop_step(step_no, content, calls, results,
                                     self.loop.tool_calls_count)
            await self._attach_screenshots(results, messages)
            self._append_budget_reminder(messages)

            if self.state.finished:
                outcome.status = "completed" if self.state.finish_status == "completed" else "paused"
                logger.warning(f"[Workshop] {self.chat_id} work_finish status={outcome.status}")
                break

            if content:
                self.state.notes.append(content[:120])

        outcome.session_id = self.state.session_id
        outcome.steps = step_no
        outcome.tool_calls = self.loop.tool_calls_count
        outcome.notes = list(self.state.notes[-6:])
        if self.state.finished:
            outcome.work_log = self.state.work_log
            outcome.artifacts = list(self.state.artifacts)
        else:
            # 熔断/超时：用最近几轮文本生成兜底工作日志，状态按「暂停」留待接续
            outcome.work_log = self._fallback_work_log()
            outcome.artifacts = list(self.state.artifacts)
            self._save_fallback_session(outcome)
        transcript.event("workshop_finish", status=outcome.status,
                         steps=outcome.steps, tool_calls=outcome.tool_calls,
                         work_log=outcome.work_log, artifacts=outcome.artifacts)
        return outcome

    # ------------------------------------------------------------ 收尾辅助
    def _fallback_work_log(self) -> str:
        notes = [n for n in self.state.notes if n]
        if notes:
            text = "本轮进度（被系统收尾）：" + " → ".join(notes[-3:])
        else:
            text = "本轮没有产出可用进度（工坊在开始不久就被系统收尾）。"
        return truncate_chars(text, WORK_LOG_MAX_CHARS)

    def _save_fallback_session(self, outcome: WorkshopOutcome) -> None:
        session_id = outcome.session_id or work_session_store.new_session_id(self.chat_id)
        record = work_session_store.load(session_id) or {
            "session_id": session_id,
            "title": self.goal or "未命名工作",
            "kind": "misc",
            "chat_id": self.chat_id,
        }
        record.update({
            "status": "paused",
            "work_log": outcome.work_log,
            "artifacts": outcome.artifacts or list(record.get("artifacts") or []),
        })
        work_session_store.save(record)
        self.state.session_id = session_id
        self.state.work_log = outcome.work_log

    def _append_budget_reminder(self, messages: list[dict]) -> None:
        used = self.loop.tool_calls_count
        if used > self.max_tool_calls:
            return
        if not messages or messages[-1].get("role") != "tool":
            return
        if used >= max(1, self.max_tool_calls - 5):
            messages[-1]["content"] = str(messages[-1].get("content") or "") + (
                BUDGET_REMINDER_TEMPLATE.format(used=used, limit=self.max_tool_calls)
            )
        elif self.max_tool_calls >= 20 and used in (20, 35, 45):
            messages[-1]["content"] = str(messages[-1].get("content") or "") + (
                f"\n\n[工坊节奏提示：已用 {used}/{self.max_tool_calls} 次工具调用]"
            )

    def _drain_inner_events(self, messages: list[dict]) -> None:
        events = self.pop_inner_events()
        if not events:
            return
        for event in events:
            messages.append({
                "role": "user",
                "content": INNER_EVENT_TEMPLATE.format(
                    content=str(event.get("content") or "").strip()[:1500]
                ),
            })
        logger.info(f"[Workshop] {self.chat_id} 合并 {len(events)} 条内部事件进上下文")

    async def _attach_screenshots(self, results: list[dict], messages: list[dict]) -> None:
        attach = getattr(self.deps, "image_attach", None)
        if not callable(attach):
            return
        try:
            await attach(results, messages)
        except Exception as exc:
            logger.debug(f"[Workshop] 截图附加失败: {exc}")


def _main_tool_names(registry) -> list[str]:
    if registry is None or not hasattr(registry, "list_functions"):
        return []
    return list(registry.list_functions())
