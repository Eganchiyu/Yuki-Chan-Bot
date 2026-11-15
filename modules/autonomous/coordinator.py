# modules/autonomous/coordinator.py
"""AutonomousCoordinator：chat → debate →（复盘）→ workshop → chat 的调度器。

职责边界：
- 只做编排与配额/准入门禁，具体循环在 `inner_debate.py` / `workshop.py`；
- 模式进出统一走 `ModeRouter`（唯一体性），退出后统一补台；
- 任何异常都必须走到 finally：退模式、清 active_mode、abort 子聚焦、派发补台。
"""
from __future__ import annotations

import asyncio
import datetime
import time

from config import cfg
from core.focus import focus_manager
from core.modes.base import Mode
from core.modes.router import ModeBusyError, ModeRouter
from modules.autonomous import prompts as sb_prompts
from modules.autonomous.mode_impl import DebateMode, WorkshopMode, make_mode_factory
from modules.autonomous.sandbox_loop import (
    AdaptorHistory,
    SandboxDeps,
    SandboxLoop,
    build_tool_context,
    run_step_with_timeout,
)
from modules.autonomous.storage import (
    daily_memory_store,
    group_name_cache,
    state_store,
    truncate_chars,
    work_session_store,
)
from modules.autonomous.tools import (
    SandboxState,
    build_registry,
    record_work_memory,
    save_autonomous_memo,
    save_work_diary_entry,
)
from utils.logger import get_logger

logger = get_logger("autonomous")

REFLECTION_MAX_ATTEMPTS = 3
NUDGE_TEXT = (
    "（还没有落盘哦。请调用 conclude_reflection，写下标题、备忘录正文并选择 "
    "abandon / memo_only / start_work 之一。）"
)


