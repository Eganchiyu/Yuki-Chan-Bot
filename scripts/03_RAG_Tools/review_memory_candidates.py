import argparse
import datetime
import hashlib
import json
import os
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

LOW_VALUE_PATTERNS = [
    "打印了",
    "吃了",
    "去了",
    "刚刚",
    "今天",
    "闲聊",
]

AUTO_APPROVE_TYPES = {"fact", "preference", "relationship", "event"}
NEEDS_REVIEW_TYPES = {"profile_candidate", "todo"}


def load_candidate_entries(input_files):
    entries = []
    for input_file in input_files:
        with open(input_file, "r", encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                item["_input_file"] = input_file
                item["_line_number"] = line_number
                entries.append(item)
    return entries


def normalize_text(text):
    text = str(text or "").strip().lower()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，。！？、,.!?；;：:\"'“”‘’（）()【】\[\]{}]", "", text)
    return text


def build_candidate_id(source_diary_id, index, candidate):
    raw = "|".join([
        str(source_diary_id),
        str(index),
        str(candidate.get("type", "")),
        str(candidate.get("subject", "")),
        str(candidate.get("content", "")),
    ])
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"cand_{source_diary_id}_{index}_{digest}"


def flatten_candidates(entries):
    flattened = []
    for entry in entries:
        source_diary_id = entry.get("source_diary_id")
        source_metadata = entry.get("source_metadata", {}) or {}
        for index, candidate in enumerate(entry.get("memories", []) or []):
            item = {
                "candidate_id": build_candidate_id(source_diary_id, index, candidate),
                "source_diary_id": source_diary_id,
                "source_metadata": source_metadata,
                "extracted_at": entry.get("extracted_at"),
                "candidate": candidate,
                "input_file": entry.get("_input_file"),
                "line_number": entry.get("_line_number"),
            }
            flattened.append(item)
    return flattened


def is_low_value_candidate(candidate):
    content = str(candidate.get("content", ""))
    memory_type = candidate.get("type")
    importance = int(candidate.get("importance", 1) or 1)
    if memory_type == "event" and importance <= 2:
        return any(pattern in content for pattern in LOW_VALUE_PATTERNS)
    return False


def review_candidate(item, min_confidence=0.75, approve_profile_candidates=False):
    candidate = item.get("candidate", {}) or {}
    content = str(candidate.get("content", "")).strip()
    subject = str(candidate.get("subject", "")).strip()
    evidence = str(candidate.get("evidence", "")).strip()
    memory_type = candidate.get("type")
    risk = candidate.get("risk", "medium")
    confidence = float(candidate.get("confidence", 0) or 0)
    time_scope = candidate.get("time_scope", "unknown")

    if not content or not subject or not evidence:
        return "rejected", "missing_required_fields"
    if len(content) < 8:
        return "rejected", "content_too_short"
    if risk == "high":
        return "rejected", "high_risk"
    if confidence < min_confidence:
        return "rejected", "low_confidence"
    if is_low_value_candidate(candidate):
        return "rejected", "low_value_event"
    if risk == "medium":
        return "needs_review", "medium_risk"
    if memory_type in NEEDS_REVIEW_TYPES:
        if memory_type == "profile_candidate" and approve_profile_candidates:
            return "approved", "profile_candidate_auto_approved"
        return "needs_review", f"{memory_type}_requires_review"
    if memory_type == "todo" and time_scope == "short_term":
        return "needs_review", "short_term_todo"
    if memory_type in AUTO_APPROVE_TYPES:
        return "approved", "auto_approved"
    return "needs_review", "unknown_type"


def is_duplicate(current, previous, similarity_threshold=0.92):
    cur_candidate = current.get("candidate", {}) or {}
    prev_candidate = previous.get("candidate", {}) or {}
    if cur_candidate.get("type") != prev_candidate.get("type"):
        return False
    if normalize_text(cur_candidate.get("subject")) != normalize_text(prev_candidate.get("subject")):
        return False
    cur_content = normalize_text(cur_candidate.get("content"))
    prev_content = normalize_text(prev_candidate.get("content"))
    if not cur_content or not prev_content:
        return False
    if cur_content == prev_content:
        return True
    return SequenceMatcher(None, cur_content, prev_content).ratio() >= similarity_threshold


