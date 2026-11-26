# core/engine_diary.py
import asyncio
import datetime
import json
import re

from config import cfg
from core.focus import focus_manager
from core.history_filter import dialogue_messages
from core.prompts import get_base_setting, get_summary_prompt
from modules.memory.jargon_miner import mine_jargons_background
from modules.memory.style_learner import learn_styles_background
from utils.background_tasks import spawn_background_task
from utils.llm_client import llm_chat
from utils.logger import get_logger

logger = get_logger("engine")


def merge_summarized_session(
    snapshot: list,
    summarized: list | None,
    current: list | None,
) -> list | None:
    """将压缩后的摘要会话与等待 LLM 期间新到达的消息安全合并。

    - 若 `summarized is snapshot`（摘要失败回退原引用），返回 `None` 提示跳过回写，防止覆盖回滚并发新消息；
    - 即使等待期间 `sync_system_prompts` 更新了首条 system 或 `ToolHistoryPruner` 折叠了工具消息，
      仍能通过对话消息序列/尾锚点识别增量消息并拼接到摘要尾部。
    """
    if summarized is None or summarized is snapshot:
        return None
    merged_head = list(summarized)
    if not isinstance(current, list) or not current:
        return merged_head

    # 若期间更新了 system 提示词，同步保留最新 system 消息
    if (
        merged_head
        and merged_head[0].get("role") == "system"
        and current[0].get("role") == "system"
    ):
        merged_head[0] = current[0]

    tail: list = []
    snap_len = len(snapshot)
    if len(current) >= snap_len and current[:snap_len] == snapshot:
        tail = current[snap_len:]
    else:
        snap_chats = dialogue_messages(snapshot)
        if len(current) >= snap_len and dialogue_messages(current[:snap_len]) == snap_chats:
            tail = current[snap_len:]
        elif snap_chats:
            anchor = snap_chats[-1]
            anchor_sig = (anchor.get("role"), anchor.get("content"), anchor.get("time"))
            for idx in range(len(current) - 1, -1, -1):
                msg = current[idx]
                if (
                    isinstance(msg, dict)
                    and (msg.get("role"), msg.get("content"), msg.get("time")) == anchor_sig
                ):
                    tail = current[idx + 1 :]
                    break

    return merged_head + tail


class EngineDiaryService:
    """负责会话摘要与日记写入。"""

    def __init__(self, rag, history):
        self.rag = rag
        self.history = history

    async def do_summarize(self, chat_id, history):
        """总结会话内容并写入记忆库。

        只总结聊天部分：工具执行结果（手机控件树、截图说明）与调用痕迹不进日记，
        它们是当时的临时材料，写进日记只会污染长期记忆。
        """
        logger.info(f"[Engine] [{chat_id}] 记忆过长，{cfg.ROBOT_NAME.title()} 正在写日记...")
        dialogue_msgs = dialogue_messages(history)
        if getattr(cfg, "JARGON_ENABLED", True) and dialogue_msgs:
            spawn_background_task(
                mine_jargons_background(str(chat_id), dialogue_msgs),
                name=f"mine_jargons:{chat_id}",
            )
        if getattr(cfg, "STYLE_LEARNING_ENABLED", True) and dialogue_msgs:
            spawn_background_task(
                learn_styles_background(str(chat_id), dialogue_msgs),
                name=f"learn_styles:{chat_id}",
            )
        content_to_summarize = json.dumps(dialogue_msgs, ensure_ascii=False)
        try:
            messages = [
                {"role": "system", "content": get_base_setting()},
                {"role": "user", "content": (
                    f"以下是需要总结的对话内容：\n{content_to_summarize}\n\n"
                    f"---任务指令---\n"
                    f"{get_summary_prompt()}"
                )}
            ]
            diary_content = await llm_chat(
                messages=messages,
                model=cfg.LLM_MODEL,
                temperature=0.7,
                top_p=0.8,
                frequency_penalty=0.1,
                presence_penalty=0.0,
                max_tokens=2048,
            )
            
            # 检查是否为 Filtered 或长度异常短（例如小于 50 个字符）
            if not diary_content or diary_content == "Filtered" or len(diary_content.strip()) < 50:
                logger.warning(f"[Engine] [{chat_id}] 主模型生成日记异常 (内容: {repr(diary_content)}), 重新请求重试...")
                diary_content = await llm_chat(
                    messages=messages,
                    model=None,
                    temperature=0.7,
                    top_p=0.8,
                    frequency_penalty=0.1,
                    presence_penalty=0.0,
                    max_tokens=2048,
                )

            if not diary_content or diary_content == "Filtered" or len(diary_content.strip()) < 50:
                logger.error(f"[Engine] [{chat_id}] 备用模型生成日记依然无效: {repr(diary_content)}")
                return history

            diary_content = re.sub(r'\s*FINISHED\s*$', '', diary_content, flags=re.IGNORECASE)
            diary_content = f"【日记({datetime.datetime.now().strftime('%Y-%m-%d %H:%M')})】：\n{diary_content}"
            self.rag.save_diary(diary_content, chat_id=chat_id)
            logger.info(f"[Engine] 日记已存入记忆库: {diary_content[:60]}...")

            return [msg for msg in history if msg["role"] == "system"] + dialogue_msgs[-cfg.KEEP_LAST_DIALOGUE:]

        except Exception as e:
            logger.error(f"[Engine] 写日记失败: {e}")
            return history

    async def summarize_idle_session(self, chat_id, session):
        """摘要单个空闲会话并按会话粒度回写（聚焦模式期间跳过；总结期间新到消息保留）。"""
        if focus_manager.is_focused(chat_id):
            logger.debug(f"[Engine] [{chat_id}] 处于聚焦模式中，跳过空闲日记总结")
            return
        cid_str = str(chat_id)
        normalized_cid = int(cid_str) if cid_str.isdigit() else cid_str
        summarized = await self.do_summarize(normalized_cid, session)
        current = (
            self.history.get_session(chat_id)
            if hasattr(self.history, "get_session")
            else None
        )
        merged = merge_summarized_session(session, summarized, current)
        if merged is not None:
            self.history.replace_session(chat_id, merged)
