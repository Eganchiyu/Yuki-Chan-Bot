import json
import random

with open("data/memory_exports/mimo_1057020972_candidates.jsonl", "r", encoding="utf-8") as f:
    lines = f.readlines()

# 抽样 10 条，分布在不同位置
indices = sorted(random.sample(range(len(lines)), min(10, len(lines))))

for idx in indices:
    data = json.loads(lines[idx])
    doc_id = data["source_diary_id"]
    memories = data.get("memories", [])
    print(f"=== [{idx+1}/{len(lines)}] {doc_id} ({len(memories)}条候选) ===")
    for m in memories:
        mtype = m["type"]
        subject = m["subject"]
        content = m["content"][:90]
        conf = m["confidence"]
        imp = m["importance"]
        risk = m["risk"]
        print(f"  [{mtype:16s}] conf={conf:.1f} imp={imp} risk={risk:6s} | {subject}: {content}")
    print()