class AutonomousCoordinator:
    """自主轮次的唯一编排入口。"""

    def __init__(self, pipeline, *, router: ModeRouter | None = None):
        self.pipeline = pipeline
        self.router = router or getattr(pipeline, "mode_router", None) or ModeRouter()
        self._runs: dict[str, asyncio.Task] = {}
        self._last_error: dict[str, str] = {}
        self._register_modes()
        try:
            self.router.set_catchup_handler(pipeline.handle_catchup)
        except Exception:  # pragma: no cover - 防御
            pass

    # ------------------------------------------------------------ 依赖采集
    def _register_modes(self) -> None:
        self.router.register_mode("debate", make_mode_factory("debate"))
        self.router.register_mode("workshop", make_mode_factory("workshop"))

    @property
    def deps(self) -> SandboxDeps:
        engine = getattr(self.pipeline, "engine", None)
        return SandboxDeps(
            yuki=self.pipeline.yuki,
            sender=self.pipeline.sender,
            main_registry=getattr(engine, "tool_registry", None),
            history_manager=self.pipeline.history_manager,
            memory_rag=getattr(self.pipeline, "memory_rag", None),
            image_store=getattr(self.pipeline, "image_store", None),
            process_callback=getattr(engine, "process_callback", None),
            gateway=self.pipeline.sender,
            image_attach=getattr(getattr(engine, "reply_service", None),
                                 "_attach_tool_screenshots", None),
        )

    # ------------------------------------------------------------ 群级准入
    def is_group_enabled(self, chat_id) -> bool:
        """唯一准入函数：自动触发与 /深思 共用。"""
        gid = str(chat_id)
        if not cfg.autonomous.enabled:
            return False
        if cfg.TARGET_GROUPS and not _in_target_groups(gid):
            return False
        override = state_store.get_group_override(gid)
        if override is not None:
            return bool(override)
        return gid in {str(g) for g in (cfg.autonomous.enabled_groups or [])}

    def gate_reason(self, chat_id) -> str:
        gid = str(chat_id)
        if not cfg.autonomous.enabled:
            return "总开关 autonomous.enabled 未开启"
        if cfg.TARGET_GROUPS and not _in_target_groups(gid):
            return "不属于目标群（TARGET_GROUPS）"
        override = state_store.get_group_override(gid)
        if override is True:
            return "已开启（来源：运行时覆盖）"
        if override is False:
            return "未开启（来源：运行时覆盖）"
        if gid in {str(g) for g in (cfg.autonomous.enabled_groups or [])}:
            return "已开启（来源：配置白名单）"
        return "未开启（不在 enabled_groups 白名单里）"

    def enabled_group_ids(self) -> list[str]:
        groups = {str(g) for g in (cfg.autonomous.enabled_groups or [])}
        if cfg.TARGET_GROUPS:
            groups &= {str(g) for g in cfg.TARGET_GROUPS}
        for gid, value in (state_store.load().get("group_overrides") or {}).items():
            if value and (not cfg.TARGET_GROUPS or _in_target_groups(gid)):
                groups.add(str(gid))
            elif not value:
                groups.discard(str(gid))
        return sorted(groups)

    # ------------------------------------------------------------ 对外操作
    def is_running(self, chat_id=None) -> bool:
        if chat_id is None:
            return bool(self._runs) or self.router.global_run is not None
        return str(chat_id) in self._runs

    async def start_run(self, chat_id, *, trigger: str = "manual", goal: str = "",
                        mode_arg: str = "group", notify_master: bool | None = None) -> dict:
        """启动一次自主轮（后台跑），返回给调用方的即时回执。"""
        gid = str(chat_id)
        if self.is_running(gid):
            return {"ok": False, "reason": "已经在一个人的独处时间里啦，稍等一下下"}
        if not self.is_group_enabled(gid):
            return {
                "ok": False,
                "reason": (
                    f"这个群没开自主轮哦（{self.gate_reason(gid)}）。"
                    "要用的话先 /自主轮 开"
                ),
            }
        if self.router.global_run is not None:
            other = self.router.global_run
            return {"ok": False, "reason": f"现在正在群 {other.chat_id} 里独处，等这边结束再说"}

        task = asyncio.create_task(
            self._run(gid, trigger=trigger, goal=goal, mode_arg=mode_arg,
                      notify_master=notify_master if notify_master is not None else trigger == "manual")
        )
        self._runs[gid] = task
        logger.warning(f"[Autonomous] {gid} 启动自主轮 trigger={trigger}")
        return {"ok": True, "chat_id": gid, "trigger": trigger}

    def force_release(self, chat_id=None) -> dict:
        state = self.router.force_release("force_release")
        if state is None:
            return {"ok": False, "reason": "现在没有在跑的自主轮"}
        return {"ok": True, "chat_id": state.chat_id, "mode": state.mode}

    def status_text(self, chat_id=None) -> str:
        lines = [f"【自主轮状态】{self.gate_reason(chat_id) if chat_id else ''}".rstrip()]
        run = self.router.global_run
        if run is None:
            lines.append("当前模式：chat（群里正常聊天）")
        else:
            elapsed = int(time.time() - run.started_at)
            lines.append(
                f"当前模式：{run.mode}（群 {run.chat_id}，已占用 {elapsed}s）"
                + (f" 会话 {run.session_id}" if run.session_id else "")
            )
        sessions = work_session_store.list(status="paused", limit=3)
        if sessions:
            lines.append("暂停中的工作：")
            for row in sessions:
                lines.append(
                    f"- {row.get('session_id')} 《{row.get('title') or '无题'}》："
                    f"{row.get('log_head') or '(无日志)'}"
                )
        quota = cfg.autonomous.daily_max_runs
        lines.append(f"今日自动触发：{state_store.auto_runs_today()}/{quota}")
        last = state_store.last_run_at()
        if last:
            when = datetime.datetime.fromtimestamp(last).strftime("%m-%d %H:%M")
            lines.append(f"上次结束：{when}")
        if chat_id and self._last_error.get(str(chat_id)):
            lines.append(f"上次异常：{self._last_error[str(chat_id)]}")
        return "\n".join(lines)

    # ------------------------------------------------------------ 主流程
    async def _run(self, gid: str, *, trigger: str, goal: str, mode_arg: str,
                   notify_master: bool) -> dict:
        deps = self.deps
        chat_label = await self._chat_label(gid, deps)
        run_id = f"run-{int(time.time() * 1000)}"
        state = SandboxState(run_id=run_id, chat_id=gid)
        state_store.set_active_mode(gid, "debate", run_id)
        self._resolve_reply_watch(gid)
        summary = ""
        episode = False      # 只有 memo_only / start_work 才算「带着东西回到群里」
        try:
            debate_mode = DebateMode(
                chat_id=gid, router=self.router, run_id=run_id, deps=deps,
                state=state, chat_label=chat_label, mode_arg=mode_arg,
            )
            self.router.enter(gid, "debate", run_id=run_id, instance=debate_mode)
            run_result = await self._run_mode(debate_mode)
            debate = getattr(debate_mode, "debate_result", None)
            self.router.exit(gid, run_id=run_id)

            if debate is None or debate.stopped in {"force", "timeout", "empty"}:
                summary = self._stalled_summary(debate)
                logger.warning(f"[Autonomous] {gid} 思考阶段中断：{summary}")
                return {"ok": False, "reason": summary}

            if debate.verdict == "do_nothing":
                logger.warning(f"[Autonomous] {gid} 念头层决定什么都不做，静默退出")
                return {"ok": True, "outcome": "do_nothing"}

            state.phase = "reflection"
            reflection = await self._reflect(gid, chat_label, state, debate, deps)
            if reflection is None or reflection.get("action") == "abandon":
                logger.warning(f"[Autonomous] {gid} 本尊决定放弃，静默退出")
                return {"ok": True, "outcome": "abandon"}

            memo_id = save_autonomous_memo(
                reflection, gid, state.session_id, kind="memo",
            )
            save_work_diary_entry(reflection, gid, state.session_id)
            self._apply_notebook_pointer(reflection)
            state.notes.append(f"memo={memo_id or '-'}")

            if reflection.get("action") != "start_work":
                record_work_memory(
                    state, {**reflection, "memo_content": reflection.get("memo_content", "")},
                    status="随想",
                )
                summary = self._reflection_summary(reflection, memo_id)
                episode = True
                return {"ok": True, "outcome": "memo_only", "summary": summary}

            # ---- Phase 3：自主执行工坊 ----
            state.phase = "workshop"
            session = self._ensure_work_session(gid, reflection)
            state.session_id = session["session_id"]
            state_store.set_active_mode(gid, "workshop", run_id, session_id=state.session_id)
            workshop_mode = WorkshopMode(
                chat_id=gid, router=self.router, run_id=run_id,
                session_id=state.session_id, goal=reflection.get("title", ""),
                deps=deps, state=state, chat_label=chat_label, mode_arg=mode_arg,
            )
            self.router.enter(gid, "workshop", run_id=run_id,
                              session_id=state.session_id, instance=workshop_mode)
            await self._run_mode(workshop_mode)
            self.router.exit(gid, run_id=run_id)
            record_work_memory(state, reflection, status="可接续")
            summary = self._reflection_summary(reflection, memo_id, state)
            episode = True
            return {"ok": True, "outcome": "start_work", "summary": summary}
        except ModeBusyError as exc:
            self._last_error[gid] = str(exc)
            logger.warning(f"[Autonomous] {gid} 模式占用冲突: {exc}")
            return {"ok": False, "reason": str(exc)}
        except Exception as exc:
            self._last_error[gid] = str(exc)
            logger.error(f"[Autonomous] {gid} 自主轮异常: {exc}")
            return {"ok": False, "reason": f"自主轮异常：{exc}"}
        finally:
            try:
                self.router.exit(gid, run_id=run_id)
            except Exception:
                pass
            try:
                focus_manager.abort(gid)
            except Exception:
                pass
            state_store.clear_active_mode()
            self._runs.pop(gid, None)
            if notify_master and summary:
                await self._notify_master(gid, summary)
            await self._after_run(gid, episode=episode)

    async def _run_mode(self, mode: Mode) -> dict:
        """带墙钟上限地跑一个模式；超时则请求它尽快收尾。"""
        limit = max(30.0, float(cfg.autonomous.max_wall_seconds))
        task = asyncio.create_task(mode.run())
        try:
            return await asyncio.wait_for(task, timeout=limit)
        except asyncio.TimeoutError:
            logger.warning(
                f"[Autonomous] {mode.chat_id} {mode.name} 超过 {limit:.0f}s 墙钟上限，强制收尾"
            )
            mode.request_stop("timeout")
            try:
                await asyncio.wait_for(task, timeout=20)
            except Exception:
                task.cancel()
            self._mark_session_paused(mode.chat_id, "自主轮超过墙钟上限，被系统收尾")
            return {"outcome": "timeout"}

    # ------------------------------------------------------------ Phase 2 复盘
    async def _reflect(self, gid, chat_label, state: SandboxState, debate,
                       deps: SandboxDeps) -> dict | None:
        registry = build_registry(deps.main_registry, ["conclude_reflection"], main_tool_names=set())
        history = AdaptorHistory(gid)
        context = build_tool_context(
            chat_id=gid, yuki=deps.yuki, sender=self._silent_sender(gid),
            history=history, image_store=deps.image_store,
            metadata={"sandbox": state, "is_autonomous": True, "phase": "reflection"},
        )
        loop = SandboxLoop(
            chat_id=gid, registry=registry, context=context, history=history,
            max_steps=REFLECTION_MAX_ATTEMPTS, max_tokens=900, temperature=0.8,
            pinned={"conclude_reflection"}, debug_tag="reflection",
        )
        messages = [
            {"role": "system", "content": sb_prompts.reflection_system(chat_label)},
            {"role": "user", "content": sb_prompts.reflection_user_block(
                chat_label, debate.summary(), debate.verdict)},
        ]
        for attempt in range(1, REFLECTION_MAX_ATTEMPTS + 1):
            try:
                msg, _ = await run_step_with_timeout(loop.call_model(messages))
            except Exception as exc:
                logger.error(f"[Autonomous] {gid} 复盘第 {attempt} 次 LLM 失败: {exc}")
                continue
            calls = loop.extract_calls(msg, {"conclude_reflection"})
            if not calls:
                messages.append({"role": "assistant", "content": msg.get("content") or ""})
                messages.append({"role": "user", "content": NUDGE_TEXT})
                continue
            try:
                await run_step_with_timeout(loop.execute_calls(calls, {"conclude_reflection"}))
            except Exception as exc:
                logger.error(f"[Autonomous] {gid} 复盘落盘失败: {exc}")
            if state.reflection:
                return state.reflection
        logger.warning(f"[Autonomous] {gid} 复盘没有落盘，按放弃处理")
        return None

    def _silent_sender(self, gid):
        from modules.autonomous.sandbox_loop import SilentSender

        return SilentSender(gid)

    # ------------------------------------------------------------ 落盘辅助
    def _ensure_work_session(self, gid, reflection: dict) -> dict:
        resumable = work_session_store.latest_resumable(chat_id=gid)
        if resumable is not None:
            resumable["status"] = "active"
            resumable.setdefault("title", reflection.get("title", ""))
            return work_session_store.save(resumable)
        session_id = work_session_store.new_session_id(gid)
        return work_session_store.save({
            "session_id": session_id,
            "title": reflection.get("title", "未命名工作"),
            "kind": "creative",
            "status": "active",
            "work_log": "",
            "artifacts": [],
            "chat_id": str(gid),
        })

    def _mark_session_paused(self, gid, reason: str) -> None:
        session_id = (state_store.get_active_mode() or {}).get("session_id")
        record = work_session_store.load(session_id) if session_id else None
        if record is None:
            return
        work_session_store.update(
            session_id,
            status="paused",
            work_log=truncate_chars(f"{record.get('work_log') or ''}（{reason}）", 512),
        )

    def _apply_notebook_pointer(self, reflection: dict) -> None:
        pointer = (reflection or {}).get("notebook_pointer", "").strip()
        if not pointer:
            return
        try:
            from core.notebook import notebook_store

            save_zone = getattr(notebook_store, "save_zone", None)
            if callable(save_zone):
                save_zone("plans", pointer)
            else:  # 兼容尚未双区化的旧存储
                current = notebook_store.load()
                notebook_store.save(f"{current}\n{pointer}".strip())
        except Exception as exc:
            logger.warning(f"[Autonomous] 写入小本本长期路标失败: {exc}")

    # ------------------------------------------------------------ 回群收尾
    async def _after_run(self, gid, *, episode: bool = False) -> None:
        try:
            await self.router.dispatch_catchups()
        except Exception as exc:
            logger.error(f"[Autonomous] 补台失败: {exc}")
        if not episode:
            # do_nothing / abandon / 中断：不拉高欲望、不主动破冰，安静回到群聊
            return
        self._mark_high_spirits(gid)
        if not self.pipeline.yuki.message_buffer.get(str(gid)):
            await self._trigger_ice_break(gid)

    def _mark_high_spirits(self, gid) -> None:
        marker = getattr(self.pipeline.yuki, "mark_high_spirits", None)
        if callable(marker):
            try:
                marker(gid)
            except Exception as exc:
                logger.debug(f"[Autonomous] 心情高涨标记失败: {exc}")

    async def _trigger_ice_break(self, gid) -> None:
        """回群时群里仍然安静：立刻给一次破冰机会（Phase 4 主动开口）。"""
        try:
            callback = getattr(getattr(self.pipeline, "engine", None), "process_callback", None)
            if callback is None:
                return
            asyncio.create_task(callback(
                str(gid), "group", debounce_flag=False, force_reply=True, ice_break=True,
            ))
        except Exception as exc:
            logger.debug(f"[Autonomous] 回群破冰失败: {exc}")

    def _resolve_reply_watch(self, gid) -> None:
        try:
            from core.reply_watch import resolve

            resolve(str(gid), "autonomous_start")
        except Exception:
            pass

    async def _chat_label(self, gid: str, deps: SandboxDeps) -> str:
        try:
            return await group_name_cache.fetch(deps.gateway, gid)
        except Exception:
            return group_name_cache.name(gid)

    async def _notify_master(self, gid: str, text: str) -> None:
        sender = getattr(self.pipeline, "sender", None)
        if sender is None or not hasattr(sender, "send"):
            return
        try:
            await sender.send(cfg.TARGET_QQ, text, mode="private")
        except Exception as exc:
            logger.warning(f"[Autonomous] 汇报机主失败: {exc}")

    # ------------------------------------------------------------ 摘要文案
    @staticmethod
    def _stalled_summary(debate) -> str:
        if debate is None:
            return "这次独处没能开始（思考阶段没有产出）。"
        reason = {"force": "被 /强制放行 打断", "timeout": "单步超时", "empty": "模型没有回应"}
        return f"这次独处半途中断了：{reason.get(debate.stopped, debate.stopped)}。"

    @staticmethod
    def _reflection_summary(reflection: dict, memo_id: str | None, state: SandboxState | None = None) -> str:
        title = reflection.get("title") or "（无题）"
        lines = [f"【独处汇报】《{title}》"]
        memo = (reflection.get("memo_content") or "").strip()
        if memo:
            lines.append(truncate_chars(memo, 400))
        if state is not None:
            if state.session_id:
                lines.append(f"工作会话：{state.session_id}")
            if state.work_log:
                lines.append("工作日志：" + truncate_chars(state.work_log, 300))
            if state.artifacts:
                lines.append("产物：" + "、".join(state.artifacts[:6]))
        if memo_id:
            lines.append("（已存进日记库，参与之后的回忆检索）")
        return "\n".join(lines)

    # ------------------------------------------------------------ 冷场自动触发
    async def auto_trigger_check(self) -> dict | None:
        """冷场巡检调用：满足条件就自动开一次自主轮。"""
        if not cfg.autonomous.enabled or not cfg.autonomous.auto_trigger_enabled:
            return None
        if not self.router.is_idle():
            return None
        if _in_quiet_hours():
            return None
        now = time.time()
        if now - state_store.last_run_at() < max(0, cfg.autonomous.cooldown_minutes) * 60:
            return None
        if state_store.auto_runs_today() >= max(1, cfg.autonomous.daily_max_runs):
            return None
        candidate = self._pick_candidate(now)
        if candidate is None:
            return None
        state_store.bump_auto_runs()
        result = await self.start_run(candidate, trigger="auto", notify_master=False)
        if result.get("ok"):
            logger.warning(f"[Autonomous] 冷场触发自动自主轮：{candidate}")
            return result
        return None

    def _pick_candidate(self, now: float) -> str | None:
        """候选群 = 白名单 ∩ TARGET_GROUPS，按「静默最久 → 精力最高」取第一个。"""
        best = None
        best_key = None
        for gid in self.enabled_group_ids():
            if not self.is_group_enabled(gid):
                continue
            last = float(self.pipeline.yuki.last_message_time.get(gid, 0.0) or 0.0)
            idle_minutes = (now - last) / 60 if last else 1e9
            if idle_minutes < float(cfg.autonomous.min_group_idle_minutes):
                continue
            energy = float(getattr(self.pipeline.yuki, "energy", {}).get(gid, cfg.INITIAL_ENERGY))
            if energy / max(1.0, float(cfg.MAX_ENERGY)) < float(cfg.autonomous.min_energy):
                continue
            key = (-idle_minutes, -energy)
            if best_key is None or key < best_key:
                best, best_key = gid, key
        return best

    # ------------------------------------------------------------ 重启兜底
    def sweep_stale_runs(self) -> int:
        """启动时清理上次没跑完的 active_mode：会话标 paused，模式状态放行。"""
        stale = state_store.get_active_mode() or {}
        gid = str(stale.get("chat_id") or "")
        if not gid:
            return 0
        session_id = str(stale.get("session_id") or "")
        if session_id:
            record = work_session_store.load(session_id)
            if record and record.get("status") == "active":
                work_session_store.update(
                    session_id,
                    status="paused",
                    work_log=truncate_chars(
                        f"{record.get('work_log') or ''}（进程重启，自动暂停）", 512,
                    ),
                )
        self.router.exit(gid)
        state_store.clear_active_mode()
        logger.warning(f"[Autonomous] 清理上次残留的运行状态：群 {gid} mode={stale.get('mode')}")
        return 1


def _in_target_groups(gid) -> bool:
    try:
        return int(gid) in {int(g) for g in cfg.TARGET_GROUPS}
    except (TypeError, ValueError):
        return False


def _in_quiet_hours(now: datetime.datetime | None = None) -> bool:
    hours = list(cfg.autonomous.quiet_hours or [])
    if len(hours) != 2:
        return False
    start, end = int(hours[0]), int(hours[1])
    hour = (now or datetime.datetime.now()).hour
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end
