import importlib.util
import json
import os
import sys
import types

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

sys.modules.setdefault("chromadb", types.SimpleNamespace(PersistentClient=object))
sys.modules.setdefault(
    "sentence_transformers",
    types.SimpleNamespace(SentenceTransformer=object),
)

from modules.yuki_memory.migrator import LegacyDiaryMigrator
from modules.yuki_memory.models import MemoryRecord
from modules.yuki_memory.store import YukiMemoryStore


def load_script_module(module_name, relative_path):
    module_path = os.path.join(project_root, relative_path)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migrate_script = load_script_module(
    "migrate_legacy_diaries_to_yuki_memory",
    "scripts/03_RAG_Tools/migrate_legacy_diaries_to_yuki_memory.py",
)


class FakeEmbedding:
    def tolist(self):
        return [0.1, 0.2, 0.3]


class FakeModel:
    def encode(self, content):
        return FakeEmbedding()


class FakeCollection:
    def __init__(self):
        self.records = {}
        self.last_query = None

    def add(self, documents, embeddings, metadatas, ids):
        for doc, embedding, metadata, memory_id in zip(documents, embeddings, metadatas, ids):
            self.records[memory_id] = {
                "document": doc,
                "embedding": embedding,
                "metadata": metadata,
            }

    def query(self, query_embeddings, n_results, where=None, include=None):
        self.last_query = {"where": where, "include": include, "n_results": n_results}
        items = []
        for memory_id, record in self.records.items():
            if self._matches(record["metadata"], where):
                items.append((memory_id, record))
        items = items[:n_results]
        return {
            "ids": [[memory_id for memory_id, _ in items]],
            "documents": [[record["document"] for _, record in items]],
            "metadatas": [[record["metadata"] for _, record in items]],
            "distances": [[0.2 for _ in items]],
        }

    def get(self, ids=None, where=None, include=None):
        items = []
        for memory_id, record in self.records.items():
            if ids and memory_id not in ids:
                continue
            if self._matches(record["metadata"], where):
                items.append((memory_id, record))
        return {
            "ids": [memory_id for memory_id, _ in items],
            "documents": [record["document"] for _, record in items],
            "metadatas": [record["metadata"] for _, record in items],
        }

    def update(self, ids, metadatas):
        for memory_id, metadata in zip(ids, metadatas):
            self.records[memory_id]["metadata"] = metadata

    def count(self):
        return len(self.records)

    @staticmethod
    def _matches(metadata, where):
        if not where:
            return True
        if "$and" in where:
            return all(FakeCollection._matches(metadata, item) for item in where["$and"])
        for key, expected in where.items():
            actual = metadata.get(key)
            if isinstance(expected, dict) and "$in" in expected:
                if actual not in expected["$in"]:
                    return False
            elif actual != expected:
                return False
        return True


class FakeClient:
    def __init__(self):
        self.collection = FakeCollection()

    def get_or_create_collection(self, name, metadata=None):
        return self.collection


def build_store():
    return YukiMemoryStore(client=FakeClient(), model=FakeModel())


def write_backup(tmp_path, records):
    backup_file = tmp_path / "backup.json"
    backup_file.write_text(
        json.dumps({"records": records}, ensure_ascii=False),
        encoding="utf-8",
    )
    return backup_file


def test_memory_record_metadata_serializes_complex_values():
    record = MemoryRecord(
        memory_id="mem_1",
        type="summary",
        content="今天聊了猫猫表情包",
        chat_id=123,
        source="legacy_diary",
        source_ids=["old_1"],
        metadata={"tags": ["猫猫", "表情包"]},
    )

    metadata = record.to_metadata()

    assert metadata["type"] == "summary"
    assert metadata["chat_id"] == "123"
    assert metadata["source"] == "legacy_diary"
    assert json.loads(metadata["source_ids"]) == ["old_1"]
    assert json.loads(metadata["tags"]) == ["猫猫", "表情包"]


def test_yuki_memory_store_save_and_search_summary():
    store = build_store()
    record = MemoryRecord(
        memory_id="mem_1",
        type="summary",
        content="用户喜欢猫猫表情包",
        chat_id="100",
    )

    saved_id = store.save(record)
    results = store.search_summaries("猫猫", chat_id="100", top_k=3)

    assert saved_id == "mem_1"
    assert len(results) == 1
    assert results[0]["content"] == "用户喜欢猫猫表情包"
    assert results[0]["metadata"]["type"] == "summary"
    assert results[0]["score"] == 0.8
    assert store.collection.last_query["where"] == {
        "$and": [{"chat_id": "100"}, {"type": "summary"}, {"status": "active"}]
    }


def test_legacy_diary_migrator_loads_and_converts_backup(tmp_path):
    backup_file = write_backup(tmp_path, [
        {
            "id": "diary_1",
            "document": "旧日记内容",
            "metadata": {"chat_id": "100", "timestamp": 123.0},
        },
        {"id": "empty", "document": "", "metadata": {}},
    ])

    records = LegacyDiaryMigrator.load_backup(str(backup_file))
    memory_record = LegacyDiaryMigrator.to_memory_record(records[0])

    assert len(records) == 1
    assert memory_record.memory_id == "legacy_diary_1"
    assert memory_record.type == "summary"
    assert memory_record.chat_id == "100"
    assert memory_record.source == "legacy_diary"
    assert memory_record.source_ids == ["diary_1"]
    assert memory_record.created_at == 123.0


def test_legacy_diary_migrator_dry_run_does_not_write():
    store = build_store()
    migrator = LegacyDiaryMigrator(store=store)
    records = [{"id": "diary_1", "document": "旧日记内容", "metadata": {}}]

    converted = migrator.migrate_records(records, dry_run=True)

    assert len(converted) == 1
    assert store.collection.records == {}


def test_migrate_script_dry_run_reports_planned_count(tmp_path):
    backup_file = write_backup(tmp_path, [
        {"id": "diary_1", "document": "旧日记1", "metadata": {}},
        {"id": "diary_2", "document": "旧日记2", "metadata": {}},
    ])

    result = migrate_script.migrate_legacy_diaries(
        input_path=str(backup_file),
        dry_run=True,
        limit=1,
    )

    assert result == {"total": 2, "planned": 1, "migrated": 0, "skipped": 0}


def test_migrate_script_writes_and_resumes(tmp_path):
    backup_file = write_backup(tmp_path, [
        {"id": "diary_1", "document": "旧日记1", "metadata": {"chat_id": "100"}},
        {"id": "diary_2", "document": "旧日记2", "metadata": {"chat_id": "100"}},
    ])
    store = build_store()

    first_result = migrate_script.migrate_legacy_diaries(
        input_path=str(backup_file),
        store=store,
        limit=1,
    )
    second_result = migrate_script.migrate_legacy_diaries(
        input_path=str(backup_file),
        store=store,
        resume=True,
    )

    assert first_result["migrated"] == 1
    assert second_result["migrated"] == 1
    assert second_result["skipped"] == 1
    assert store.collection.count() == 2
    assert "legacy_diary_1" in store.collection.records
    assert "legacy_diary_2" in store.collection.records
