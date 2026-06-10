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
review_memory = load_script_module(
    "review_memory_candidates",
    "scripts/03_RAG_Tools/review_memory_candidates.py",
)
import_memory = load_script_module(
    "import_memory_candidates",
    "scripts/03_RAG_Tools/import_memory_candidates.py",
)

_build_records = export_memory._build_records
_build_stats = export_memory._build_stats
load_records = backfill_memory.load_records
normalize_llm_json = backfill_memory.normalize_llm_json
sanitize_candidate = backfill_memory.sanitize_candidate
select_records = backfill_memory.select_records
build_report = backfill_memory.build_report
is_fatal_llm_error = backfill_memory.is_fatal_llm_error
flatten_candidates = review_memory.flatten_candidates
apply_review = review_memory.apply_review
split_reviewed = review_memory.split_reviewed
candidate_to_record = import_memory.candidate_to_record
filter_importable = import_memory.filter_importable


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


def test_is_fatal_llm_error_detects_auth_errors_only():
    assert is_fatal_llm_error("HTTP 401: invalid_api_key") is True
    assert is_fatal_llm_error("HTTP 403: key expired") is True
    assert is_fatal_llm_error("HTTP 429: rate limit exceeded") is False
    assert is_fatal_llm_error("timeout while reading response") is False


def test_select_records_filters_orders_samples_and_limits():
    records = [
        {"id": "a", "document": "早", "metadata": {"chat_id": "1", "timestamp": 100}},
        {"id": "b", "document": "晚", "metadata": {"chat_id": "1", "timestamp": 300}},
        {"id": "c", "document": "其他群", "metadata": {"chat_id": "2", "timestamp": 200}},
    ]

    selected = select_records(records, chat_id="1", order="newest", limit=1)
    sampled = select_records(records, sample_size=2, seed=42)

    assert [record["id"] for record in selected] == ["b"]
    assert len(sampled) == 2
    assert {record["id"] for record in sampled}.issubset({"a", "b", "c"})


def test_build_report_contains_stage_c_stats():
    args = types.SimpleNamespace(
        input="backup.json",
        output="candidates.jsonl",
        error_output="errors.jsonl",
        chat_id="1",
        order="newest",
        sample_size=10,
        limit=5,
        batch_size=2,
        dry_run=True,
        retries=3,
        max_consecutive_failures=5,
    )

    report = build_report({"processed": 5, "failed": 0}, args, "start", "end")

    assert report["chat_id"] == "1"
    assert report["order"] == "newest"
    assert report["dry_run"] is True
    assert report["stats"]["processed"] == 5


def test_review_candidates_approves_rejects_and_deduplicates():
    entries = [{
        "source_diary_id": "diary_1",
        "source_metadata": {"chat_id": "1", "timestamp": 100},
        "memories": [
            {
                "type": "fact",
                "subject": "主人哥哥",
                "content": "主人哥哥喜欢使用 ComfyUI 进行图像工作流实验",
                "confidence": 0.95,
                "importance": 4,
                "time_scope": "long_term",
                "evidence": "主人哥哥说最近在用 ComfyUI",
                "risk": "low",
            },
            {
                "type": "fact",
                "subject": "主人哥哥",
                "content": "主人哥哥喜欢使用ComfyUI进行图像工作流实验",
                "confidence": 0.95,
                "importance": 4,
                "time_scope": "long_term",
                "evidence": "主人哥哥说最近在用 ComfyUI",
                "risk": "low",
            },
            {
                "type": "profile_candidate",
                "subject": "Yuki",
                "content": "Yuki 有日记系统",
                "confidence": 0.9,
                "importance": 3,
                "time_scope": "long_term",
                "evidence": "Yuki 的日记系统记录了这件事",
                "risk": "low",
            },
            {
                "type": "event",
                "subject": "主人哥哥",
                "content": "主人哥哥今天吃了饭",
                "confidence": 0.9,
                "importance": 1,
                "time_scope": "short_term",
                "evidence": "今天吃了饭",
                "risk": "low",
            },
        ],
    }]

    flattened = flatten_candidates(entries)
    reviewed, stats, by_type, by_reason = apply_review(flattened)
    approved, needs_review, rejected = split_reviewed(reviewed)

    assert stats["total_candidates"] == 4
    assert len(approved) == 1
    assert len(needs_review) == 1
    assert len(rejected) == 2
    assert stats["duplicates"] == 1
    assert by_type["fact"] == 2
    assert by_reason["profile_candidate_requires_review"] == 1


def test_import_candidate_to_memory_record_and_filtering():
    item = {
        "candidate_id": "cand_1",
        "source_diary_id": "diary_1",
        "source_metadata": {"chat_id": "123", "timestamp": 100.0},
        "candidate": {
            "type": "preference",
            "subject": "主人哥哥",
            "content": "主人哥哥偏好简洁直接的说明",
            "confidence": 0.9,
            "importance": 4,
            "time_scope": "long_term",
            "evidence": "主人哥哥说希望直接说明",
            "risk": "low",
        },
        "review": {"status": "approved", "reason": "auto_approved"},
    }
    profile_item = {
        **item,
        "candidate_id": "cand_profile",
        "candidate": {**item["candidate"], "type": "profile_candidate"},
    }

    importable, skipped = filter_importable([item, profile_item], include_profile=False)
    record = candidate_to_record(item)

    assert len(importable) == 1
    assert len(skipped) == 1
    assert record.type == "preference"
    assert record.chat_id == "123"
    assert record.subject == "主人哥哥"
    assert record.metadata["candidate_id"] == "cand_1"
    assert record.source_ids == ["diary_1", "cand_1"]
