import argparse
import datetime
import json
import os
import sys
from collections import Counter, defaultdict

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from modules.memory.rag import MemoryRAG


def _safe_metadata(metadata):
    return metadata if isinstance(metadata, dict) else {}


def _build_records(all_data):
    records = []
    ids = all_data.get("ids", []) or []
    documents = all_data.get("documents", []) or []
    metadatas = all_data.get("metadatas", []) or []

    for index, doc_id in enumerate(ids):
        document = documents[index] if index < len(documents) else ""
        metadata = _safe_metadata(metadatas[index] if index < len(metadatas) else {})
        records.append({
            "id": doc_id,
            "document": document,
            "metadata": metadata,
        })
    return records


def _build_stats(records):
    chat_counter = Counter()
    type_counter = Counter()
    status_counter = Counter()
    empty_count = 0
    duplicate_counter = Counter()
    lengths = []
    timestamps = []
    missing_standard_fields = defaultdict(int)
    standard_fields = ["type", "status", "confidence", "importance"]

    for record in records:
        document = record["document"] or ""
        metadata = record["metadata"]
        chat_counter[str(metadata.get("chat_id", "unknown"))] += 1
        type_counter[str(metadata.get("type", "summary"))] += 1
        status_counter[str(metadata.get("status", "legacy"))] += 1
        duplicate_counter[(document, str(metadata.get("chat_id", "unknown")))] += 1
        lengths.append(len(document))

        if not document.strip():
            empty_count += 1
        if isinstance(metadata.get("timestamp"), (int, float)):
            timestamps.append(metadata["timestamp"])
        for field in standard_fields:
            if field not in metadata:
                missing_standard_fields[field] += 1

    duplicate_count = sum(count - 1 for count in duplicate_counter.values() if count > 1)
    avg_length = round(sum(lengths) / len(lengths), 2) if lengths else 0

    time_range = None
    if timestamps:
        time_range = {
            "earliest": datetime.datetime.fromtimestamp(min(timestamps)).isoformat(),
            "latest": datetime.datetime.fromtimestamp(max(timestamps)).isoformat(),
        }

    return {
        "total": len(records),
        "empty_count": empty_count,
        "duplicate_count": duplicate_count,
        "average_length": avg_length,
        "max_length": max(lengths) if lengths else 0,
        "min_length": min(lengths) if lengths else 0,
        "time_range": time_range,
        "by_chat_id": dict(chat_counter.most_common()),
        "by_type": dict(type_counter.most_common()),
        "by_status": dict(status_counter.most_common()),
        "missing_standard_fields": dict(missing_standard_fields),
    }


def export_current_memory(output_dir="data/memory_exports"):
    """从当前 Chroma 记忆库导出全量日记，并生成基础统计。"""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(output_dir, f"diaries_backup_{timestamp}.json")
    stats_file = os.path.join(output_dir, f"diaries_stats_{timestamp}.json")

    print("[Backup] 正在连接记忆库...")
    rag = MemoryRAG()
    all_data = rag.collection.get(include=["documents", "metadatas"])
    records = _build_records(all_data)
    stats = _build_stats(records)

    if not records:
        print("[Backup] 记忆库为空，无需导出。")
        return None, None

    export_payload = {
        "exported_at": datetime.datetime.now().isoformat(),
        "collection": "diaries",
        "records": records,
    }

    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump(export_payload, f, ensure_ascii=False, indent=2)
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print("-" * 30)
    print(f"[Success] 成功导出 {stats['total']} 条记忆")
    print(f"[Success] 备份文件: {os.path.abspath(backup_file)}")
    print(f"[Success] 统计文件: {os.path.abspath(stats_file)}")
    print(f"[Stats] 重复记录: {stats['duplicate_count']}，空内容: {stats['empty_count']}")
    print("-" * 30)
    return backup_file, stats_file


def main():
    parser = argparse.ArgumentParser(description="导出 Yuki 当前长期记忆并生成统计")
    parser.add_argument(
        "--output-dir",
        default="data/memory_exports",
        help="导出目录，默认 data/memory_exports",
    )
    args = parser.parse_args()
    export_current_memory(args.output_dir)


if __name__ == "__main__":
    main()
