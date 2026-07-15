import datetime
import json
import os
import threading

from config import cfg
from utils.logger import get_logger

logger = get_logger("history")


class HistoryManager:
    def __init__(self, history_file=cfg.HISTORY_FILE, log_file=cfg.LOG_FILE):
        self.history_file = history_file
        self.log_file = log_file
        self._cache = None
        self._lock = threading.Lock()

    def load(self) -> dict:
        """【外部调用】获取所有历史（带缓存）"""
        with self._lock:
            if self._cache is None:
                # 第一次访问，从硬盘读入内存
                logger.info("[History] 正在预载历史数据到内存...")
                self._cache = self.read_from_disk()
            return self._cache

    @staticmethod
    def _ensure_system_message(session: list, system_content: str | None):
        if not system_content:
            return session
        if not session:
            session.append({"role": "system", "content": system_content})
        elif session[0].get("role") == "system":
            session[0]["content"] = system_content
        else:
            session.insert(0, {"role": "system", "content": system_content})
        return session

    def get_session(self, chat_id: str, system_content: str | None = None) -> list:
        """获取单个会话，并按需补齐 system 提示词。"""
        data = self.load()
        cid = str(chat_id)
        session = data.setdefault(cid, [])
        return self._ensure_system_message(session, system_content)

    def append_session_message(self, chat_id: str, role: str, content: str, **extra):
        """向单个会话追加一条消息，并同步落盘。"""
        data = self.load()
        cid = str(chat_id)
        session = data.setdefault(cid, [])
        item = {
            "role": role,
            "content": content,
            "time": datetime.datetime.now().strftime("%Y年%m月%d日%H:%M"),
        }
        item.update(extra)
        session.append(item)
        self.save(data)
        return session

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
        """【外部调用】原子化保存并同步更新内存"""
        with self._lock:
            # 1. 同步内存缓存
            self._cache = data

            # 2. 原子化保存到硬盘
            temp_file = f"{self.history_file}.tmp"
            try:
                # 确保目录存在
                os.makedirs(os.path.dirname(os.path.abspath(self.history_file)), exist_ok=True)

                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                # 原子替换：即使程序在中途崩溃，原有的 history.json 也不会坏
                os.replace(temp_file, self.history_file)
            except Exception as e:
                logger.error(f"[History] 保存失败: {e}")
                if os.path.exists(temp_file):
                    os.remove(temp_file)

    def get_chat(self, chat_id: str) -> list:
        """【快捷获取】直接拿到某个 chat_id 的历史列表"""
        data = self.load()
        return data.get(str(chat_id), [])

    def append_chat(self, chat_id: str, role: str, content: str):
        """【快捷添加】一步完成：读取、追加、保存"""
        return self.append_session_message(chat_id, role, content)

    def append_to_log(self, chat_id, sender, message):
        time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{time_str}] [{chat_id}] {sender}: {message}\n"
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(log_entry)

    def inject_whisper(self, chat_id, message):
        """向指定对话注入悄悄话"""
        history = self.load()
        cid = str(chat_id)

        if cid in history:
            whisper_msg = {
                "role": "assistant",
                "content": f"【{cfg.MASTER_NAME}对{cfg.ROBOT_NAME}的悄悄话】：{message}"
            }
            history[cid].append(whisper_msg)
            self.save(history)
            logger.info(f"悄悄话已注入到对话 {chat_id}: {message}")
            return True
        else:
            logger.warning(f"对话 {chat_id} 不存在")
            return False
