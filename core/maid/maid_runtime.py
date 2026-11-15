"""小女仆任务运行时登记表：会话内编号、并行执行、强制叫停。

为什么要单独一张表：
    maid_worker 原来是串行队列，任务在跑的时候 Yuki 既看不到编号也叫不停。
    并行之后「谁在跑、要停哪一个」必须有唯一事实源，这里就是那个事实源。

叫停是两段式：
    1. 容器侧：取消正在等结果的协程（asyncio.Task.cancel），并把状态改成 cancelling；
    2. 宿主侧：往 tasks/dsh/<task_id>/cancel.request 落一个标记，
       deploy/maid_runner.py 见到就把 dsh 子进程组 SIGKILL 掉。

叫停成功不汇报：被取消的任务不写会话历史，同时打上 reported.ok 标记，
让重启补报巡检（maid_resume）也不要再把它当「已完成但未汇报」捡出来。
"""
import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from core.maid.maid_common import logger

# 还在做（含排队等并发位）的状态；其它状态都算已结束
ACTIVE_STATUSES = ("queued", "running", "cancelling")
# 注入上下文的提示里最多列几个任务，避免刷屏
SUMMARY_MAX_TASKS = 4
LABEL_GOAL_CHARS = 24


@dataclass
class MaidTaskRecord:
    """一个小女仆任务的运行时元数据（不进历史、不落盘）。"""

    uid: str
    goal: str
    chat_id: str
    mode: str = "group"
    source: str = "yuki"
    status: str = "queued"          # queued / running / cancelling / cancelled / done
    seq: int = 0                    # 会话内编号，展示给 Yuki 用（#1、#2 ...）
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    dsh_task_id: str = ""           # 宿主 runner 的任务目录名，harness 启动后回填
    cancel_requested: bool = False
    handler: Any = None             # 容器侧等待协程（asyncio.Task）
    tool_calls: list = field(default_factory=list)

    @property
    def short_id(self) -> str:
        return f"#{self.seq}" if self.seq else ""

    @property
    def active(self) -> bool:
        return self.status in ACTIVE_STATUSES

    def label(self) -> str:
        goal = (self.goal or "").strip().replace("\n", " ")
        if len(goal) > LABEL_GOAL_CHARS:
            goal = goal[:LABEL_GOAL_CHARS] + "…"
        return f"{self.short_id}「{goal}」" if self.short_id else f"「{goal}」"


class MaidRuntime:
    """会话维度的小女仆任务登记表。"""

    def __init__(self):
        self._records: dict[str, MaidTaskRecord] = {}
        self._seq: dict[str, int] = {}

    # ---- 登记 ----
    def register(self, goal: str, chat_id: str, mode: str = "group", source: str = "yuki") -> MaidTaskRecord:
        cid = str(chat_id)
        uid = f"m{uuid.uuid4().hex[:10]}"
        seq = int(self._seq.get(cid, 0)) + 1
        self._seq[cid] = seq
        record = MaidTaskRecord(
            uid=uid, goal=str(goal or ""), chat_id=cid, mode=str(mode or "group"), source=source, seq=seq
        )
        self._records[uid] = record
        return record

    def get(self, uid: str) -> MaidTaskRecord | None:
        return self._records.get(uid) if uid else None

    def attach_handler(self, uid: str, handler) -> None:
        record = self.get(uid)
        if record is not None:
            record.handler = handler

    def publish_dsh_task(self, uid: str, dsh_task_id: str) -> None:
        """harness 拿到宿主任务目录名后回填，叫停时要靠它落 cancel.request。"""
        record = self.get(uid)
        if record is not None and dsh_task_id:
            record.dsh_task_id = str(dsh_task_id)

    def mark(self, uid: str, status: str) -> None:
        record = self.get(uid)
        if record is None:
            return
        record.status = status
        if status == "running" and not record.started_at:
            record.started_at = time.time()

    def remove(self, uid: str) -> None:
        self._records.pop(uid, None)

    # ---- 查询 ----
    def active_for_chat(self, chat_id: str) -> list:
        cid = str(chat_id)
        return [r for r in self._records.values() if r.chat_id == cid and r.active]

    def active_all(self) -> list:
        return [r for r in self._records.values() if r.active]

    def live_for_chat(self, chat_id: str) -> list:
        """还在跑、还没被叫停的任务（正在收尾的 cancelling 不算）。"""
        return [r for r in self.active_for_chat(chat_id) if not r.cancel_requested]

    def running_count(self) -> int:
        """真正在跑的（不含排队等并发位的）。"""
        return len([r for r in self._records.values() if r.status == "running"])

    def find(self, chat_id: str, task_id: str = "", keyword: str = "") -> tuple[list, list]:
        """按编号/关键词挑选本会话的任务，返回 (命中, 本会话在跑的全部)。"""
        active = self.active_for_chat(chat_id)
        wanted = str(task_id or "").strip().lstrip("#").lower()
        kw = str(keyword or "").strip().lower()
        if not wanted and not kw:
            return list(active), active
        matched = []
        for record in active:
            if wanted and not (
                str(record.seq) == wanted
                or record.uid.lower() == wanted
                or (record.dsh_task_id and record.dsh_task_id.lower() == wanted)
            ):
                continue
            if kw and kw not in record.goal.lower():
                continue
            matched.append(record)
        return matched, active

    def summary_for_chat(self, chat_id: str) -> str:
        """给上下文注入用的一句话（没有在跑的任务时返回空串）。"""
        active = self.live_for_chat(chat_id)
        if not active:
            return ""
        items = [record.label() for record in sorted(active, key=lambda r: r.seq)]
        extra = len(items) - SUMMARY_MAX_TASKS
        text = "、".join(items[:SUMMARY_MAX_TASKS])
        if extra > 0:
            text += f" 等 {len(items)} 个"
        return (
            f"【任务进行中】小女仆 {text} 还在后台干活，还没汇报，不要催也不用手动查进度；"
            "要叫停就用 stop_maid。\n"
        )

    # ---- 叫停 ----
    def request_cancel(self, records: list) -> list:
        """强制叫停：落宿主取消标记 + 取消容器侧协程，返回被叫停任务的可读标签。"""
        labels = []
        for record in records:
            if not record.active:
                continue
            record.cancel_requested = True
            record.status = "cancelling"
            if record.dsh_task_id and _mark_host_cancel(record.dsh_task_id):
                logger.info(f"[Maid] 已通知宿主终止 {record.dsh_task_id}（{record.label()}）")
            handler = record.handler
            if handler is not None and hasattr(handler, "done") and not handler.done():
                handler.cancel()
            labels.append(record.label())
            logger.info(f"[Maid] 叫停 {record.chat_id} {record.label()}（dsh={record.dsh_task_id or '-'}）")
        return labels


def _mark_host_cancel(dsh_task_id: str) -> bool:
    """给宿主 runner 落取消标记，并标记「不用汇报」，避免补报巡检再播一遍。"""
    from core.maid.maid_harness import write_cancel_request
    from core.maid.maid_resume import mark_reported

    ok = write_cancel_request(dsh_task_id)
    mark_reported(dsh_task_id)
    return ok


def runtime_of(yuki) -> MaidRuntime:
    """取（必要时给 yuki_state 挂一个）运行时登记表，兼容没有该字段的测试替身。"""
    runtime = getattr(yuki, "maid_runtime", None)
    if isinstance(runtime, MaidRuntime):
        return runtime
    runtime = MaidRuntime()
    try:
        yuki.maid_runtime = runtime
    except Exception:  # 只读替身等极端情况：退化成一次性表
        pass
    return runtime
