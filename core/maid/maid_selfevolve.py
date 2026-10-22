"""自进化工具：让「小女仆改 Yuki 自己」变成受控流程。

关键设计——容器内代码是只读的，所以这里**只写 staging/**，应用与重启由
宿主 `deploy/supervisor.py` 执行。三个工具的职责：

    propose_patch    写候选补丁到 staging/<task_id>/files/
    verify_patch     快速自检（语法/规模/diff 概览）+ 明确告知完整校验在宿主侧
    request_self_reload 落 request.json，交给 supervisor 走 校验→切换→回滚

这样即使模型乱来，也改不到正在运行的代码，更谈不上把 Yuki 弄到起不来。
"""
import ast
import json
import os
from datetime import datetime

from core.maid.maid_charter import (
    MAX_PATCH_REMOVED_RATIO,
    MAX_PATCH_ADDED_LINES,
    MAX_PATCH_FILES,
    classify_path,
    is_sensitive,
)
from core.maid.maid_common import logger

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STAGING_DIR = os.path.join(PROJECT_ROOT, "staging")
REQUEST_FILE = "request.json"
FILES_SUBDIR = "files"


def _task_dir(task_id: str) -> str:
    safe = "".join(ch for ch in str(task_id) if ch.isalnum() or ch in "_-")
    return os.path.join(STAGING_DIR, safe or "unknown")


def _normalize_files(files) -> list:
    """容忍模型给 dict 或 list；统一成 [{path, content}]。"""
    if isinstance(files, dict):
        return [{"path": k, "content": v} for k, v in files.items()]
    if isinstance(files, list):
        out = []
        for item in files:
            if isinstance(item, dict):
                out.append({
                    "path": item.get("path") or item.get("file") or "",
                    "content": item.get("content") or item.get("code") or "",
                })
        return out
    return []


def propose_patch(task_id: str, files, summary: str = "") -> str:
    """把候选改动写入 staging，不在生产树上留下任何痕迹。"""
    items = _normalize_files(files)
    if not items:
        return "错误：files 为空。请传入 [{\"path\": \"core/xxx.py\", \"content\": \"完整文件内容\"}]"

    if len(items) > MAX_PATCH_FILES:
        return f"错误：单次最多改 {MAX_PATCH_FILES} 个文件，当前 {len(items)} 个。请拆分。"

    # 先全量校验路径，避免写一半才发现有禁区
    checked = []
    for item in items:
        path = str(item.get("path") or "").replace("\\", "/").strip()
        level = classify_path(path)
        if level == "forbidden":
            return f"错误：'{path}' 属于禁区（数据/配置/部署/人格/准则），任何情况下不得改动。"
        if level == "unknown":
            return f"错误：'{path}' 不在允许范围内。只能改 core/ utils/ modules/ network/ main.py config.py 或 skills/。"
        if not path.endswith(".py") and level != "free":
            return f"错误：'{path}' 不是 Python 文件，受限区只接受 .py 改动。"
        if not str(item.get("content") or "").strip():
            return f"错误：'{path}' 的 content 为空。请给出完整文件内容（不是 diff 片段）。"
        checked.append({"path": path, "content": str(item["content"])})

    return _write_staging(task_id, checked, summary)


