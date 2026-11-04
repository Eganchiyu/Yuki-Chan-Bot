# 原位于 core/toolchain.py 的 ToolCallManager 空兼容钩子（第 186-190 行）


def start_session(self, chat_id: str, user_text: str):
    """保留会话入口，当前仅用于兼容调用点。"""


def finish_session(self, chat_id: str):
    """保留会话出口，当前无需维护额外状态。"""
