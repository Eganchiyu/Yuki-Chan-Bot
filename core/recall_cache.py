# core/recall_cache.py
"""记忆召回缓存：把每个会话「最近两轮召回各自的最佳日记」落盘，重启后不丢。"""
import os
import threading

from utils import BASE_DIR
from utils.json_store import atomic_write_json, read_json_cached
from utils.logger import get_logger

logger = get_logger("recall_cache")

DEFAULT_RECALL_CACHE_PATH = os.path.join(BASE_DIR, "data", "recall_best.json")
_MAX_KEEP = 2  # 只保留最近两轮


class RecallCacheStore:
    """按 chat_id 保存最近两轮召回的 top-1（JSON 落盘，进程内缓存）。"""

    def __init__(self, path: str = DEFAULT_RECALL_CACHE_PATH):
        self.path = os.path.abspath(path)
        self._lock = threading.Lock()
        self._data: dict[str, list[dict]] | None = None

    def _ensure_loaded(self) -> None:
        """惰性加载，调用方需持有 self._lock。"""
        if self._data is not None:
            return
        self._data = {}
        raw = read_json_cached(self.path, None, copy_result=False)
        if not isinstance(raw, dict):
            return
        for chat_id, items in raw.items():
            if not isinstance(items, list):
                continue
            valid = [i for i in items if isinstance(i, dict) and i.get("content")]
            if valid:
                self._data[str(chat_id)] = valid[-_MAX_KEEP:]

    def get(self, chat_id) -> list[dict]:
        with self._lock:
            self._ensure_loaded()
            return [dict(item) for item in self._data.get(str(chat_id), [])]

    def put(self, chat_id, items: list[dict]) -> None:
        """覆盖写入某会话的保留条目（只留最后 _MAX_KEEP 条）并落盘。"""
        with self._lock:
            self._ensure_loaded()
            self._data[str(chat_id)] = [dict(item) for item in list(items)[-_MAX_KEEP:]]
            self._flush()

    def _flush(self) -> None:
        """调用方需持有 self._lock。"""
        try:
            atomic_write_json(self.path, self._data, indent=2, default=str)
        except Exception as e:
            logger.error(f"[RecallCache] 写入失败: {e}")


recall_cache_store = RecallCacheStore()
