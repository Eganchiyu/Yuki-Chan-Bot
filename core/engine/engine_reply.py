# core/engine_reply.py
import re
from typing import Any, Callable, Optional

from config import cfg
from core.prompts import build_chat_context
from core.reply_format import (
    clean_visible_reply,
    normalize_reply_markup,
    strip_layout_markup,
    strip_meme_tags,
)
from core.toolchain import ToolCallManager, ToolContext, ToolRuntime
from modules.debug.context_snapshot import context_snapshot_store
from utils.llm_client import llm_chat, llm_chat_raw
from utils.logger import get_logger

logger = get_logger("engine")


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
        self.tool_registry_provider = tool_registry
        self.tool_registry = tool_registry.get_registry() if hasattr(tool_registry, "get_registry") else tool_registry
        self.tool_manager = tool_manager
        self.get_process_callback = get_process_callback
        self.get_image_store = get_image_store
        self.get_meme_processor = get_meme_processor

    @staticmethod
    def clean_visible_reply(content):
        """清理工具链期间可对外发送的回复文本（含括号写错的标记变体）。"""
        return clean_visible_reply(content)

    async def _resolve_pending_image(self, meme_processor, img):
        """工具调用期间新增图片，按与主管线一致的开关处理。"""
        url, is_meme = img["url"], img["is_meme"]
        if cfg.LLM_NATIVE_VISION_ENABLED and not is_meme and self.get_image_store():
            result = await meme_processor.register_from_url(url)
            if result.get("attachment"):
                return f"[图片]{self._idx_tag(result.get('index'))}", result["attachment"]
        result = await meme_processor.understand_from_url(url, is_meme=is_meme)
        desc = result.get("description") or "未知图片/表情"
        kind = "表情" if is_meme else "图片"
        return f"[{kind}:{desc}]{self._idx_tag(result.get('index'))}", None

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
            if mode in {"desktop_pet", "browser_interaction"}:
                from modules.LiveYukiL2D.server import broadcast
                await broadcast({"type": "say", "text": display_content})
            else:
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

    async def chat_with_tools(self, chat_id, combined_text, session, mode, messages, message_objs=None):
        """执行支持多轮工具调用的 LLM 对话。"""
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
        active_registry = (
            self.tool_registry_provider.get_registry(mode)
            if hasattr(self.tool_registry_provider, "get_registry")
            else self.tool_registry
        )
        active_tool_manager = ToolCallManager(active_registry, max_rounds=self.tool_manager.max_rounds)
        self.tool_manager.start_session(str(chat_id), combined_text)

        async def build_backup_messages():
            """备用线路不支持视觉时，按需把图片附件转写为文本。"""
            return await self._prepare_model_messages(messages, native_vision=False)

        native_vision_enabled = cfg.LLM_NATIVE_VISION_ENABLED
        tool_messages = await self._prepare_model_messages(messages, native_vision=native_vision_enabled)
        fallback_factory = None
        if native_vision_enabled and not cfg.BACKUP_NATIVE_VISION_ENABLED:
            fallback_factory = build_backup_messages
        sent_thoughts = set()

        try:
            for _ in range(active_tool_manager.max_rounds):
                response_message = await llm_chat_raw(
                    messages=tool_messages,
                    model=cfg.LLM_MODEL,
                    temperature=0.9,
                    top_p=0.8,
                    frequency_penalty=0.3,
                    presence_penalty=0.2,
                    max_tokens=1024,
                    tools=active_registry.get_tools(),
                    tool_choice="auto",
                    fallback_messages_factory=fallback_factory,
                )
                tool_calls = response_message.get("tool_calls") or []
                if tool_calls:
                    tool_names = [
                        call.get("function", {}).get("name", "")
                        for call in tool_calls
                    ]
                    logger.info(f"[ToolChain] 模型请求工具调用 chat_id={chat_id} tools={tool_names}")

                    sent_content = await self.send_tool_thought(
                        chat_id,
                        mode,
                        response_message.get("content"),
                        sent_thoughts,
                        tool_names,
                    )
                    if sent_content:
                        self.history.append_session_message(
                            chat_id,
                            "assistant",
                            sent_content,
                            is_tool_thought=True,
                            sent_realtime=True,
                            save_immediately=False,
                            return_snapshot=False,
                        )
                else:
                    if response_message.get("_finish_reason") == "content_filter":
                        logger.warning(f"[ToolChain] {chat_id} 回复被内容安全过滤")
                        return "Filtered", "Filtered"
                    raw_answer = response_message.get("content")
                    answer = self.clean_visible_reply(raw_answer)
                    # 写回历史的原始回复先归一化标记，避免错误格式被模型学走
                    return normalize_reply_markup(raw_answer), answer

                tool_messages.append(response_message)
                tool_result_messages = await active_tool_manager.execute_tool_calls(tool_calls, context)
                for tool_result_message in tool_result_messages:
                    self.history.append_session_message(
                        chat_id,
                        "tool",
                        tool_result_message.get("content"),
                        name=tool_result_message.get("name"),
                        tool_call_id=tool_result_message.get("tool_call_id"),
                        save_immediately=False,
                        return_snapshot=False,
                    )
                    if mode == "browser_interaction":
                        await self.yuki.mode_manager.record_step(
                            f"调用工具 {tool_result_message.get('name')}"
                        )
                tool_messages.extend(tool_result_messages)
                remaining_budget = max(
                    0,
                    cfg.model.native_vision_max_images - self._used_image_slots(tool_messages),
                )
                await self.merge_pending_messages(chat_id, tool_messages, image_budget=remaining_budget)

            fallback_raw = await llm_chat(
                messages=tool_messages,
                model=cfg.LLM_MODEL,
                temperature=0.8,
                top_p=0.8,
                max_tokens=1024,
                fallback_messages_factory=fallback_factory,
            )
            return normalize_reply_markup(fallback_raw), self.clean_visible_reply(fallback_raw)
        finally:
            active_tool_manager.finish_session(str(chat_id))
            self.tool_manager.finish_session(str(chat_id))

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
                context_snapshot_store.update(
                    debug_snapshot_id,
                    built_messages=combined_api_message,
                    tool_context={
                        "tools_enabled": True,
                        "tool_count": len(
                            self.tool_registry_provider.get_tools(mode)
                            if hasattr(self.tool_registry_provider, "get_tools")
                            else self.tool_registry.get_tools()
                        ),
                        "mode": mode,
                        "max_rounds": self.tool_manager.max_rounds,
                    },
                )
            except Exception as exc:
                logger.debug(f"[ContextDebug] 记录 LLM messages 失败: {exc}")

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
