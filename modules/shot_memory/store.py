import datetime
import json
import os
import re
import tempfile
import threading
from pathlib import Path

from utils import BASE_DIR
from utils.logger import get_logger

logger = get_logger("shot_memory")

DEFAULT_BASE_DIR = os.path.join(BASE_DIR, "data", "shot_memory")
_INDEX_FILE = "index.json"
_INVALID_FILENAME_CHARS = r'<>:"/\\|?*\r\n\t'


class ShotMemoryStore:
    """Permanent per-group screenshot memory with short live indexes."""

    def __init__(self, base_dir: str = DEFAULT_BASE_DIR):
        self.base_dir = os.path.abspath(base_dir)
        self._lock = threading.Lock()
        self._preview_cache: dict[str, dict[str, str]] = {}
        os.makedirs(self.base_dir, exist_ok=True)

    def group_dir(self, chat_id) -> str:
        group_id = self._safe_group_id(chat_id)
        path = os.path.join(self.base_dir, group_id)
        os.makedirs(path, exist_ok=True)
        return path

    def save_record(self, chat_id, note: str, image_bytes: bytes, metadata: dict | None = None) -> dict:
        note = (note or "截屏留念").strip() or "截屏留念"
        now = datetime.datetime.now()
        group_dir = self.group_dir(chat_id)
        filename = self._build_filename(note, now, group_dir)
        file_path = os.path.join(group_dir, filename)

        with open(file_path, "wb") as f:
            f.write(image_bytes)

        record = {
            "id": now.strftime("%Y%m%d%H%M%S%f"),
            "chat_id": str(chat_id),
            "note": note,
            "file_path": os.path.abspath(file_path),
            "filename": filename,
            "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        }
        if metadata:
            record.update(metadata)

        with self._lock:
            records = self._load_records_unlocked(chat_id)
            records.append(record)
            self._save_records_unlocked(chat_id, records)

        logger.info(f"[ShotMemory] 已保存截屏 {record['file_path']}")
        return record

    def search(self, chat_id, keyword: str | None = None, limit: int = 5) -> list[dict]:
        keyword = (keyword or "").strip().lower()
        limit = max(1, min(int(limit or 5), 20))
        with self._lock:
            records = self._load_records_unlocked(chat_id)

        if keyword:
            filtered = []
            for rec in records:
                haystack = " ".join([
                    str(rec.get("note", "")),
                    str(rec.get("group_name", "")),
                    str(rec.get("text", "")),
                    str(rec.get("created_at", "")),
                ]).lower()
                if keyword in haystack:
                    filtered.append(rec)
            records = filtered

        records = [r for r in records if os.path.isfile(r.get("file_path", ""))]
        records.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return records[:limit]

    def preload(self, chat_id, records: list[dict]) -> list[dict]:
        cid = str(chat_id)
        mapping = {}
        prepared = []
        for i, rec in enumerate(records[:5], 1):
            path = os.path.abspath(rec.get("file_path", ""))
            if not path or not os.path.isfile(path):
                continue
            idx = str(i)
            mapping[idx] = path
            item = dict(rec)
            item["shot_tag"] = f"[shot:{idx}]"
            item["absolute_path"] = path
            prepared.append(item)
        self._preview_cache[cid] = mapping
        return prepared

    def resolve(self, chat_id, index: str) -> str | None:
        path = self._preview_cache.get(str(chat_id), {}).get(str(index))
        if path and os.path.isfile(path):
            return path
        return None

    def _index_path(self, chat_id) -> str:
        return os.path.join(self.group_dir(chat_id), _INDEX_FILE)

    def _load_records_unlocked(self, chat_id) -> list[dict]:
        path = self._index_path(chat_id)
        if not os.path.isfile(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except Exception as e:
            logger.warning(f"[ShotMemory] 读取索引失败 {path}: {e}")
        return []

    def _save_records_unlocked(self, chat_id, records: list[dict]) -> None:
        path = self._index_path(chat_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix="index_", suffix=".json", dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    @staticmethod
    def _safe_group_id(chat_id) -> str:
        raw = str(chat_id or "unknown")
        return re.sub(r"[^0-9A-Za-z_-]", "_", raw)[:80] or "unknown"

    def _build_filename(self, note: str, now: datetime.datetime, group_dir: str) -> str:
        clean = self._sanitize_filename(note)
        suffix = now.strftime("_%Y%m%d_%H%M%S.png")
        max_stem_len = 120
        stem = clean[:max_stem_len].rstrip(" ._") or "截屏留念"
        filename = f"{stem}{suffix}"
        path = Path(group_dir) / filename
        if not path.exists():
            return filename
        for i in range(2, 100):
            filename = f"{stem}_{i}{suffix}"
            if not (Path(group_dir) / filename).exists():
                return filename
        return f"{stem}_{now.strftime('%f')}{suffix}"

    @staticmethod
    def _sanitize_filename(text: str) -> str:
        table = str.maketrans({ch: "_" for ch in _INVALID_FILENAME_CHARS})
        clean = text.translate(table)
        clean = re.sub(r"\s+", " ", clean).strip()
        clean = clean.strip(" ._")
        return clean or "截屏留念"
