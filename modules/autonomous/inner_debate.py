# modules/autonomous/inner_debate.py
"""debate 模式：第一人称双念头交锋（≤32 轮、双向投票、三段式压力、上下文压缩）。"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from config import cfg
from core.tool_markup import strip_tool_call_markup
from modules.autonomous import corner_client, prompts as sb_prompts
from modules.autonomous.inspiration import build_inspiration_bundle, render_inspiration_block
from modules.autonomous.sandbox_loop import (
    AdaptorHistory,
    SandboxLoop,
    SilentSender,
    build_tool_context,
    parse_tool_payload,
    run_step_with_timeout,
)
from modules.autonomous.storage import diary_seed_sampler, work_session_store
from modules.autonomous.tools import SandboxState, build_registry
from modules.autonomous.transcript import transcript_for
from utils.llm_client import llm_chat
from utils.logger import get_logger

logger = get_logger("autonomous.debate")

# 交锋前 debate_retrieval_steps 步可以翻日记/群聊截屏/工作档案，之后收起，只剩投票
DEBATE_MAIN_TOOLS = {"search_diary", "search_group_snapshots"}
DEBATE_SANDBOX_TOOLS = ["inner_vote", "list_recent_work_sessions", "inspect_work_session"]
DEBATE_VISIBLE = DEBATE_MAIN_TOOLS | set(DEBATE_SANDBOX_TOOLS)
RETRIEVAL_TOOLS = DEBATE_MAIN_TOOLS | {"list_recent_work_sessions", "inspect_work_session"}
DISCUSSION_ONLY_TOOLS = {"inner_vote"}   # 检索窗口关闭后的纯讨论视图
ANCHOR_MAX_CHARS = 600
CONSENSUS_SUMMARY_MAX_CHARS = 600


@dataclass
class DebateResult:
    verdict: str = "undecided"          # start_work | memo_only | do_nothing | undecided
    consensus_note: str = ""
    rounds: int = 0
    stopped: str = "cap"                # vote | cap | force | timeout | empty
    transcript: list[dict] = field(default_factory=list)
    anchor: str = ""
    votes: list[dict] = field(default_factory=list)

    def summary(self) -> str:
        """给 Phase 2 的「交锋共识 / 最后几轮摘要」。"""
        if self.consensus_note:
            return self.consensus_note[:CONSENSUS_SUMMARY_MAX_CHARS]
        lines = []
        for turn in self.transcript[-6:]:
            label = sb_prompts.ROLE_LABELS.get(turn.get("role", ""), "【念头】")
            lines.append(f"{label} {turn.get('content', '')}")
        return "\n".join(lines)[:CONSENSUS_SUMMARY_MAX_CHARS]


class InnerDebate:
    """一次完整的双念头交锋。"""

    def __init__(
        self,
        *,
        chat_id,
        chat_label: str,
        state: SandboxState,
        main_registry,
        yuki,
        sender=None,
        image_store=None,
        max_rounds: int | None = None,
        stop_check=None,
    ):
        self.chat_id = str(chat_id)
        self.chat_label = chat_label or f"群 {self.chat_id}"
        self.state = state
        self.main_registry = main_registry
        self.yuki = yuki
        self.sender = sender or SilentSender(self.chat_id)
        self.image_store = image_store
        self.max_rounds = int(max_rounds or cfg.autonomous.debate_max_rounds)
        self.retrieval_steps = max(0, int(cfg.autonomous.debate_retrieval_steps))
        self.stop_check = stop_check or (lambda: False)

        self.history = AdaptorHistory(self.chat_id)
        self.registry = build_registry(
            main_registry, DEBATE_SANDBOX_TOOLS, main_tool_names=DEBATE_MAIN_TOOLS,
        )
        self.context = build_tool_context(
            chat_id=self.chat_id,
            yuki=yuki,
            sender=self.sender,
            history=self.history,
            image_store=image_store,
            metadata={"sandbox": state, "is_autonomous": True, "phase": "debate"},
        )
        self.loop = SandboxLoop(
            chat_id=self.chat_id,
            registry=self.registry,
            context=self.context,
            history=self.history,
            max_steps=self.max_rounds,
            max_tokens=cfg.autonomous.debate_max_tokens,
            temperature=0.95,
            pinned=set(DEBATE_SANDBOX_TOOLS),
            debug_tag="debate",
        )

    # ------------------------------------------------------------ 主循环
    async def run(self) -> DebateResult:
        result = DebateResult()
        seeds = await asyncio.to_thread(diary_seed_sampler.sample, self.chat_id)
        inspiration_text = ""
        spark_title = ""
        unread_count = 0
        if getattr(cfg.autonomous, "creative_mode_enabled", True):
            corner_fb = await corner_client.fetch_feedback(limit=6, mark_read=True)
            recent_sessions = await asyncio.to_thread(work_session_store.list, None, 6)
            bundle = await asyncio.to_thread(
                build_inspiration_bundle,
                self.chat_id,
                corner_feedback=corner_fb,
                work_sessions=recent_sessions,
            )
            inspiration_text = render_inspiration_block(bundle)
            spark_title = str((bundle.get("spark_card") or {}).get("title") or "")
            unread_count = len(bundle.get("unread_notes") or [])

        shared = sb_prompts.debate_shared(self.chat_label, self.retrieval_steps)
        transcript = transcript_for(self.state, mode="debate")
        transcript.event("debate_start", rounds_limit=self.max_rounds,
                        retrieval_steps=self.retrieval_steps,
                        seeds=[s.get("source") for s in seeds],
                        spark_card=spark_title,
                        corner_unread_notes=unread_count)
        turns: list[dict] = []
        anchor = ""
        used_retrieval = False
        compress_every = max(2, int(cfg.autonomous.debate_compress_every))

        for step in range(1, self.max_rounds + 1):
            if self.stop_check():
                result.stopped = "force"
                logger.warning(f"[Debate] {self.chat_id} 收到强制放行，第 {step} 步收尾")
                break

            role = "A" if step % 2 == 1 else "B"
            visible = self._visible_tools(step)
            narration = sb_prompts.pressure_narration(
                step, self.max_rounds, used_retrieval, self.retrieval_steps,
            )
            messages = self._build_messages(
                shared, role, seeds, inspiration_text, turns, anchor, narration, step,
            )

            try:
                msg, _llm_ms = await run_step_with_timeout(
                    self.loop.call_model(messages, visible)
                )
            except asyncio.TimeoutError:
                result.stopped = "timeout"
                logger.warning(f"[Debate] {self.chat_id} 第 {step} 步 LLM 超时")
                break
            except Exception as exc:
                logger.error(f"[Debate] {self.chat_id} 第 {step} 步 LLM 失败: {exc}")
                result.stopped = "empty"
                break

            content = strip_tool_call_markup(msg.get("content") or "").strip()
            calls = self.loop.extract_calls(msg, visible)
            step_results: list[dict] = []
            tool_findings: list[dict] = []
            if calls:
                self.context.metadata["debate_role"] = role
                names = {((c.get("function") or {}).get("name") or "") for c in calls}
                if names & RETRIEVAL_TOOLS:
                    used_retrieval = True
                try:
                    results = await run_step_with_timeout(
                        self.loop.execute_calls(
                            calls, visible, finish_reason=msg.get("_finish_reason") or "",
                        )
                    )
                except asyncio.TimeoutError:
                    result.stopped = "timeout"
                    logger.warning(f"[Debate] {self.chat_id} 第 {step} 步工具超时")
                    break
                step_results = results
                for message in results:
                    tname = str(message.get("name") or "")
                    payload = parse_tool_payload(message)
                    if tname == "inner_vote":
                        logger.info(
                            f"[Debate] {self.chat_id} step={step} role={role} vote={payload.get('data')}"
                        )
                        vote = (payload.get("data") or {}).get("vote") or {}
                        if vote:
                            transcript.vote(step, role, vote.get("agree"),
                                            vote.get("verdict"), vote.get("note", ""))
                    else:
                        finding_text = str(
                            payload.get("content") or payload.get("error") or message.get("content") or ""
                        ).strip()
                        if finding_text:
                            tool_findings.append({"tool": tname or "tool", "content": finding_text})

            result.rounds = step
            turn_entry: dict = {"role": role, "content": content or "（先翻了翻旧记录和档案）"}
            if tool_findings:
                turn_entry["tool_findings"] = tool_findings
            turns.append(turn_entry)
            transcript.debate_step(step, role, content, calls, step_results, narration)

            consensus = self.state.consensus()
            if consensus:
                result.verdict = consensus["verdict"]
                result.consensus_note = consensus["note"]
                result.stopped = "vote"
                logger.warning(
                    f"[Debate] {self.chat_id} 第 {step} 步收敛 verdict={result.verdict}"
                )
                break

            if step % compress_every == 0 and len(turns) > 6:
                anchor = await self._compress(turns[:-6], anchor)
                turns = turns[-6:]

        if isinstance(result.verdict, str) and result.verdict == "undecided" and result.stopped == "cap":
            logger.warning(f"[Debate] {self.chat_id} 达到 {self.max_rounds} 轮上限，转入本尊复盘")

        result.transcript = turns[-6:]
        result.anchor = anchor
        result.votes = list(self.state.votes)
        transcript.event("debate_finish", stopped=result.stopped, verdict=result.verdict,
                         rounds=result.rounds, note=result.consensus_note)
        return result

    def _visible_tools(self, step: int) -> set[str]:
        """前 retrieval_steps 步放开检索工具，之后收起只剩投票（纯讨论）。"""
        if step <= self.retrieval_steps:
            return set(DEBATE_VISIBLE)
        return set(DISCUSSION_ONLY_TOOLS)

    def _build_messages(self, shared, role, seeds, inspiration_text, turns, anchor, narration, step) -> list[dict]:
        body = []
        if seeds:
            body.append(sb_prompts.seeds_block(seeds))
        if inspiration_text:
            body.append(inspiration_text)
        body.append(sb_prompts.transcript_block(turns, anchor))
        if narration:
            body.append(narration)
        body.append(sb_prompts.debate_step_instruction(
            role, step, self.max_rounds, self.retrieval_steps,
        ))
        return [
            {"role": "system", "content": shared + sb_prompts.role_prompt(role)},
            {"role": "user", "content": "\n\n".join(p for p in body if p)},
        ]

    async def _compress(self, old_turns: list[dict], anchor: str) -> str:
        """每 compress_every 步把旧交锋压成锚点卡（失败回落到代码截断）。"""
        text = sb_prompts.transcript_block(old_turns, anchor)
        fallback = "；".join(
            f"{sb_prompts.ROLE_LABELS.get(t.get('role', ''), '')}{(' '.join(str(t.get('content') or '').split()))[:40]}"
            for t in old_turns
        )[:ANCHOR_MAX_CHARS]
        if not text.strip():
            return anchor
        try:
            summary = await run_step_with_timeout(
                llm_chat(
                    messages=[
                        {"role": "system", "content": (
                            "把下面这段内心独白压缩成客观的要点锚点：只保留提出过的想法、"
                            "否掉的理由、已经定下的步骤与需要记住的事实。不要角色扮演，不要评价。"
                            f"不超过 300 字。"
                        )},
                        {"role": "user", "content": text[:3000]},
                    ],
                    model=(cfg.autonomous.digest_model or None),
                    temperature=0.3,
                    max_tokens=400,
                ),
                seconds=min(60.0, float(cfg.autonomous.step_timeout_seconds)),
            )
        except Exception as exc:
            logger.debug(f"[Debate] 压缩失败，回落代码截断: {exc}")
            return fallback
        summary = (summary or "").strip()
        return summary[:ANCHOR_MAX_CHARS] or fallback
