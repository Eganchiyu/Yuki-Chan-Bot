# core/engine_reply.py
import re
from typing import Any, Callable, Optional

from config import cfg
from core.prompts import build_chat_context
from core.toolchain import ToolContext, ToolRuntime
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
    ):
        self.yuki = yuki
        self.history = history
        self.sender = sender
        self.tool_registry = tool_registry
        self.tool_manager = tool_manager
        self.get_process_callback = get_process_callback
        self.get_image_store = get_image_store

    @staticmethod
    def clean_visible_reply(content):
        """清理工具链期间可对外发送的回复文本。"""
        if not content:
            return ""
        clean_content = re.sub(r'\s*FINISHED\s*$', '', content, flags=re.IGNORECASE).strip()
        clean_content = re.sub(r'<layout>.*?</layout>', '', clean_content, flags=re.DOTALL).strip()
        return clean_content

    def merge_pending_messages(self, chat_id, tool_messages):
        """工具调用间隙合并同群新消息，避免消息流分叉。"""
        pending_objs = self.yuki.message_buffer.get(chat_id) or self.yuki.message_buffer.get(str(chat_id))
        if not pending_objs:
            return
        pending_objs = self.yuki.pop_buffer(chat_id)
        pending_text = "\n".join([m["content"] for m in pending_objs]).replace("\n", "  ").strip()
        if not pending_text:
            return
        logger.info(f"[ToolChain] {chat_id} 合并工具调用期间新增消息: {pending_text}")
        self.history.append_session_message(chat_id, "user", pending_text, is_pending_during_tool=True)
        tool_messages.append({"role": "user", "content": f"【工具调用期间新增消息】{pending_text}"})

    async def send_tool_thought(self, chat_id, mode, content, sent_thoughts, tool_names=None):
        """实时发送工具链中模型产生的阶段性文本。"""
        clean_content = self.clean_visible_reply(content)
        if not clean_content or clean_content in sent_thoughts:
            return ""

        display_content = re.sub(r'\[MEME:.+?\]', '', clean_content, flags=re.DOTALL).strip()
        if tool_names and "delegate_to_maid" in tool_names:
            display_content = clean_content + " | (๑•̀ㅂ•́)و💻"
        if display_content:
            if mode == "desktop_pet":
                from modules.LiveYukiL2D.server import broadcast
                await broadcast({"type": "say", "text": display_content})
            else:
                send_mode = "private" if mode == "master_private" else mode
                await self.sender.send(chat_id, display_content, mode=send_mode)
        sent_thoughts.add(clean_content)
        logger.info(f"[ToolChain] 实时发送阶段性文本 chat_id={chat_id}: {clean_content}")
        return clean_content

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
        self.tool_manager.start_session(str(chat_id), combined_text)
        tool_messages = list(messages)
        sent_thoughts = set()

        try:
            for _ in range(self.tool_manager.max_rounds):
                response_message = await llm_chat_raw(
                    messages=tool_messages,
                    model=cfg.LLM_MODEL,
                    temperature=1.1,
                    top_p=0.9,
                    frequency_penalty=0.5,
                    presence_penalty=0.4,
                    max_tokens=520,
                    tools=self.tool_registry.get_tools(),
                    tool_choice="auto",
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
                        )
                else:
                    answer = self.clean_visible_reply(response_message.get("content"))
                    return answer, answer

                tool_messages.append(response_message)
                tool_result_messages = await self.tool_manager.execute_tool_calls(tool_calls, context)
                for tool_result_message in tool_result_messages:
                    self.history.append_session_message(
                        chat_id,
                        "tool",
                        tool_result_message.get("content"),
                        name=tool_result_message.get("name"),
                        tool_call_id=tool_result_message.get("tool_call_id"),
                    )
                tool_messages.extend(tool_result_messages)
                self.merge_pending_messages(chat_id, tool_messages)

            fallback = await llm_chat(
                messages=tool_messages,
                model=cfg.LLM_MODEL,
                temperature=0.8,
                top_p=0.8,
                max_tokens=220,
            )
            fallback = self.clean_visible_reply(fallback)
            return fallback, fallback
        finally:
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
                        "tool_count": len(self.tool_registry.get_tools()),
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
            yuki_answer = re.sub(r'<layout>.*?</layout>', '', yuki_answer, flags=re.DOTALL).strip()
            yuki_answer = re.sub(r'\n+', ' ', yuki_answer).strip()
            return yuki_answer_raw, yuki_answer, ""
        except Exception as e:
            logger.error(f"[Engine] LLM 调用失败: {e}")
            return "API 接口调用失败", "API 接口调用失败", ""
