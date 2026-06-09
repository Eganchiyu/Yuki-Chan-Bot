import argparse
import datetime
import json
import os
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from modules.yuki_memory.models import MemoryRecord
from modules.yuki_memory.store import YukiMemoryStore

TYPE_MAPPING = {
    "fact": "fact",
    "preference": "preference",
    "relationship": "relationship",
    "todo": "todo",
    "event": "event",
    "profile_candidate": "profile",
}


def load_reviewed_candidates(input_files):
    items = []
    for input_file in input_files:
        with open(input_file, "r", encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                item["_input_file"] = input_file
                item["_line_number"] = line_number
                items.append(item)
    return items


def get_source_timestamp(item):
    metadata = item.get("source_metadata", {}) or {}
    timestamp = metadata.get("timestamp") or metadata.get("created_at")
    try:
        return float(timestamp) if timestamp is not None else None
    except (TypeError, ValueError):
        return None


def build_memory_id(item):
    candidate_id = item.get("candidate_id") or "unknown"
    memory_type = TYPE_MAPPING.get((item.get("candidate") or {}).get("type"), "fact")
    return f"ymem_{memory_type}_{candidate_id}"


def candidate_to_record(item, status="active"):
    candidate = item.get("candidate", {}) or {}
    source_metadata = item.get("source_metadata", {}) or {}
    candidate_type = candidate.get("type")
    memory_type = TYPE_MAPPING.get(candidate_type)
    if not memory_type:
        raise ValueError(f"不支持的候选类型: {candidate_type}")

    created_at = get_source_timestamp(item) or datetime.datetime.now().timestamp()
    metadata = {
        "candidate_id": item.get("candidate_id", ""),
        "source_diary_id": item.get("source_diary_id", ""),
        "candidate_type": candidate_type,
        "time_scope": candidate.get("time_scope", "unknown"),
        "evidence": candidate.get("evidence", ""),
        "risk": candidate.get("risk", "medium"),
        "review_status": (item.get("review", {}) or {}).get("status", "approved"),
        "review_reason": (item.get("review", {}) or {}).get("reason", ""),
    }

    return MemoryRecord(
        memory_id=build_memory_id(item),
        type=memory_type,
        content=candidate.get("content", ""),
        scope="group",
        chat_id=source_metadata.get("chat_id"),
        subject=candidate.get("subject"),
        status=status,
        confidence=candidate.get("confidence", 1.0),
        importance=candidate.get("importance", 3),
        source="llm_candidate_backfill",
        source_ids=[item.get("source_diary_id", ""), item.get("candidate_id", "")],
        created_at=created_at,
        updated_at=datetime.datetime.now().timestamp(),
        metadata=metadata,
    )


def filter_importable(items, include_profile=False):
    importable = []
    skipped = []
    for item in items:
        review = item.get("review", {}) or {}
        if review.get("status", "approved") != "approved":
            skipped.append((item, "not_approved"))
            continue
        candidate_type = (item.get("candidate", {}) or {}).get("type")
        if candidate_type == "profile_candidate" and not include_profile:
            skipped.append((item, "profile_candidate_skipped"))
            continue
        importable.append(item)
    return importable, skipped


def run(args):
    started_at = datetime.datetime.now().isoformat()
    items = load_reviewed_candidates(args.input)
    importable, skipped = filter_importable(items, include_profile=args.include_profile)

    stats = Counter({
        "input_total": len(items),
        "importable": len(importable),
        "skipped": len(skipped),
        "imported": 0,
        "failed": 0,
    })
    by_type = Counter()
    failed = []
    records = []

    store = None if args.dry_run else YukiMemoryStore(
        collection_name=args.collection,
        db_path=args.db_path,
    )

    for item in importable:
        try:
            record = candidate_to_record(item, status=args.status)
            records.append(record)
            by_type[record.type] += 1
            if not args.dry_run:
                store.save(record)
            stats["imported"] += 1
        except Exception as exc:
            stats["failed"] += 1
            failed.append({
                "candidate_id": item.get("candidate_id"),
                "source_diary_id": item.get("source_diary_id"),
                "error": str(exc),
            })

    report = {
        "started_at": started_at,
        "finished_at": datetime.datetime.now().isoformat(),
        "input": args.input,
        "collection": args.collection,
        "db_path": args.db_path,
        "dry_run": args.dry_run,
        "status": args.status,
        "include_profile": args.include_profile,
        "stats": dict(stats),
        "by_type": dict(by_type),
        "skipped_reasons": dict(Counter(reason for _, reason in skipped)),
        "failed": failed[:100],
    }

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    if args.preview_output:
        Path(args.preview_output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.preview_output, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps({
                    "memory_id": record.memory_id,
                    "type": record.type,
                    "content": record.content,
                    "metadata": record.to_metadata(),
                }, ensure_ascii=False) + "\n")

    print(f"[Import] input={stats['input_total']} importable={stats['importable']} skipped={stats['skipped']}")
    print(f"[Import] imported={stats['imported']} failed={stats['failed']} dry_run={args.dry_run}")
    print(f"[Import] 报告: {Path(args.report).resolve()}")


def main():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    parser = argparse.ArgumentParser(description="导入审核通过的 Yuki-Memory 结构化候选")
    parser.add_argument("--input", nargs="+", required=True, help="review_memory_candidates.py 输出的 approved JSONL")
    parser.add_argument("--collection", default="yuki_memory", help="目标 Chroma collection")
    parser.add_argument("--db-path", default=None, help="目标 Chroma DB 路径，默认使用 cfg.VECTOR_DB_PATH")
    parser.add_argument("--status", choices=["active", "candidate"], default="active", help="导入后的记忆状态")
    parser.add_argument("--include-profile", action="store_true", help="允许导入 profile_candidate 为 profile")
    parser.add_argument("--dry-run", action="store_true", help="只转换和生成报告，不写入数据库")
    parser.add_argument(
        "--report",
        default=f"data/memory_exports/import_memory_candidates_report_{timestamp}.json",
        help="导入报告 JSON",
    )
    parser.add_argument("--preview-output", default="", help="dry-run 预览 JSONL 输出")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
