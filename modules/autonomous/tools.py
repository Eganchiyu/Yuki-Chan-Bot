# modules/autonomous/tools.py
"""沙盒专属工具：投票、复盘落盘、工作会话读写、工坊收尾。

这些工具**不注册进主 registry**（见 docs/autonomous-sandbox-plan.md §2.1），
只在沙盒自建的 registry 里出现，因此不会污染群聊模式的工具空间。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.toolchain import FunctionRegistry, ToolResult, ToolSpec
from modules.autonomous.storage import (
    WORK_LOG_MAX_CHARS,
    daily_memory_store,
    group_name_cache,
    memo_store,
    truncate_chars,
    work_diary_store,
    work_session_store,
)
from utils.logger import get_logger

logger = get_logger("autonomous.tools")

VERDICTS = ("start_work", "memo_only", "do_nothing")
REFLECTION_ACTIONS = ("start_work", "memo_only", "abandon")
SANDBOX_TOOL_NAMES = frozenset({
    "inner_vote",
    "conclude_reflection",
    "list_recent_work_sessions",
    "inspect_work_session",
    "write_work_diary",
    "work_finish",
})


@dataclass
class SandboxState:
    """一次沙盒运行的共享状态，工具与循环共同读写。"""

    run_id: str
    chat_id: str
    phase: str = "debate"
    session_id: str = ""
    votes: list[dict] = field(default_factory=list)
    reflection: dict | None = None
    work_log: str = ""
    artifacts: list[str] = field(default_factory=list)
    finished: bool = False
    finish_status: str = ""
    tool_calls: int = 0
    notes: list[str] = field(default_factory=list)

    # -- 投票 --
    def record_vote(self, role: str, agree: bool, verdict: str, note: str = "") -> dict:
        record = {
            "role": str(role),
            "agree": bool(agree),
            "verdict": str(verdict),
            "note": str(note or ""),
        }
        self.votes.append(record)
        return record

    def consensus(self) -> dict | None:
        """连续两步 agree + verdict 一致才算收敛。"""
        if len(self.votes) < 2:
            return None
        last, prev = self.votes[-1], self.votes[-2]
        if not (last["agree"] and prev["agree"]):
            return None
        if last["verdict"] != prev["verdict"]:
            return None
        return {"verdict": last["verdict"], "note": last["note"] or prev["note"]}


def _state_of(context) -> SandboxState | None:
    state = (context.metadata or {}).get("sandbox")
    return state if isinstance(state, SandboxState) else None


def current_role(context) -> str:
    return str((context.metadata or {}).get("debate_role") or "")


# ---------------------------------------------------------------- 投票

async def inner_vote_tool(context, agree_to_end: bool = False, verdict: str = "do_nothing",
                          consensus_note: str = ""):
    state = _state_of(context)
    role = current_role(context) or "?"
    if verdict not in VERDICTS:
        return ToolResult.failure(
            f"verdict 必须是 {VERDICTS} 之一", "invalid_verdict", name="inner_vote",
        )
    record = state.record_vote(role, bool(agree_to_end), verdict, consensus_note) if state else {}
    if not agree_to_end:
        hint = "已记录：你还想继续讨论，投票计数器清零。"
    else:
        consensus = state.consensus() if state else None
        if consensus:
            hint = f"双方已就「{consensus['verdict']}」达成一致，思考轮次结束。"
        else:
            hint = "已记录结束意愿，等待另一个念头也投票同意且结论一致。"
    logger.info(f"[Sandbox] inner_vote role={role} agree={agree_to_end} verdict={verdict} {consensus_note[:60]}")
    return ToolResult(success=True, content=f"{hint}", data={"vote": record,
                                                            "consensus": state.consensus() if state else None},
                      name="inner_vote")


# ---------------------------------------------------------------- 复盘落盘

async def conclude_reflection_tool(context, action: str = "memo_only", title: str = "",
                                   memo_content: str = "", work_diary_entry: str = "",
                                   notebook_pointer: str = ""):
    state = _state_of(context)
    if action not in REFLECTION_ACTIONS:
        return ToolResult.failure(
            f"action 必须是 {REFLECTION_ACTIONS} 之一", "invalid_action", name="conclude_reflection",
        )
    payload = {
        "action": action,
        "title": str(title or "").strip(),
        "memo_content": str(memo_content or "").strip(),
        "work_diary_entry": str(work_diary_entry or "").strip(),
        "notebook_pointer": str(notebook_pointer or "").strip(),
    }
    if state is not None:
        state.reflection = payload
    logger.info(f"[Sandbox] conclude_reflection action={action} title={payload['title']}")
    return ToolResult(
        success=True,
        content=f"复盘已记录（action={action}）。",
        data=payload,
        name="conclude_reflection",
    )


# ---------------------------------------------------------------- 工作会话

async def list_recent_work_sessions_tool(context, limit: int = 5, status: str = ""):
    rows = work_session_store.list(status=status or None, limit=min(max(int(limit or 5), 1), 20))
    if not rows:
        return ToolResult(success=True, content="还没有未完成或已完成的工作档案。",
                          data={"sessions": []}, name="list_recent_work_sessions")
    lines = []
    for row in rows:
        lines.append(
            f"- {row.get('session_id')} [{row.get('status')}] {row.get('title') or '(无题)'}"
            f" | 进度：{row.get('log_head') or '(无日志)'}"
        )
    return ToolResult(
        success=True,
        content="近期工作会话：\n" + "\n".join(lines),
        data={"sessions": rows},
        name="list_recent_work_sessions",
    )


async def inspect_work_session_tool(context, session_id: str = ""):
    record = work_session_store.load(str(session_id)) if session_id else None
    if record is None:
        return ToolResult.failure("找不到这个工作会话", "session_not_found",
                                  name="inspect_work_session")
    content = (
        f"#{record.get('session_id')} 《{record.get('title') or '无题'}》"
        f"状态={record.get('status')} 类型={record.get('kind')}\n"
        f"产物：{', '.join(record.get('artifacts') or []) or '(暂无)'}\n"
        f"工作日志（≤{WORK_LOG_MAX_CHARS} 字）：\n{record.get('work_log') or '(空)'}"
    )
    return ToolResult(success=True, content=content, data=record, name="inspect_work_session")


async def write_work_diary_tool(context, content: str = "", title: str = "", kind: str = "insight"):
    state = _state_of(context)
    chat_id = getattr(context, "chat_id", "")
    record = work_diary_store.append(
        session_id=state.session_id if state else "",
        title=str(title or ""),
        kind=str(kind or "insight"),
        content=str(content or ""),
        chat_id=chat_id,
    )
    return ToolResult(
        success=True,
        content=f"已记进工作日记本（{len(record['content'])} 字）。",
        data={"work_diary": record},
        name="write_work_diary",
    )


# ---------------------------------------------------------------- 工坊收尾

async def work_finish_tool(context, status: str = "completed", work_log: str = "",
                           artifacts: list[str] | None = None, title: str = ""):
    state = _state_of(context)
    if status not in ("completed", "paused"):
        return ToolResult.failure("status 只能是 completed / paused", "invalid_status",
                                  name="work_finish")
    text = str(work_log or "").strip()
    if not text:
        return ToolResult.failure(
            "work_log 不能为空：请写清楚这轮干了什么、产物路径、下次从哪接（≤512 字）。",
            "empty_work_log", name="work_finish",
        )
    truncated = len(text) > WORK_LOG_MAX_CHARS
    text = truncate_chars(text, WORK_LOG_MAX_CHARS)
    artifacts = [str(a) for a in (artifacts or []) if str(a).strip()]

    session_id = state.session_id if state and state.session_id else ""
    record = work_session_store.load(session_id) if session_id else None
    if record is None:
        session_id = work_session_store.new_session_id(getattr(context, "chat_id", ""))
        record = {
            "session_id": session_id,
            "title": str(title or "未命名工作"),
            "kind": "misc",
            "chat_id": str(getattr(context, "chat_id", "")),
        }
    record.update({
        "status": status,
        "work_log": text,
        "artifacts": artifacts or list(record.get("artifacts") or []),
    })
    if title:
        record["title"] = str(title)
    record = work_session_store.save(record)
    if state is not None:
        state.session_id = session_id
        state.work_log = text
        state.artifacts = list(record.get("artifacts") or [])
        state.finish_status = status
        state.finished = True

    logger.info(f"[Sandbox] work_finish {session_id} status={status} artifacts={len(artifacts)}")
    note = "（已按 512 字上限截断）" if truncated else ""
    return ToolResult(
        success=True,
        content=(
            f"工作日志已保存{note}，会话 {session_id} 状态={status}。"
            if status == "paused" else
            f"本轮工作已归档{note}，会话 {session_id} 完成。"
        ),
        data={"session_id": session_id, "status": status, "work_log": text,
              "artifacts": record.get("artifacts") or []},
        name="work_finish",
    )


# ---------------------------------------------------------------- 规格与注册

INNER_VOTE_SPEC = ToolSpec(
    name="inner_vote",
    description=(
        "投票是否结束这次独处思考。只有两个念头连续两次都投 agree_to_end=true "
        "且 verdict 完全一致时，思考才会真正结束。"
        "verdict=do_nothing 表示今天什么都不想做（安静退回群聊）；"
        "memo_only 表示写成一篇随想备忘录就好；start_work 表示想动手做点什么。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "agree_to_end": {"type": "boolean", "description": "是否认为可以结束思考了"},
            "verdict": {
                "type": "string",
                "enum": list(VERDICTS),
                "description": "结束后的去向：start_work / memo_only / do_nothing",
            },
            "consensus_note": {
                "type": "string",
                "description": "一句话写下你们的共识（想做什么、为什么、大概怎么做）",
            },
        },
        "required": ["agree_to_end", "verdict"],
    },
    handler=inner_vote_tool,
    persist_result=False,
)

CONCLUDE_REFLECTION_SPEC = ToolSpec(
    name="conclude_reflection",
    description=(
        "复盘落盘：决定这次独处思考的最终去向。"
        "abandon=算了，什么都不做，安静回群；memo_only=只写一篇思考备忘录取进日记库；"
        "start_work=写好备忘录后进入自己的工坊动手做。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": list(REFLECTION_ACTIONS),
                       "description": "最终去向"},
            "title": {"type": "string", "description": "给这次思考/作品起个短标题"},
            "memo_content": {"type": "string",
                             "description": "思考备忘录正文（第一人称，200~500 字，写清灵感来源与打算）"},
            "work_diary_entry": {"type": "string",
                                 "description": "可选：往工作日记本里再记一条 150~400 字的思考产物"},
            "notebook_pointer": {"type": "string",
                                 "description": "可选：写进小本本「长期规划路标区」的一句话（≤160 字）"},
        },
        "required": ["action", "title", "memo_content"],
    },
    handler=conclude_reflection_tool,
    persist_result=False,
)

LIST_WORK_SESSIONS_SPEC = ToolSpec(
    name="list_recent_work_sessions",
    description="列出近期的工作会话档案（标题、状态、进度摘要），用来接续之前没做完的事。",
    parameters={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "返回条数，默认 5，最多 20"},
            "status": {"type": "string", "enum": ["", "active", "paused", "completed"],
                       "description": "只看某个状态，留空看全部"},
        },
    },
    handler=list_recent_work_sessions_tool,
    persist_result=False,
)

INSPECT_WORK_SESSION_SPEC = ToolSpec(
    name="inspect_work_session",
    description="读取某个工作会话的 512 字工作日志与产物路径，用于跨轮接续任务。",
    parameters={
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "会话编号，如 sess_20261115_01"},
        },
        "required": ["session_id"],
    },
    handler=inspect_work_session_tool,
)

WRITE_WORK_DIARY_SPEC = ToolSpec(
    name="write_work_diary",
    description="往自己的工作日记本里追加一条记录（思考产物、灵感碎片、创作心得，150~400 字）。",
    parameters={
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "这轮的想法或创作心得"},
            "title": {"type": "string", "description": "短标题"},
            "kind": {"type": "string", "enum": ["insight", "creation", "plan", "misc"],
                     "description": "记录类型"},
        },
        "required": ["content"],
    },
    handler=write_work_diary_tool,
)

WORK_FINISH_SPEC = ToolSpec(
    name="work_finish",
    description=(
        "结束或暂停本轮工作，必须写 ≤512 字工作日志："
        "① 这一轮具体干了什么；② 产出了什么作品/文件及其完整路径；③ 下次从哪里接着做。"
        "随时可以 paused 暂停，下次凭 session_id 继续。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["completed", "paused"],
                       "description": "completed=这轮做完了；paused=先停在这儿留待下次"},
            "work_log": {"type": "string", "description": "≤512 字工作日志"},
            "artifacts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "产物路径列表，如 [\"workspace/novels/snow_radio_ch1.md\"]",
            },
            "title": {"type": "string", "description": "可选：这次工作的标题"},
        },
        "required": ["status", "work_log"],
    },
    handler=work_finish_tool,
    persist_result=False,
)

ALL_SANDBOX_SPECS = {
    "inner_vote": INNER_VOTE_SPEC,
    "conclude_reflection": CONCLUDE_REFLECTION_SPEC,
    "list_recent_work_sessions": LIST_WORK_SESSIONS_SPEC,
    "inspect_work_session": INSPECT_WORK_SESSION_SPEC,
    "write_work_diary": WRITE_WORK_DIARY_SPEC,
    "work_finish": WORK_FINISH_SPEC,
}


def build_registry(main_registry: Any, sandbox_names: list[str] | None = None,
                   main_tool_names: set[str] | None = None) -> FunctionRegistry:
    """用主 registry 的 spec 副本 + 沙盒工具组装一个独立 registry。"""
    registry = FunctionRegistry()
    for name in sorted(main_tool_names or set()):
        spec = main_registry.get_spec(name) if hasattr(main_registry, "get_spec") else None
        if spec is not None:
            registry.register(spec)
    for name in sandbox_names or []:
        spec = ALL_SANDBOX_SPECS.get(name)
        if spec is not None:
            registry.register(spec)
    return registry


def record_work_memory(state: SandboxState, reflection: dict, status: str = "可接续") -> None:
    """把本轮产出写进 L4 今日工作记忆（Phase 4 会常驻上下文）。"""
    summary = state.work_log or (reflection or {}).get("memo_content", "")
    if not summary:
        return
    daily_memory_store.add(
        summary=summary,
        status=status,
        session_id=state.session_id,
        artifacts=state.artifacts,
    )


def save_autonomous_memo(reflection: dict, chat_id, session_id: str, kind: str = "memo") -> str | None:
    """L1：把思考备忘录只追加写进日记库。"""
    content = (reflection or {}).get("memo_content", "")
    if not content:
        return None
    return memo_store.save_memo(
        content=content, chat_id=chat_id, session_id=session_id, kind=kind,
    )


def save_work_diary_entry(reflection: dict, chat_id, session_id: str) -> None:
    entry = (reflection or {}).get("work_diary_entry", "")
    if not entry:
        return
    work_diary_store.append(
        session_id=session_id,
        title=(reflection or {}).get("title", ""),
        kind="insight",
        content=entry,
        chat_id=chat_id,
    )


def group_label(chat_id) -> str:
    return group_name_cache.name(chat_id)
