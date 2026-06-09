import argparse
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

import chromadb

from config import cfg
from modules.yuki_memory.migrator import LegacyDiaryMigrator
from modules.yuki_memory.store import YukiMemoryStore


DEFAULT_INPUT = "data/memory_exports/diaries_backup_20260608_234723.json"


def _build_parser():
    parser = argparse.ArgumentParser(description="迁移旧 diaries 备份到 yuki_memory collection")
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT,
        help=f"旧日记备份 JSON，默认 {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--collection",
        "--collection-name",
        dest="collection_name",
        default="yuki_memory",
        help="目标 Chroma collection 名称，默认 yuki_memory",
    )
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写入数据库")
    parser.add_argument("--limit", type=int, default=None, help="限制迁移条数")
    parser.add_argument("--resume", action="store_true", help="跳过目标库中已存在的 memory_id")
    parser.add_argument(
        "--reset-test-collection",
        action="store_true",
        help="迁移前删除目标 collection，仅用于测试 collection",
    )
    return parser


def _load_existing_ids(store):
    existing = store.collection.get()
    return set(existing.get("ids") or [])


def _reset_collection(client, collection_name):
    try:
        client.delete_collection(collection_name)
        print(f"[Reset] 已删除 collection: {collection_name}")
    except Exception as exc:
        print(f"[Reset] collection 不存在或删除失败，继续执行: {exc}")


def migrate_legacy_diaries(
    input_path,
    collection_name="yuki_memory",
    dry_run=False,
    limit=None,
    resume=False,
    reset_test_collection=False,
    store=None,
):
    """迁移旧日记备份到 Yuki-Memory。"""
    input_path = os.path.abspath(input_path)
    legacy_records = LegacyDiaryMigrator.load_backup(input_path)
    selected_records = legacy_records[:limit] if limit else legacy_records

    if store is None and not dry_run:
        client = chromadb.PersistentClient(path=cfg.VECTOR_DB_PATH)
        if reset_test_collection:
            _reset_collection(client, collection_name)
        store = YukiMemoryStore(collection_name=collection_name, client=client)

    migrator = LegacyDiaryMigrator(store=store)
    converted = [migrator.to_memory_record(record) for record in selected_records]

    if dry_run:
        print(f"[DryRun] 输入文件: {input_path}")
        print(f"[DryRun] 备份总数: {len(legacy_records)}")
        print(f"[DryRun] 计划迁移: {len(converted)}")
        if converted:
            sample = converted[0]
            print(
                "[DryRun] 示例: "
                f"id={sample.memory_id}, type={sample.type}, chat_id={sample.chat_id}, "
                f"source={sample.source}"
            )
        return {"total": len(legacy_records), "planned": len(converted), "migrated": 0, "skipped": 0}

    migrated = 0
    skipped = 0
    existing_ids = _load_existing_ids(store) if resume else set()
    if resume:
        print(f"[Resume] 已加载目标库现有 ID: {len(existing_ids)} 条")

    for record in converted:
        if record.memory_id in existing_ids:
            skipped += 1
            continue
        store.save(record)
        existing_ids.add(record.memory_id)
        migrated += 1
        if migrated % 100 == 0:
            print(f"[Progress] 已迁移 {migrated} 条，跳过 {skipped} 条")

    print("-" * 30)
    print(f"[Success] 备份总数: {len(legacy_records)}")
    print(f"[Success] 本次计划: {len(converted)}")
    print(f"[Success] 成功迁移: {migrated}")
    print(f"[Success] 跳过已有: {skipped}")
    if store is not None:
        print(f"[Success] 目标 collection: {collection_name}")
        print(f"[Success] 当前 count: {store.collection.count()}")
    print("-" * 30)
    return {
        "total": len(legacy_records),
        "planned": len(converted),
        "migrated": migrated,
        "skipped": skipped,
    }


def main():
    args = _build_parser().parse_args()
    migrate_legacy_diaries(
        input_path=args.input,
        collection_name=args.collection_name,
        dry_run=args.dry_run,
        limit=args.limit,
        resume=args.resume,
        reset_test_collection=args.reset_test_collection,
    )


if __name__ == "__main__":
    main()
