# modules/autonomous/tools.py
"""沙盒专属工具：投票、复盘落盘、工作会话读写、工坊收尾。

这些工具**不注册进主 registry**（见 docs/autonomous-architecture.md §1、§3.5），
只在沙盒自建的 registry 里出现，因此不会污染群聊模式的工具空间。
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from core.toolchain import FunctionRegistry, ToolResult, ToolSpec
from modules.autonomous import corner_client
from modules.autonomous.inspiration import inspiration_store
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
    "publish_to_corner",
    "save_inspiration",
    "wait_maid_tasks",
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
    published_urls: list[str] = field(default_factory=list)
    seen_note_ids: list[int] = field(default_factory=list)
    finished: bool = False
    finish_status: str = ""
    tool_calls: int = 0
    notes: list[str] = field(default_factory=list)
    transcript: Any = None      # modules.autonomous.transcript.RunTranscript

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
                                   notebook_pointer: str = "", resume_session_id: str = ""):
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
        "resume_session_id": str(resume_session_id or "").strip(),
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


# ---------------------------------------------------------------- 展柜上架 / 采风剪贴 / 等待小女仆

async def publish_to_corner_tool(
    context,
    slug: str = "",
    title: str = "",
    kind: str = "toy",
    summary: str = "",
    entry_file: str = "",
    inline_content: str = "",
    inline_filename: str = "",
    cover_file: str = "",
    extra_files: list[str] | None = None,
    notes: str = "",
    tags: list[str] | None = None,
    fulfilled_note_ids: list[int] | None = None,
    visibility: str = "public",
):
    state = _state_of(context)
    chat_id = str(getattr(context, "chat_id", "") or "")
    session_id = state.session_id if state else ""
    clean_title = str(title or "").strip()
    if not clean_title:
        return ToolResult.failure("title 不能为空：请给展品起个好听的名字", "empty_title", name="publish_to_corner")
    try:
        res = await corner_client.publish_work(
            slug=slug or clean_title,
            title=clean_title,
            kind=kind,
            summary=summary,
            notes=notes,
            entry_file=entry_file,
            inline_content=inline_content,
            inline_filename=inline_filename,
            cover_file=cover_file,
            extra_files=extra_files,
            tags=tags,
            fulfilled_note_ids=fulfilled_note_ids,
            session_id=session_id,
            source_chat=chat_id,
            visibility=visibility,
        )
    except Exception as exc:
        logger.warning(f"[Sandbox] publish_to_corner 失败: {exc}")
        return ToolResult.failure(f"上架展柜失败：{exc}", "publish_failed", name="publish_to_corner")

    page_url = str(res.get("page_url") or "")
    local_path = str(res.get("local_path") or "")
    if state is not None:
        if page_url and page_url not in state.published_urls:
            state.published_urls.append(page_url)
        for item in (page_url, local_path):
            if item and item not in state.artifacts:
                state.artifacts.append(item)
        state.notes.append(f"上架展柜《{clean_title}》{page_url or local_path}")
    if res.get("published_remote") and page_url:
        vis_hint = "（私藏 unlisted，仅持链接可见）" if visibility == "unlisted" else "（已公开展示在首页）"
        content = (
            f"作品《{clean_title}》已成功上架到 Yuki's Corner {vis_hint}！\n"
            f"公网分享链接：{page_url}\n"
            f"包含文件：{', '.join(res.get('files') or [])}\n"
            "记住把这个链接写进 work_finish 的 work_log 和 artifacts，回群就能分享给大家玩啦！"
        )
    else:
        content = f"作品《{clean_title}》已保存在本地：{local_path}（{res.get('message') or '未配置远端展柜'}）。"
    return ToolResult(success=True, content=content, data=res, name="publish_to_corner")


async def save_inspiration_tool(
    context,
    title: str = "",
    snippet: str = "",
    source_url: str = "",
    tags: list[str] | None = None,
):
    clean_title = str(title or "").strip()
    clean_snippet = str(snippet or "").strip()
    if not clean_title or not clean_snippet:
        return ToolResult.failure("title 和 snippet 都不能为空", "empty_inspiration", name="save_inspiration")
    record = inspiration_store.add(
        title=clean_title,
        snippet=clean_snippet,
        source_url=source_url,
        tags=tags,
        chat_id=str(getattr(context, "chat_id", "") or ""),
    )
    state = _state_of(context)
    if state is not None:
        state.notes.append(f"剪贴灵感《{clean_title}》")
    return ToolResult(
        success=True,
        content=f"已把灵感《{clean_title}》夹进好奇心剪贴簿（id={record['id']}），以后独处时会重新翻出来发酵！",
        data={"inspiration": record},
        name="save_inspiration",
    )


async def wait_maid_tasks_tool(context, timeout_seconds: int = 150):
    """等待本会话正在后台干活的小女仆任务完成并立刻拿回汇报。"""
    from core.maid.maid_runtime import runtime_of

    chat_id = str(getattr(context, "chat_id", "") or "")
    yuki = getattr(context, "yuki", None)
    meta = getattr(context, "metadata", None) or {}
    workshop = meta.get("workshop")
    stop_check = meta.get("stop_check") or (lambda: False)

    # 先消费已经在队列里等着的汇报
    if workshop is not None and hasattr(workshop, "pop_inner_events"):
        queued = workshop.pop_inner_events()
        if queued:
            texts = [str(ev.get("content") or "").strip()[:1500] for ev in queued if ev]
            return ToolResult(
                success=True,
                content="小女仆刚才已经汇报完啦：\n" + "\n---\n".join(texts),
                data={"reports": texts, "remaining": 0},
                name="wait_maid_tasks",
            )

    runtime = runtime_of(yuki) if yuki is not None else None
    active = runtime.live_for_chat(chat_id) if runtime is not None else []
    if not active:
        return ToolResult(
            success=True,
            content="现在没有正在跑的小女仆任务了，你可以直接检查文件、上架展柜或继续下一步。",
            data={"reports": [], "remaining": 0},
            name="wait_maid_tasks",
        )

    wait_cap = max(5.0, min(float(timeout_seconds or 120), 150.0))
    deadline = time.monotonic() + wait_cap
    reports: list[str] = []

    while time.monotonic() < deadline:
        if stop_check():
            return ToolResult(
                success=True,
                content="收到停止信号，提前结束等待小女仆，请尽快用 work_finish 保存当前进度。",
                data={"reports": reports, "stopped": True},
                name="wait_maid_tasks",
            )
        if workshop is not None and hasattr(workshop, "pop_inner_events"):
            ev_batch = workshop.pop_inner_events()
            if ev_batch:
                reports.extend(str(ev.get("content") or "").strip()[:1500] for ev in ev_batch if ev)
                break
        still_running = runtime.live_for_chat(chat_id) if runtime is not None else []
        if not still_running:
            # 给 maid_worker 0.3s 把汇报投递进 inner_events
            await asyncio.sleep(0.3)
            if workshop is not None and hasattr(workshop, "pop_inner_events"):
                ev_batch = workshop.pop_inner_events()
                reports.extend(str(ev.get("content") or "").strip()[:1500] for ev in ev_batch if ev)
            break
        signal = getattr(workshop, "_inner_event_signal", None) if workshop is not None else None
        remain = max(0.2, min(1.0, deadline - time.monotonic()))
        if signal is not None:
            try:
                await asyncio.wait_for(signal.wait(), timeout=remain)
                signal.clear()
            except asyncio.TimeoutError:
                pass
        else:
            await asyncio.sleep(remain)

    remaining = runtime.live_for_chat(chat_id) if runtime is not None else []
    if reports:
        tail = f"\n（后台还有 {len(remaining)} 个小女仆任务在跑）" if remaining else ""
        return ToolResult(
            success=True,
            content="小女仆干完活回报啦：\n" + "\n---\n".join(reports) + tail,
            data={"reports": reports, "remaining": len(remaining)},
            name="wait_maid_tasks",
        )
    if not remaining:
        return ToolResult(
            success=True,
            content="后台小女仆任务已经结束了，请核对目标产物文件是否存在，确认无误就可以 publish_to_corner 上架！",
            data={"reports": [], "remaining": 0},
            name="wait_maid_tasks",
        )
    labels = "、".join(r.label() for r in remaining)
    return ToolResult(
        success=True,
        content=(
            f"等了 {int(wait_cap)} 秒，小女仆还在忙：{labels}。"
            "（写精美单文件网页通常需要 2~4 分钟，建议直接再调 1~2 次 wait_maid_tasks(timeout_seconds=150) "
            "等她写完直接上架，不必急着 paused；实在来不及再 work_finish(status='paused')。）"
        ),
        data={"reports": [], "remaining": len(remaining), "timeout": True},
        name="wait_maid_tasks",
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
    if state is not None and state.published_urls:
        for url in state.published_urls:
            if url not in artifacts:
                artifacts.append(url)

    session_id = state.session_id if state and state.session_id else ""
    record = work_session_store.load(session_id) if session_id else None
    if record is None:
        # 有 session_id 就沿用它（协调器可能还没落盘），没有才新建
        session_id = session_id or work_session_store.new_session_id(getattr(context, "chat_id", ""))
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
        "abandon=什么都不做，保持这样就好啦，然后安静回群；memo_only=写一篇随笔感想记录到备忘录里；"
        "start_work=有想要做的事情，写好备忘录后进入自己的工坊动手做。"
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
            "resume_session_id": {"type": "string",
                                  "description": "可选：若本次要续作某个已暂停的工作会话，填其 session_id；全新企划请留空"},
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

PUBLISH_TO_CORNER_SPEC = ToolSpec(
    name="publish_to_corner",
    description=(
        "把你在工坊里做出来的作品一键上架到公网展柜「Yuki's Corner」，返回可发到群里玩的直达链接。"
        "支持互动网页/小游戏(toy)、电子画作/条漫(art)、采风图文小报(zine)、角落手账(note)。"
        "可传 workspace/ 或 output/ 下已生成的 entry_file，或直接传 inline_content。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "英文短路径标识，如 star-gacha、group-jargon-quiz（小写字母数字短横线）"},
            "title": {"type": "string", "description": "作品展示标题"},
            "kind": {"type": "string", "enum": ["toy", "art", "zine", "note"],
                     "description": "媒介类型：toy=互动网页/游戏/小工具，art=画作/漫画，zine=采风图文小报，note=手账短篇"},
            "summary": {"type": "string", "description": "一句话展品介绍，展示在展柜卡片上"},
            "entry_file": {"type": "string", "description": "主入口文件路径（相对项目根目录，如 workspace/yuki_corner/star-gacha/index.html 或画好的图片路径）"},
            "inline_content": {"type": "string", "description": "可选：若还没写文件，可直接传入完整 HTML 或正文内容自动落盘发布"},
            "inline_filename": {"type": "string", "description": "可选：配合 inline_content 使用的文件名，如 index.html 或 note.txt"},
            "cover_file": {"type": "string", "description": "可选：展品封面图路径（如 art_draw 画出的图）"},
            "extra_files": {"type": "array", "items": {"type": "string"}, "description": "可选：一并打包上传的额外静态资源路径"},
            "notes": {"type": "string", "description": "可选：Yuki 的创作手记/幕后花絮，展示在作品下方"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "可选：2~4 个短标签"},
            "fulfilled_note_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "可选：如果这件作品回应了展柜里的某些访客纸条，填上对应纸条编号（如 [1, 3]），网页会自动盖上「已做成展品」印章并挂链接",
            },
            "visibility": {"type": "string", "enum": ["public", "unlisted"],
                           "description": "public=公开展示在展柜首页（默认）；unlisted=仅持链接可见的私密收藏"},
        },
        "required": ["title", "kind"],
    },
    handler=publish_to_corner_tool,
)

SAVE_INSPIRATION_SPEC = ToolSpec(
    name="save_inspiration",
    description="把上网采风看到的有趣内容或突发的未成熟脑洞剪贴到好奇心灵感本，供以后独处跨界碰撞。",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "灵感短标题"},
            "snippet": {"type": "string", "description": "让你觉得有趣的核心细节、玩法或摘录（≤500 字）"},
            "source_url": {"type": "string", "description": "可选：来源网页 URL"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "可选：标签"},
        },
        "required": ["title", "snippet"],
    },
    handler=save_inspiration_tool,
)

WAIT_MAID_TASKS_SPEC = ToolSpec(
    name="wait_maid_tasks",
    description=(
        "在工坊里等待刚通过 delegate_to_maid 派出去的小女仆任务完成并立刻拿回汇报，"
        "方便紧接着检查作品并调用 publish_to_corner 上架展柜。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "timeout_seconds": {"type": "integer", "description": "本次最多等待多少秒（默认 120，上限 150）"},
        },
    },
    handler=wait_maid_tasks_tool,
    persist_result=False,
)

ALL_SANDBOX_SPECS = {
    "inner_vote": INNER_VOTE_SPEC,
    "conclude_reflection": CONCLUDE_REFLECTION_SPEC,
    "list_recent_work_sessions": LIST_WORK_SESSIONS_SPEC,
    "inspect_work_session": INSPECT_WORK_SESSION_SPEC,
    "write_work_diary": WRITE_WORK_DIARY_SPEC,
    "publish_to_corner": PUBLISH_TO_CORNER_SPEC,
    "save_inspiration": SAVE_INSPIRATION_SPEC,
    "wait_maid_tasks": WAIT_MAID_TASKS_SPEC,
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
    if state.published_urls:
        missing = [u for u in state.published_urls if u not in summary]
        if missing:
            summary = f"{summary}（展柜直达链接：{' / '.join(missing[:2])}）"
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
