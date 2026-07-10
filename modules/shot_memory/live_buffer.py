import datetime
import os
import threading
from collections import defaultdict, deque
from copy import deepcopy

from utils import BASE_DIR


class ShotLiveBuffer:
    """Short-lived raw visual message buffer for group snapshot rendering."""

    def __init__(self, max_messages: int = 40):
        self.max_messages = max_messages
        self._buffers: dict[str, deque] = defaultdict(lambda: deque(maxlen=self.max_messages))
        self._lock = threading.Lock()
        self.media_cache_dir = os.path.join(BASE_DIR, "data", "shot_memory", "media_cache")
        os.makedirs(self.media_cache_dir, exist_ok=True)

    def append(self, chat_id, *, name: str, raw_text: str, content: str = "", segments=None,
               user_id=None, message_id=None, is_bot: bool = False) -> None:
        entry = {
            "chat_id": str(chat_id),
            "name": name or ("Yuki" if is_bot else "群友"),
            "raw_text": raw_text or "",
            "content": content or raw_text or "",
            "segments": deepcopy(segments) if segments is not None else [],
            "user_id": user_id,
            "message_id": message_id,
            "is_bot": bool(is_bot),
            "time": datetime.datetime.now().strftime("%m月%d日%H:%M"),
        }
        with self._lock:
            self._buffers[str(chat_id)].append(entry)

    def snapshot(self, chat_id, limit: int = 20) -> list[dict]:
        limit = max(1, min(int(limit or 14), self.max_messages))
        with self._lock:
            return list(self._buffers.get(str(chat_id), []))[-limit:]


shot_live_buffer = ShotLiveBuffer()
