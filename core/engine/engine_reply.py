# core/engine/engine_reply.py
import asyncio
import json
import re
import time
from typing import Any, Callable, Optional

from config import cfg
from core.engine.turn import TurnState
from core.engine.turn_hooks import (
    FocusHook,
    FocusTraceHook,
    PruneHook,
    SnapshotHook,
    TurnHookChain,
)
from core.focus import ToolView, focus_manager
from core.prompts import build_chat_context
from core.reply_format import (
    clean_visible_reply,
    normalize_reply_markup,
    strip_layout_markup,
    strip_meme_tags,
)
from core.tool_markup import extract_text_tool_calls, strip_tool_call_markup
from core.tool_prune import ToolHistoryPruner
from core.toolchain import SKIP_REPLY_MARKER, ToolCallManager, ToolContext, ToolRuntime
from modules.debug.context_snapshot import context_snapshot_store
from modules.vision.prefetch import resolve_image
from utils.llm_client import llm_chat, llm_chat_raw
from utils.logger import get_logger

logger = get_logger("engine")

# 已开始执行工具、但最终回复被清洗干净时的占位文案
WORKING_NOTICE = "工作中......"


class EngineReplyService:
    """负责 LLM 回复生成与工具链对话。"""

    def __init__(
            self,
            yuki,
            history,
            sender,
            tool_registry,
            tool_manager,
            get_process_callback: Callable[[], Any],
            get_image_store: Callable[[], Any],
            get_meme_processor: Callable[[], Any] = lambda: None,
    ):
        self.yuki = yuki
        self.history = history
        self.sender = sender
        self.tool_registry = tool_registry
        self.tool_manager = tool_manager
        self.get_process_callback = get_process_callback
        self.get_image_store = get_image_store
        self.get_meme_processor = get_meme_processor
        self.pruner = ToolHistoryPruner(
            history,
            idle_turns=int(getattr(getattr(cfg, "tools", None), "prune_idle_turns", 2) or 2),
        )
        self.focus_hook = FocusHook(lambda: self.history)
        self.prune_hook = PruneHook(lambda: self.pruner)
        self.trace_hook = FocusTraceHook()
        self.snapshot_hook = SnapshotHook()
        self.hooks = TurnHookChain([
            self.focus_hook,
            self.prune_hook,
            self.trace_hook,
            self.snapshot_hook,
        ])

    @staticmethod
    def clean_visible_reply(content):
        """清理工具链期间可对外发送的回复文本（含括号写错的标记变体）。"""
        return clean_visible_reply(content)

    @staticmethod
    def finalize_answer(raw_content, tools_executed=False):
        """收敛最终回复，返回 (写回历史的文本, 实际发送的文本)。"""
        visible = clean_visible_reply(raw_content)
        if not visible.strip() and tools_executed:
            logger.info("[ToolChain] 回复被清洗为空但本轮已执行工具，发送工作中占位")
            visible = WORKING_NOTICE
        return normalize_reply_markup(raw_content), visible

    async def _resolve_pending_image(self, meme_processor, img):
        """工具调用期间新增图片，按与主管线一致的开关处理，并复用预取结果。"""
        url, is_meme = img["url"], img["is_meme"]
        result = await resolve_image(meme_processor, url, is_meme)
        idx_tag = self._idx_tag(result.get("index"))
        if result.get("native"):
            return f"[图片]{idx_tag}", result.get("attachment")
        desc = result.get("description") or "未知图片/表情"
        kind = "表情" if is_meme else "图片"
        return f"[{kind}:{desc}]{idx_tag}", None

    @staticmethod
    def _idx_tag(index):
        return f"[img:{index}]" if index else ""

    async def merge_pending_messages(self, chat_id, tool_messages, image_budget=None):
        """工具调用间隙合并同群新消息，避免消息流分叉。"""
        pending_objs = self.yuki.message_buffer.get(chat_id) or self.yuki.message_buffer.get(str(chat_id))
        if not pending_objs:
            return
        pending_objs = self.yuki.pop_buffer(chat_id)
        pending_text = "\n".join([m["content"] for m in pending_objs]).replace("\n", "  ").strip()
        if not pending_text:
            return

        attachments = []
        meme_processor = self.get_meme_processor()
        if meme_processor:
            pending_text, images_info = meme_processor.extract_urls_from_text(pending_text)
            if images_info:
                resolved = await asyncio.gather(*[
                    self._resolve_pending_image(meme_processor, img) for img in images_info
                ])
                for content, attachment in resolved:
                    pending_text = pending_text.replace("[图片占位符]", content, 1)
                    if attachment:
                        attachments.append(attachment)

        logger.info(f"[ToolChain] {chat_id} 合并工具调用期间新增消息: {pending_text}")
        for domain in focus_manager.domains():
            if domain.on_incoming is not None:
                try:
                    domain.on_incoming(str(chat_id), pending_text)
                except Exception:
                    pass
        self.history.append_session_message(
            chat_id,
            "user",
            pending_text,
            image_attachments=attachments,
            is_pending_during_tool=True,
            save_immediately=False,
            return_snapshot=False,
        )
        pending_message = {
            "role": "user",
            "content": f"【工具调用期间新增消息】{pending_text}",
            "image_attachments": attachments,
        }
        rendered, _ = await self._render_message(
            pending_message,
            cfg.LLM_NATIVE_VISION_ENABLED,
            0 if image_budget is None else image_budget,
        )
        tool_messages.append(rendered)

    async def send_tool_thought(self, chat_id, mode, content, sent_thoughts, tool_names=None):
        """实时发送工具链中模型产生的阶段性文本。"""
        clean_content = self.clean_visible_reply(content)
        if not clean_content or clean_content in sent_thoughts:
            return ""

        display_content = strip_meme_tags(clean_content).strip()
        if tool_names and "delegate_to_maid" in tool_names:
            display_content = clean_content + " | (๑•̀ㅂ•́)و💻"
        if display_content:
            send_mode = "private" if mode == "master_private" else mode
            await self.sender.send(chat_id, display_content, mode=send_mode)
        sent_thoughts.add(clean_content)
        logger.info(f"[ToolChain] 实时发送阶段性文本 chat_id={chat_id}: {clean_content}")
        return clean_content

    async def _render_message(self, message, native_vision, image_budget):
        """把单条消息的附件引用渲染为图片块或转写文本，返回 (消息, 剩余图片额度)。"""
        item = {key: value for key, value in message.items() if key != "image_attachments"}
        attachments = message.get("image_attachments") or []
        image_store = self.get_image_store()
        meme_processor = self.get_meme_processor()
        if not attachments or not image_store:
            return item, image_budget

        content = item.get("content") or ""
        blocks = [{"type": "text", "text": content}]
        descriptions = []
        for attachment in attachments:
            image_data = image_store.read_attachment(attachment)
            if not image_data:
                descriptions.append("[图片已过期]")
                continue
            if native_vision and image_budget > 0 and meme_processor:
                b64_data = meme_processor.compress_image(
                    image_data,
                    max_size=cfg.model.native_vision_max_size,
                    quality=cfg.model.native_vision_quality,
                )
                if b64_data:
                    blocks.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"},
                    })
                    image_budget -= 1
                    continue
            description = await meme_processor.understand_bytes(image_data) if meme_processor else "未知图片"
            descriptions.append(f"[图片:{description}]")

        if native_vision and len(blocks) > 1:
            if descriptions:
                blocks[0]["text"] += " " + " ".join(descriptions)
            item["content"] = blocks
        elif descriptions:
            item["content"] = content + " " + " ".join(descriptions)
        return item, image_budget

    async def _prepare_model_messages(self, messages, native_vision=True):
        """把历史中的轻量附件引用转换为模型消息或按需转写文本。"""
        prepared = []
        image_budget = max(0, cfg.model.native_vision_max_images)
        user_positions = [
            i for i, message in enumerate(messages)
            if message.get("role") == "user" and message.get("image_attachments")
        ]
        allowed_positions = set(user_positions[-max(0, cfg.model.native_vision_history_turns):])

        for position, message in enumerate(messages):
            if position not in allowed_positions:
                prepared.append({k: v for k, v in message.items() if k != "image_attachments"})
                continue
            item, image_budget = await self._render_message(message, native_vision, image_budget)
            prepared.append(item)
        return prepared

    @staticmethod
    def _used_image_slots(messages):
        """统计已渲染进请求的图片块数量。"""
        return sum(
            1
            for message in messages
            if isinstance(message.get("content"), list)
            for block in message["content"]
            if block.get("type") == "image_url"
        )

    @staticmethod
    def _tool_payload(tool_message) -> dict:
        """解析工具消息里的标准 JSON 载荷（失败返回空字典）。"""
        content = tool_message.get("content")
        if not isinstance(content, str):
            return {}
        try:
            payload = json.loads(content)
        except (TypeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _is_tool_screenshot_msg(msg: dict) -> bool:
        if not isinstance(msg, dict) or msg.get("role") != "user":
            return False
        content = msg.get("content")
        if isinstance(content, str) and content.startswith("【工具截图】"):
            return True
        if isinstance(content, list) and any(
            isinstance(b, dict) and str(b.get("text") or "").startswith("【工具截图】")
            for b in content
        ):
            return True
        return False

    async def _attach_tool_screenshots(self, tool_result_messages, tool_messages):
        """把工具产生的截图渲染成多模态图像块塞进本轮上下文。"""
        if not cfg.LLM_NATIVE_VISION_ENABLED:
            return
        attachments = []
        for tool_message in tool_result_messages:
            data = self._tool_payload(tool_message).get("data")
            shot = data.get("screenshot") if isinstance(data, dict) else None
            if isinstance(shot, dict) and shot.get("index"):
                attachments.append(shot)
        if not attachments:
            return

        # 移除上一步旧的【工具截图】，始终只保留最新一步画面，防止多轮操作耗尽图片配额
        tool_messages[:] = [m for m in tool_messages if not self._is_tool_screenshot_msg(m)]

        budget = max(1, cfg.model.native_vision_max_images - self._used_image_slots(tool_messages))
        for shot in attachments[-max(1, cfg.model.native_vision_max_images):]:
            if budget <= 0:
                break
            message = {
                "role": "user",
                "content": f"【工具截图】[img:{shot.get('index')}]",
                "image_attachments": [shot],
            }
            rendered, budget = await self._render_message(
                message, cfg.LLM_NATIVE_VISION_ENABLED, budget
            )
            tool_messages.append(rendered)

    def _after_turn(self, chat_id, tools_executed: bool, used_domains: set[str] | None = None) -> None:
        """保留向后兼容的单轮收尾方法。"""
        try:
            focus_manager.after_turn(chat_id, used_domains or set(), history=self.history)
        except Exception as exc:
            logger.warning(f"[Focus] 轮次闲置检查失败: {exc}")
        try:
            self.pruner.after_turn(chat_id, tools_executed)
        except Exception as exc:
            logger.warning(f"[ToolPrune] 折叠失败: {exc}")

    @staticmethod
    def _resolve_active_tools(active_registry, view: ToolView) -> list:
        try:
            return active_registry.get_tools(view=view)
        except TypeError:
            return active_registry.get_tools()

    async def _begin_turn(
        self, chat_id, combined_text, session, mode, messages, message_objs=None
    ) -> TurnState:
        context = ToolContext(
            chat_id=str(chat_id),
            mode=mode,
            session=session,
            combined_text=combined_text,
            runtime=ToolRuntime(
                sender=self.sender,
                yuki_state=self.yuki,
                image_store=self.get_image_store(),
            ),
            metadata={
                "process_callback": self.get_process_callback(),
                "history_manager": self.history,
                "message_objs": message_objs or [],
            },
        )
        active_registry = self.tool_registry
        active_tool_manager = ToolCallManager(active_registry, max_rounds=self.tool_manager.max_rounds)
        valid_tool_names = (
            set(active_registry.list_functions())
            if hasattr(active_registry, "list_functions")
            else set()
        ) or None

        async def build_backup_messages():
            return await self._prepare_model_messages(messages, native_vision=False)

        native_vision = cfg.LLM_NATIVE_VISION_ENABLED
        tool_messages = await self._prepare_model_messages(messages, native_vision=native_vision)
        fallback_factory = (
            build_backup_messages
            if native_vision and not cfg.BACKUP_NATIVE_VISION_ENABLED
            else None
        )
        debug_snap_id = getattr(self, "_debug_snapshot_by_chat", {}).get(str(chat_id))
        return TurnState(
            chat_id=str(chat_id),
            mode=mode,
            context=context,
            tool_messages=tool_messages,
            active_registry=active_registry,
            active_tool_manager=active_tool_manager,
            valid_tool_names=valid_tool_names,
            fallback_factory=fallback_factory,
            max_rounds=active_tool_manager.max_rounds,
            base_max_rounds=active_tool_manager.max_rounds,
            debug_snap_id=debug_snap_id,
        )

    async def _call_llm(self, st: TurnState, view: ToolView) -> tuple[dict, int]:
        t0 = time.monotonic()
        msg = await llm_chat_raw(
            messages=st.tool_messages,
            model=cfg.LLM_MODEL,
            temperature=0.9,
            top_p=0.8,
            frequency_penalty=0.3,
            presence_penalty=0.2,
            max_tokens=1024,
            tools=self._resolve_active_tools(st.active_registry, view),
            tool_choice="auto",
            fallback_messages_factory=st.fallback_factory,
        )
        return msg, int((time.monotonic() - t0) * 1000)

    @staticmethod
    def _extract_calls(st: TurnState, msg: dict) -> list[dict]:
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            text_calls, cleaned_content = extract_text_tool_calls(
                msg.get("content"), st.valid_tool_names
            )
            if text_calls:
                logger.warning(
                    f"[ToolChain] {st.chat_id} 工具调用被写成正文文本，已解析为真实调用: "
                    f"{[c['function']['name'] for c in text_calls]}"
                )
                msg["content"] = cleaned_content
                msg["tool_calls"] = text_calls
                tool_calls = text_calls
        return tool_calls

    def _finalize_turn(self, st: TurnState, msg: dict, llm_ms: int) -> tuple[str, str]:
        if msg.get("_finish_reason") == "content_filter":
            logger.warning(f"[ToolChain] {st.chat_id} 回复被内容安全过滤")
            st.outcome = "filtered"
            return "Filtered", "Filtered"
        raw_ans, clean_ans = self.finalize_answer(
            strip_tool_call_markup(msg.get("content")),
            st.tools_executed,
        )
        st.tool_trace.append({
            "round": st.round_idx,
            "llm_ms": llm_ms,
            "thought": (msg.get("content") or "")[:240],
            "calls": [],
        })
        st.outcome = "reply"
        return raw_ans, clean_ans

    async def _emit_thought(self, st: TurnState, msg: dict, calls: list[dict]) -> None:
        st.tools_executed = True
        tool_names = [(c.get("function") or {}).get("name") or "" for c in calls]
        for tn in tool_names:
            if tn:
                st.tools_used.append(tn)
        logger.info(f"[ToolChain] 模型请求工具调用 chat_id={st.chat_id} tools={tool_names}")

        st.pending_thought = ""
        if "skip" not in tool_names:
            st.pending_thought = await self.send_tool_thought(
                st.chat_id,
                st.mode,
                msg.get("content"),
                st.sent_thoughts,
                tool_names,
            )

    async def _execute_batch(
        self, st: TurnState, msg: dict, calls: list[dict], llm_ms: int
    ) -> list[dict]:
        # P3 保持原写入时机：若未开写入闸门，在工具执行前先写入阶段性文本
        if st.pending_thought and not self.focus_hook.gate_exited_writes:
            decision = self.hooks.classify_persist(
                st, {"role": "assistant", "content": st.pending_thought, "is_tool_thought": True}
            )
            if decision.action != "drop":
                extra = {"focus_work": decision.focus_work} if decision.focus_work else {}
                self.history.append_session_message(
                    st.chat_id,
                    "assistant",
                    st.pending_thought,
                    is_tool_thought=True,
                    sent_realtime=True,
                    save_immediately=False,
                    return_snapshot=False,
                    **extra,
                )
            st.pending_thought = ""

        st.tool_messages.append(msg)
        t_exec0 = time.monotonic()
        results = await st.active_tool_manager.execute_tool_calls(
            calls,
            st.context,
            finish_reason=msg.get("_finish_reason") or "",
        )
        exec_ms = int((time.monotonic() - t_exec0) * 1000)
        st.tool_trace.append({
            "round": st.round_idx,
            "llm_ms": llm_ms,
            "exec_ms": exec_ms,
            "thought": (msg.get("content") or "")[:240],
            "calls": [
                {
                    "name": (c.get("function") or {}).get("name") or "",
                    "args": str((c.get("function") or {}).get("arguments") or "")[:200],
                }
                for c in calls
            ],
        })
        return results

    def _commit_batch(self, st: TurnState, msg: dict, results: list[dict]) -> None:
        self.focus_hook.collect_batch_exits(st)
        if st.pending_thought:
            decision = self.hooks.classify_persist(
                st, {"role": "assistant", "content": st.pending_thought, "is_tool_thought": True}
            )
            if decision.action != "drop":
                extra = {"focus_work": decision.focus_work} if decision.focus_work else {}
                self.history.append_session_message(
                    st.chat_id,
                    "assistant",
                    st.pending_thought,
                    is_tool_thought=True,
                    sent_realtime=True,
                    save_immediately=False,
                    return_snapshot=False,
                    **extra,
                )
            st.pending_thought = ""

        for tool_result_message in results:
            tool_name = tool_result_message.get("name")
            spec = st.active_registry.get_spec(tool_name)
            if spec is not None and not spec.persist_result:
                continue
            payload_data = self._tool_payload(tool_result_message).get("data")
            if isinstance(payload_data, dict) and payload_data.get("no_persist"):
                continue
            decision = self.hooks.classify_persist(st, tool_result_message)
            if decision.action == "drop":
                continue
            extra = {"focus_work": decision.focus_work} if decision.focus_work else {}
            self.history.append_session_message(
                st.chat_id,
                "tool",
                tool_result_message.get("content"),
                name=tool_name,
                tool_call_id=tool_result_message.get("tool_call_id"),
                save_immediately=False,
                return_snapshot=False,
                **extra,
            )
        st.tool_messages.extend(results)

    async def _finish_batch(self, st: TurnState, results: list[dict]) -> None:
        await self._attach_tool_screenshots(results, st.tool_messages)
        self.hooks.after_batch(st, results)
        remaining_budget = max(
            0,
            cfg.model.native_vision_max_images - self._used_image_slots(st.tool_messages),
        )
        await self.merge_pending_messages(st.chat_id, st.tool_messages, image_budget=remaining_budget)

    async def _close_exhausted(self, st: TurnState) -> tuple[str, str]:
        logger.warning(f"[ToolChain] {st.chat_id} 工具调用轮次用尽，转为纯文本收尾")
        closing_messages = st.tool_messages + [{
            "role": "user",
            "content": "（本轮工具调用次数已用尽，请直接用文字回复用户，不要再输出任何工具调用、"
                       "参数 JSON 或类似标记。）",
        }]
        fallback_raw = await llm_chat(
            messages=closing_messages,
            model=cfg.LLM_MODEL,
            temperature=0.8,
            top_p=0.8,
            max_tokens=1024,
            fallback_messages_factory=st.fallback_factory,
        )
        st.outcome = "exhausted"
        return self.finalize_answer(fallback_raw, st.tools_executed)

    async def chat_with_tools(self, chat_id, combined_text, session, mode, messages, message_objs=None):
        """执行支持多轮工具调用的 LLM 对话。"""
        st = await self._begin_turn(chat_id, combined_text, session, mode, messages, message_objs)
        self.hooks.on_turn_start(st)
        try:
            while st.round_idx < st.max_rounds:
                st.round_idx += 1
                self.hooks.before_llm(st)
                view = ToolView.resolve(
                    st.active_registry, focus_manager, st.chat_id, st.exited_this_turn
                )
                msg, llm_ms = await self._call_llm(st, view)
                calls = self._extract_calls(st, msg)
                if not calls:
                    st.final = self._finalize_turn(st, msg, llm_ms)
                    return st.final
                self.hooks.on_model_call(st, msg, calls)
                await self._emit_thought(st, msg, calls)
                results = await self._execute_batch(st, msg, calls, llm_ms)
                if st.context.metadata.get("skip_reply"):
                    logger.info(f"[ToolChain] {st.chat_id} 本轮选择 skip，保持安静")
                    st.outcome = "skip"
                    st.final = (SKIP_REPLY_MARKER, SKIP_REPLY_MARKER)
                    return st.final
                self._commit_batch(st, msg, results)
                await self._finish_batch(st, results)
            st.final = await self._close_exhausted(st)
            return st.final
        finally:
            self.hooks.on_turn_end(st)

    async def api_reply(self, chat_id: str, combined_text: str, session: list, mode,
                        relevant_diaries: list[Any],
                        ice_break: bool = False, debug_snapshot_id: Optional[str] = None,
                        message_objs: Optional[list[dict]] = None) -> tuple[str, str, str]:
        """构建上下文并生成最终回复。"""
        combined_api_message = await build_chat_context(
            self.yuki,
            chat_id,
            combined_text,
            {str(chat_id): session},
            mode,
            relevant_diaries,
            ice_break=ice_break,
        )
        if debug_snapshot_id:
            try:
                view = ToolView.resolve(self.tool_registry, focus_manager, chat_id)
                context_snapshot_store.update(
                    debug_snapshot_id,
                    built_messages=combined_api_message,
                    tool_context={
                        "tools_enabled": True,
                        "tool_count": len(view.visible),
                        "mode": mode,
                        "max_rounds": self.tool_manager.max_rounds,
                    },
                )
            except Exception as exc:
                logger.debug(f"[ContextDebug] 记录 LLM messages 失败: {exc}")

        if not hasattr(self, "_debug_snapshot_by_chat"):
            self._debug_snapshot_by_chat = {}
        self._debug_snapshot_by_chat[str(chat_id)] = debug_snapshot_id
        logger.info(f"[Engine] {cfg.ROBOT_NAME.title()} 正在打字...")
        try:
            yuki_answer_raw, yuki_answer = await self.chat_with_tools(
                chat_id,
                combined_text,
                session,
                mode,
                combined_api_message,
                message_objs=message_objs,
            )
            yuki_answer = strip_layout_markup(yuki_answer).strip()
            yuki_answer = re.sub(r'\n+', ' ', yuki_answer).strip()
            return yuki_answer_raw, yuki_answer, ""
        except Exception as e:
            logger.error(f"[Engine] LLM 调用失败: {e}")
            return "暂时连接不上网络", "暂时连接不上网络", ""
        finally:
            self._debug_snapshot_by_chat.pop(str(chat_id), None)
