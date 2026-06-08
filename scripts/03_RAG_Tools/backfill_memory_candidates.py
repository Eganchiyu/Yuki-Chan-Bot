import argparse
import asyncio
import datetime
import json
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from config import cfg
from utils.llm_client import llm_chat

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


async def extract_record(record, model=None):
    raw_text = await llm_chat(
        build_messages(record),
        model=model or cfg.LLM_MODEL,
        temperature=0.1,
        top_p=0.8,
        max_tokens=900,
        response_format={"type": "json_object"},
    )
    parsed = normalize_llm_json(raw_text)
    memories = []
    for candidate in parsed.get("memories", []):
        sanitized = sanitize_candidate(candidate)
        if sanitized:
            memories.append(sanitized)
    return memories


async def run(args):
    records = load_records(args.input)
    if args.limit:
        records = records[:args.limit]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    processed = load_processed_ids(args.output) if args.resume else set()

    total = 0
    skipped = 0
    failed = 0

    with open(args.output, "a", encoding="utf-8") as f:
        for record in records:
            source_id = record.get("id")
            if source_id in processed:
                skipped += 1
                continue
            if not record.get("document", "").strip():
                skipped += 1
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
                    result["memories"] = await extract_record(record, model=args.model)
            except Exception as e:
                failed += 1
                result["error"] = str(e)

            f.write(json.dumps(result, ensure_ascii=False) + "\n")
            f.flush()
            total += 1
            print(f"[Extract] 已处理 {total} 条，跳过 {skipped} 条，失败 {failed} 条: {source_id}")

    print("-" * 30)
    print(f"[Done] 输出文件: {output_path.resolve()}")
    print(f"[Done] 处理 {total} 条，跳过 {skipped} 条，失败 {failed} 条")
    print("-" * 30)


def main():
    parser = argparse.ArgumentParser(description="从日记导出文件离线提取结构化长期记忆候选")
    parser.add_argument("--input", required=True, help="export_memory.py 生成的 diaries_backup_*.json")
    parser.add_argument("--output", default="data/memory_exports/memory_candidates.jsonl")
    parser.add_argument("--limit", type=int, default=0, help="仅处理前 N 条，0 表示不限")
    parser.add_argument("--model", default=None, help="指定提取模型，默认使用 cfg.LLM_MODEL")
    parser.add_argument("--resume", action="store_true", help="根据输出 JSONL 跳过已处理 source_diary_id")
    parser.add_argument("--dry-run", action="store_true", help="只验证输入输出流程，不调用 LLM")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
