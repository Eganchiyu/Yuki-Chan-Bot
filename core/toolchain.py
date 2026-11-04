# core/toolchain.py
import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from config import cfg
from utils.logger import get_logger

logger = get_logger("toolchain")

# 委托小女仆时的目标描述约束：工具轮次输出上限有限，参数写太长会被截断
MAID_GOAL_BREVITY_HINT = (
    "（调用时 arguments 务必简练：单个字符串参数控制在 500 字以内，"
    "只写关键指令，不要复制整段聊天记录或历史内容。）"
)

# skip 工具生效后，引擎用它作为「本轮不回复」的最终回复标记，管线见到后不发送任何消息
SKIP_REPLY_MARKER = "\x00SKIP_REPLY\x00"


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
    # False 表示工具结果不回写会话历史（仅本轮对话内可见），避免污染长期上下文
    persist_result: bool = True

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

    def get_spec(self, name: str) -> ToolSpec | None:
        """获取指定 function 的声明。"""
        return self._tools.get(name)

    def list_functions(self) -> list:
        """列出所有已注册的 function 名称。"""
        return list(self._tools.keys())

    def scan_and_register(self, tool_specs: list[ToolSpec]):
        """批量注册 tools（先清空再扫描）。"""
        self._tools.clear()
        logger.info("[FunctionRegistry] 已清空所有注册")
        for spec in tool_specs:
            self.register(spec)


class ToolCallManager:
    """工具调用执行器：负责参数解析、调用状态和结果标准化。"""

    def __init__(self, registry: FunctionRegistry, max_rounds: int = 4):
        self.registry = registry
        self.max_rounds = max_rounds
        self.timeout_seconds = max(1.0, float(getattr(cfg.timing, "tool_call_timeout_seconds", 120)))

    @staticmethod
    def _delay_seconds() -> float:
        return max(0.0, float(cfg.timing.tool_call_delay_seconds))

    async def execute_tool_call(self, tool_call: dict, context: ToolContext, finish_reason: str = "") -> dict:
        """执行单个 tool call，并返回 OpenAI tool 消息。

        finish_reason 来自本轮模型响应，用于区分「参数写错」和「参数被输出上限截断」，
        后者要提示模型压缩参数后重试，否则它会重复生成同样的超长参数。
        """
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
                if isinstance(result.data, dict) and result.data.get("skip_reply"):
                    # 标记本轮保持安静，由引擎收尾、管线跳过发送
                    context.metadata["skip_reply"] = True
            except json.JSONDecodeError as e:
                logger.warning(f"[ToolCall] {name} 参数 JSON 无效: {e} (finish_reason={finish_reason})")
                if finish_reason == "length":
                    feedback = (
                        f"工具参数不是合法 JSON：arguments 在输出上限处被截断（{e}）。"
                        f"请重新调用 {name}，把参数压缩到 500 字以内，只保留最关键的指令。"
                    )
                else:
                    feedback = (
                        f"工具参数不是合法 JSON（{e}）。请重新调用 {name}，"
                        "arguments 必须是完整合法的 JSON 对象，字符串里的引号、换行要转义。"
                    )
                result = ToolResult.failure(
                    feedback,
                    "invalid_json",
                    data={"finish_reason": finish_reason, "arguments_tail": arguments_text[-160:]},
                    name=name,
                )
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

    async def execute_tool_calls(self, tool_calls: list, context: ToolContext, finish_reason: str = "") -> list:
        """按顺序执行一轮工具调用，避免共享状态并发写入。"""
        messages = []
        for tool_call in tool_calls:
            messages.append(await self.execute_tool_call(tool_call, context, finish_reason))
            if context.metadata.get("skip_reply"):
                # 已经决定不说话了，同批剩下的工具不再执行，避免跳过之后又发出消息
                break
        return messages
