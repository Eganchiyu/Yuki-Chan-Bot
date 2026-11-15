# modules/autonomous/inner_debate.py
"""debate 模式：第一人称双念头交锋（≤32 轮、双向投票、三段式压力、上下文压缩）。"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from config import cfg
from core.tool_markup import strip_tool_call_markup
from modules.autonomous import prompts as sb_prompts
from modules.autonomous.sandbox_loop import (
    AdaptorHistory,
    SandboxLoop,
    SilentSender,
    build_tool_context,
    parse_tool_payload,
    run_step_with_timeout,
)
from modules.autonomous.storage import diary_seed_sampler
from modules.autonomous.tools import SandboxState, build_registry
from utils.llm_client import llm_chat
from utils.logger import get_logger

logger = get_logger("autonomous.debate")

# 交锋阶段只挂只读接地工具 + 投票（§4.2 第 3 条）
DEBATE_MAIN_TOOLS = {"search_diary", "search_group_snapshots"}
DEBATE_SANDBOX_TOOLS = ["inner_vote", "list_recent_work_sessions", "inspect_work_session"]
DEBATE_VISIBLE = DEBATE_MAIN_TOOLS | set(DEBATE_SANDBOX_TOOLS)
RETRIEVAL_TOOLS = DEBATE_MAIN_TOOLS | {"list_recent_work_sessions", "inspect_work_session"}
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
        shared = sb_prompts.debate_shared(self.chat_label)
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
            narration = sb_prompts.pressure_narration(step, self.max_rounds, used_retrieval)
            messages = self._build_messages(shared, role, seeds, turns, anchor, narration, step)

            try:
                msg, _llm_ms = await run_step_with_timeout(
                    self.loop.call_model(messages, DEBATE_VISIBLE)
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
            calls = self.loop.extract_calls(msg, DEBATE_VISIBLE)
            if calls:
                self.context.metadata["debate_role"] = role
                names = {((c.get("function") or {}).get("name") or "") for c in calls}
                if names & RETRIEVAL_TOOLS:
                    used_retrieval = True
                try:
                    results = await run_step_with_timeout(
                        self.loop.execute_calls(
                            calls, DEBATE_VISIBLE, finish_reason=msg.get("_finish_reason") or "",
                        )
                    )
                except asyncio.TimeoutError:
                    result.stopped = "timeout"
                    logger.warning(f"[Debate] {self.chat_id} 第 {step} 步工具超时")
                    break
                for message in results:
                    if message.get("name") == "inner_vote":
                        payload = parse_tool_payload(message)
                        logger.info(
                            f"[Debate] {self.chat_id} step={step} role={role} vote={payload.get('data')}"
                        )

            result.rounds = step
            turns.append({"role": role, "content": content or "（先翻了翻旧记录和档案）"})

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
        return result

    def _build_messages(self, shared, role, seeds, turns, anchor, narration, step) -> list[dict]:
        body = []
        if seeds:
            body.append(sb_prompts.seeds_block(seeds))
        body.append(sb_prompts.transcript_block(turns, anchor))
        if narration:
            body.append(narration)
        body.append(sb_prompts.debate_step_instruction(role, step, self.max_rounds))
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
