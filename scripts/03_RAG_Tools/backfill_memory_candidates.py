import argparse
import asyncio
import datetime
import json
import os
import random
import re
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from config import cfg
from utils.llm_client import chat_completion

ALLOWED_TYPES = {"fact", "preference", "relationship", "todo", "event", "profile_candidate"}

EXTRACT_PROMPT = """你是 YukiV6 的长期记忆提取器。请从输入的日记中提取可长期使用的结构化记忆候选。

规则：
1. 只能提取日记中明确表达的信息，禁止编造。
2. 玩笑、反讽、角色扮演、临时情绪不要抽成长期事实。
3. 不要做心理诊断，不要提取敏感隐私信息。
4. subject 不明确时不要提取。
5. 每条候选必须保留 evidence 原文片段。
6. profile_candidate 只是画像候选，不代表可直接入库。
7. 宁可漏掉，不要误提取。
8. 只输出 JSON，不要输出解释。

输出格式：
{
  "memories": [
    {
      "type": "fact|preference|relationship|todo|event|profile_candidate",
      "subject": "明确主体",
      "content": "一条独立、可检索、可更新的记忆",
      "confidence": 0.0,
      "importance": 1,
      "time_scope": "short_term|long_term|past|unknown",
      "evidence": "日记原文片段",
      "risk": "low|medium|high"
    }
  ]
}
"""


def load_records(input_file):
    with open(input_file, "r", encoding="utf-8") as f:
        payload = json.load(f)

    if isinstance(payload, dict) and "records" in payload:
        return payload["records"]
    if isinstance(payload, dict) and "documents" in payload:
        records = []
        ids = payload.get("ids", []) or []
        docs = payload.get("documents", []) or []
        metas = payload.get("metadatas", []) or []
        for index, document in enumerate(docs):
            records.append({
                "id": ids[index] if index < len(ids) else f"legacy_{index}",
                "document": document,
                "metadata": metas[index] if index < len(metas) else {},
            })
        return records
    raise ValueError("不支持的导出文件格式")


