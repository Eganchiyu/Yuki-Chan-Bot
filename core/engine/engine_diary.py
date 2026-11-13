# core/engine_diary.py
import datetime
import json
import re

from config import cfg
from core.focus import focus_manager
from core.history_filter import dialogue_messages
from core.prompts import get_base_setting, get_summary_prompt
from utils.llm_client import llm_chat
from utils.logger import get_logger

logger = get_logger("engine")


class EngineDiaryService:
    """负责会话摘要与日记写入。"""

    def __init__(self, rag, history):
        self.rag = rag
        self.history = history

    async def do_summarize(self, chat_id, history):
        """总结会话内容并写入记忆库。

        只总结聊天部分：工具执行结果（bash 输出、手机控件树）与调用痕迹不进日记，
        它们是当时的临时材料，写进日记只会污染长期记忆。
        """
        logger.info(f"[Engine] [{chat_id}] 记忆过长，{cfg.ROBOT_NAME.title()} 正在写日记...")
        dialogue_msgs = dialogue_messages(history)
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
                logger.warning(f"[Engine] [{chat_id}] 主模型生成日记异常 (内容: {repr(diary_content)}), 切换备用模型重试...")
                diary_content = await llm_chat(
                    messages=messages,
                    model=cfg.BACKUP_MODEL,
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
        """摘要单个空闲会话并按会话粒度回写（聚焦模式期间跳过）。"""
        if focus_manager.is_focused(chat_id):
            logger.debug(f"[Engine] [{chat_id}] 处于聚焦模式中，跳过空闲日记总结")
            return
        new_session = await self.do_summarize(int(chat_id), session)
        self.history.replace_session(chat_id, new_session)