def apply_review(flattened, min_confidence=0.75, similarity_threshold=0.92, approve_profile_candidates=False):
    reviewed = []
    approved_seen = []
    stats = Counter({
        "total_candidates": len(flattened),
        "approved": 0,
        "needs_review": 0,
        "rejected": 0,
        "duplicates": 0,
    })
    by_type = Counter()
    by_reason = Counter()

    for item in flattened:
        candidate = item.get("candidate", {}) or {}
        by_type[candidate.get("type", "unknown")] += 1
        status, reason = review_candidate(
            item,
            min_confidence=min_confidence,
            approve_profile_candidates=approve_profile_candidates,
        )

        duplicate_of = None
        if status == "approved":
            for previous in approved_seen:
                if is_duplicate(item, previous, similarity_threshold=similarity_threshold):
                    status = "rejected"
                    reason = "duplicate"
                    duplicate_of = previous.get("candidate_id")
                    stats["duplicates"] += 1
                    break

        reviewed_item = dict(item)
        reviewed_item["review"] = {
            "status": status,
            "reason": reason,
            "duplicate_of": duplicate_of or "",
            "reviewed_at": datetime.datetime.now().isoformat(),
        }
        reviewed.append(reviewed_item)
        stats[status] += 1
        by_reason[reason] += 1
        if status == "approved":
            approved_seen.append(reviewed_item)

    return reviewed, stats, by_type, by_reason


def write_jsonl(path, items):
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def split_reviewed(reviewed):
    approved = [item for item in reviewed if item["review"]["status"] == "approved"]
    needs_review = [item for item in reviewed if item["review"]["status"] == "needs_review"]
    rejected = [item for item in reviewed if item["review"]["status"] == "rejected"]
    return approved, needs_review, rejected


def run(args):
    started_at = datetime.datetime.now().isoformat()
    entries = load_candidate_entries(args.input)
    flattened = flatten_candidates(entries)
    reviewed, stats, by_type, by_reason = apply_review(
        flattened,
        min_confidence=args.min_confidence,
        similarity_threshold=args.similarity_threshold,
        approve_profile_candidates=args.approve_profile_candidates,
    )
    approved, needs_review, rejected = split_reviewed(reviewed)

    for path in [args.approved_output, args.needs_review_output, args.rejected_output, args.report]:
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    write_jsonl(args.approved_output, approved)
    write_jsonl(args.needs_review_output, needs_review)
    write_jsonl(args.rejected_output, rejected)

    report = {
        "started_at": started_at,
        "finished_at": datetime.datetime.now().isoformat(),
        "input": args.input,
        "approved_output": args.approved_output,
        "needs_review_output": args.needs_review_output,
        "rejected_output": args.rejected_output,
        "min_confidence": args.min_confidence,
        "similarity_threshold": args.similarity_threshold,
        "approve_profile_candidates": args.approve_profile_candidates,
        "stats": dict(stats),
        "by_type": dict(by_type),
        "by_reason": dict(by_reason),
    }
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"[Review] 候选总数: {stats['total_candidates']}")
    print(f"[Review] approved={stats['approved']} needs_review={stats['needs_review']} rejected={stats['rejected']}")
    print(f"[Review] duplicates={stats['duplicates']}")
    print(f"[Review] 报告: {Path(args.report).resolve()}")


def main():
    parser = argparse.ArgumentParser(description="审核和去重 Yuki-Memory 结构化候选")
    parser.add_argument("--input", nargs="+", required=True, help="backfill_memory_candidates.py 输出的 JSONL")
    parser.add_argument("--approved-output", required=True, help="自动通过候选 JSONL")
    parser.add_argument("--needs-review-output", required=True, help="需要人工审核候选 JSONL")
    parser.add_argument("--rejected-output", required=True, help="自动拒绝候选 JSONL")
    parser.add_argument("--report", required=True, help="审核报告 JSON")
    parser.add_argument("--min-confidence", type=float, default=0.75, help="自动审核最低置信度")
    parser.add_argument("--similarity-threshold", type=float, default=0.92, help="同主体同类型去重相似度阈值")
    parser.add_argument("--approve-profile-candidates", action="store_true", help="允许 profile_candidate 自动通过")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
