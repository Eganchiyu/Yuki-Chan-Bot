# core/session_pipeline.py
import asyncio
import datetime
import os
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any

from config import cfg
from core.brain import YukiState
from core.reply_format import clean_visible_reply
from core.reply_watch import auto_subscribe, is_human_incoming, resolve
from modules.debug.context_snapshot import PIPELINE_STAGES, context_snapshot_store
from modules.vision.prefetch import prefetch_images, resolve_image
from utils.logger import get_logger
from utils.paths import normalize_stored_path

logger = get_logger("session_pipeline")


# ---------- 预编译正则 / 常量 ----------

_QUOTED_PREFIX_RE = re.compile(r'^【"[^"]*"】说:\s*')
_MEME_FULLMATCH_RE = re.compile(r'\[MEME:(.+?)\]', re.DOTALL)
_MEME_SPLIT_RE = re.compile(r'(\[MEME:.*?\])')

_MEME_DISCARD_SLEEP = 3.0      # 被随机丢弃时的节奏延迟
_MEME_SENT_SLEEP = 2.0         # 表情包已发送后的节奏延迟
_TEXT_SENT_SLEEP = 0.5         # 文本已发送后的节奏延迟
_MEME_RANDOM_KEEP_PROB = 0.6   # 非最后一个表情包保留概率

_ALWAYS_REPLY_MODES = frozenset({"private", "master_private"})
_REPLYABLE_MODES = frozenset({"group", "private", "master_private"})


@dataclass
class IncomingMessage:
    """管线内统一使用的入站消息，显式标记来源、归属和状态。"""
    name: str
    content: str
    raw_text: str = ""
    user_id: int | None = None
    message_id: Any = None
    is_bot: bool = False
    source: str = "napcat"
    owner_id: str = ""
    status: str = "received"
    tags: set[str] = field(default_factory=set)
    segments: list[dict] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, data: dict) -> "IncomingMessage":
        if isinstance(data, cls):
            return data
        return cls(
            name=data.get("name", ""),
            content=data.get("content", ""),
            raw_text=data.get("raw_text", ""),
            user_id=data.get("user_id"),
            message_id=data.get("message_id"),
            is_bot=bool(data.get("is_bot", False)),
            source=data.get("source", "napcat"),
            owner_id=str(data.get("owner_id", "")),
            status=data.get("status", "received"),
            tags=set(data.get("tags") or []),
            segments=list(data.get("segments") or []),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "content": self.content,
            "raw_text": self.raw_text,
            "is_bot": self.is_bot,
            "user_id": self.user_id,
            "message_id": self.message_id,
            "source": self.source,
            "owner_id": self.owner_id,
            "status": self.status,
            "tags": sorted(self.tags),
            "segments": self.segments,
        }


