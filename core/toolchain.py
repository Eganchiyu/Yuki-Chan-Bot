# core/toolchain.py
import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from config import cfg
from utils.logger import get_logger

logger = get_logger("toolchain")


@dataclass
class ToolResult:
    """工具调用的标准结果封装。"""
    success: bool
    content: str
    data: Any = None
    error: str = ""
    name: str = ""

    def __post_init__(self):
        if self.success:
            self.error = ""
        elif not self.error:
            self.error = "tool_failed"

    @classmethod
    def failure(cls, content: str, error: str, data: Any = None, name: str = ""):
        return cls(success=False, content=content, data=data, error=error, name=name)

    def to_message_content(self) -> str:
        payload = {
            "success": self.success,
            "content": self.content,
            "data": self.data,
            "error": self.error,
        }
        return json.dumps(payload, ensure_ascii=False)


@dataclass
class ToolRuntime:
    """工具可访问的运行时依赖，避免直接暴露完整 Engine。"""
    sender: Any
    yuki_state: Any
    image_store: Any = None


@dataclass
class ToolContext:
    """工具调用上下文，保持多轮工具调用期间的会话状态。"""
    chat_id: str
    mode: str
    session: list
    combined_text: str
    runtime: ToolRuntime
    metadata: dict = field(default_factory=dict)

    @property
    def history(self):
        return self.session

    @property
    def sender(self):
        return self.runtime.sender

    @property
    def yuki(self):
        return self.runtime.yuki_state

    @property
    def image_store(self):
        return self.runtime.image_store


@dataclass
class ToolSpec:
    """单个 function tool 的声明，统一维护 schema 与 handler。"""
    name: str
    description: str
    parameters: dict
    handler: Callable[..., Awaitable[ToolResult]]

    def to_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class FunctionRegistry:
    """Function Call 注册中心：注册、注销、提供 tools 列表。"""

    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec):
        """注册一个 function tool。"""
        self._tools[spec.name] = spec
        logger.info(f"[FunctionRegistry] 注册 function: {spec.name}")

    def unregister(self, name: str):
        """注销一个 function tool。"""
        if name in self._tools:
            del self._tools[name]
            logger.info(f"[FunctionRegistry] 注销 function: {name}")

    def get_tools(self) -> list:
        """获取所有已注册的 tools schema 列表。"""
        return [spec.to_schema() for spec in self._tools.values()]

    def get_handler(self, name: str):
        """获取指定 function 的执行函数。"""
        spec = self._tools.get(name)
        return spec.handler if spec else None

    def list_functions(self) -> list:
        """列出所有已注册的 function 名称。"""
        return list(self._tools.keys())

    def scan_and_register(self, tool_specs: list[ToolSpec]):
        """批量注册 tools（先清空再扫描）。"""
        self._tools.clear()
        logger.info("[FunctionRegistry] 已清空所有注册")
        for spec in tool_specs:
            self.register(spec)


class ToolRegistryProvider:
    """按 mode 提供不同 FunctionRegistry。"""

    def __init__(self, default_specs: list[ToolSpec], mode_specs: dict[str, list[ToolSpec]] | None = None):
        self.default_registry = FunctionRegistry()
        self.default_registry.scan_and_register(default_specs)
        self._registries: dict[str, FunctionRegistry] = {"default": self.default_registry}
        self._mode_to_group: dict[str, str] = {}
        for mode, specs in (mode_specs or {}).items():
            registry = FunctionRegistry()
            registry.scan_and_register(specs)
            self._registries[mode] = registry
            self._mode_to_group[mode] = mode

    def get_registry(self, mode: str | None = None) -> FunctionRegistry:
        """获取指定 mode 的工具注册表，未知 mode 回退默认工具组。"""
        if not mode:
            return self.default_registry
        group = self._mode_to_group.get(mode, mode)
        return self._registries.get(group, self.default_registry)

    def get_tools(self, mode: str | None = None) -> list:
        return self.get_registry(mode).get_tools()

    def list_functions(self, mode: str | None = None) -> list:
        return self.get_registry(mode).list_functions()


class ToolCallManager:
    """工具调用执行器：负责参数解析、调用状态和结果标准化。"""

    def __init__(self, registry: FunctionRegistry, max_rounds: int = 4):
        self.registry = registry
        self.max_rounds = max_rounds
        self.timeout_seconds = max(1.0, float(getattr(cfg.timing, "tool_call_timeout_seconds", 120)))

    def start_session(self, chat_id: str, user_text: str):
        """保留会话入口，当前仅用于兼容调用点。"""

    def finish_session(self, chat_id: str):
        """保留会话出口，当前无需维护额外状态。"""

    @staticmethod
    def _delay_seconds() -> float:
        return max(0.0, float(cfg.timing.tool_call_delay_seconds))

    async def execute_tool_call(self, tool_call: dict, context: ToolContext) -> dict:
        """执行单个 tool call，并返回 OpenAI tool 消息。"""
        function_info = tool_call.get("function", {})
        name = function_info.get("name", "")
        arguments_text = function_info.get("arguments") or "{}"
        call_id = tool_call.get("id", f"call_{int(time.time() * 1000)}")
        handler = self.registry.get_handler(name)

        logger.debug(f"[ToolCall] 准备执行 chat_id={context.chat_id} name={name} args={arguments_text}")
        delay_seconds = self._delay_seconds()
        if delay_seconds > 0:
            logger.debug(f"[ToolCall] {name} 等待 {delay_seconds:.1f}s 后执行")
            await asyncio.sleep(delay_seconds)

        started_at = time.time()
        if not handler:
            result = ToolResult.failure("工具未注册", "handler_not_found", name=name)
        else:
            try:
                args = json.loads(arguments_text) if isinstance(arguments_text, str) else arguments_text
                if not isinstance(args, dict):
                    raise TypeError("工具参数必须是 JSON 对象")
                result = await asyncio.wait_for(
                    handler(context, **args),
                    timeout=self.timeout_seconds,
                )
                if not isinstance(result, ToolResult):
                    raise TypeError("工具必须返回 ToolResult")
                result.name = result.name or name
            except json.JSONDecodeError as e:
                logger.warning(f"[ToolCall] {name} 参数 JSON 无效: {e}")
                result = ToolResult.failure("工具参数不是合法 JSON", "invalid_json", name=name)
            except TypeError as e:
                logger.warning(f"[ToolCall] {name} 参数不符合接口要求: {e}")
                result = ToolResult.failure("工具参数不符合接口要求", "invalid_arguments", name=name)
            except asyncio.TimeoutError:
                logger.error(f"[ToolCall] {name} 执行超时 ({self.timeout_seconds:.1f}s)")
                result = ToolResult.failure("工具执行超时", "timeout", name=name)
            except Exception as e:
                logger.error(f"[ToolCall] {name} 执行失败: {e}")
                result = ToolResult.failure("工具执行异常", "tool_execution_failed", name=name)

        elapsed = time.time() - started_at
        logger.info(f"[ToolCall] {name} chat={context.chat_id} success={result.success} elapsed={elapsed:.2f}s")
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
        return messages
