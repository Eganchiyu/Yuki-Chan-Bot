"""工作历史与交接：让小女仆能查「之前谁动过这块代码、做到哪一步了」。

背景：复杂功能改造经常跨任务/跨会话，一次做不到底。没有历史可查时，
模型每次都从零开始，容易重复踩坑、重复改同一处、或覆盖别人没做完的改动。

数据来源（都是已有产物，不新增落盘）：
    logs/task_index.jsonl   每个任务的目标/状态/结果摘要
    logs/self_evolve.jsonl  每次自改的审查结果/commit/tag
    logs/trace_<id>.md      单任务的完整步骤轨迹
"""
import json
import os

from core.maid.maid_common import logger

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
TASK_INDEX = os.path.join(LOGS_DIR, "task_index.jsonl")
SELF_EVOLVE = os.path.join(LOGS_DIR, "self_evolve.jsonl")

TAIL_LINES = 800
MAX_RESULT_CHARS = 300


def _tail_json_lines(path, n=TAIL_LINES):
    """只读文件尾部若干行，避免索引膨胀后一次读爆内存。"""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = min(size, 256 * 1024)
            f.seek(size - block)
            data = f.read().decode("utf-8", errors="replace")
        lines = [ln for ln in data.splitlines() if ln.strip()]
        if block < size and lines:
            lines = lines[1:]        # 第一行可能被截断，丢掉
        out = []
        for line in lines[-n:]:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out
    except Exception as e:
        logger.warning(f"[WorkLog] 读取 {path} 失败: {e}")
        return []


def _match(record, keyword):
    if not keyword:
        return True
    blob = json.dumps(record, ensure_ascii=False).lower()
    return str(keyword).lower() in blob


def list_previous_work(keyword: str = None, limit: int = 8) -> str:
    """列出过去做过的任务与自改记录，可用关键词过滤。

    用于接手一项复杂改造前先看历史：谁改过、改到哪、为什么失败。
    """
    try:
        limit = max(1, min(int(limit or 8), 20))
    except Exception:
        limit = 8

    tasks = [r for r in _tail_json_lines(TASK_INDEX) if _match(r, keyword)]
    evolves = [r for r in _tail_json_lines(SELF_EVOLVE) if _match(r, keyword)]

    if not tasks and not evolves:
        return f"没有匹配「{keyword or '全部'}」的历史记录。"

    lines = []
    if tasks:
        lines.append(f"== 历史任务（最近 {min(len(tasks), limit)} 条）==")
        for r in tasks[-limit:][::-1]:
            result = str(r.get("result") or "").replace("\n", " ")[:MAX_RESULT_CHARS]
            lines.append(
                f"- [{r.get('finished_at', '?')}] task={r.get('task_id')} "
                f"状态={r.get('status')} 轮次={r.get('rounds', '?')}\n"
                f"  目标：{str(r.get('goal') or '')[:200]}\n"
                f"  结果：{result}"
            )

    if evolves:
        lines.append(f"\n== 自改记录（最近 {min(len(evolves), limit)} 条）==")
        for r in evolves[-limit:][::-1]:
            detail = str(r.get("detail") or "").replace("\n", " ")[:200]
            lines.append(
                f"- task={r.get('task_id')} 结果={r.get('result')} "
                f"commit={str(r.get('commit') or '')[:10]} 摘要={r.get('summary', '')}\n"
                f"  详情：{detail}"
            )

    lines.append(
        "\n要看某次任务的完整步骤，用 read_work_trace(task_id=...)。"
        "如果要接着做，可以 resume_task(task_id) 恢复它被中断时的上下文。"
    )
    return "\n".join(lines)


def read_work_trace(task_id: str, max_chars: int = 4000) -> str:
    """读某个任务的完整轨迹（尾部截断），用于交接时了解细节。"""
    if not task_id:
        return "错误：请提供 task_id（可用 list_previous_work 查询）。"
    safe = "".join(ch for ch in str(task_id) if ch.isalnum() or ch in "_-")
    path = os.path.join(LOGS_DIR, f"trace_{safe}.md")
    if not os.path.exists(path):
        return f"找不到任务 {safe} 的轨迹文件（可能已被保留策略归档）。"

    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        return f"读取失败：{e}"

    try:
        max_chars = max(500, min(int(max_chars or 4000), 12000))
    except Exception:
        max_chars = 4000

    head, tail = content[:600], content[-max_chars:] if len(content) > max_chars else ""
    if tail:
        body = f"{head}\n\n... [中间省略 {len(content) - len(head) - len(tail)} 字符] ...\n\n{tail}"
    else:
        body = content

    evolves = [r for r in _tail_json_lines(SELF_EVOLVE) if str(r.get("task_id")) == safe]
    extra = ""
    if evolves:
        e = evolves[-1]
        extra = (
            f"\n\n[该任务的自改结果] result={e.get('result')} "
            f"commit={str(e.get('commit') or '')[:10]}\n{str(e.get('detail') or '')[:600]}"
        )
    return f"=== 任务 {safe} 轨迹（{len(content)} 字符）===\n{body}{extra}"

# 自审流程端到端验证标记
