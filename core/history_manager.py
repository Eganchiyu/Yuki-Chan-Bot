import datetime
import copy
import json
import os
import threading
from typing import Any

from config import cfg
from utils.logger import get_logger

logger = get_logger("history")


class HistoryManager:
    def __init__(self, history_file=cfg.HISTORY_FILE, log_file=cfg.LOG_FILE):
        self.history_file = history_file
        self.log_file = log_file
        self._cache = None
        self._dirty = False
        self._lock = threading.Lock()

    def preload(self) -> None:
        """只预载历史到内存，不返回全量深拷贝。"""
        with self._lock:
            self._get_data_locked()

    def load(self, *, copy_result: bool = True) -> dict:
        """获取全部历史；默认返回独立快照以兼容旧调用。"""
        with self._lock:
            data = self._get_data_locked()
            return copy.deepcopy(data) if copy_result else data

    @staticmethod
    def _ensure_system_message(session: list, system_content: str | None) -> bool:
        """确保 system 提示词存在，返回会话是否被修改。"""
        if not system_content:
            return False
        if not session:
            session.append({"role": "system", "content": system_content})
            return True
        if session[0].get("role") == "system":
            if session[0].get("content") == system_content:
                return False
            session[0]["content"] = system_content
            return True
        session.insert(0, {"role": "system", "content": system_content})
        return True

    def get_session(self, chat_id: str, system_content: str | None = None) -> list:
        """获取单个会话，并只在 system 提示词变化时落盘。"""
        cid = str(chat_id)
        with self._lock:
            data = self._get_data_locked()
            session = data.setdefault(cid, [])
            if self._ensure_system_message(session, system_content):
                self._save_locked(data)
            return copy.deepcopy(session)

    def replace_session(self, chat_id: str, session: list) -> list:
        """原子替换一个会话并返回替换后的独立快照。"""
        cid = str(chat_id)
        with self._lock:
            data = self._get_data_locked()
            data[cid] = copy.deepcopy(session)
            self._save_locked(data)
            return copy.deepcopy(data[cid])

    def session_exists(self, chat_id: str) -> bool:
        """判断会话是否存在。"""
        with self._lock:
            return str(chat_id) in self._get_data_locked()

    def append_session_message(
        self,
        chat_id: str,
        role: str,
        content: str,
        system_content: str | None = None,
        *,
        save_immediately: bool = True,
        return_snapshot: bool = True,
        **extra: Any,
    ):
        """向单个会话追加消息，可按需延迟落盘或跳过返回深拷贝。"""
        cid = str(chat_id)
        with self._lock:
            data = self._get_data_locked()
            session = data.setdefault(cid, [])
            self._ensure_system_message(session, system_content)
            item = {
                "role": role,
                "content": content,
                "time": datetime.datetime.now().strftime("%Y年%m月%d日%H:%M"),
            }
            item.update(extra)
            session.append(item)
            self._mark_dirty_locked(data)
            if save_immediately:
                self._save_locked(data)
            return copy.deepcopy(session) if return_snapshot else None

    def _get_data_locked(self) -> dict:
        if self._cache is None:
            logger.info("[History] 正在预载历史数据到内存...")
            self._cache = self.read_from_disk()
        return self._cache

    def _mark_dirty_locked(self, data: dict) -> None:
        self._cache = data
        self._dirty = True

    def flush(self) -> None:
        """将延迟写入的历史一次性落盘。"""
        with self._lock:
            if self._dirty and self._cache is not None:
                self._save_locked(self._cache)

    def _save_locked(self, data: dict):
        self._cache = data
        temp_file = f"{self.history_file}.tmp"
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.history_file)), exist_ok=True)
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
            os.replace(temp_file, self.history_file)
            self._dirty = False
        except Exception as e:
            logger.error(f"[History] 保存失败: {e}")
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def read_from_disk(self) -> dict:
        """从硬盘读取数据，增加格式校验"""
        if not os.path.exists(self.history_file):
            return {}
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 如果读出来的是 list 或者是 None，强行转成 dict
                return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.error(f"[History] 加载文件失败: {e}")
            return {}

    def save(self, data: dict):
        """原子化替换全部历史。"""
        with self._lock:
            self._save_locked(copy.deepcopy(data))

    def append_to_log(self, chat_id, sender, message):
        time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{time_str}] [{chat_id}] {sender}: {message}\n"
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(log_entry)

    def inject_whisper(self, chat_id, message):
        """向指定对话注入悄悄话。"""
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