def _write_staging(task_id, checked, summary) -> str:
    tdir = _task_dir(task_id)
    fdir = os.path.join(tdir, FILES_SUBDIR)
    os.makedirs(fdir, exist_ok=True)

    added = 0
    removed_violations = []
    lines = []
    for item in checked:
        path = item["path"]
        dst = os.path.join(fdir, path)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        live = os.path.join(PROJECT_ROOT, path)
        old = ""
        if os.path.exists(live):
            try:
                with open(live, encoding="utf-8", errors="replace") as f:
                    old = f.read()
            except Exception:
                old = ""
        old_lines = old.count("\n") + 1 if old else 0
        new_lines = item["content"].count("\n") + 1
        # 防误删：保留大段缩水必须显式拆分成多次小改
        if old_lines > 20 and new_lines < old_lines * (1 - MAX_PATCH_REMOVED_RATIO):
            removed_violations.append(f"'{path}' 从 {old_lines} 行缩到 {new_lines} 行")
        added += max(0, new_lines - old_lines)
        with open(dst, "w", encoding="utf-8") as f:
            f.write(item["content"])
        level = classify_path(path)
        lines.append(f"  - {path} [{level}] 现有 {old_lines} 行 → 新 {new_lines} 行")

    if removed_violations:
        return (
            "错误：以下文件缩水超过 "
            f"{int(MAX_PATCH_REMOVED_RATIO * 100)}%，疑似误删整段逻辑，已拒绝：\n  "
            + "\n  ".join(removed_violations)
            + "\n请只保留任务必需的最小改动，保留原有功能。"
        )

    if added > MAX_PATCH_ADDED_LINES:
        return (
            f"错误：本次净增 {added} 行，超过上限 {MAX_PATCH_ADDED_LINES} 行。"
            "请把改动拆小，只做当前任务必需的最小修改。"
        )

    # request.json 由 request_self_reload 落盘；这里只记录草案元信息
    meta = {
        "task_id": os.path.basename(tdir),
        "summary": (summary or "未命名自改")[:120],
        "files": [{"path": c["path"]} for c in checked],
        "sensitive": is_sensitive("\n".join(c["content"] for c in checked)),
        "proposed_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
    }
    with open(os.path.join(tdir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    logger.info(f"[Maid] 自改补丁已写入 staging: {tdir}（{len(checked)} 个文件）")
    head = "已写入候选补丁（尚未生效）：\n" + "\n".join(lines)
    tail = (
        f"\n净增 {added} 行。下一步：\n"
        "1. 调 verify_patch 做快速自检\n"
        "2. 自检通过后调 request_self_reload 提交，由 supervisor 做完整校验并重启\n"
        "注意：受限区改动若校验或健康检查失败会自动回滚，失败日志会回传给你。"
    )
    return head + tail


def verify_patch(task_id: str) -> str:
    """容器内快速自检：语法 + 规模 + diff 概览。

    完整的 5 道门（compileall/import/tests/dry_run/health）在宿主 supervisor 侧执行，
    因为容器内没有 docker socket，也不该让被测代码自己决定校验标准。
    """
    tdir = _task_dir(task_id)
    fdir = os.path.join(tdir, FILES_SUBDIR)
    if not os.path.isdir(fdir):
        return "错误：还没有候选补丁，请先调 propose_patch。"

    problems = []
    report = []
    for root, _, names in os.walk(fdir):
        for name in sorted(names):
            full = os.path.join(root, name)
            rel = os.path.relpath(full, fdir).replace("\\", "/")
            try:
                with open(full, encoding="utf-8") as f:
                    code = f.read()
            except Exception as e:
                problems.append(f"{rel}: 读取失败 {e}")
                continue

            try:
                tree = ast.parse(code)
            except SyntaxError as e:
                problems.append(f"{rel}: 语法错误 第{e.lineno}行 {e.msg}")
                continue

            defs = sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for n in ast.walk(tree))
            live = os.path.join(PROJECT_ROOT, rel)
            live_defs = 0
            if os.path.exists(live):
                try:
                    with open(live, encoding="utf-8", errors="replace") as f:
                        live_defs = sum(
                            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                            for n in ast.walk(ast.parse(f.read()))
                        )
                except Exception:
                    live_defs = 0
            if live_defs and defs < live_defs:
                problems.append(
                    f"{rel}: 定义数从 {live_defs} 掉到 {defs}，疑似误删函数/类。"
                    "请确认这是有意为之，否则补全后再提交。"
                )
            report.append(f"  - {rel}: 语法 OK，{len(code.splitlines())} 行，定义 {defs} 个")

    if not report and not problems:
        return "错误：staging 中没有可校验的文件。"

    out = ["快速自检结果："] + report
    if problems:
        out.append("\n发现问题（请修正后重新 propose_patch）：")
        out += [f"  ✗ {p}" for p in problems]
        out.append(
            "\n注意：这只是容器内快速检查。完整校验（编译/导入/单测/试启动/健康）"
            "由宿主 supervisor 执行，失败会自动回滚并把日志回传给你。"
        )
        return "\n".join(out)

    out.append("\n未发现语法/规模问题。")
    out.append(
        "完整校验（编译/导入/单测/试启动/健康检查）由宿主 supervisor 执行，"
        "过程中若失败会自动回滚并把错误日志回传。"
    )
    return "\n".join(out)


def request_self_reload(task_id: str, summary: str = "", reason: str = "") -> str:
    """落 request.json，交给宿主 supervisor 走 校验→切换→回滚 的完整链路。"""
    tdir = _task_dir(task_id)
    fdir = os.path.join(tdir, FILES_SUBDIR)
    if not os.path.isdir(fdir):
        return "错误：没有候选补丁，无法请求生效。请先调 propose_patch。"

    files = []
    for root, _, names in os.walk(fdir):
        for name in names:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, fdir).replace("\\", "/")
            files.append({"path": rel})
    if not files:
        return "错误：staging 中文件为空。"

    request = {
        "task_id": os.path.basename(tdir),
        "summary": (summary or "未命名自改")[:120],
        "reason": str(reason)[:1000],
        "files": files,
        "requested_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
    }
    with open(os.path.join(tdir, REQUEST_FILE), "w", encoding="utf-8") as f:
        json.dump(request, f, ensure_ascii=False, indent=2)

    logger.info(f"[Maid] 已提交自改请求: {tdir}")
    return (
        "已提交给守护进程，正在执行：路径分级校验 → yuki_memory 快照 → 应用 + git commit "
        "→ 5 道校验门 → 重启容器 → 健康检查。\n"
        "成功会打 tag 存档；失败会自动回滚到上一个可用版本，并把错误日志写进 "
        f"{os.path.join(tdir, 'result.json')} 和 logs/self_evolve.jsonl。\n"
        "重启期间 Yuki 会短暂离线（约 15~30 秒），这是预期行为。"
    )


def read_last_result(task_id: str = None) -> str:
    """读最近一次自改结果，供任务 resume 后判断上一轮是否成功。"""
    if not os.path.isdir(STAGING_DIR):
        return "还没有任何自改记录。"
    dirs = sorted(
        (os.path.join(STAGING_DIR, d) for d in os.listdir(STAGING_DIR)),
        key=lambda p: os.path.getmtime(p),
        reverse=True,
    )
    for d in dirs:
        if task_id and os.path.basename(d) != str(task_id):
            continue
        result = os.path.join(d, "result.json")
        if os.path.exists(result):
            try:
                with open(result, encoding="utf-8") as f:
                    data = json.load(f)
                return f"最近一次自改结果：{json.dumps(data, ensure_ascii=False)[:2000]}"
            except Exception as e:
                return f"读取结果失败：{e}"
    return "还没有已完成的《自改》记录。"
