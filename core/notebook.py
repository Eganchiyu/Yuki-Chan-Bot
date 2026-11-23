# core/notebook.py
"""小本本：Yuki 自己长期维护的私密笔记。

双区结构（docs/autonomous-architecture.md §5.4 L5）：
- `daily`（≤350 字）：日常群聊潜意识随记，由 `update_notebook` 维护；
- `plans`（≤160 字）：长期规划路标，只放最活跃的 1~2 条自主轮任务指针。

旧格式只有 `content` 一个字段，读取时回落为 `daily`，写入时同步维护 `content`
保持向后兼容（旧代码仍可 `load()` 拿到整本）。
"""
import os
import threading

from utils import BASE_DIR
from utils.json_store import atomic_write_json, read_json_cached
from utils.logger import get_logger

logger = get_logger("notebook")

NOTEBOOK_MAX_CHARS = 512
NOTEBOOK_DAILY_MAX_CHARS = 350
NOTEBOOK_PLANS_MAX_CHARS = 160
DEFAULT_NOTEBOOK_PATH = os.path.join(BASE_DIR, "data", "notebook.json")

ZONE_LIMITS = {
    "daily": NOTEBOOK_DAILY_MAX_CHARS,
    "plans": NOTEBOOK_PLANS_MAX_CHARS,
}


class NotebookStore:
    """小本本的持久化存储（全局一份，不区分群聊）。"""

    def __init__(self, path: str = DEFAULT_NOTEBOOK_PATH):
        self.path = os.path.abspath(path)
        self._lock = threading.Lock()

    # ------------------------------------------------------------ 读
    def _load_raw(self) -> dict:
        with self._lock:
            data = read_json_cached(self.path, None, copy_result=False)
        if data is None:
            return {}
        if isinstance(data, dict):
            return dict(data)
        return {"content": data} if isinstance(data, str) else {}

    def load_zones(self) -> dict:
        """返回 {"daily": str, "plans": str}，旧格式自动回落。"""
        data = self._load_raw()
        legacy = str(data.get("content") or "")
        daily = data.get("daily")
        plans = data.get("plans")
        if daily is None:
            daily = legacy
        return {
            "daily": str(daily or "")[:NOTEBOOK_DAILY_MAX_CHARS],
            "plans": str(plans or "")[:NOTEBOOK_PLANS_MAX_CHARS],
        }

    def load_zone(self, zone: str = "daily") -> str:
        zone = zone if zone in ZONE_LIMITS else "daily"
        return self.load_zones()[zone]

    def load(self) -> str:
        """兼容旧接口：返回整本小本本的可见文本（日常随记 + 长期路标）。"""
        return self.render()

    def render(self) -> str:
        """整本可见文本（≤512 字）；空间不够时优先保住长期规划区。"""
        zones = self.load_zones()
        daily, plans = zones["daily"], zones["plans"]
        if not plans:
            return daily[:NOTEBOOK_MAX_CHARS]
        tail = f"\n【长期规划】{plans}"
        budget = NOTEBOOK_MAX_CHARS - len(tail)
        if budget > 0:
            return daily[:budget] + tail
        return tail[:NOTEBOOK_MAX_CHARS]

    # ------------------------------------------------------------ 写
    def _write(self, zones: dict) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        daily = str(zones.get("daily") or "")[:NOTEBOOK_DAILY_MAX_CHARS]
        plans = str(zones.get("plans") or "")[:NOTEBOOK_PLANS_MAX_CHARS]
        payload = {
            "version": 2,
            "daily": daily,
            "plans": plans,
            # 旧字段保留整本可见文本，避免旧代码/旧数据读到空
            "content": "\n".join(p for p in [
                daily,
                f"【长期规划】{plans}" if plans else "",
            ] if p)[:NOTEBOOK_MAX_CHARS],
        }
        with self._lock:
            atomic_write_json(self.path, payload, indent=2)

    def save(self, content: str) -> str:
        """覆盖写入「日常随记区」（兼容旧接口），长期路标区保持不变。"""
        content = str(content or "").strip()
        truncated = len(content) > NOTEBOOK_DAILY_MAX_CHARS
        zones = self.load_zones()
        zones["daily"] = content[:NOTEBOOK_DAILY_MAX_CHARS]
        self._write(zones)
        if truncated:
            logger.info(f"[Notebook] 日常随记超长已截断到 {NOTEBOOK_DAILY_MAX_CHARS} 字")
        return zones["daily"]

    def save_zone(self, zone: str, content: str) -> str:
        """覆盖写入指定分区，返回实际保存的内容。"""
        zone = zone if zone in ZONE_LIMITS else "daily"
        limit = ZONE_LIMITS[zone]
        content = str(content or "").strip()
        truncated = len(content) > limit
        zones = self.load_zones()
        zones[zone] = content[:limit]
        self._write(zones)
        if truncated:
            logger.info(f"[Notebook] {zone} 区超长已截断到 {limit} 字")
        return zones[zone]


notebook_store = NotebookStore()
