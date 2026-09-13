# modules/vision/image_store.py
import os
import threading
import uuid
from collections import OrderedDict
from utils.logger import get_logger

logger = get_logger("image_store")


class ImageStore:
    """
    临时图片索引存储。
    - 下载的图片保存到 data/image_store/，分配短索引 (001, 002, ...)
    - 维护 索引 -> 绝对路径 映射
    - 每轮 tick() 递增轮次计数器，超过 max_age_rounds 的条目自动清理（删文件+释放索引）
    """

    def __init__(self, store_dir="data/image_store", max_age_rounds=40):
        self.store_dir = os.path.abspath(store_dir)
        os.makedirs(self.store_dir, exist_ok=True)
        self.max_age_rounds = max_age_rounds
        self._counter = 0
        self._current_round = 0
        # OrderedDict: key=索引, value={"path": str, "round": int}
        self._index: OrderedDict[str, dict] = OrderedDict()
        self._lock = threading.Lock()

    def _next_idx(self) -> str:
        self._counter = (self._counter + 1) % 1000
        return f"{self._counter:03d}"

    def register(self, image_data: bytes, url: str = "", ext: str = ".jpg") -> str:
        """
        保存图片到磁盘并注册索引，返回短索引字符串。
        """
        attachment_id = uuid.uuid4().hex
        save_path = os.path.join(self.store_dir, f"{attachment_id}{ext}")
        temp_path = save_path + ".tmp"
        try:
            with open(temp_path, "wb") as f:
                f.write(image_data)
            os.replace(temp_path, save_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        with self._lock:
            idx = self._next_idx()
            previous = self._index.get(idx)
            if previous and os.path.exists(previous["path"]):
                os.remove(previous["path"])
            self._index[idx] = {
                "path": save_path,
                "id": attachment_id,
                "round": self._current_round,
                "url": url,
            }

        logger.info(f"[ImageStore] 注册 [{idx}] -> {save_path}")
        return idx

    def resolve(self, idx: str) -> str | None:
        """索引 -> 绝对路径，不存在返回 None。"""
        entry = self._index.get(idx)
        return entry["path"] if entry else None

    def attachment(self, idx: str) -> dict | None:
        """生成可持久化的附件引用，不把文件内容写入历史。"""
        with self._lock:
            entry = self._index.get(idx)
            return {"index": idx, "id": entry["id"]} if entry else None

    def read_attachment(self, attachment: dict) -> bytes | None:
        """校验唯一身份后读取附件，避免短索引复用导致串图。"""
        with self._lock:
            entry = self._index.get(attachment.get("index"))
            if not entry or entry["id"] != attachment.get("id"):
                return None
            try:
                with open(entry["path"], "rb") as f:
                    return f.read()
            except FileNotFoundError:
                return None

    def list_all(self) -> dict[str, str]:
        """返回所有 {索引: 绝对路径} 映射（供调试/工具使用）。"""
        return {k: v["path"] for k, v in self._index.items()}

    def tick(self):
        """每轮调用一次，递增轮次计数器并清理过期条目。"""
        with self._lock:
            self._current_round += 1
            self._cleanup()

    def _cleanup(self):
        """删除超过 max_age_rounds 的条目及其文件。"""
        cutoff = self._current_round - self.max_age_rounds
        expired = [k for k, v in self._index.items() if v["round"] <= cutoff]
        for k in expired:
            entry = self._index.pop(k)
            try:
                os.remove(entry["path"])
                logger.info(f"[ImageStore] 清理过期图片 [{k}] {entry['path']}")
            except FileNotFoundError:
                pass
            except Exception as e:
                logger.warning(f"[ImageStore] 删除文件失败 [{k}]: {e}")
        if expired:
            logger.info(f"[ImageStore] 本轮清理 {len(expired)} 张过期图片，剩余 {len(self._index)} 张")
