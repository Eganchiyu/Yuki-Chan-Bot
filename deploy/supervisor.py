#!/usr/bin/env python3
"""Yuki 自进化守护进程（跑在宿主机，不进容器）。

职责边界（这是整个自进化安全模型的根）：
    - 容器内的代码树是只读的 → 小女仆只能在 staging/ 写候选补丁
    - 只有本进程有权限把候选补丁应用到生产代码树、提交 git、重启容器
    - 任何一步失败都必须能回到上一个 good 状态

处理一个请求的完整链路：
    读取 staging/<task>/request.json
      → 路径分级校验（禁区直接拒）
      → 速率/冷却检查
      → yuki_memory 快照（改代码前先保命）
      → 应用文件 + git commit
      → 含受限区改动则跑 deploy/verify.sh（5 道门）
      → 重启容器 + /health 探活
      → 失败自动 git reset --hard <last_good> + 重启 + 复检
      → 写 result.json / logs/self_evolve.jsonl

用法:
    python3 deploy/supervisor.py            # 前台守护
    python3 deploy/supervisor.py --once     # 处理一轮就退出（调试用）
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

ROOT = os.environ.get("YUKI_ROOT", "/home/asumi/Yuki")
sys.path.insert(0, ROOT)

# 按文件加载准则模块，避免触发 core/__init__.py（万一将来引入重依赖，宿主环境不完整）
import importlib.util as _iutil  # noqa: E402

_spec = _iutil.spec_from_file_location(
    "maid_charter", os.path.join(ROOT, "core", "maid", "maid_charter.py")
)
_charter = _iutil.module_from_spec(_spec)
_spec.loader.exec_module(_charter)

COOLDOWN_AFTER_FAILURES = _charter.COOLDOWN_AFTER_FAILURES
COOLDOWN_HOURS = _charter.COOLDOWN_HOURS
MAX_EVOLVE_PER_DAY = _charter.MAX_EVOLVE_PER_DAY
MAX_EVOLVE_PER_HOUR = _charter.MAX_EVOLVE_PER_HOUR
MAX_PATCH_ADDED_LINES = _charter.MAX_PATCH_ADDED_LINES
MAX_PATCH_FILES = _charter.MAX_PATCH_FILES
MAX_RESTART_PER_HOUR = int(os.environ.get("YUKI_MAX_RESTART_PER_HOUR", 5))
MAX_REVIEW_REJECTS = int(os.environ.get("YUKI_MAX_REVIEW_REJECTS", 3))
classify_path = _charter.classify_path
is_sensitive = _charter.is_sensitive

# 审查器同目录加载：宿主侧实现，容器内改不到
_rspec = _iutil.spec_from_file_location(
    "reviewer", os.path.join(os.path.dirname(os.path.abspath(__file__)), "reviewer.py")
)
_reviewer = _iutil.module_from_spec(_rspec)
_rspec.loader.exec_module(_reviewer)
review_patch = _reviewer.review_patch

STAGING = os.path.join(ROOT, "staging")
STATE_FILE = os.path.join(ROOT, "deploy", "state.json")
EVOLVE_LOG = os.path.join(ROOT, "logs", "self_evolve.jsonl")
SUP_LOG = os.path.join(ROOT, "logs", "supervisor.log")
SNAP_ROOT = os.path.join(ROOT, "backups", "yuki_memory")
SNAP_KEEP = 7
HEALTH_URL = os.environ.get("YUKI_HEALTH_URL", "http://127.0.0.1:8778/health")
HEALTH_TIMEOUT = int(os.environ.get("YUKI_HEALTH_TIMEOUT", "150"))
IMAGE = os.environ.get("YUKI_IMAGE", "yuki:base")
CONTAINER = os.environ.get("YUKI_CONTAINER", "yuki")


# ------------------------------------------------------------------ 基础工具
def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(SUP_LOG), exist_ok=True)
        with open(SUP_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def sh(cmd, cwd=ROOT, timeout=600, env=None):
    """跑命令，返回 (rc, stdout+stderr)。绝不抛异常，失败由调用方判定。"""
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, timeout=timeout, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        return proc.returncode, proc.stdout or ""
    except subprocess.TimeoutExpired:
        return 124, f"命令超时（{timeout}s）：{' '.join(cmd)}"
    except Exception as e:
        return 1, f"命令异常：{e}"


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_good": "", "history": []}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    state["history"] = state.get("history", [])[-50:]  # 只留最近 50 条，防爆盘
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


def append_evolve_log(entry):
    try:
        os.makedirs(os.path.dirname(EVOLVE_LOG), exist_ok=True)
        with open(EVOLVE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        log(f"写 self_evolve.jsonl 失败: {e}")


# ------------------------------------------------------------------ 数据快照
def snapshot_memory() -> str:
    """改代码前给 yuki_memory 做一次硬链接增量快照，秒级完成。"""
    src = os.path.join(ROOT, "yuki_memory")
    if not os.path.isdir(src):
        return ""
    if shutil.which("rsync") is None:
        log("未安装 rsync，跳过快照（建议 apt install rsync）")
        return ""
    os.makedirs(SNAP_ROOT, exist_ok=True)
    snap = os.path.join(SNAP_ROOT, datetime.now().strftime("%Y%m%d_%H%M%S"))
    existing = sorted(
        os.path.join(SNAP_ROOT, d) for d in os.listdir(SNAP_ROOT)
        if os.path.isdir(os.path.join(SNAP_ROOT, d))
    )
    cmd = ["rsync", "-a", "--delete"]
    if existing:
        cmd.append(f"--link-dest={existing[-1]}")
    cmd += [src + "/", snap + "/"]
    rc, out = sh(cmd, cwd=ROOT, timeout=300)
    if rc != 0:
        log(f"快照失败: {out[-300:]}")
        return ""
    # 只留最近 SNAP_KEEP 份
    snaps = sorted(
        os.path.join(SNAP_ROOT, d) for d in os.listdir(SNAP_ROOT)
        if os.path.isdir(os.path.join(SNAP_ROOT, d))
    )
    for old in snaps[:-SNAP_KEEP]:
        shutil.rmtree(old, ignore_errors=True)
    return snap


# ------------------------------------------------------------------ 速率/冷却
def rate_limit_reason(state):
    now = time.time()
    hist = [h for h in state.get("history", []) if h.get("result") in {"ok", "verify_failed", "health_failed", "apply_failed"}]
    hour = [h for h in hist if now - h.get("ts", 0) < 3600]
    day = [h for h in hist if now - h.get("ts", 0) < 86400]
    if len(hour) >= MAX_EVOLVE_PER_HOUR:
        return f"每小时自改已达上限 {MAX_EVOLVE_PER_HOUR} 次"
    if len(day) >= MAX_EVOLVE_PER_DAY:
        return f"每日自改已达上限 {MAX_EVOLVE_PER_DAY} 次"
    recent = hist[-COOLDOWN_AFTER_FAILURES:]
    if len(recent) == COOLDOWN_AFTER_FAILURES and all(h.get("result") != "ok" for h in recent):
        last_ts = max(h.get("ts", 0) for h in recent)
        if now - last_ts < COOLDOWN_HOURS * 3600:
            left = COOLDOWN_HOURS * 3600 - (now - last_ts)
            return f"连续失败进入冷却，还需等待 {int(left / 60)} 分钟"
    return ""


# ------------------------------------------------------------------ 应用补丁
def validate_request(req):
    """返回 (ok, reason, files)。禁区命中一律拒绝。"""
    if str(req.get("type") or "patch") == "restart":
        return True, "", []          # 重启不带补丁
    files = req.get("files") or []
    if not files:
        return False, "request.files 为空", []
    if len(files) > MAX_PATCH_FILES:
        return False, f"文件数 {len(files)} 超过上限 {MAX_PATCH_FILES}", []
    for item in files:
        path = str(item.get("path") or "")
        level = classify_path(path)
        if level == "forbidden":
            return False, f"禁区文件，拒绝改动：{path}", []
        if level == "unknown":
            return False, f"未纳入分级的路径，拒绝改动：{path}", []
        if not os.path.exists(os.path.join(ROOT, path)) and not item.get("content"):
            return False, f"目标不存在且未提供内容：{path}", []
    return True, "", files


def apply_patch(request_dir, files):
    """把 staging 里的候选内容写进生产代码树。返回 (ok, msg)。"""
    added = 0
    for item in files:
        rel = str(item["path"]).replace("\\", "/")
        dst = os.path.join(ROOT, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        content = item.get("content")
        if content is None:
            src = os.path.join(request_dir, "files", rel)
            if not os.path.exists(src):
                return False, f"staging 中缺少文件：{rel}"
            with open(src, encoding="utf-8") as f:
                content = f.read()
        old = ""
        if os.path.exists(dst):
            with open(dst, encoding="utf-8", errors="replace") as f:
                old = f.read()
        added += max(0, content.count("\n") - old.count("\n"))
        with open(dst, "w", encoding="utf-8") as f:
            f.write(content)
    if added > MAX_PATCH_ADDED_LINES:
        return False, f"净增 {added} 行超过上限 {MAX_PATCH_ADDED_LINES}"
    return True, f"已应用 {len(files)} 个文件"


def git_commit(summary, task_id, files):
    """只提交补丁涉及的路径。

    绝不用 `git add -A`：那会把守护进程自己的运行时状态、staging 目录、
    以及人工未提交的改动一起卷进自进化提交，回滚时连带删掉不该删的东西。
    """
    paths = [str(f["path"]) for f in files]
    rc, out = sh(["git", "add", "--"] + paths, cwd=ROOT)
    if rc != 0:
        return False, f"git add 失败: {out}"
    rc, out = sh(["git", "commit", "-m", f"self-evolve: {summary}\n\ntask: {task_id}"], cwd=ROOT)
    if rc != 0:
        if "nothing to commit" in out:
            return False, "补丁与原文件完全相同，没有实际改动，已取消（无需重启）"
        return False, out
    rc, sha = sh(["git", "rev-parse", "HEAD"], cwd=ROOT)
    return True, sha.strip()


def git_reset(rev):
    rc, out = sh(["git", "reset", "--hard", rev], cwd=ROOT)
    return rc == 0, out


# ------------------------------------------------------------------ 容器切换
def wait_health(timeout=HEALTH_TIMEOUT):
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=5) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                if body.get("ready"):
                    return True, body
                last = f"ready=false {body}"
        except urllib.error.HTTPError as e:
            last = f"http {e.code}"
        except Exception as e:
            last = str(e)
        time.sleep(3)
    return False, last


def restart_container():
    rc, out = sh(["bash", os.path.join(ROOT, "deploy", "run.sh")], cwd=ROOT, timeout=300)
    if rc != 0:
        return False, out
    return wait_health()


def _bump_review_round(request_dir, approved, detail, risk):
    """记录这份补丁的审查轮次，返回「本次是第几次被驳回」。

    存在 staging/<task>/review.json：模型可以直接读它，不必只靠同步返回的文本
    （重启/session 断掉之后还能看）。
    """
    path = os.path.join(request_dir, "review.json")
    record = {"rejects": 0, "rounds": 0}
    try:
        with open(path, encoding="utf-8") as f:
            record.update(json.load(f) or {})
    except Exception:
        pass

    record["rounds"] = int(record.get("rounds") or 0) + 1
    record["approved"] = bool(approved)
    record["risk"] = str(risk)
    record["detail"] = str(detail)[-4000:]
    record["ts"] = datetime.now().isoformat(timespec="seconds")
    if not approved:
        record["rejects"] = int(record.get("rejects") or 0) + 1
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"写 review.json 失败: {e}")
    return int(record.get("rejects") or 0)


# ------------------------------------------------------------------ 主处理
def handle_request(request_dir):
    task_id = os.path.basename(request_dir.rstrip("/"))
    state = load_state()
    started = time.time()

    def finish(result, detail, summary=""):
        entry = {
            "ts": started, "task_id": task_id, "result": result,
            "summary": str(summary)[:120],
            "detail": str(detail)[-1500:],
            "commit": state.get("last_good", ""),
        }
        append_evolve_log(entry)
        state["history"].append(entry)
        save_state(state)
        out = {"task_id": task_id, "result": result, "detail": str(detail)[-3000:],
               "finished_at": datetime.now().isoformat(timespec="seconds")}
        with open(os.path.join(request_dir, "result.json"), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        log(f"[{task_id}] {result}: {str(detail)[:200]}")
        return out

    try:
        with open(os.path.join(request_dir, "request.json"), encoding="utf-8") as f:
            req = json.load(f)
    except Exception as e:
        return finish("bad_request", f"request.json 不可读: {e}")

    ok, why, files = validate_request(req)
    if not ok:
        return finish("rejected", why)

    limited = rate_limit_reason(state)
    if limited:
        return finish("rejected", limited)

    # ---- 重启类请求：不改代码，只重新初始化（快照 → 重建容器 → 探活）----
    if str(req.get("type") or "patch") == "restart":
        recent = [
            h for h in state.get("history", [])
            if h.get("result") in {"restarted", "restart_failed"} and time.time() - h.get("ts", 0) < 3600
        ]
        if len(recent) >= MAX_RESTART_PER_HOUR:
            return finish("rejected", f"每小时重启已达上限 {MAX_RESTART_PER_HOUR} 次")
        snap = snapshot_memory()
        log(f"[{task_id}] 重启请求，记忆快照: {snap or '(跳过)'}")
        ok, health = restart_container()
        if ok:
            return finish("restarted", f"容器已重建并健康；快照={os.path.basename(snap) if snap else '-'}", "重启容器")
        return finish("restart_failed", f"重建后健康检查失败，需人工介入: {health}")

    summary = str(req.get("summary") or "未命名自改")[:120]
    needs_restart = any(classify_path(f["path"]) == "restricted" for f in files)

    # 回滚基线 = 本次改动前的 HEAD（比 last_good 更准确：即使 last_good 未初始化也不会回错）
    rc, base = sh(["git", "rev-parse", "HEAD"], cwd=ROOT)
    if rc != 0:
        return finish("apply_failed", f"无法读取当前 HEAD: {base}")
    base = base.strip()
    state["base_commit"] = base

    # 1) 先保命：改代码前快照记忆
    snap = snapshot_memory()
    log(f"[{task_id}] 记忆快照: {snap or '(跳过)'} 基线: {base[:10]}")

    # 2) 独立模型审查（宿主侧）：只有必修问题才驳回，建议类不阻断
    t_review = time.time()
    try:
        approved, review_detail, risk = review_patch(request_dir, req, files)
    except Exception as e:
        approved, review_detail, risk = False, f"审查不可用：审查器异常 {e}", "unknown"
    review_ms = int((time.time() - t_review) * 1000)
    log(f"[{task_id}] 审查 {'通过' if approved else '驳回'}（{risk}, {review_ms}ms）")

    # 驳回次数落盘：既给模型下一轮读，也防止同一份补丁无限打转
    rejects = _bump_review_round(request_dir, approved, review_detail, risk)
    if approved and rejects:
        review_detail += f"\n（注：这份补丁之前被驳回 {rejects} 次，本次才通过）"
    if not approved:
        hint = (
            f"\n\n[第 {rejects} 次被驳回] 改完直接重新提交即可（删掉 staging 里的旧 result.json）。"
        )
        if rejects >= MAX_REVIEW_REJECTS:
            hint = (
                f"\n\n[已连续被驳回 {rejects} 次，达到上限 {MAX_REVIEW_REJECTS}] "
                "不要再原样重试：把问题原样报告给 Yuki，说明卡在哪一条必修问题上。"
            )
        return finish("review_rejected", review_detail + hint, summary)

    # 3) 应用 + 提交（先提交，失败才能 reset 回滚）
    ok, msg = apply_patch(request_dir, files)
    if not ok:
        git_reset(base)
        return finish("apply_failed", msg)

    ok, sha = git_commit(summary, task_id, files)
    if not ok:
        git_reset(base)
        return finish("apply_failed", f"git commit 失败: {sha}")

    # 4) 受限区改动必须过校验门
    if needs_restart:
        rc, out = sh(["bash", os.path.join(ROOT, "deploy", "verify.sh")], cwd=ROOT, timeout=1800)
        if rc != 0:
            git_reset(base)
            return finish("verify_failed", out[-2000:])

    # 5) 切换并探活
    if needs_restart:
        ok, health = restart_container()
        if not ok:
            log(f"[{task_id}] 健康检查失败，开始回滚: {health}")
            git_reset(base)
            ok2, health2 = restart_container()
            if not ok2:
                return finish("health_failed", f"回滚后仍不健康，需人工介入: {health2}；新版本错误: {health}")
            return finish("health_failed", f"新版本不健康，已回滚到 {base[:10]}: {health}")

    # 6) 成功
    state["last_good"] = sha
    tag = f"good-{datetime.now():%Y%m%d_%H%M%S}"
    sh(["git", "tag", tag, sha], cwd=ROOT)
    sensitive = is_sensitive("\n".join(str(f.get("content") or "") for f in files))
    return finish("ok", f"commit={sha[:10]} tag={tag} 重启={needs_restart} 敏感={sensitive} 快照={os.path.basename(snap) if snap else '-'}", summary)


def scan_once():
    if not os.path.isdir(STAGING):
        return 0
    handled = 0
    for name in sorted(os.listdir(STAGING)):
        d = os.path.join(STAGING, name)
        req = os.path.join(d, "request.json")
        if not os.path.isdir(d) or not os.path.exists(req):
            continue
        if os.path.exists(os.path.join(d, "result.json")):
            continue
        handle_request(d)
        handled += 1
    return handled


def ensure_running():
    rc, out = sh(["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER], timeout=30)
    if rc != 0 or "true" not in out:
        log("生产容器未运行，启动中…")
        ok, health = restart_container()
        log(f"启动结果: {'健康' if ok else '异常: ' + str(health)}")
        if ok:
            rc2, sha = sh(["git", "rev-parse", "HEAD"], cwd=ROOT)
            state = load_state()
            if not state.get("last_good") and rc2 == 0:
                state["last_good"] = sha.strip()
                save_state(state)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="处理一轮后退出")
    args = parser.parse_args()

    os.makedirs(STAGING, exist_ok=True)
    log("supervisor 启动，监听 staging/*/request.json")
    ensure_running()
    if args.once:
        n = scan_once()
        log(f"处理了 {n} 个请求")
        return
    while True:
        try:
            n = scan_once()
            if n:
                log(f"本轮处理了 {n} 个请求")
        except Exception as e:
            log(f"轮询异常: {e}")
        time.sleep(3)


if __name__ == "__main__":
    main()