def load_processed_ids(output_file):
    processed = set()
    if not os.path.exists(output_file):
        return processed
    with open(output_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
                source_id = item.get("source_diary_id")
                if source_id:
                    processed.add(source_id)
            except json.JSONDecodeError:
                continue
    return processed


def normalize_llm_json(raw_text):
    text = raw_text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end >= start:
        text = text[start:end + 1]
    return json.loads(text)


def sanitize_candidate(candidate):
    memory_type = candidate.get("type")
    if memory_type not in ALLOWED_TYPES:
        return None

    content = str(candidate.get("content", "")).strip()
    subject = str(candidate.get("subject", "")).strip()
    evidence = str(candidate.get("evidence", "")).strip()
    if not content or not subject or not evidence:
        return None

    try:
        confidence = float(candidate.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    try:
        importance = int(candidate.get("importance", 1))
    except (TypeError, ValueError):
        importance = 1

    return {
        "type": memory_type,
        "subject": subject,
        "content": content,
        "confidence": max(0.0, min(confidence, 1.0)),
        "importance": max(1, min(importance, 5)),
        "time_scope": str(candidate.get("time_scope", "unknown")),
        "evidence": evidence,
        "risk": str(candidate.get("risk", "medium")),
    }


def get_record_timestamp(record):
    metadata = record.get("metadata", {}) or {}
    timestamp = metadata.get("timestamp") or metadata.get("created_at") or 0
    try:
        return float(timestamp)
    except (TypeError, ValueError):
        return 0.0


def filter_records(records, chat_id=None):
    if chat_id is None:
        return list(records)
    chat_id = str(chat_id)
    return [
        record for record in records
        if str((record.get("metadata", {}) or {}).get("chat_id")) == chat_id
    ]


def order_records(records, order="original"):
    records = list(records)
    if order == "newest":
        return sorted(records, key=get_record_timestamp, reverse=True)
    if order == "oldest":
        return sorted(records, key=get_record_timestamp)
    return records


def sample_records(records, sample_size=0, seed=None):
    records = list(records)
    if not sample_size or sample_size >= len(records):
        return records
    rng = random.Random(seed)
    return rng.sample(records, sample_size)


def select_records(records, chat_id=None, order="original", sample_size=0, seed=None, limit=0):
    selected = filter_records(records, chat_id=chat_id)
    selected = order_records(selected, order=order)
    selected = sample_records(selected, sample_size=sample_size, seed=seed)
    if limit:
        selected = selected[:limit]
    return selected


def build_messages(record):
    document = record.get("document", "")
    metadata = record.get("metadata", {}) or {}
    source_info = {
        "id": record.get("id"),
        "chat_id": metadata.get("chat_id"),
        "timestamp": metadata.get("timestamp"),
    }
    return [
        {"role": "system", "content": EXTRACT_PROMPT},
        {"role": "user", "content": json.dumps({
            "source": source_info,
            "diary": document,
        }, ensure_ascii=False)},
    ]


async def extract_record(record, model=None, base_url=None, api_key=None):
    effective_model = model or cfg.LLM_MODEL
    effective_url = base_url or cfg.LLM_BASE_URL
    effective_key = api_key or cfg.LLM_API_KEY
    raw_text = await chat_completion(
        effective_url,
        effective_key,
        build_messages(record),
        model=effective_model,
        temperature=0.1,
        top_p=0.8,
        max_tokens=900,
        timeout=120.0,
        response_format={"type": "json_object"},
    )
    parsed = normalize_llm_json(raw_text)
    memories = []
    for candidate in parsed.get("memories", []):
        sanitized = sanitize_candidate(candidate)
        if sanitized:
            memories.append(sanitized)
    return memories


async def extract_record_with_retry(record, model=None, base_url=None, api_key=None, retries=0):
    last_error = None
    for attempt in range(retries + 1):
        try:
            return await extract_record(record, model=model, base_url=base_url, api_key=api_key)
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                await asyncio.sleep(min(2 ** attempt, 5))
    raise last_error


def write_jsonl_line(file_obj, item):
    file_obj.write(json.dumps(item, ensure_ascii=False) + "\n")
    file_obj.flush()


def build_report(stats, args, started_at, finished_at):
    return {
        "started_at": started_at,
        "finished_at": finished_at,
        "input": args.input,
        "output": args.output,
        "error_output": args.error_output,
        "chat_id": args.chat_id,
        "order": args.order,
        "sample_size": args.sample_size,
        "limit": args.limit,
        "batch_size": args.batch_size,
        "dry_run": args.dry_run,
        "retries": args.retries,
        "stats": dict(stats),
    }


async def run(args):
    started_at = datetime.datetime.now().isoformat()
    all_records = load_records(args.input)
    records = select_records(
        all_records,
        chat_id=args.chat_id,
        order=args.order,
        sample_size=args.sample_size,
        seed=args.seed,
        limit=args.limit,
    )

    output_path = Path(args.output)
    error_path = Path(args.error_output)
    report_path = Path(args.report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    error_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    processed = load_processed_ids(args.output) if args.resume else set()
    stats = Counter({
        "input_total": len(all_records),
        "selected_total": len(records),
        "processed": 0,
        "skipped": 0,
        "failed": 0,
        "candidates": 0,
    })

    batch_size = max(1, int(args.batch_size or 1))
    with open(args.output, "a", encoding="utf-8") as f, open(args.error_output, "a", encoding="utf-8") as error_f:
        for batch_start in range(0, len(records), batch_size):
            batch = records[batch_start:batch_start + batch_size]
            batch_index = batch_start // batch_size + 1
            print(f"[Batch] 开始处理批次 {batch_index}，数量 {len(batch)}")

            for record in batch:
                source_id = record.get("id")
                if source_id in processed:
                    stats["skipped"] += 1
                    continue
                if not record.get("document", "").strip():
                    stats["skipped"] += 1
                    continue

                result = {
                    "source_diary_id": source_id,
                    "source_metadata": record.get("metadata", {}),
                    "extracted_at": datetime.datetime.now().isoformat(),
                    "dry_run": args.dry_run,
                    "memories": [],
                    "error": None,
                }

                try:
                    if args.dry_run:
                        result["memories"] = []
                    else:
                        result["memories"] = await extract_record_with_retry(
                            record,
                            model=args.model,
                            base_url=args.base_url,
                            api_key=args.api_key,
                            retries=args.retries,
                        )
                except Exception as e:
                    stats["failed"] += 1
                    result["error"] = str(e)
                    write_jsonl_line(error_f, result)
                else:
                    write_jsonl_line(f, result)
                    stats["candidates"] += len(result["memories"])

                stats["processed"] += 1
                processed.add(source_id)
                print(
                    f"[Extract] 已处理 {stats['processed']} 条，跳过 {stats['skipped']} 条，"
                    f"失败 {stats['failed']} 条，候选 {stats['candidates']} 条: {source_id}"
                )

    finished_at = datetime.datetime.now().isoformat()
    report = build_report(stats, args, started_at, finished_at)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("-" * 30)
    print(f"[Done] 输出文件: {output_path.resolve()}")
    print(f"[Done] 错误文件: {error_path.resolve()}")
    print(f"[Done] 统计报告: {report_path.resolve()}")
    print(
        f"[Done] 处理 {stats['processed']} 条，跳过 {stats['skipped']} 条，"
        f"失败 {stats['failed']} 条，候选 {stats['candidates']} 条"
    )
    print("-" * 30)


def main():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    parser = argparse.ArgumentParser(description="从日记导出文件离线提取结构化长期记忆候选")
    parser.add_argument("--input", required=True, help="export_memory.py 生成的 diaries_backup_*.json")
    parser.add_argument(
        "--output",
        default=f"data/memory_exports/memory_candidates_{timestamp}.jsonl",
        help="候选输出 JSONL",
    )
    parser.add_argument(
        "--error-output",
        default=f"data/memory_exports/memory_candidates_errors_{timestamp}.jsonl",
        help="失败记录输出 JSONL",
    )
    parser.add_argument(
        "--report",
        default=f"data/memory_exports/memory_candidates_report_{timestamp}.json",
        help="统计报告输出 JSON",
    )
    parser.add_argument("--chat-id", default=None, help="仅处理指定 chat_id 的日记")
    parser.add_argument("--limit", type=int, default=0, help="仅处理前 N 条，0 表示不限")
    parser.add_argument("--sample-size", type=int, default=0, help="随机抽样 N 条，0 表示不抽样")
    parser.add_argument("--seed", type=int, default=None, help="随机抽样种子")
    parser.add_argument(
        "--order",
        choices=["original", "newest", "oldest"],
        default="original",
        help="处理顺序",
    )
    parser.add_argument("--batch-size", type=int, default=1, help="批处理大小，用于进度分段")
    parser.add_argument("--retries", type=int, default=1, help="单条失败重试次数")
    parser.add_argument("--model", default=None, help="指定提取模型，默认使用 cfg.LLM_MODEL")
    parser.add_argument("--base-url", default=None, help="指定 API base URL，默认使用 cfg.LLM_BASE_URL")
    parser.add_argument("--api-key", default=None, help="指定 API key，默认使用 cfg.LLM_API_KEY")
    parser.add_argument("--resume", action="store_true", help="根据输出 JSONL 跳过已处理 source_diary_id")
    parser.add_argument("--dry-run", action="store_true", help="只验证输入输出流程，不调用 LLM")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
