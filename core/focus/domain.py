# core/focus/domain.py
"""聚焦模式领域声明（纯数据 + 可选生命周期钩子）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

# 聚焦模式下默认保留的群聊基础互动工具
BASE_KEEP_TOOLS: frozenset[str] = frozenset({
    "send_master_private",
    "send_qq_file",
    "search_diary",
})


@dataclass(frozen=True)
class FocusDomain:
    """单个聚焦模式的完整声明。"""

    name: str                                               # 域名，如 "phone" / "art"
    title: str                                              # 人类可读名称，如 "手机" / "艺术创作"
    entry_tool: str                                         # 常态唯一暴露的入口，如 "phone_start"
    exit_tool: str                                          # 退出工具，如 "phone_finish"
    domain_tools: frozenset[str]                            # 只在聚焦时展开的专精工具
    keep_tools: frozenset[str] = BASE_KEEP_TOOLS            # 聚焦时保留的基础工具
    summary_prefix: str = ""                                # 默认 f"【{title}总结】"
    exit_hint: str = ""                                     # 内存覆写时附在总结后的当轮提示
    idle_turns_key: str = ""                                # cfg.tools 上的配置键，空则用默认值 5
    max_rounds_key: str = ""                                # cfg.tools 上的配置键，空则用默认值 100
    max_trace: int = 20
    default_fallback: str = ""                              # state 为空时的默认兜底总结
    empty_trace_fallback: str = ""                          # goal 和 trace 均为空时的兜底总结

    # —— 可选钩子（都有空实现，按需覆盖）——
    on_enter: Callable[[str, str], None] | None = None              # (chat_id, goal)
    on_exit: Callable[[str, str, str], None] | None = None          # (chat_id, summary, reason)
    on_model_call: Callable[[str, str, list], None] | None = None   # (chat_id, thought, tool_calls)
    on_final_reply: Callable[[str, str, str], None] | None = None   # (chat_id, raw_ans, clean_ans)
    on_incoming: Callable[[str, str], None] | None = None           # (chat_id, text)
    stub: Callable[[dict], str] | None = None                       # 给 pruner 的单行存根格式

    @property
    def effective_summary_prefix(self) -> str:
        return self.summary_prefix or f"【{self.title}总结】"

    @property
    def effective_exit_hint(self) -> str:
        return self.exit_hint or f"（你已结束本轮{self.title}操作，请直接根据上述操作结果回复用户。）"

    @property
    def work_tools(self) -> frozenset[str]:
        """覆写时要抹掉的工具 = 入口 + 专精 + 退出。"""
        return frozenset({self.entry_tool, self.exit_tool, *self.domain_tools})

    @property
    def hidden_in_default(self) -> frozenset[str]:
        """常态视图下隐藏的工具 = 专精 + 退出（仅保留入口）。"""
        return frozenset({self.exit_tool, *self.domain_tools})

    @property
    def focus_allowed(self) -> frozenset[str]:
        """聚焦视图下白名单允许的工具 = 专精 + 退出 + 基础保留工具。"""
        return frozenset({self.exit_tool, *self.domain_tools, *self.keep_tools})
