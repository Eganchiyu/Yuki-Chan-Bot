#!/usr/bin/env python3
"""存储保留策略：让"可追溯"不以爆盘为代价（进化准则第 11 条）。

四类资产分开处理：
    logs/trace_*.md      最近 7 天全量 → 更早按周打包成归档 → 总量超 200MB 删最旧
    logs/self_evolve.jsonl 永久保留（每行几百字节）
    logs/supervisor.log  滚动，超过 20MB 截断保留末尾
    backups/yuki_memory  由 supervisor 管理（保留 7 份硬链接快照）
    staging/             已完成的请求目录超过 3 天即删（result.json 已进 self_evolve.jsonl）

用法:
    python3 deploy/retention.py --dry-run   # 只看会删什么
    python3 deploy/retention.py             # 实际执行
建议 cron: 每天 04:00
"""
import argparse
import json
import os
import shutil
import tarfile
import time
from datetime import datetime

ROOT = os.environ.get("YUKI_ROOT", "/home/asumi/Yuki")
LOGS = os.path.join(ROOT, "logs")
ARCHIVE = os.path.join(LOGS, "archive")
STAGING = os.path.join(ROOT, "staging")

TRACE_KEEP_DAYS = 7
ARCHIVE_BUDGET_MB = 200
SUPERVISOR_LOG_MAX_MB = 20
STAGING_KEEP_DAYS = 3

dry_run = False


def log(msg):
    print(("[dry] " if dry_run else "") + msg, flush=True)


def human(size):
    return f"{size / 1024 / 1024:.1f}MB" if size > 1024 * 1024 else f"{size / 1024:.0f}KB"


# ---------------------------------------------------------------- trace 归档
def archive_old_traces():
    if not os.path.isdir(LOGS):
        return
    cutoff = time.time() - TRACE_KEEP_DAYS * 86400
    old = [
        os.path.join(LOGS, f) for f in os.listdir(LOGS)
        if f.startswith("trace_") and f.endswith(".md")
        and os.path.getmtime(os.path.join(LOGS, f)) < cutoff
    ]
    if not old:
        log("trace: 无需归档")
        return

    os.makedirs(ARCHIVE, exist_ok=True)
    # 按 ISO 周分组，一周一个 tar.gz，只存摘要文本，不存原始全文
    weeks = {}
    for path in old:
        mtime = datetime.fromtimestamp(os.path.getmtime(path))
        week = f"{mtime.isocalendar()[0]}-W{mtime.isocalendar()[1]:02d}"
        weeks.setdefault(week, []).append(path)

    for week, paths in weeks.items():
        target = os.path.join(ARCHIVE, f"trace-{week}.tar.gz")
        summary = [
            f"# trace 归档 {week}",
            f"归档时间: {datetime.now():%Y-%m-%d %H:%M}",
            f"文件数: {len(paths)}",
            "",
        ]
        # 每份 trace 只保留首行标题 + 任务目标，防止归档本身爆盘
        for p in paths:
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    head = [next(f, "").strip(), next(f, "").strip(), next(f, "").strip()]
                summary.append(f"- {os.path.basename(p)}: {' | '.join(h for h in head if h)[:200]}")
            except Exception:
                summary.append(f"- {os.path.basename(p)}: (读取失败)")
        log(f"trace: 归档 {len(paths)} 个文件 → {target}")
        if not dry_run:
            with tarfile.open(target, "w:gz") as tar:
                for p in paths:
                    tar.add(p, arcname=os.path.basename(p))
            for p in paths:
                os.remove(p)
            with open(os.path.splitext(target)[0] + ".summary.md", "w", encoding="utf-8") as f:
                f.write("\n".join(summary) + "\n")


# ---------------------------------------------------------------- 归档总量
def trim_archives():
    if not os.path.isdir(ARCHIVE):
        return
    files = sorted(
        os.path.join(ARCHIVE, f) for f in os.listdir(ARCHIVE)
        if f.endswith(".tar.gz")
    )
    total = sum(os.path.getsize(f) for f in files)
    budget = ARCHIVE_BUDGET_MB * 1024 * 1024
    for path in files:
        if total <= budget:
            break
        size = os.path.getsize(path)
        log(f"archive: 超出预算，删除 {os.path.basename(path)} ({human(size)})")
        if not dry_run:
            os.remove(path)
            summary = os.path.splitext(path)[0] + ".summary.md"
            if os.path.exists(summary):
                os.remove(summary)
        total -= size


# ---------------------------------------------------------------- 大日志截断
def trim_file(path, max_mb):
    if not os.path.exists(path):
        return
    size = os.path.getsize(path)
    if size <= max_mb * 1024 * 1024:
        return
    log(f"{os.path.basename(path)}: {human(size)} 超限，保留末尾 50%")
    if dry_run:
        return
    keep = size // 2
    with open(path, "rb") as f:
        f.seek(-keep, os.SEEK_END)
        tail = f.read()
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write("[... 前半部分已按保留策略截断 ...]\n".encode("utf-8") + tail)
    os.replace(tmp, path)


# ---------------------------------------------------------------- staging 清理
def clean_staging():
    if not os.path.isdir(STAGING):
        return
    cutoff = time.time() - STAGING_KEEP_DAYS * 86400
    for name in os.listdir(STAGING):
        d = os.path.join(STAGING, name)
        if not os.path.isdir(d):
            continue
        if not os.path.exists(os.path.join(d, "result.json")):
            continue  # 未处理完的不动
        if os.path.getmtime(d) < cutoff:
            log(f"staging: 删除已完成的 {name}")
            if not dry_run:
                shutil.rmtree(d, ignore_errors=True)


def main():
    global dry_run
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    dry_run = ap.parse_args().dry_run

    log(f"保留策略开始（root={ROOT}）")
    archive_old_traces()
    trim_archives()
    trim_file(os.path.join(LOGS, "yuki.log"), SUPERVISOR_LOG_MAX_MB)
    trim_file(os.path.join(LOGS, "supervisor.log"), SUPERVISOR_LOG_MAX_MB)
    trim_file(os.path.join(ROOT, "data", "yuki_log.txt"), SUPERVISOR_LOG_MAX_MB)
    clean_staging()
    log("保留策略完成")


if __name__ == "__main__":
    main()
