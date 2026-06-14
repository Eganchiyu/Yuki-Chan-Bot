import argparse
import asyncio
import datetime
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from config import cfg
from modules.yuki_memory.consolidator import ConsolidationConfig, MultiLayerMemoryConsolidator
from modules.yuki_memory.store import YukiMemoryStore


def load_history_messages(history_file, chat_id, limit=0):
    with open(history_file, "r", encoding="utf-8") as f:
        payload = json.load(f)
    messages = payload.get(str(chat_id), []) if isinstance(payload, dict) else []
    messages = [message for message in messages if isinstance(message, dict)]
    if limit:
        return messages[-limit:]
    return messages


def write_result(path, result):
    payload = {
        "generated_at": datetime.datetime.now().isoformat(),
        "chat_id": result.chat_id,
        "raw_count": result.raw_count,
        "sample_count": result.sample_count,
        "buffer_summaries": result.buffer_summaries,
        "candidates": result.candidates,
        "diary": result.diary,
        "saved_ids": result.saved_ids,
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


async def run(args):
    messages = load_history_messages(args.history_file, args.chat_id, limit=args.limit)
    config = ConsolidationConfig(
        coarse_buffer_size=args.coarse_buffer_size,
        summary_buffer_size=args.summary_buffer_size,
        summary_overlap=args.summary_overlap,
        max_samples_per_buffer=args.max_samples_per_buffer,
        min_candidate_confidence=args.min_candidate_confidence,
        import_profile=args.include_profile,
        candidate_status=args.status,
        llm_base_url=args.base_url,
        llm_api_key=args.api_key,
        llm_model=args.model,
    )
    store = None
    if args.save:
        store = YukiMemoryStore(collection_name=args.collection, db_path=args.db_path)
    consolidator = MultiLayerMemoryConsolidator(store=store, config=config)
    result = await consolidator.consolidate(args.chat_id, messages, save=args.save)
    write_result(args.output, result)

    print("-" * 30)
    print(f"[Consolidate] chat_id={args.chat_id}")
    print(f"[Consolidate] raw={result.raw_count} samples={result.sample_count}")
    print(f"[Consolidate] buffers={len(result.buffer_summaries)} candidates={len(result.candidates)}")
    print(f"[Consolidate] diary_chars={len(result.diary)} saved={len(result.saved_ids)}")
    print(f"[Consolidate] output={Path(args.output).resolve()}")
    print(f"[Consolidate] save={args.save}")
    print("-" * 30)


def main():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    parser = argparse.ArgumentParser(description="旁路运行 Yuki-Memory 多层压缩整理器")
    parser.add_argument("--chat-id", required=True, help="要整理的 chat_id")
    parser.add_argument("--history-file", default=cfg.HISTORY_FILE, help="聊天历史 JSON 文件")
    parser.add_argument("--limit", type=int, default=80, help="只整理最近 N 条非 system 消息，0 表示不限")
    parser.add_argument("--output", default=f"data/memory_exports/runtime_consolidation_{timestamp}.json", help="结果 JSON")
    parser.add_argument("--save", action="store_true", help="写入 yuki_memory；默认只 dry-run 输出文件")
    parser.add_argument("--collection", default="yuki_memory", help="目标 collection")
    parser.add_argument("--db-path", default=None, help="目标 Chroma DB 路径")
    parser.add_argument("--status", choices=["active", "candidate"], default="active", help="结构化候选写入状态")
    parser.add_argument("--include-profile", action="store_true", help="允许 profile_candidate 入库为 profile")
    parser.add_argument("--coarse-buffer-size", type=int, default=24, help="粗筛每个 buffer 的消息数")
    parser.add_argument("--summary-buffer-size", type=int, default=4, help="每个总结 buffer 包含的粗样本数")
    parser.add_argument("--summary-overlap", type=int, default=1, help="总结 buffer 重叠粗样本数")
    parser.add_argument("--max-samples-per-buffer", type=int, default=16, help="每个粗筛 buffer 最多保留样本数")
    parser.add_argument("--min-candidate-confidence", type=float, default=0.75, help="入库候选最低置信度")
    parser.add_argument("--base-url", default=None, help="指定 LLM API base URL，默认使用 cfg.LLM_BASE_URL")
    parser.add_argument("--api-key", default=None, help="指定 LLM API key，默认使用 cfg.LLM_API_KEY")
    parser.add_argument("--model", default=None, help="指定整理模型，默认使用 cfg.LLM_MODEL")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
