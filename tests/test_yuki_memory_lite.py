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
if "jieba" not in sys.modules:
    jieba_module = types.ModuleType("jieba")
    analyse_module = types.ModuleType("jieba.analyse")
    analyse_module.extract_tags = lambda *args, **kwargs: []
    jieba_module.analyse = analyse_module
    sys.modules["jieba"] = jieba_module
    sys.modules["jieba.analyse"] = analyse_module

from modules.memory.rag import MemoryRAG


def load_script_module(module_name, relative_path):
    module_path = os.path.join(project_root, relative_path)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


export_memory = load_script_module("export_memory", "scripts/03_RAG_Tools/export_memory.py")
backfill_memory = load_script_module(
    "backfill_memory_candidates",
    "scripts/03_RAG_Tools/backfill_memory_candidates.py",
)

_build_records = export_memory._build_records
_build_stats = export_memory._build_stats
load_records = backfill_memory.load_records
normalize_llm_json = backfill_memory.normalize_llm_json
sanitize_candidate = backfill_memory.sanitize_candidate


def test_build_memory_metadata_defaults():
    metadata = MemoryRAG._build_memory_metadata(
        memory_type="preference",
        chat_id="123",
        subject="用户A",
        confidence=0.88,
        importance=4,
        source_ids=["diary_1"],
        extra_metadata={"tags": ["猫猫", "表情包"]},
    )

    assert metadata["type"] == "preference"
    assert metadata["status"] == "active"
    assert metadata["chat_id"] == "123"
    assert metadata["subject"] == "用户A"
    assert metadata["confidence"] == 0.88
    assert metadata["importance"] == 4
    assert metadata["access_count"] == 0
    assert json.loads(metadata["source_ids"]) == ["diary_1"]
    assert json.loads(metadata["tags"]) == ["猫猫", "表情包"]


def test_export_memory_stats_handles_legacy_records():
    all_data = {
        "ids": ["a", "b", "c"],
        "documents": ["同一条日记", "同一条日记", ""],
        "metadatas": [
            {"chat_id": "1", "timestamp": 100.0},
            {"chat_id": "1", "timestamp": 200.0, "type": "summary", "status": "active"},
            {},
        ],
    }

    records = _build_records(all_data)
    stats = _build_stats(records)

    assert len(records) == 3
    assert stats["total"] == 3
    assert stats["duplicate_count"] == 1
    assert stats["empty_count"] == 1
    assert stats["by_chat_id"]["1"] == 2
    assert stats["by_type"]["summary"] == 3
    assert stats["missing_standard_fields"]["confidence"] == 3


def test_load_records_supports_new_export_format(tmp_path):
    backup_file = tmp_path / "backup.json"
    backup_file.write_text(json.dumps({
        "records": [
            {"id": "diary_1", "document": "测试日记", "metadata": {"chat_id": "1"}}
        ]
    }, ensure_ascii=False), encoding="utf-8")

    records = load_records(str(backup_file))

    assert records == [{"id": "diary_1", "document": "测试日记", "metadata": {"chat_id": "1"}}]


def test_sanitize_candidate_rejects_invalid_and_normalizes_valid():
    assert sanitize_candidate({"type": "schema", "content": "无效", "subject": "A", "evidence": "x"}) is None
    assert sanitize_candidate({"type": "fact", "content": "缺证据", "subject": "A"}) is None

    candidate = sanitize_candidate({
        "type": "preference",
        "subject": "用户A",
        "content": "用户A喜欢猫猫表情包",
        "confidence": 1.8,
        "importance": 9,
        "evidence": "用户A说喜欢猫猫表情包",
        "risk": "low",
    })

    assert candidate["type"] == "preference"
    assert candidate["confidence"] == 1.0
    assert candidate["importance"] == 5
    assert candidate["risk"] == "low"


def test_normalize_llm_json_strips_markdown_fence():
    parsed = normalize_llm_json('```json\n{"memories": []}\n```')
    assert parsed == {"memories": []}
