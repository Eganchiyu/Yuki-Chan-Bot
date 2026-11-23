# core/outbound_sender.py
"""出站消息分段发送服务：封装表情包抽样检索、语义断句、Filtered 彩蛋、语音与截屏缓冲记账。"""
from __future__ import annotations

import asyncio
import os
import random
import re
from typing import Any, Callable

from config import cfg
from core.reply_format import clean_visible_reply
from utils import BASE_DIR
from utils.logger import get_logger
from utils.paths import normalize_stored_path

logger = get_logger("outbound_sender")

_MEME_FULLMATCH_RE = re.compile(r"\[MEME:(.+?)\]", re.DOTALL)
_MEME_SPLIT_RE = re.compile(r"(\[MEME:.*?\])")

_MEME_DISCARD_SLEEP = 3.0      # 被随机丢弃时的节奏延迟
_MEME_SENT_SLEEP = 2.0         # 表情包已发送后的节奏延迟
_TEXT_SENT_SLEEP = 0.5         # 文本已发送后的节奏延迟
_MEME_RANDOM_KEEP_PROB = 0.6   # 非最后一个表情包保留概率

_FILTERED_EGG_IMAGE = os.path.join(BASE_DIR, "output", "reference", "Filtered.jpg")
_FILTERED_EGG_CQ = f"[CQ:image,file=file:///{os.path.abspath(_FILTERED_EGG_IMAGE)},sub_type=1]"


def select_kept_memes(parts: list[str]) -> set[int]:
    """决定哪些 [MEME] 片段保留：最后一个必留，其余按概率保留。"""
    meme_indices = [
        i for i, part in enumerate(parts) if _MEME_FULLMATCH_RE.fullmatch(part.strip())
    ]
    keep: set[int] = set()
    if not meme_indices:
        return keep
    keep.add(meme_indices[-1])
    for idx in meme_indices[:-1]:
        if random.random() >= _MEME_RANDOM_KEEP_PROB:
            keep.add(idx)
    return keep


def valid_message_id(mid: Any) -> str | None:
    if isinstance(mid, bool) or mid is None:
        return None
    if isinstance(mid, (int, str)):
        val = str(mid).strip()
        return val if val else None
    return None


def record_sent_message_id(context: dict, mid: Any) -> str | None:
    valid = valid_message_id(mid)
    if valid is not None:
        context.setdefault("sent_message_ids", []).append(valid)
    return valid


