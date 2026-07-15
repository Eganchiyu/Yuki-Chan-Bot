# core/engine_diary.py
import datetime
import json
import re

from config import cfg
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
        """总结会话内容并写入记忆库。"""
        logger.info(f"[Engine] [{chat_id}] 记忆过长，{cfg.ROBOT_NAME.title()} 正在写日记...")
        dialogue_msgs = [msg for msg in history if msg["role"] != "system"]
        content_to_summarize = json.dumps(dialogue_msgs, ensure_ascii=False)
        try:
            diary_content = await llm_chat(
                messages=[
                    {"role": "system", "content": get_base_setting()},
                    {"role": "user", "content": (
                        f"以下是需要总结的对话内容：\n{content_to_summarize}\n\n"
                        f"---任务指令---\n"
                        f"{get_summary_prompt()}"
                    )}
                ],
                model=cfg.LLM_MODEL,
                temperature=0.7,
                top_p=0.8,
                frequency_penalty=0.1,
                presence_penalty=0.0,
                max_tokens=200,
            )
            diary_content = re.sub(r'\s*FINISHED\s*$', '', diary_content, flags=re.IGNORECASE)
            diary_content = f"【日记({datetime.datetime.now().strftime('%Y-%m-%d %H:%M')})】：\n{diary_content}"
            self.rag.save_diary(diary_content, chat_id=chat_id)
            logger.info(f"[Engine] 日记已存入记忆库: {diary_content[:60]}...")

            return [msg for msg in history if msg["role"] == "system"] + dialogue_msgs[-cfg.KEEP_LAST_DIALOGUE:]

        except Exception as e:
            logger.error(f"[Engine] 写日记失败: {e}")
            return history

    async def summarize_idle_session(self, chat_id, session):
        """摘要单个空闲会话并按会话粒度回写。"""
        new_session = await self.do_summarize(int(chat_id), session)
        self.history.replace_session(chat_id, new_session)
