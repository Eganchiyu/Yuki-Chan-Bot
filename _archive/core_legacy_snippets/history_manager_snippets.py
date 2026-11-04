# 原位于 core/history_manager.py 的未挂载方法
import datetime
from config import cfg
from utils.logger import get_logger

logger = get_logger("history")


def session_exists(self, chat_id: str) -> bool:
    """判断会话是否存在。（原位于 core/history_manager.py 第 110-113 行）"""
    with self._lock:
        return str(chat_id) in self._get_data_locked()


def inject_whisper(self, chat_id, message):
    """向指定对话注入悄悄话。（原位于 core/history_manager.py 第 199-216 行）"""
    cid = str(chat_id)
    with self._lock:
        data = self._get_data_locked()
        session = data.get(cid)
        if session is None:
            logger.warning(f"对话 {chat_id} 不存在")
            return False
        item = {
            "role": "assistant",
            "content": f"【{cfg.MASTER_NAME}对{cfg.ROBOT_NAME}的悄悄话】：{message}",
            "time": datetime.datetime.now().strftime("%Y年%m月%d日%H:%M"),
        }
        session.append(item)
        self._save_locked(data)
    logger.info(f"悄悄话已注入到对话 {chat_id}: {message}")
    return True
