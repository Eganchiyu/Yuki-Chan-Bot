# modules/autonomous/sandbox_loop.py
"""沙盒循环底座：静默发送器、内存历史适配器、独立 LLM 工具循环。

三条铁律（docs/autonomous-sandbox-plan.md §2）：
1. 非聊天模式不写真实会话历史 —— 走 `AdaptorHistory`（只读写内存流）；
2. 不往群里发消息 —— 走 `SilentSender`（记录到 outbox 便于观察，不触网）；
3. 工具视图自己算 —— 沙盒工具不注册进主 registry，`work_finish` 恒在可见集。
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from config import cfg
from core.tool_markup import extract_text_tool_calls
from core.toolchain import FunctionRegistry, ToolCallManager, ToolContext, ToolRuntime
from core.focus import ToolView
from utils.llm_client import llm_chat_raw
from utils.logger import get_logger

logger = get_logger("autonomous.loop")


class SilentSender:
    """静默发送器：记录「她本来想发什么」，但绝不真的发出去。"""

    def __init__(self, chat_id: str = ""):
        self.chat_id = str(chat_id)
        self.outbox: list[dict] = []
        self.connected = True

    def _record(self, kind: str, **payload):
        self.outbox.append({"kind": kind, "at": time.time(), **payload})
        logger.debug(f"[Sandbox] 拦截发送 {kind}: {str(payload)[:120]}")

    async def send(self, chat_id, message, mode="private"):
        self._record("text", chat_id=str(chat_id), mode=mode, message=str(message))
        return {"dry_run": True}

    async def send_local_image(self, chat_id, local_path, mode="private"):
        self._record("image", chat_id=str(chat_id), mode=mode, path=str(local_path))
        return {"dry_run": True}

    async def send_local_file(self, chat_id, local_path, mode="private"):
        self._record("file", chat_id=str(chat_id), mode=mode, path=str(local_path))
        return {"dry_run": True}

    async def send_local_voice(self, chat_id, local_path, mode="group"):
        self._record("voice", chat_id=str(chat_id), mode=mode, path=str(local_path))
        return {"dry_run": True}

    async def send_poke(self, user_id, group_id):
        self._record("poke", chat_id=str(group_id), user_id=user_id)
        return {"dry_run": True}

    async def parse_cq_codes(self, text, chat_id):
        return text


class AdaptorHistory:
    """给 `focus_manager.exit(history=...)` 用的内存历史适配器。

    只暴露 get_session / replace_session / append_session_message，
    读写的都是模式自己的内存流，绝不碰 data/chat_history.json。
    """

    def __init__(self, chat_id: str, messages: list[dict] | None = None):
        self.chat_id = str(chat_id)
        self.messages: list[dict] = list(messages or [])

    def get_session(self, chat_id=None, system_content=None) -> list:
        return self.messages

    def replace_session(self, chat_id=None, session: list | None = None) -> list:
        self.messages = list(session or [])
        return self.messages

    def append_session_message(self, chat_id=None, role="user", content="", **extra) -> list:
        item = {"role": role, "content": content}
        item.update(extra)
        self.messages.append(item)
        return self.messages


@dataclass
class SandboxDeps:
    """一次沙盒运行需要的外部依赖（由 coordinator 从 pipeline 上采集）。"""

    yuki: Any
    sender: Any
    main_registry: Any
    history_manager: Any = None
    memory_rag: Any = None
    image_store: Any = None
    process_callback: Any = None
    gateway: Any = None
    image_attach: Any = None          # 工具截图转多模态块的辅助函数（可选）


@dataclass
class LoopStep:
    idx: int
    content: str
    calls: list[dict] = field(default_factory=list)
    results: list[dict] = field(default_factory=list)
    llm_ms: int = 0
    tool_names: list[str] = field(default_factory=list)


class SandboxLoop:
    """独立的 LLM 工具循环：一次一步，由调用方决定何时停。"""

    def __init__(
        self,
        *,
        chat_id,
        registry: FunctionRegistry,
        context: ToolContext,
        history: AdaptorHistory,
        max_steps: int,
        max_tokens: int | None = None,
        temperature: float = 0.9,
        tool_choice: str = "auto",
        model: str | None = None,
        debug_tag: str = "",
        pinned: set[str] | None = None,
    ):
        self.chat_id = str(chat_id)
        self.registry = registry
        self.context = context
        self.history = history
        self.max_steps = max(1, int(max_steps))
        self.max_tokens = int(max_tokens or cfg.autonomous.debate_max_tokens)
        self.temperature = float(temperature)
        self.tool_choice = tool_choice
        self.model = model
        self.debug_tag = debug_tag
        self.step_index = 0
        self.tool_calls_count = 0
        self.pinned: set[str] = set(pinned or ())
        self.steps: list[LoopStep] = []
        self._manager = ToolCallManager(registry, max_rounds=self.max_steps)

    # ------------------------------------------------------------ 工具视图
    def all_tool_names(self) -> set[str]:
        return set(self.registry.list_functions())

    def focus_view(self) -> set[str]:
        """主 registry 的当前视图（含子聚焦收起），再加沙盒常驻工具。"""
        from core.focus import focus_manager

        names = set(ToolView.resolve(self.registry, focus_manager, self.chat_id).visible)
        return (names | self.pinned) & self.all_tool_names()

    def view(self, visible: set[str] | None = None) -> ToolView:
        names = self.focus_view() if visible is None else (set(visible) & self.all_tool_names())
        return ToolView(frozenset(names))

    def schemas(self, visible: set[str] | None = None) -> list[dict]:
        return self.registry.get_tools(view=self.view(visible))

    # ------------------------------------------------------------ LLM
    async def call_model(self, messages: list[dict], visible: set[str] | None = None) -> tuple[dict, int]:
        tools = self.schemas(visible)
        if not tools:
            tools = []
        started = time.monotonic()
        msg = await llm_chat_raw(
            messages=messages,
            model=self.model,
            temperature=self.temperature,
            top_p=0.8,
            max_tokens=self.max_tokens,
            tools=tools,
            tool_choice=self.tool_choice if tools else "none",
        )
        return msg, int((time.monotonic() - started) * 1000)

    def extract_calls(self, msg: dict, visible: set[str] | None = None) -> list[dict]:
        """原生 tool_calls 优先；模型把调用写成正文时用 tool_markup 还原。"""
        calls = list(msg.get("tool_calls") or [])
        if calls:
            return calls
        valid = self.all_tool_names() if visible is None else (set(visible) & self.all_tool_names())
        text_calls, cleaned = extract_text_tool_calls(msg.get("content"), valid)
        if text_calls:
            logger.warning(
                f"[Sandbox] {self.chat_id} 工具调用被写成正文，已解析为真实调用: "
                f"{[c['function']['name'] for c in text_calls]}"
            )
            msg["content"] = cleaned
            msg["tool_calls"] = text_calls
        return text_calls

    # ------------------------------------------------------------ 执行
    async def execute_calls(self, calls: list[dict], visible: set[str] | None = None,
                            finish_reason: str = "") -> list[dict]:
        view = self.view(visible)
        results = await self._manager.execute_tool_calls(
            calls, self.context, finish_reason=finish_reason, view=view,
        )
        self.tool_calls_count += len(results)
        return results

    async def step(
        self,
        content: str | None = None,
        *,
        visible: set[str] | None = None,
        timeout: float | None = None,
    ) -> LoopStep | None:
        """新增一条 user 消息（可选）并跑一步；返回 None 表示超时/被跳过。"""
        raise NotImplementedError

    @staticmethod
    def summarize_calls(calls: list[dict]) -> str:
        names = [(c.get("function") or {}).get("name") or "?" for c in calls]
        return "、".join(names) if names else ""


def parse_tool_payload(result_message: dict) -> dict:
    """把 tool 消息的 JSON 内容解成 dict（失败返回空 dict）。"""
    try:
        payload = json.loads(result_message.get("content") or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def build_tool_context(
    *,
    chat_id,
    yuki,
    sender,
    history: AdaptorHistory,
    image_store=None,
    mode: str = "group",
    metadata: dict | None = None,
) -> ToolContext:
    return ToolContext(
        chat_id=str(chat_id),
        mode=mode,
        session=history.messages,
        combined_text="",
        runtime=ToolRuntime(sender=sender, yuki_state=yuki, image_store=image_store),
        metadata=dict(metadata or {}),
    )


async def run_step_with_timeout(coro, seconds: float | None = None):
    """单步超时熔断：LLM + 该批工具整体不超过 step_timeout_seconds。"""
    limit = float(seconds or cfg.autonomous.step_timeout_seconds)
    return await asyncio.wait_for(coro, timeout=limit)
