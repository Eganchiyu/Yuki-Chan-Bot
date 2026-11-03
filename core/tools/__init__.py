# core/tools/__init__.py
"""工具模块门面：拆分后保持 `core.tools` 旧引用路径与公开名称兼容。"""
from .tools import TOOL_HANDLERS, TOOL_SCHEMAS, TOOL_SPECS
from .tools_diary import search_diary_tool
from .tools_maid import delegate_to_maid_tool
from .tools_media import download_file_tool, generate_image_tool
from .tools_message import poke_tool, send_master_private_tool, send_qq_file_tool
from .tools_notebook import update_notebook_tool
from .tools_rich import parse_rich_message_tool
from .tools_skip import skip_reply_tool
from .tools_snapshot import capture_group_snapshot_tool, search_group_snapshots_tool

__all__ = [
    "TOOL_SPECS",
    "TOOL_SCHEMAS",
    "TOOL_HANDLERS",
    "search_diary_tool",
    "delegate_to_maid_tool",
    "download_file_tool",
    "generate_image_tool",
    "poke_tool",
    "send_master_private_tool",
    "send_qq_file_tool",
    "update_notebook_tool",
    "parse_rich_message_tool",
    "skip_reply_tool",
    "capture_group_snapshot_tool",
    "search_group_snapshots_tool",
]