class SessionPipeline:
    """按 chat_id 串行运行的会话管道，负责把消息流、工具链和回复统一回写到同一 session。"""

    def __init__(self, components: dict, group_active_state: dict):
        self.sender = components["sender"]
        self.meme_processor = components["meme_processor"]
        self.yuki = components["yuki"]
        self.history_manager = components["history_manager"]
        self.memory_rag = components["memory_rag"]
        self.engine = components["engine"]
        self.sticker_manager = components.get("sticker_manager")
        self.image_store = components.get("image_store")
        self.group_active_state = group_active_state

        # --- 防抖与锁机制 ---
        self._timer_tasks: dict = {}    # chat_id -> asyncio.Task (当前正在计时的防抖任务)
        self._chat_locks: dict = {}     # chat_id -> asyncio.Lock (确保处理管线串行)
        self._skip_debounce: dict = {}  # chat_id -> bool (是否跳过本次防抖的持久化标志)

        self.last_process_end_time: dict = {}
        self.last_msg_time: dict = {}
        self._recent_msg_times: dict = {}  # chat_id -> 最近真人消息时间戳（用于估算等待）

        self.stages = [
            self.prepare_message_batch,
            self.normalize_incoming_content,
            self.prepare_chat_context,
            self.retrieve_memories,
            self.decide_reply_action,
            self.generate_reply,
            self.send_reply,
            self.finalize_conversation,
        ]

    # ---------------------------------------------------------------
    # 基础设施
    # ---------------------------------------------------------------

    def _get_lock(self, chat_id: str) -> asyncio.Lock:
        if chat_id not in self._chat_locks:
            self._chat_locks[chat_id] = asyncio.Lock()
        return self._chat_locks[chat_id]

    def _schedule_image_prefetch(self, content: str):
        """入队阶段就为消息中的图片起后台预取任务，不阻塞消息缓冲。"""
        if not cfg.IMAGE_PREFETCH_ENABLED or not self.meme_processor or not content:
            return
        try:
            _, images_info = self.meme_processor.extract_urls_from_text(content)
        except Exception as exc:
            logger.debug(f"[ImagePrefetch] 提取图片失败，跳过预取: {exc}")
            return
        prefetch_images(self.meme_processor, images_info)

    def _mark_stage(self, context, stage_name, status="done", error=None):
        snapshot_id = context.get("debug_snapshot_id")
        if not snapshot_id:
            return
        latency = dict(context.get("debug_latency") or {})
        started_at = context.get("debug_stage_started_at")
        if started_at is not None:
            latency[stage_name] = round(time.time() - started_at, 3)
            latency["total"] = round(time.time() - context.get("debug_started_at", started_at), 3)
        context["debug_latency"] = latency
        errors = list(context.get("debug_errors") or [])
        if error:
            errors.append({"stage": stage_name, "error": str(error)})
            context["debug_errors"] = errors
        try:
            context_snapshot_store.update(
                snapshot_id, stage=stage_name, stage_status=status,
                latency=latency, errors=errors,
            )
        except Exception:
            pass

    def _update_snapshot(self, context, **fields):
        snapshot_id = context.get("debug_snapshot_id")
        if not snapshot_id:
            return
        try:
            context_snapshot_store.update(snapshot_id, **fields)
        except Exception:
            pass

    # ---------------------------------------------------------------
    # 入队（防抖 + 排队）
    # ---------------------------------------------------------------

    def _append_poke_to_buffer(self, buffer: list, incoming: IncomingMessage) -> bool:
        """把「连续戳同一目标」合并成一条；返回是否已合并。"""
        if incoming.source != "napcat.notice.poke" or not buffer:
            return False
        last = buffer[-1]
        last_base = last.get("poke_base") or last.get("content")
        if (last.get("source") != "napcat.notice.poke"
                or last.get("user_id") != incoming.user_id
                or last_base != incoming.content):
            return False
        count = last.get("poke_count", 1) + 1
        last["poke_base"] = last_base
        last["poke_count"] = count
        last["content"] = f"{last_base} x{count}"
        return True

    async def enqueue_message(self, chat_id, mode, message_obj=None, debounce_flag=True,
                              force_reply=None, ice_break=False):
        """核心入列机制：写入缓冲 -> 重置定时器 -> 等待执行锁"""
        chat_id_str = str(chat_id)

        # 1. 安全写入缓冲区
        if message_obj:
            incoming = IncomingMessage.from_mapping(message_obj)
            if not incoming.owner_id:
                incoming.owner_id = chat_id_str
            buffer = self.yuki.message_buffer.setdefault(chat_id_str, [])
            if not self._append_poke_to_buffer(buffer, incoming):
                buffer.append(incoming.to_dict())
            self.last_msg_time[chat_id_str] = time.time()
            # 有人来了就算等到了：解除回复订阅，避免 Yuki 继续追击
            if is_human_incoming(incoming):
                resolve(chat_id_str, "human_message")
                self._record_human_timestamp(chat_id_str)
            # 消息一到就后台预取图片，把下载与图像理解挪出回复关键路径
            self._schedule_image_prefetch(incoming.content)

        # 2. 本轮是否需要跳过防抖：被直接叫到（名字/被 @）时上游会带
        #    debounce_flag=False + force_reply=True，这里把状态锁住供定时器读取
        should_skip = bool(force_reply) or not debounce_flag or ice_break
        if should_skip:
            self._skip_debounce[chat_id_str] = True

        # 3. 核心防抖拦截：取消还在倒计时的旧任务
        if chat_id_str in self._timer_tasks:
            self._timer_tasks[chat_id_str].cancel()

        # 4. 创建新的控制流 (按序执行：计时 -> 获取锁 -> 消费)
        async def _wait_and_process():
            try:
                # 步骤A：严格防抖。计时期间被新消息 cancel 会直接抛 CancelledError 重新排队
                if not self._skip_debounce.get(chat_id_str, False):
                    await asyncio.sleep(cfg.DEBOUNCE_TIME)

                # 步骤B：计时结束，说明这批消息落定，清空 skip 标志位以备下一轮
                self._skip_debounce[chat_id_str] = False

                # 从定时器字典中摘除自己，避免获取锁执行期间被无关新消息错误 Cancel
                if self._timer_tasks.get(chat_id_str) == asyncio.current_task():
                    self._timer_tasks.pop(chat_id_str, None)

                # 步骤C：非阻塞排队。上一个管线（如长耗时工具链）没跑完时在此等待
                async with self._get_lock(chat_id_str):
                    # 获取锁后进行空载检查
                    if not self.yuki.message_buffer.get(chat_id_str) and not force_reply and not ice_break:
                        return
                    if mode == "group" and not self.group_active_state.get(chat_id_str, True):
                        return

                    # 执行唯一的一次流转，不使用 while True 死循环
                    await self.run_once(chat_id_str, mode, debounce_flag, force_reply, ice_break)

            except asyncio.CancelledError:
                # 收到新消息，当前倒计时作废，属于防抖的正常现象
                pass
            except Exception as e:
                logger.error(f"[Pipeline] 管道处理异常 {chat_id_str}: {e}")

        task = asyncio.create_task(_wait_and_process())
        self._timer_tasks[chat_id_str] = task
        return task

    # ---------------------------------------------------------------
    # 单次流水线
    # ---------------------------------------------------------------

    def _new_pipeline_context(self, chat_id, mode, debounce_flag, force_reply, ice_break) -> dict:
        """创建单次管线上下文，集中声明跨阶段数据的初始形态。"""
        return {
            "chat_id": str(chat_id),
            "mode": mode,
            "debounce_flag": debounce_flag,
            "force_reply": force_reply,
            "ice_break": ice_break,
            "debug_started_at": time.time(),
            "debug_latency": {},
            "debug_errors": [],
        }

    async def run_once(self, chat_id, mode, debounce_flag=True, force_reply=None, ice_break=False):
        """执行单次完整的管道流水线。"""
        context = self._new_pipeline_context(chat_id, mode, debounce_flag, force_reply, ice_break)
        try:
            context["debug_snapshot_id"] = context_snapshot_store.put({
                "chat_id": str(chat_id), "mode": mode, "stage": "run_once",
                "should_reply": None, "tool_context": {"pipeline_stages": PIPELINE_STAGES},
            })
        except Exception:
            pass

        for stage in self.stages:
            stage_name = stage.__name__
            context["debug_stage_started_at"] = time.time()
            self._mark_stage(context, stage_name, status="running")
            try:
                context = await stage(context)
            except Exception as exc:
                self._mark_stage(context, stage_name, status="error", error=exc)
                raise
            self._mark_stage(context, stage_name, status="done")
            if context.get("stop"):
                self._update_snapshot(context, stage="stopped")
                return context
        return context

    # ---------------------------------------------------------------
    # 阶段一：读取缓冲
    # ---------------------------------------------------------------

    async def prepare_message_batch(self, context):
        """防抖已在外部完成，此处只需极简读取缓冲，无需任何 Sleep 逻辑"""
        chat_id, mode = context["chat_id"], context["mode"]

        if context.get("ice_break"):
            recent_msgs = self.history_manager.get_session(chat_id)[-5:]
            context["combined_text"] = "".join(
                m["content"] for m in recent_msgs if m.get("role") != "system"
            ) or "（群聊安静中）"
            context["message_objs"] = []
            context["first_time"] = time.time()
            await self.yuki.boost_activity(chat_id)
            return context

        if mode == "group" and not self.group_active_state.get(str(chat_id), True):
            self.yuki.pop_buffer(chat_id)
            context["stop"] = True
            return context

        # 发送兜底白名单：非白名单群直接终止，不生成/不发送回复
        if mode == "group" and cfg.TARGET_GROUPS and int(chat_id) not in cfg.TARGET_GROUPS:
            self.yuki.pop_buffer(chat_id)
            context["stop"] = True
            return context

        cid = str(chat_id)
        self.yuki.message_buffer.setdefault(cid, [])
        incoming_messages = self.yuki.pop_buffer(cid)
        if not incoming_messages and not context["force_reply"]:
            context["stop"] = True
            return context

        context["first_time"] = time.time()
        context["incoming_messages"] = incoming_messages
        context["message_objs"] = incoming_messages
        await self.yuki.boost_activity(chat_id)
        return context

    # ---------------------------------------------------------------
    # 阶段二：内容归一化
    # ---------------------------------------------------------------

    @staticmethod
    def _merge_consecutive_messages(incoming_messages: list[dict]) -> str:
        """合并同一用户连续消息，去掉重复前缀。"""
        merged_contents: list[str] = []
        previous_user_id = None
        for message in incoming_messages:
            user_id = message.get("user_id")
            text = message["content"]
            if user_id and user_id == previous_user_id and text.startswith("【"):
                text = _QUOTED_PREFIX_RE.sub("", text)
            merged_contents.append(text)
            previous_user_id = user_id
        return "\n".join(merged_contents)

    async def _understand_images(self, images_info: list[dict]) -> list[tuple[dict, Any]]:
        """并发解析所有图片；预取命中的直接复用结果。"""
        async def understand_one(img):
            result = await resolve_image(self.meme_processor, img["url"], img["is_meme"])
            return img, result

        return await asyncio.gather(*(understand_one(img) for img in images_info))

    @staticmethod
    def _format_image_result(img: dict, result: Any) -> tuple[str, Any]:
        """返回 (占位符替换文本, native_attachment)。"""
        is_meme = img["is_meme"]
        desc = result.get("description", "未知图片/表情") if isinstance(result, dict) else result
        desc = str(desc or "").strip()
        idx = result.get("index") if isinstance(result, dict) else None
        idx_tag = f"[img:{idx}]" if idx else ""
        kind = "表情" if is_meme else "图片"

        if result.get("native"):
            return f"[图片]{idx_tag}", result.get("attachment")
        if desc:
            if not is_meme:
                logger.debug(f"[Pipeline_meme]收到[{kind}:{desc}]{idx_tag}")
            return f"[{kind}:{desc}]{idx_tag}", None
        # 识别为空/失败时也必须占掉一个占位符，否则占位符会原样漏进模型上下文
        return f"[{kind}:未知图片/表情]{idx_tag}", None

    async def normalize_incoming_content(self, context):
        """合并消息、理解图片、解析 CQ 码，生成用户输入文本。"""
        # 破冰模式已在 prepare_message_batch 中设置 combined_text，直接跳过
        if context.get("ice_break"):
            return context

        chat_id = context["chat_id"]
        incoming_messages = context.get("incoming_messages") or context["message_objs"]

        # 更新用户昵称到 QQ 号的映射
        for m in incoming_messages:
            if m.get("user_id") and m.get("name"):
                self.yuki.user_mapping.update(chat_id, m["name"], m["user_id"])

        combined_text = self._merge_consecutive_messages(incoming_messages)

        modified_text, images_info = self.meme_processor.extract_urls_from_text(combined_text)
        native_images: list[Any] = []
        if images_info:
            understood_contents: list[str] = []
            for img, result in await self._understand_images(images_info):
                placeholder, attachment = self._format_image_result(img, result)
                if attachment:
                    native_images.append(attachment)
                understood_contents.append(placeholder)

            combined_text = modified_text
            for content in understood_contents:
                combined_text = combined_text.replace("[图片占位符]", content, 1)

        # 兜底清扫：无论上游有没有解析出图片，都不允许占位符漏给模型
        if "[图片占位符]" in combined_text:
            logger.warning("[Pipeline] 检测到未替换的图片占位符，已降级为 [图片]")
            combined_text = combined_text.replace("[图片占位符]", "[图片]")

        combined_text = await self.sender.parse_cq_codes(combined_text, chat_id)
        combined_text = combined_text.replace("\n", " | ").strip()
        logger.info(f"[Pipeline] [{chat_id}] 收到消息: {combined_text[:80]}")
        self.history_manager.append_to_log(chat_id, "User/Group", combined_text)

        context["combined_text"] = combined_text
        context["native_images"] = native_images
        self._update_snapshot(
            context, combined_text=combined_text, native_image_count=len(native_images)
        )
        return context

    # ---------------------------------------------------------------
    # 阶段三：加载上下文
    # ---------------------------------------------------------------

    async def prepare_chat_context(self, context):
        """加载上下文，确保系统提示词存在，并追加当前用户消息。"""
        logger.debug("[Pipeline] 加载上下文信息")
        chat_id = str(context["chat_id"])
        mode = context["mode"]
        system_prompt = self.yuki.get_setting(mode)

        current_time_str = datetime.datetime.now().strftime("%Y年%m月%d日%H:%M")
        session = self.history_manager.append_session_message(
            chat_id,
            "user",
            context["combined_text"],
            time=current_time_str,
            system_content=system_prompt,
            image_attachments=context.get("native_images", []),
            save_immediately=False,
        )

        context["chat_id"] = chat_id
        context["session"] = session
        context["current_time_str"] = current_time_str
        self._update_snapshot(
            context, current_time_str=current_time_str, message_count=len(session)
        )
        logger.debug("[Pipeline] 上下文加载完成")
        return context

    # ---------------------------------------------------------------
    # 阶段四：RAG 检索
    # ---------------------------------------------------------------

    async def retrieve_memories(self, context):
        """根据输入长度动态检索相关日记。"""
        if not cfg.RAG_ENABLED:
            logger.debug("[Pipeline] RAG 已关闭，跳过日记检索，直接使用上下文")
            context["relevant_diaries"] = []
            return context

        logger.debug(f"[Pipeline] {cfg.ROBOT_NAME.title()} 正在回忆")
        chat_id = context["chat_id"]
        combined_text = context["combined_text"]
        speaker_names = [
            str(message.get("name") or "").strip()
            for message in context.get("message_objs", [])
            if message.get("name")
        ]
        dynamic_top_k = 10 if len(combined_text) > 100 else 8

        relevant_diaries = self.memory_rag.search_diaries(
            combined_text,
            chat_id=chat_id,
            speaker_names=speaker_names,
            top_k_keywords=dynamic_top_k,
            n_results=8,
        )
        logger.debug(f"[Pipeline] 检索到 {len(relevant_diaries)} 条相关日记")
        logger.info(
            f"[Pipeline] [{chat_id}] 回忆 {len(relevant_diaries)} 条"
            f" | 耗时 {(time.time() - context['first_time']):.2f}s"
        )

        context["relevant_diaries"] = relevant_diaries
        self._update_snapshot(context, relevant_diaries=relevant_diaries)
        return context

    # ---------------------------------------------------------------
    # 阶段五：决策是否回复
    # ---------------------------------------------------------------

    @staticmethod
    def _compute_rag_interest(relevant_diaries: list[dict]) -> float:
        """从 RAG 结果中取纯语义分（不加权），作为群聊回复兴趣度。"""
        if not relevant_diaries:
            return 0.0
        avg = sum(d.get("relevance", d.get("score", 0)) for d in relevant_diaries) / len(relevant_diaries)
        return min(1.0, max(0.0, avg))

    async def decide_reply_action(self, context):
        """群聊中判断是否继续回复；潜水时保留用户上下文。"""
        # 破冰模式强制回复，跳过决策
        if context.get("ice_break"):
            return context

        # 私聊 / 桌宠 / 聚焦模式：永远回复，跳过群聊潜水决策
        if context["mode"] in _ALWAYS_REPLY_MODES:
            self._update_snapshot(context, should_reply=True)
            return context

        chat_id = context["chat_id"]
        session = context["session"]
        rag_interest = self._compute_rag_interest(context.get("relevant_diaries", []))

        if context["mode"] == "group" and not await self.engine.decide_to_reply(
            session,
            context["message_objs"],
            chat_id,
            force_reply=context["force_reply"],
            rag_interest=rag_interest,
        ):
            self.history_manager.replace_session(chat_id, session)
            logger.info(f"[Pipeline] {cfg.ROBOT_NAME.title()} 决定继续潜水")
            context["stop"] = True
            self._update_snapshot(context, should_reply=False)
        else:
            self._update_snapshot(context, should_reply=True)
        return context

    # ---------------------------------------------------------------
    # 阶段六：生成回复
    # ---------------------------------------------------------------

    async def generate_reply(self, context):
        """调用引擎生成回复。"""
        chat_id = context["chat_id"]
        answer_raw, answer_text, voice = await self.engine.api_reply(
            chat_id,
            context["combined_text"],
            context["session"],
            context["mode"],
            context["relevant_diaries"],
            ice_break=context.get("ice_break", False),
            debug_snapshot_id=context.get("debug_snapshot_id"),
            message_objs=context.get("message_objs", []),
        )
        logger.debug(f"[Pipeline] {cfg.ROBOT_NAME.title()} 回复生成完成")

        context["answer_raw"] = answer_raw
        context["answer_text"] = answer_text
        context["voice"] = voice
        return context

    # ---------------------------------------------------------------
    # 阶段七：发送回复（文本 / 表情包 / 语音）
    # ---------------------------------------------------------------

    @staticmethod
    def _select_kept_memes(parts: list[str]) -> set[int]:
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

    def _record_bot_message_to_shot_buffer(self, shot_live_buffer, chat_id, **kwargs):
        if not shot_live_buffer:
            return
        try:
            shot_live_buffer.append(chat_id, user_id=cfg.SELF_QQ, is_bot=True, **kwargs)
        except Exception as exc:
            logger.debug(f"[ShotMemory] 记录到截屏缓冲失败: {exc}")

    async def _send_meme_segment(self, chat_id, send_mode, meme_match, shot_live_buffer):
        if not getattr(self, "sticker_manager", None):
            return
        search_query = meme_match.group(1).strip()
        best = await self.sticker_manager.get_suitable_sticker(search_query, chat_id)
        if not best:
            return

        image_path = os.path.abspath(normalize_stored_path(best["image_ref"]))
        self.yuki.last_sent_meme[chat_id] = best["id"]

        cq_code = f"[CQ:image,file=file:///{image_path},sub_type=1]"
        await self.sender.send(chat_id, cq_code, mode=send_mode)

        self._record_bot_message_to_shot_buffer(
            shot_live_buffer, chat_id,
            name=cfg.ROBOT_NAME.title(),
            raw_text="[表情包]",
            content="[表情包]",
            segments=[{"type": "image", "data": {"file": image_path}}],
        )
        # 因为检索已经耗时，这里的强制睡眠可以大幅缩短
        await asyncio.sleep(_MEME_SENT_SLEEP)

    async def _send_text_segment(self, chat_id, send_mode, part, shot_live_buffer):
        await self.sender.send(chat_id, part, mode=send_mode)

        bot_name = cfg.ROBOT_NAME.title()
        self._record_bot_message_to_shot_buffer(
            shot_live_buffer, chat_id,
            name=bot_name,
            raw_text=part,
            content=f'【"{bot_name}"】说: {part}',
            segments=[{"type": "text", "data": {"text": part}}],
            message_id=None,
        )
        await asyncio.sleep(_TEXT_SENT_SLEEP)

    async def send_reply(self, context):
        """发送文本、表情包分段或语音回复。"""
        chat_id = context["chat_id"]
        mode = context["mode"]
        # 发送前再做一次标记归一化：兼容模型把 <layout>/[MEME] 括号写错的情况
        answer_text = clean_visible_reply(context["answer_text"])
        voice = context.get("voice")

        # master_private 使用私聊 API 发送
        send_mode = "private" if mode == "master_private" else mode

        if mode == "group":
            self.yuki.consume_energy(chat_id)

        logger.debug(
            f"[Pipeline] {cfg.ROBOT_NAME.title()} 正在发送消息 "
            f"(精力: {self.yuki.energy.get(chat_id, 0):.1f})"
        )

        # === 1. 语音直接发送 ===
        if voice:
            await self.sender.send(chat_id, voice, mode=send_mode)
            logger.info("[Pipeline] 发送语音完成")
            return context

        # deepseek 等模型有时返回空字符串，拦截并发送占位提示，避免静默无回复
        if not answer_text or not answer_text.strip():
            logger.warning(f"[Pipeline] {cfg.ROBOT_NAME.title()} 回复内容为空，拦截并发送占位提示")
            await self.sender.send(chat_id, "Yuki回复了空字符", mode=send_mode)
            return context

        # === 2. 流式发送文本与表情包 ===
        # 按 [MEME:xxx] 切分，() 保留分隔符，结果类似 ['文本1', '[MEME:关键词]', '文本2']
        parts = _MEME_SPLIT_RE.split(answer_text)
        keep_set = self._select_kept_memes(parts)

        # 延迟导入，避免潜在循环依赖
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
                await self._send_meme_segment(chat_id, send_mode, meme_match, shot_live_buffer)
            else:
                await self._send_text_segment(chat_id, send_mode, part, shot_live_buffer)

        logger.info(f"[Pipeline] 发送完成，内容: {answer_text[:80]}")
        return context

    # ---------------------------------------------------------------
    # 阶段八：收尾
    # ---------------------------------------------------------------

    def _record_human_timestamp(self, chat_id: str):
        """记录真人消息时间，保留最近若干条用于估算平均间隔。"""
        stamps = self._recent_msg_times.setdefault(chat_id, [])
        stamps.append(time.time())
        if len(stamps) > 16:
            del stamps[:-16]

    def _maybe_subscribe_reply(self, context):
        """回复发出后，若像在等人回答，就静默订阅一段时间。"""
        answer_text = context.get("answer_text") or ""
        if not answer_text.strip():
            return None
        # 破冰和注入事件不订阅，避免自己套自己
        if context.get("ice_break"):
            return None
        message_objs = context.get("message_objs") or []
        if any(m.get("is_reply_watch_event") or m.get("is_timer_event") for m in message_objs):
            return None
        # 只有真正发给人的模式才订阅
        if context.get("mode") not in _REPLYABLE_MODES:
            return None

        callback = getattr(self.engine, "process_callback", None)
        if callback is None:
            return None

        chat_id = str(context["chat_id"])
        energy = float(getattr(self.yuki, "energy", {}).get(chat_id, 0.0))
        activity = float(getattr(self.yuki, "group_activity", {}).get(chat_id, 0.0))
        try:
            bioclock = YukiState.get_smooth_time_weight()
        except Exception:
            bioclock = 1.0

        return auto_subscribe(
            chat_id,
            context["mode"],
            callback,
            answer_text,
            energy_ratio=energy / max(1.0, float(cfg.MAX_ENERGY)),
            bioclock_ratio=(bioclock - 0.2) / 1.3,
            activity_ratio=min(activity / 5.0, 1.0),
            recent_times=list(self._recent_msg_times.get(chat_id, [])),
        )

    async def finalize_conversation(self, context):
        """保存回复上下文，并在历史过长时触发总结。"""
        chat_id = context["chat_id"]
        answer_text = context["answer_text"]

        # 她刚才那句话像在等人回答，就静默等她一会儿
        try:
            self._maybe_subscribe_reply(context)
        except Exception as exc:
            logger.warning(f"[Pipeline] 自动订阅判定失败 {chat_id}: {exc}")

        logger.debug(f"[Pipeline] {cfg.ROBOT_NAME.title()} 正在保存上下文")
        self.history_manager.append_to_log(chat_id, cfg.ROBOT_NAME.title(), answer_text)
        session = self.history_manager.append_session_message(
            chat_id, "assistant", context["answer_raw"], time=context["current_time_str"]
        )
        self._update_snapshot(context, answer_text=answer_text, message_count=len(session))
        logger.debug("[Pipeline] 上下文保存完成")

        # 记录本次处理完成时间，用于冷启动判断
        self.last_process_end_time[chat_id] = time.time()

        # 递减用户映射表 TTL
        self.yuki.user_mapping.tick(chat_id)

        # 递增图片索引轮次，清理过期图片
        if self.image_store:
            self.image_store.tick()

        if len(session) > cfg.DIARY_MAX_LENGTH:
            history_snapshot = session.copy()
            self.history_manager.replace_session(chat_id, [session[0]])
            asyncio.create_task(self._background_summarize(chat_id, history_snapshot))

        # 破冰模式：递增失败计数
        if context.get("ice_break"):
            async with self.yuki.lock:
                self.yuki.ice_break_fail_count[chat_id] = (
                    self.yuki.ice_break_fail_count.get(chat_id, 0) + 1
                )
            logger.info(f"[Pipeline] {chat_id} 破冰计数递增至 {self.yuki.ice_break_fail_count[chat_id]}")

        return context

    async def _background_summarize(self, chat_id, history_snapshot):
        """后台处理摘要，不阻塞主流程。"""
        try:
            summarized_list = await self.engine.do_summarize(chat_id, history_snapshot)
            self.history_manager.replace_session(chat_id, summarized_list)
            logger.info(f"[Pipeline] [{chat_id}] 日记写入完成，历史已同步")
        except Exception as e:
            logger.error(f"[Pipeline] [{chat_id}] 后台摘要失败: {e}")