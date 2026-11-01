# core/notebook.py
"""小本本：Yuki 自己长期维护的私密笔记，最多 512 字。"""
import json
import os
import threading

from utils import BASE_DIR
from utils.logger import get_logger

logger = get_logger("notebook")

NOTEBOOK_MAX_CHARS = 512
DEFAULT_NOTEBOOK_PATH = os.path.join(BASE_DIR, "data", "notebook.json")


class NotebookStore:
    """小本本的持久化存储（全局一份，不区分群聊）。"""

    def __init__(self, path: str = DEFAULT_NOTEBOOK_PATH):
        self.path = os.path.abspath(path)
        self._lock = threading.Lock()

    def load(self) -> str:
        """读取小本本内容，文件不存在或损坏时返回空字符串。"""
        if not os.path.exists(self.path):
            return ""
        with self._lock:
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                logger.warning(f"[Notebook] 读取失败: {e}")
                return ""
        content = data.get("content") if isinstance(data, dict) else data
        return str(content or "")[:NOTEBOOK_MAX_CHARS]

    def save(self, content: str) -> str:
        """覆盖写入小本本，超长部分截断到 512 字，返回实际保存的内容。"""
        content = str(content or "").strip()
        truncated = len(content) > NOTEBOOK_MAX_CHARS
        content = content[:NOTEBOOK_MAX_CHARS]
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        temp_file = f"{self.path}.tmp"
        with self._lock:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump({"content": content}, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, self.path)
        if truncated:
            logger.info(f"[Notebook] 内容超长已截断到 {NOTEBOOK_MAX_CHARS} 字")
        return content


notebook_store = NotebookStore()
