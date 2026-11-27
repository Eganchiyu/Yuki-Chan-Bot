#!/usr/bin/env python3
"""Yuki 小女仆的 harness 执行器（跑在宿主机，不进容器）。

为什么要在宿主：
    - 容器是 python:3.11-slim，没有 node，装进去会白白把镜像撑大；
    - 凭证在宿主的 ~/.dsh 里，不用往容器里塞 API key；
    - harness 的沙箱全放行只影响本进程拉起的 dsh 子进程，边界清楚。

协议（和 Yuki 容器之间只通过文件说话，两边都不需要端口）：
    <ROOT>/tasks/dsh/<task_id>/request.json   容器写：{goal, session_id?, timeout_s?}
    <ROOT>/tasks/dsh/<task_id>/events.jsonl   本进程写：dsh --json 的原始事件，逐行追加
    <ROOT>/tasks/dsh/<task_id>/result.json    本进程写：{status, result, session_id, ...}
    <ROOT>/tasks/dsh/<task_id>/stderr.log     本进程写：诊断输出
    <ROOT>/tasks/dsh/<task_id>/cancel.request 容器写：取消标记，见到即杀掉 dsh 进程组

约定：
    - 并发池（默认 3，按 YUKI_MAID_CONCURRENCY 调）：每个任务一个线程，
      队列里的任务不会被一个长任务堵死。
    - request.json 是「原子文件」：容器用 tmp+rename 写，本进程看到即完整。
    - result.json 同理由 tmp+rename 写出，容器不会读到半截。
    - 取消是硬中断：启动前见到 cancel.request 就直接落 cancelled 结果不拉起进程；
      跑的过程中每 0.5s 查一次，见到就 SIGKILL 整个进程组。

用法:
    python3 deploy/maid_runner.py            # 前台守护
    python3 deploy/maid_runner.py --once     # 处理最多一个任务就退出（调试用）
"""
import argparse
import json
import os
import re
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime

ROOT = os.environ.get("YUKI_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TASKS = os.path.join(ROOT, "tasks", "dsh")
WORKSPACE = os.path.join(ROOT, "workspace")
LOGS = os.path.join(ROOT, "logs")
DSH_HOME = os.environ.get("YUKI_DSH_HOME", os.path.join(ROOT, "deploy", "dsh-home"))
DSH_BIN = os.environ.get(
    "YUKI_DSH_BIN", os.path.join(ROOT, "deploy", "dsh-runtime", "node_modules", ".bin", "dsh")
)
PROFILE = os.environ.get("YUKI_MAID_PROFILE", "yuki-maid")
# 单任务硬上限（机主 2026-11-12 指定 600s）：容器侧请求带 timeout_s=480，
# 这里同时压住默认值与最大可申请值，防止绕过容器侧的预算。
DEFAULT_TIMEOUT = int(os.environ.get("YUKI_MAID_TIMEOUT", "600"))
MAX_TIMEOUT = int(os.environ.get("YUKI_MAID_MAX_TIMEOUT", "600"))
POLL_SECONDS = float(os.environ.get("YUKI_MAID_POLL", "2"))
# 同时在跑的小女仆任务数（与容器侧 core/maid/maid_common.py 的 MAID_MAX_CONCURRENT 对齐）
MAX_CONCURRENT = max(1, int(os.environ.get("YUKI_MAID_CONCURRENCY", "3")))
# 跑的过程中多久查一次取消标记 / 超时
RUN_POLL_SECONDS = float(os.environ.get("YUKI_MAID_RUN_POLL", "0.5"))
CANCEL_FILE = "cancel.request"
RUN_LOG = os.path.join(LOGS, "maid_runner.log")
CREDENTIALS = os.path.expanduser("~/.dsh/.credentials.yaml")
# 结论文本上限：报告要进 Yuki 的记忆流，不能被一次超长输出淹掉
RESULT_MAX_CHARS = 12000


def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    try:
        with open(RUN_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def write_json_atomic(path, payload):
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


_MOUNTED_PREFIXES = tuple(
    os.path.join(ROOT, d) + os.sep
    for d in ("data", "output", "temp", "workspace", "temp_images")
)
_SYS_PREFIXES = ("/usr/", "/etc/", "/bin/", "/sbin/", "/lib/", "/var/", "/proc/", "/sys/", "/dev/")
_ARTIFACT_PATH_RE = re.compile(r"(?:file://)?((?:/|~/)[A-Za-z0-9_.\-/~]+)")


def _collect_unmounted_artifacts(text, max_bytes=200 * 1024 * 1024):
    """将小女仆结果中提及的宿主机未挂载文件复制到 data/inbox/，确保容器内 Yuki 可直接发送。"""
    if not text:
        return []
    inbox_dir = os.path.join(ROOT, "data", "inbox")
    synced = []
    seen = set()
    for raw in _ARTIFACT_PATH_RE.findall(str(text)):
        p = raw.rstrip(".,;:!?\"'`).")
        if not p or p in seen:
            continue
        seen.add(p)
        abs_p = os.path.abspath(os.path.expanduser(p))
        if abs_p.startswith(_SYS_PREFIXES) or abs_p.startswith(_MOUNTED_PREFIXES):
            continue
        if abs_p.startswith(os.path.join(ROOT, "core") + os.sep) or abs_p.startswith(os.path.join(ROOT, "deploy") + os.sep):
            continue
        if not os.path.isfile(abs_p):
            continue
        try:
            st = os.stat(abs_p)
        except OSError:
            continue
        if st.st_size <= 0 or st.st_size > max_bytes:
            continue
        dst = os.path.join(inbox_dir, os.path.basename(abs_p))
        try:
            os.makedirs(inbox_dir, exist_ok=True)
            if not (os.path.isfile(dst) and os.path.getsize(dst) == st.st_size and os.path.getmtime(dst) >= st.st_mtime):
                shutil.copy2(abs_p, dst)
            synced.append(dst)
        except OSError as e:
            log(f"收集产物失败 {abs_p} -> {dst}: {e}")
    return synced


def _sync_host_inbox():
    """触发一次宿主机 inbox（host_inbox / /tmp/yuki_outbox）向 data/inbox 的同步。"""
    try:
        import inbox_sync
        inbox_sync.sync(log=log)
    except Exception:
        pass


def read_api_key():
    """优先用环境变量；否则从 dsh 的凭证文件里取（不落日志、不进 argv）。"""
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    try:
        with open(CREDENTIALS, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"\s*DEEPSEEK_API_KEY:\s*(\S+)\s*$", line)
                if m:
                    return m.group(1).strip().strip("'\"")
    except OSError:
        pass
    return ""


def child_env(api_key):
    env = os.environ.copy()
    env["DSH_HOME"] = DSH_HOME
    if api_key:
        env["DEEPSEEK_API_KEY"] = api_key
    # 容器里跑的都是本地服务，别让代理把 loopback 请求带出去
    env.setdefault("NO_PROXY", "127.0.0.1,localhost")
    return env


class TaskRunner:
    def __init__(self, task_dir, api_key):
        self.dir = task_dir
        self.task_id = os.path.basename(task_dir.rstrip("/"))
        self.api_key = api_key
        self.events_path = os.path.join(task_dir, "events.jsonl")
        self.result_path = os.path.join(task_dir, "result.json")
        self.stderr_path = os.path.join(task_dir, "stderr.log")
        self.workdir = os.path.join(WORKSPACE, f"dsh_{self.task_id}")
        self.session_id = None
        self.tools = []
        self.last_texts = []      # 过程中的 assistant 文本，超时时当部分结论用
        self.last_args = {}
        self.steps = 0
        self.final_text = ""
        self.stopped = False

    @property
    def cancel_path(self):
        return os.path.join(self.dir, CANCEL_FILE)

    def cancel_requested(self):
        """Yuki 叫停了没？取消标记是幂等的，看到就杀。"""
        return os.path.exists(self.cancel_path)

    # ---- 收尾 ----
    def partial_summary(self):
        """没拿到 final 时，至少告诉 Yuki 它做到哪、被什么卡住。"""
        bits = []
        if self.last_texts:
            bits.append("最后的话：" + self.last_texts[-1][:600])
        if self.last_args:
            bits.append(f"最后一个动作：{self.last_args.get('tool')}"
                        f"({str(self.last_args.get('input'))[:300]})")
        if self.tools:
            bits.append(f"共 {self.steps} 步，工具序列（尾段）：{self.tools[-6:]}")
        return "\n".join(bits)

    def finish(self, status, detail, started):
        text = self.final_text
        if not text and status != "finished":
            # 超时/崩溃时 final 往往是空的；丢掉全部进度等于白跑，这里拼个部分结论
            summary = self.partial_summary()
            text = f"[任务未完成：{status}] {detail}\n{summary}".strip()
        inbox_files = _collect_unmounted_artifacts(text)
        _sync_host_inbox()
        payload = {
            "status": status,
            "result": (text or detail or "")[:RESULT_MAX_CHARS],
            "detail": str(detail or "")[-3000:],
            "session_id": self.session_id or "",
            "task_id": self.task_id,
            "steps": self.steps,
            "tools": self.tools[-40:],
            "elapsed": round(time.time() - started, 1),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }
        if inbox_files:
            payload["inbox_files"] = inbox_files
            log(f"[{self.task_id}] 同步宿主机产物到 data/inbox: {inbox_files}")
        write_json_atomic(self.result_path, payload)
        log(f"[{self.task_id}] {status}: {payload['elapsed']}s / {self.steps} 步 / "
            f"工具 {self.tools[-5:] or '-'} / {payload['result'][:160]!r}")
        return payload

    def handle_event(self, line):
        """解析一行事件，累积进度并原样落盘（落盘由调用方负责）。"""
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            return
        kind = ev.get("type")
        if kind == "session":
            self.session_id = ev.get("sessionId") or self.session_id
        elif kind == "status" and ev.get("phase") == "step_start":
            self.steps = max(self.steps, int(ev.get("step") or 0))
        elif kind == "text":
            text = (ev.get("text") or "").strip()
            if text:
                self.last_texts.append(text[:1500])
                self.last_texts = self.last_texts[-5:]
        elif kind == "tool_call":
            name = ev.get("tool")
            if name:
                self.tools.append(name)
                self.last_args = {"tool": name, "input": ev.get("input")}
        elif kind == "final":
            self.final_text = ev.get("text") or self.final_text
        elif kind == "turn_end":
            reason = ev.get("reason") or {}
            if reason.get("kind") == "error":
                err = reason.get("error") or {}
                self.final_text = self.final_text or f"[harness 报错] {err.get('message') or err}"

    def run(self, request):
        goal = str(request.get("goal") or "").strip()
        if not goal:
            return self.finish("failed", "request.json 缺少 goal", time.time())

        timeout_s = request.get("timeout_s") or DEFAULT_TIMEOUT
        try:
            timeout_s = min(int(timeout_s), MAX_TIMEOUT)
        except (TypeError, ValueError):
            timeout_s = DEFAULT_TIMEOUT

        if self.cancel_requested():
            return self.finish("cancelled", "启动前已被 Yuki 叫停", time.time())

        os.makedirs(self.workdir, exist_ok=True)
        args = [DSH_BIN, "--profile", PROFILE, "--json"]
        resume = str(request.get("session_id") or "").strip()
        if resume:
            args += ["--session-id", resume]
            log(f"[{self.task_id}] 续做已有 session {resume}")
        # 任务走 stdin（`-`）：goal 可能很长，避免 argv 长度限制
        args.append("-")

        log(f"[{self.task_id}] 启动: {goal[:120]}（cwd={self.workdir}, 上限 {timeout_s}s）")
        started = time.time()
        try:
            proc = subprocess.Popen(
                args,
                cwd=self.workdir,
                env=child_env(self.api_key),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=open(self.stderr_path, "w", encoding="utf-8"),
                text=True,
                bufsize=1,
                start_new_session=True,  # 超时能连子进程树一起收掉
            )
        except OSError as e:
            return self.finish("failed", f"无法启动 dsh: {e}", started)

        # 任务正文 + 结束 stdin
        try:
            proc.stdin.write(goal + "\n")
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass  # 进程早期失败时由下面的退出码解释

        timed_out = False
        cancelled = False
        evf = open(self.events_path, "a", encoding="utf-8")
        try:
            assert proc.stdout is not None
            # 读线程 + 队列：主循环才能在等事件的同时定期检查超时与取消标记
            lines: queue.Queue = queue.Queue()

            def _pump(stream):
                try:
                    for raw in stream:
                        lines.put(raw)
                except (OSError, ValueError):
                    pass
                finally:
                    lines.put(None)

            threading.Thread(target=_pump, args=(proc.stdout,), daemon=True).start()
            while True:
                try:
                    raw = lines.get(timeout=RUN_POLL_SECONDS)
                except queue.Empty:
                    if self.cancel_requested():
                        cancelled = True
                        self._kill(proc)
                        break
                    if time.time() - started > timeout_s:
                        timed_out = True
                        self._kill(proc)
                        break
                    continue
                if raw is None:
                    break
                line = raw.rstrip("\n")
                if line:
                    evf.write(line + "\n")
                    evf.flush()
                    self.handle_event(line)
                if self.cancel_requested():
                    cancelled = True
                    self._kill(proc)
                    break
                if time.time() - started > timeout_s:
                    timed_out = True
                    self._kill(proc)
                    break
        finally:
            evf.close()

        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self._kill(proc)

        elapsed = time.time() - started
        if cancelled:
            return self.finish(
                "cancelled", f"被 Yuki 叫停，已强制终止（进度：{self.steps} 步）", started
            )
        if timed_out:
            return self.finish(
                "timeout", f"超过 {timeout_s}s 上限，已终止（进度：{self.steps} 步）", started
            )
        if proc.returncode != 0:
            tail = self._stderr_tail()
            # 有 final 文本就还算部分成功：模型可能已经给结论，只是进程非零退出
            if self.final_text:
                return self.finish("finished", f"退出码 {proc.returncode}：{tail}", started)
            return self.finish("failed", f"退出码 {proc.returncode}：{tail}", started)
        if not self.final_text:
            return self.finish("failed", "进程正常退出但没有 final 结论", started)
        return self.finish("finished", f"耗时 {elapsed:.1f}s", started)

    def _kill(self, proc):
        self.stopped = True
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass

    def _stderr_tail(self, limit=1200):
        try:
            with open(self.stderr_path, encoding="utf-8", errors="replace") as f:
                return f.read()[-limit:].strip()
        except OSError:
            return ""


def peek_request(task_dir):
    path = os.path.join(task_dir, "request.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def claim_task():
    """认领一个待办任务，返回 (task_dir, request) 或 None。

    认领成功会占住 running.lock，保证并发池里不会有两个线程抢同一个任务。
    """
    if not os.path.isdir(TASKS):
        return None
    for name in sorted(os.listdir(TASKS)):
        d = os.path.join(TASKS, name)
        if not os.path.isdir(d):
            continue
        # 已出结果或正在跑的任务跳过
        if os.path.exists(os.path.join(d, "result.json")) or os.path.exists(
            os.path.join(d, "running.lock")
        ):
            continue
        req = peek_request(d)
        if req is None:
            continue  # 写了一半（理论上不会，容器是原子写），下轮再看
        if os.path.exists(os.path.join(d, CANCEL_FILE)):
            # 还没开跑就被叫停：落个结论就完事，不浪费一次 dsh 拉起
            log(f"[{name}] 启动前已被叫停，跳过")
            write_json_atomic(
                os.path.join(d, "result.json"),
                {
                    "status": "cancelled",
                    "result": "任务在启动前被 Yuki 叫停",
                    "task_id": name,
                    "steps": 0,
                    "finished_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
            continue

        lock = os.path.join(d, "running.lock")
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {datetime.now().isoformat()}\n".encode())
            os.close(fd)
        except FileExistsError:
            continue
        return d, req
    return None


def run_claimed(task_dir, request, api_key):
    """在独立线程里跑一个已认领的任务（并发池的 worker）。"""
    name = os.path.basename(task_dir.rstrip("/"))
    try:
        os.makedirs(LOGS, exist_ok=True)
        TaskRunner(task_dir, api_key).run(request)
    except Exception as e:  # 单任务异常不能带崩守护进程
        log(f"[{name}] 执行异常: {e}")
        write_json_atomic(
            os.path.join(task_dir, "result.json"),
            {
                "status": "failed",
                "result": f"执行器异常：{e}",
                "task_id": name,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            },
        )
    finally:
        try:
            os.unlink(os.path.join(task_dir, "running.lock"))
        except OSError:
            pass


def scan_once(api_key):
    """处理一个待办任务。返回 True 表示干过活（调试/--once 用）。"""
    claimed = claim_task()
    if claimed is None:
        return False
    run_claimed(claimed[0], claimed[1], api_key)
    return True


def main():
    ap = argparse.ArgumentParser(description="Yuki 小女仆 harness 执行器")
    ap.add_argument("--once", action="store_true", help="最多处理一个任务就退出")
    ap.add_argument("--print-env", action="store_true", help="打印解析出的配置后退出（不打印 key）")
    args = ap.parse_args()

    api_key = read_api_key()
    if args.print_env:
        print(f"ROOT={ROOT}")
        print(f"DSH_BIN={DSH_BIN} exists={os.path.exists(DSH_BIN)}")
        print(f"DSH_HOME={DSH_HOME} exists={os.path.exists(DSH_HOME)}")
        print(f"PROFILE={PROFILE}  TIMEOUT={DEFAULT_TIMEOUT}s")
        print(f"api_key={'yes(env)' if os.environ.get('DEEPSEEK_API_KEY') else ('yes(file)' if api_key else 'MISSING')}")
        return 0 if os.path.exists(DSH_BIN) else 1

    if not api_key:
        log("警告：找不到 DEEPSEEK_API_KEY（环境变量与 ~/.dsh/.credentials.yaml 都没有），"
            "启动的 dsh 会直接报 MISSING_CREDENTIAL")
    if not os.path.exists(DSH_BIN):
        log(f"致命：找不到 dsh 可执行文件 {DSH_BIN}（在 deploy/dsh-runtime 里 npm install）")
        return 1

    os.makedirs(TASKS, exist_ok=True)
    os.makedirs(WORKSPACE, exist_ok=True)
    os.makedirs(LOGS, exist_ok=True)
    log(f"小女仆执行器启动：profile={PROFILE} 轮询 {TASKS} "
        f"(every {POLL_SECONDS}s, 最多 {MAX_CONCURRENT} 个并行)")

    if args.once:
        scan_once(api_key)
        return 0
    workers: list = []
    while True:
        try:
            workers = [w for w in workers if w.is_alive()]
            spawned = False
            while len(workers) < MAX_CONCURRENT:
                claimed = claim_task()
                if claimed is None:
                    break
                worker = threading.Thread(
                    target=run_claimed, args=(claimed[0], claimed[1], api_key), daemon=True
                )
                worker.start()
                workers.append(worker)
                spawned = True
            if not spawned:
                time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            log("收到中断，退出")
            return 0
        except Exception as e:
            log(f"主循环异常: {e}")
            time.sleep(max(POLL_SECONDS, 5))


if __name__ == "__main__":
    sys.exit(main())
