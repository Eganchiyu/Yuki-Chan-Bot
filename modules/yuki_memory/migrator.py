import json

from modules.yuki_memory.models import MemoryRecord


class LegacyDiaryMigrator:
    """旧 diaries 备份迁移辅助器。"""

    def __init__(self, store=None):
        self.store = store

    @staticmethod
    def load_backup(input_path):
        """读取 export_memory.py 导出的旧日记备份。"""
        with open(input_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        records = payload.get("records", payload if isinstance(payload, list) else [])
        return [record for record in records if record.get("document")]

    @staticmethod
    def to_memory_record(legacy_record):
        """将旧日记记录转换为 Yuki-Memory summary。"""
        metadata = legacy_record.get("metadata") or {}
        legacy_id = str(legacy_record.get("id") or "")
        created_at = metadata.get("timestamp") or metadata.get("created_at")

        return MemoryRecord(
            memory_id=f"legacy_{legacy_id}" if legacy_id else "legacy_unknown",
            type="summary",
            content=legacy_record.get("document", ""),
            scope="group",
            chat_id=metadata.get("chat_id"),
            subject=metadata.get("subject") or "群聊",
            status="active",
            confidence=1.0,
            importance=3,
            source="legacy_diary",
            source_ids=[legacy_id] if legacy_id else [],
            created_at=created_at,
            updated_at=created_at,
        )

    def migrate_records(self, legacy_records, dry_run=False, limit=None):
        """迁移旧日记记录，dry-run 时只返回转换后的记录。"""
        selected_records = legacy_records[:limit] if limit else legacy_records
        memory_records = [self.to_memory_record(record) for record in selected_records]
        if dry_run:
            return memory_records
        if self.store is None:
            raise ValueError("执行迁移需要提供 YukiMemoryStore")
        for record in memory_records:
            self.store.save(record)
        return memory_records
