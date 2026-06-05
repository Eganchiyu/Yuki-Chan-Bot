# core/toolchain.py
import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from config import cfg
from utils.logger import get_logger

logger = get_logger("toolchain")


@dataclass
class ToolResult:
    """工具调用的标准结果封装。"""
    name: str
    success: bool
    content: str
    data: Any = None
    error: str = ""

    def to_message_content(self) -> str:
        payload = {
            "success": self.success,
            "content": self.content,
            "data": self.data,
            "error": self.error,
        }
        return json.dumps(payload, ensure_ascii=False)


@dataclass
class ToolContext:
    """工具调用上下文，保持多轮工具调用期间的会话状态。"""
    chat_id: str
    mode: str
    history_dict: dict
    combined_text: str
    engine: Any
    metadata: dict = field(default_factory=dict)


class FunctionRegistry:
    """Function Call 注册中心：扫描、注册、提供 tools 列表。"""

    def __init__(self):
        self._functions = {}
        self._handlers = {}

    def register(self, schema: dict, handler: Callable[..., Awaitable[ToolResult]]):
        """注册一个 function tool。"""
        name = schema["function"]["name"]
        self._functions[name] = schema
        self._handlers[name] = handler
        logger.info(f"[FunctionRegistry] 注册 function: {name}")

    def unregister(self, name: str):
        """注销一个 function tool。"""
        if name in self._functions:
            del self._functions[name]
            del self._handlers[name]
            logger.info(f"[FunctionRegistry] 注销 function: {name}")

    def get_tools(self) -> list:
        """获取所有已注册的 tools 列表。"""
        return list(self._functions.values())

    def get_handler(self, name: str):
        """获取指定 function 的执行函数。"""
        return self._handlers.get(name)

    def list_functions(self) -> list:
        """列出所有已注册的 function 名称。"""
        return list(self._functions.keys())

    def scan_and_register(self, tools_list: list, handlers_dict: dict):
        """批量扫描并注册 tools（先清空再扫描）。"""
        self._functions.clear()
        self._handlers.clear()
        logger.info("[FunctionRegistry] 已清空所有注册")
        for tool in tools_list:
            name = tool["function"]["name"]
            if name in handlers_dict:
                self.register(tool, handlers_dict[name])
            else:
                logger.warning(f"[FunctionRegistry] tool {name} 缺少 handler，跳过注册")


class ToolCallManager:
    """工具调用执行器：负责参数解析、调用状态和结果标准化。"""

    def __init__(self, registry: FunctionRegistry, max_rounds: int = 4):
        self.registry = registry
        self.max_rounds = max_rounds
        self.sessions = {}

    def start_session(self, chat_id: str, user_text: str):
        """记录一次工具调用会话。"""
        self.sessions[chat_id] = {
            "started_at": time.time(),
            "user_text": user_text,
            "round": 0,
            "calls": [],
        }

    def finish_session(self, chat_id: str):
        """结束一次工具调用会话。"""
        self.sessions.pop(chat_id, None)

    async def execute_tool_call(self, tool_call: dict, context: ToolContext) -> dict:
        """执行单个 tool call，并返回 OpenAI tool 消息。"""
        function_info = tool_call.get("function", {})
        name = function_info.get("name", "")
        arguments_text = function_info.get("arguments") or "{}"
        call_id = tool_call.get("id", f"call_{int(time.time() * 1000)}")
        handler = self.registry.get_handler(name)

        logger.info(f"[ToolCall] 准备执行 chat_id={context.chat_id} name={name} args={arguments_text}")
        delay_seconds = max(0.0, float(getattr(cfg, "TOOL_CALL_DELAY_SECONDS", 1.2)))
        if delay_seconds > 0:
            logger.info(f"[ToolCall] {name} 等待 {delay_seconds:.1f}s 后执行")
            await asyncio.sleep(delay_seconds)

        started_at = time.time()
        if not handler:
            result = ToolResult(name=name, success=False, content="工具未注册", error="handler_not_found")
        else:
            try:
                args = json.loads(arguments_text) if isinstance(arguments_text, str) else arguments_text
                result = await handler(context, **(args or {}))
            except json.JSONDecodeError as e:
                result = ToolResult(name=name, success=False, content="工具参数不是合法 JSON", error=str(e))
            except TypeError as e:
                result = ToolResult(name=name, success=False, content="工具参数不符合接口要求", error=str(e))
            except Exception as e:
                logger.error(f"[ToolCall] {name} 执行失败: {e}")
                result = ToolResult(name=name, success=False, content="工具执行异常", error=str(e))

        elapsed = time.time() - started_at
        logger.info(
            f"[ToolCall] 执行完成 chat_id={context.chat_id} name={name} "
            f"success={result.success} elapsed={elapsed:.2f}s"
        )
        session = self.sessions.setdefault(context.chat_id, {"calls": [], "round": 0})
        session["calls"].append({"name": name, "success": result.success})
        return {
            "role": "tool",
            "tool_call_id": call_id,
            "name": name,
            "content": result.to_message_content(),
        }

    async def execute_tool_calls(self, tool_calls: list, context: ToolContext) -> list:
        """按顺序执行一轮工具调用，避免共享状态并发写入。"""
        messages = []
        for tool_call in tool_calls:
            messages.append(await self.execute_tool_call(tool_call, context))
        self.sessions.setdefault(context.chat_id, {"calls": [], "round": 0})["round"] += 1
        return messages
