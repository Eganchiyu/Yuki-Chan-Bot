# core/history_filter.py
"""会话历史里的「聊天部分」过滤。

历史里混着三类消息：
    - system：人设/回忆/小本本，属于注入内容；
    - user / assistant：真正的聊天往来；
    - tool：工具执行结果（bash 输出、手机控件树……），只是当时的临时材料。

日记只该记录聊天——轮数统计也只看聊天轮数，否则 Yuki 连续用几次工具就会
把「写日记」提前触发，写出来的日记还全是命令输出。
"""

DIALOGUE_ROLES = ("user", "assistant")


def is_dialogue_message(message) -> bool:
    """是否为聊天消息（排除 system 注入与 tool 结果）。"""
    return isinstance(message, dict) and message.get("role") in DIALOGUE_ROLES


def dialogue_messages(history) -> list:
    """只保留聊天消息，顺序不变。"""
    return [message for message in (history or []) if is_dialogue_message(message)]


def dialogue_length(history) -> int:
    """聊天消息条数（用于日记触发阈值）。"""
    return len(dialogue_messages(history))
