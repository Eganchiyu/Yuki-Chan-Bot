# core/tool_prune.py
"""工具历史折叠。

Yuki 亲手操作（bash / 手机）后，历史里会留下大段原始输出。这些输出只在「正在连续
操作」时有价值：一旦连续 N 轮都没再调用工具，说明那件事已经收尾，原始输出就是纯
噪音。这里在那种时刻把历史里的工具消息压成一行存根：

    【历史操作·已折叠】bash "adb devices" exit=0 备注:手机已连上

折叠不消耗任何 LLM 调用——Yuki 当时的最终回复和 note 参数本身就是这轮操作的总结。
"""
import json

from utils.logger import get_logger

logger = get_logger("tool_prune")

STUB_PREFIX = "【历史操作·已折叠】"
STUB_MAX_CHARS = 220


def _payload(content) -> dict:
    if not isinstance(content, str):
        return {}
    try:
        data = json.loads(content)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _stub(name: str, payload: dict) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    note = str(data.get("note") or "").strip()

    if name == "bash":
        command = str(data.get("command") or "").strip().replace("\n", " ")
        text = f'bash "{command[:80]}" exit={data.get("exit_code", "?")}'
    elif name == "phone_action":
        text = f"phone_action {data.get('action', '?')}"
        steps = data.get("steps") or []
        if steps:
            text += f" ({' / '.join(str(s) for s in steps[:3])})"
    else:
        # 其他工具本来就不长，保守地保留开头
        text = str(payload.get("content") or "").replace("\n", " ")

    if note:
        text += f" 备注:{note}"
    stub = f"{STUB_PREFIX}{text}"
    return stub[:STUB_MAX_CHARS]


class ToolHistoryPruner:
    """按会话统计「连续多少轮没调工具」，到阈值时折叠历史工具输出。"""

    def __init__(self, history_manager, idle_turns: int = 2):
        self.history = history_manager
        self.idle_turns = max(1, int(idle_turns or 2))
        self._idle: dict[str, int] = {}

    def note_turn(self, chat_id: str, tools_executed: bool) -> bool:
        """记录一轮结果，返回是否该折叠。"""
        cid = str(chat_id)
        if tools_executed:
            self._idle[cid] = 0
            return False
        idle = self._idle.get(cid, 0) + 1
        if idle >= self.idle_turns:
            self._idle[cid] = 0
            return True
        self._idle[cid] = idle
        return False

    def prune(self, chat_id: str) -> int:
        """把该会话里未折叠的工具消息压成存根，返回折叠条数。"""
        cid = str(chat_id)
        try:
            session = self.history.get_session(cid)
        except Exception as exc:
            logger.warning(f"[ToolPrune] 读取会话失败: {exc}")
            return 0

        pruned = 0
        for message in session:
            if not isinstance(message, dict) or message.get("role") != "tool":
                continue
            if message.get("pruned"):
                continue
            payload = _payload(message.get("content"))
            message["content"] = _stub(str(message.get("name") or ""), payload)
            message["pruned"] = True
            pruned += 1

        if pruned:
            try:
                self.history.replace_session(cid, session)
            except Exception as exc:
                logger.warning(f"[ToolPrune] 写回失败: {exc}")
                return 0
            logger.info(f"[ToolPrune] chat={cid} 已折叠 {pruned} 条工具输出")
        return pruned

    def after_turn(self, chat_id: str, tools_executed: bool) -> int:
        """一轮结束后调用：够轮数就折叠，返回折叠条数。"""
        if self.note_turn(chat_id, tools_executed):
            return self.prune(chat_id)
        return 0