class OutboundReplySender:
    """负责把引擎生成的可见回复按气泡节奏发往网关。"""

    def __init__(
        self,
        *,
        get_sender: Callable[[], Any],
        get_yuki: Callable[[], Any],
        get_sticker_manager: Callable[[], Any],
    ) -> None:
        self._get_sender = get_sender
        self._get_yuki = get_yuki
        self._get_sticker_manager = get_sticker_manager

    @staticmethod
    def record_bot_message_to_shot_buffer(shot_live_buffer: Any, chat_id: Any, **kwargs: Any) -> None:
        if not shot_live_buffer:
            return
        try:
            shot_live_buffer.append(chat_id, user_id=cfg.SELF_QQ, is_bot=True, **kwargs)
        except Exception as exc:
            logger.debug(f"[ShotMemory] 记录到截屏缓冲失败: {exc}")

    async def send_meme_segment(
        self,
        chat_id: Any,
        send_mode: str,
        meme_match: re.Match[str],
        shot_live_buffer: Any,
        context: dict | None = None,
    ) -> None:
        sticker_manager = self._get_sticker_manager()
        if not sticker_manager:
            return
        search_query = meme_match.group(1).strip()
        best = await sticker_manager.get_suitable_sticker(search_query, chat_id)
        if not best:
            return

        image_path = os.path.abspath(normalize_stored_path(best["image_ref"]))
        yuki = self._get_yuki()
        if yuki is not None and hasattr(yuki, "last_sent_meme"):
            yuki.last_sent_meme[chat_id] = best["id"]

        cq_code = f"[CQ:image,file=file:///{image_path},sub_type=1]"
        sent_raw = await self._get_sender().send(chat_id, cq_code, mode=send_mode)
        sent_id = (
            record_sent_message_id(context, sent_raw)
            if context is not None
            else valid_message_id(sent_raw)
        )

        self.record_bot_message_to_shot_buffer(
            shot_live_buffer,
            chat_id,
            name=cfg.ROBOT_NAME.title(),
            raw_text="[表情包]",
            content="[表情包]",
            segments=[{"type": "image", "data": {"file": image_path}}],
            message_id=sent_id,
        )
        await asyncio.sleep(_MEME_SENT_SLEEP)

    async def send_text_segment(
        self,
        chat_id: Any,
        send_mode: str,
        part: str,
        shot_live_buffer: Any,
        context: dict | None = None,
    ) -> None:
        sent_raw = await self._get_sender().send(chat_id, part, mode=send_mode)
        sent_id = (
            record_sent_message_id(context, sent_raw)
            if context is not None
            else valid_message_id(sent_raw)
        )

        bot_name = cfg.ROBOT_NAME.title()
        self.record_bot_message_to_shot_buffer(
            shot_live_buffer,
            chat_id,
            name=bot_name,
            raw_text=part,
            content=f'【"{bot_name}"】说: {part}',
            segments=[{"type": "text", "data": {"text": part}}],
            message_id=sent_id,
        )
        await asyncio.sleep(_TEXT_SENT_SLEEP)

    async def send_reply(self, context: dict) -> dict:
        """发送文本、表情包分段或语音回复。"""
        chat_id = context["chat_id"]
        mode = context["mode"]
        context.setdefault("sent_message_ids", [])
        answer_text = clean_visible_reply(context["answer_text"])
        voice = context.get("voice")
        send_mode = "private" if mode == "master_private" else mode

        yuki = self._get_yuki()
        if mode == "group" and yuki is not None:
            yuki.consume_energy(chat_id)

        energy_val = getattr(yuki, "energy", {}).get(chat_id, 0) if yuki is not None else 0
        logger.debug(
            f"[Pipeline] {cfg.ROBOT_NAME.title()} 正在发送消息 (精力: {energy_val:.1f})"
        )

        sender = self._get_sender()

        if voice:
            record_sent_message_id(context, await sender.send(chat_id, voice, mode=send_mode))
            logger.info("[Pipeline] 发送语音完成")
            return context

        if answer_text.strip() == "Filtered":
            if os.path.isfile(_FILTERED_EGG_IMAGE):
                logger.info(f"[Pipeline] {cfg.ROBOT_NAME.title()} 回复被过滤，改发 filtered 表情包")
                record_sent_message_id(
                    context, await sender.send(chat_id, _FILTERED_EGG_CQ, mode=send_mode)
                )
            else:
                logger.warning(
                    f"[Pipeline] filtered 彩蛋图片缺失，回落发送原文本: {_FILTERED_EGG_IMAGE}"
                )
                record_sent_message_id(
                    context, await sender.send(chat_id, "Filtered", mode=send_mode)
                )
            return context

        if not answer_text or not answer_text.strip():
            logger.warning(f"[Pipeline] {cfg.ROBOT_NAME.title()} 回复内容为空，拦截并发送占位提示")
            record_sent_message_id(
                context, await sender.send(chat_id, "Yuki回复了空字符", mode=send_mode)
            )
            return context

        parts = _MEME_SPLIT_RE.split(answer_text)
        keep_set = select_kept_memes(parts)

        try:
            from modules.shot_memory import shot_live_buffer
        except ImportError:
            shot_live_buffer = None

        for part_idx, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue

            meme_match = _MEME_FULLMATCH_RE.fullmatch(part)
            if meme_match:
                if part_idx not in keep_set:
                    logger.debug(f"[Pipeline] 表情包被随机丢弃: {part}")
                    await asyncio.sleep(_MEME_DISCARD_SLEEP)
                    continue
                await self.send_meme_segment(
                    chat_id, send_mode, meme_match, shot_live_buffer, context=context
                )
            else:
                if getattr(cfg, "SENTENCE_SPLIT_ENABLED", True):
                    from core.sentence_splitter import split_text_with_llm

                    sub_parts = await split_text_with_llm(part)
                else:
                    sub_parts = [part]
                for sub_part in sub_parts:
                    sub_part = sub_part.strip()
                    if sub_part:
                        await self.send_text_segment(
                            chat_id, send_mode, sub_part, shot_live_buffer, context=context
                        )

        logger.info(f"[Pipeline] 发送完成，内容: {answer_text[:80]}")
        return context
