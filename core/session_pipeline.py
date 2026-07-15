# core/session_pipeline.py
import asyncio
import datetime
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

from config import cfg
from modules.debug.context_snapshot import PIPELINE_STAGES, context_snapshot_store
from utils.logger import get_logger

logger = get_logger("session_pipeline")


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
        self.connector = components["connector"]
        self.sender = components["sender"]
        self.parser = components["parser"]
        self.meme_processor = components["meme_processor"]
        self.yuki = components["yuki"]
        self.history_manager = components["history_manager"]
        self.memory_rag = components["memory_rag"]
        self.engine = components["engine"]
        self.sticker_manager = components.get("sticker_manager")
        self.image_store = components.get("image_store")
        self.group_active_state = group_active_state

        # --- 极简重构的防抖与锁机制 ---
        self._timer_tasks: dict = {}  # chat_id -> asyncio.Task (当前正在计时的防抖任务)
        self._chat_locks: dict = {}  # chat_id -> asyncio.Lock (确保处理管线串行)
        self._skip_debounce: dict = {}  # chat_id -> bool (是否跳过本次防抖的持久化标志)

        self.last_process_end_time: dict = {}
        self._chat_mode: dict = {}
        self.last_msg_time = {}

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

    def _get_lock(self, chat_id: str) -> asyncio.Lock:
        if chat_id not in self._chat_locks:
            self._chat_locks[chat_id] = asyncio.Lock()
        return self._chat_locks[chat_id]

    # (保留原本的 _mark_stage 和 _update_snapshot 不变)
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
            context_snapshot_store.update(snapshot_id, stage=stage_name, stage_status=status, latency=latency,
                                          errors=errors)
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

    # ------------------- 核心逻辑重写 -------------------

    async def enqueue_message(self, chat_id, mode, message_obj=None, debounce_flag=True, force_reply=None,
                              ice_break=False):
        """核心入列机制：写入缓冲 -> 重置定时器 -> 等待执行锁"""
        chat_id_str = str(chat_id)
        self._chat_mode[chat_id_str] = mode

        # 1. 安全写入缓冲区
        if message_obj:
            incoming_message = IncomingMessage.from_mapping(message_obj)
            if not incoming_message.owner_id:
                incoming_message.owner_id = chat_id_str
            self.yuki.message_buffer.setdefault(chat_id_str, [])
            self.yuki.message_buffer[chat_id_str].append(incoming_message.to_dict())
            self.last_msg_time[chat_id_str] = time.time()

        # 2. 状态融合：只要当前批次中有任何要求跳过防抖的指令，立刻锁定 skip 状态
        # (修复 Bug：解决普通消息覆盖了 wake_quickly 导致叫名字依然防抖的问题)
        should_skip = (force_reply is not None and force_reply) or (not debounce_flag) or ice_break
        if should_skip:
            self._skip_debounce[chat_id_str] = True

        # 3. 核心防抖拦截：取消还在倒计时的旧任务
        if chat_id_str in self._timer_tasks:
            self._timer_tasks[chat_id_str].cancel()

        # 4. 创建新的控制流 (按序执行：计时 -> 获取锁 -> 消费)
        async def _wait_and_process():
            try:
                # 步骤A：严格防抖。如果在计时期间被新消息 cancel，会直接抛出 CancelledError 重新排队
                if not self._skip_debounce.get(chat_id_str, False):
                    await asyncio.sleep(cfg.DEBOUNCE_TIME)

                # 步骤B：计时结束，说明这批消息落定，清空 skip 标志位以备下一轮
                self._skip_debounce[chat_id_str] = False

                # 从定时器字典中将自己摘除，防止在获取锁执行期间，被无关的新消息错误 Cancel
                if self._timer_tasks.get(chat_id_str) == asyncio.current_task():
                    self._timer_tasks.pop(chat_id_str, None)

                # 步骤C：非阻塞排队。如果上一个管线（例如长耗时的工具链调用）还没跑完，这里乖乖等待
                # (修复 Bug：解决工具链期间新消息直接被消费没有防抖，现在它们会先防抖，然后在这里等锁)
                async with self._get_lock(chat_id_str):
                    # 获取锁后进行空载检查
                    if not self.yuki.message_buffer.get(chat_id_str) and not force_reply and not ice_break:
                        return
                    if mode == "group" and not self.group_active_state.get(chat_id_str, True):
                        return

                    # 执行唯一的一次流转，不使用 while True 死循环
                    await self.run_once(chat_id_str, mode, debounce_flag, force_reply, ice_break)

            except asyncio.CancelledError:
                # 收到新消息，当前倒计时作废，这属于防抖的正常现象
                pass
            except Exception as e:
                logger.error(f"[Pipeline] 管道处理异常 {chat_id_str}: {e}")

        task = asyncio.create_task(_wait_and_process())
        self._timer_tasks[chat_id_str] = task
        return task

    def wake_quickly(self, chat_id):
        """收到呼叫时：直接设置强制跳过防抖状态，并重置控制流"""
        cid = str(chat_id)
        self._skip_debounce[cid] = True  # 锁定本轮无视防抖

        mode = self._chat_mode.get(cid, "group")
        # 直接调用入列方法刷新流程
        asyncio.create_task(self.enqueue_message(cid, mode, debounce_flag=False, force_reply=True))

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
                "should_reply": None, "tool_context": {"pipeline_stages": PIPELINE_STAGES}
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

    # ------------------- 阶段一精简 -------------------
    async def prepare_message_batch(self, context):
        """防抖已在外部完成，此处只需极简读取缓冲，无需任何 Sleep 逻辑"""
        chat_id, mode = context["chat_id"], context["mode"]

        if context.get("ice_break"):
            recent_msgs = self.history_manager.load().get(str(chat_id), [])[-5:]
            context["combined_text"] = "".join(
                [m['content'] for m in recent_msgs if m.get("role") != "system"]) or "（群聊安静中）"
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
        if cid not in self.yuki.message_buffer:
            self.yuki.message_buffer[cid] = []

        incoming_messages = self.yuki.pop_buffer(cid)
        if not incoming_messages and not context["force_reply"]:
            context["stop"] = True
            return context

        context["first_time"] = time.time()
        context["incoming_messages"] = incoming_messages
        context["message_objs"] = incoming_messages
        await self.yuki.boost_activity(chat_id)
        return context

    # ------------------- 后续阶段（除 finalize 记录时间外无改动） -------------------
    async def normalize_incoming_content(self, context):
        """合并消息、理解图片、解析 CQ 码，生成用户输入文本。"""
        # 破冰模式已在 prepare_message_batch 中设置 combined_text，直接跳过
        if context.get("ice_break"):
            return context

        chat_id = context["chat_id"]
        incoming_messages = context.get("incoming_messages") or context["message_objs"]

        # 更新用户昵称到QQ号的映射
        for m in incoming_messages:
            if m.get("user_id") and m.get("name"):
                self.yuki.user_mapping.update(chat_id, m["name"], m["user_id"])
        # ========================================

        # 合并同一用户连续消息，去掉重复前缀
        merged_contents = []
        previous_user_id = None
        for message in incoming_messages:
            user_id = message.get("user_id")
            text = message["content"]
            if user_id and user_id == previous_user_id and text.startswith("【"):
                # 同一用户连续消息，去掉前缀
                text = re.sub(r'^【"[^"]*"】说:\s*', '', text)
            merged_contents.append(text)
            previous_user_id = user_id
        combined_text = "\n".join(merged_contents)

        modified_text, images_info = self.meme_processor.extract_urls_from_text(combined_text)
        if images_info:
            # 并发执行所有图片理解
            async def understand_image(img):
                url = img["url"]
                is_meme = img["is_meme"]
                result = await self.meme_processor.understand_from_url(url, is_meme=is_meme)
                return img, result

            tasks = [understand_image(img) for img in images_info]
            results = await asyncio.gather(*tasks)

            understood_contents = []
            for img, result in results:
                is_meme = img["is_meme"]
                desc = result.get("description", "未知图片/表情") if isinstance(result, dict) else result
                idx = result.get("index") if isinstance(result, dict) else None
                idx_tag = f"[img:{idx}]" if idx else ""

                if is_meme and desc:
                    understood_contents.append(f"[表情:{desc}]{idx_tag}")
                elif not is_meme and desc:
                    understood_contents.append(f"[图片:{desc}]{idx_tag}")
                    logger.debug(f"[Pipeline_meme]收到[图片:{desc}]{idx_tag}")

            combined_text = modified_text
            for content in understood_contents:
                combined_text = combined_text.replace("[图片占位符]", content, 1)

        combined_text = await self.parser.parse_all_cq_codes(combined_text, chat_id)
        combined_text = combined_text.replace("\n", " | ").strip()
        logger.info(f"[Pipeline] [{chat_id}] 收到消息: {combined_text[:80]}")
        self.history_manager.append_to_log(chat_id, "User/Group", combined_text)

        context["combined_text"] = combined_text
        self._update_snapshot(context, combined_text=combined_text)
        return context

    async def prepare_chat_context(self, context):
        """加载上下文，确保系统提示词存在，并追加当前用户消息。"""
        logger.info("[Pipeline] 加载上下文信息")
        history_dict = self.history_manager.load()
        chat_id = str(context["chat_id"])
        mode = context["mode"]

        if chat_id not in history_dict or not history_dict[chat_id]:
            history_dict[chat_id] = [{"role": "system", "content": self.yuki.get_setting(mode)}]
        elif history_dict[chat_id][0].get("role") != "system":
            history_dict[chat_id].insert(0, {"role": "system", "content": self.yuki.get_setting(mode)})

        current_time_str = datetime.datetime.now().strftime("%Y年%m月%d日%H:%M")
        history_dict[chat_id].append({
            "role": "user",
            "content": context["combined_text"],
            "time": current_time_str,
        })

        context["chat_id"] = chat_id
        context["history_dict"] = history_dict
        context["current_time_str"] = current_time_str
        self._update_snapshot(
            context,
            current_time_str=current_time_str,
            message_count=len(history_dict.get(chat_id, [])),
        )
        logger.info("[Pipeline] 上下文加载完成")
        return context

    async def decide_reply_action(self, context):
        """群聊中判断是否继续回复；潜水时保留用户上下文。"""
        # 破冰模式强制回复，跳过决策
        if context.get("ice_break"):
            return context

        # 私聊和桌宠模式：永远回复，跳过群聊潜水决策
        if context["mode"] in {"private", "master_private", "desktop_pet"}:
            self._update_snapshot(context, should_reply=True)
            return context

        chat_id = context["chat_id"]
        mode = context["mode"]
        history_dict = context["history_dict"]

        # 从已检索的 RAG 结果中计算话题兴趣度
        rag_interest = 0.0
        relevant_diaries = context.get("relevant_diaries", [])
        if relevant_diaries:
            rag_interest = sum(d.get("score", 0) for d in relevant_diaries) / len(relevant_diaries)

        if mode == "group" and not await self.engine.decide_to_reply(
            history_dict[chat_id],
            context["message_objs"],
            chat_id,
            force_reply=context["force_reply"],
            rag_interest=rag_interest,
        ):
            self.history_manager.save(history_dict)
            logger.info(f"[Pipeline] {cfg.ROBOT_NAME.title()} 决定继续潜水")
            context["stop"] = True
            self._update_snapshot(context, should_reply=False)
        else:
            self._update_snapshot(context, should_reply=True)
        return context

    async def retrieve_memories(self, context):
        """根据输入长度动态检索相关日记。"""
        if not cfg.RAG_ENABLED:
            logger.info(f"[Pipeline] RAG 已关闭，跳过日记检索，直接使用上下文")
            context["relevant_diaries"] = []
            return context

        logger.info(f"[Pipeline] {cfg.ROBOT_NAME.title()} 正在回忆")
        chat_id = context["chat_id"]
        combined_text = context["combined_text"]
        dynamic_top_k = 10 if len(combined_text) > 100 else 8

        relevant_diaries = self.memory_rag.search_diaries(
            combined_text,
            chat_id=chat_id,
            top_k_keywords=dynamic_top_k,
            n_results=8
        )
        logger.info(f"[Pipeline] 检索到 {len(relevant_diaries)} 条相关日记")
        logger.info(f"[Pipeline] 检索完成，耗时 {(time.time() - context['first_time']):.2f}s")

        context["relevant_diaries"] = relevant_diaries
        self._update_snapshot(context, relevant_diaries=relevant_diaries)
        return context

    async def generate_reply(self, context):
        """调用引擎生成回复。"""
        chat_id = context["chat_id"]
        answer_raw, answer_text, voice = await self.engine.api_reply(
            chat_id,
            context["combined_text"],
            context["history_dict"],
            context["mode"],
            context["relevant_diaries"],
            ice_break=context.get("ice_break", False),
            debug_snapshot_id=context.get("debug_snapshot_id"),
            message_objs=context.get("message_objs", []),
        )
        logger.info(f"[Pipeline] {cfg.ROBOT_NAME.title()} 回复生成完成")

        context["answer_raw"] = answer_raw
        context["answer_text"] = answer_text
        context["voice"] = voice
        return context

    async def send_reply(self, context):
        """发送文本、表情包分段或语音回复。"""
        chat_id = context["chat_id"]
        mode = context["mode"]
        answer_text = context["answer_text"]
        voice = context.get("voice")

        # master_private 使用私聊 API 发送
        send_mode = "private" if mode == "master_private" else mode

        if mode == "group":
            self.yuki.consume_energy(chat_id)

        logger.info(f"[Pipeline] {cfg.ROBOT_NAME.title()} 正在发送消息 (精力: {self.yuki.energy.get(chat_id, 0):.1f})")

        if mode == "desktop_pet":
            try:
                from modules.LiveYukiL2D.server import broadcast
                await broadcast({"type": "state", "state": "speaking"})
                await broadcast({"type": "say", "text": answer_text})
                await broadcast({"type": "state", "state": "idle"})
            except Exception as exc:
                logger.error(f"[DesktopPet] 发送到 Live2D 失败: {exc}")
            return context

        # === 1. 语音直接发送 ===
        if voice:
            await self.sender.send(chat_id, voice, mode=send_mode)
            logger.info(f"[Pipeline] 发送语音完成")
            return context

        # === 2. 流式发送文本与表情包 ===
        # 按 [MEME:xxx] 切分，() 保留分隔符，结果类似于 ['文本1', '[MEME:关键词]', '文本2']
        parts = re.split(r'(\[MEME:.*?\])', answer_text)

        # 提前引入截屏缓冲模块，避免循环内重复导入
        try:
            from modules.shot_memory import shot_live_buffer
        except ImportError:
            shot_live_buffer = None

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # 检查当前片段是否为表情包
            meme_match = re.fullmatch(r'\[MEME:(.+?)\]', part, re.DOTALL)

            if meme_match:
                # -------- 遇到表情包：现场检索 -> 发送 -> 记录截屏 --------
                if getattr(self, 'sticker_manager', None):
                    search_query = meme_match.group(1).strip()

                    # 现场检索，此处的网络/计算耗时天然充当了防风控的延迟
                    best_meme_data = await self.sticker_manager.get_suitable_sticker(search_query, chat_id)

                    if best_meme_data:
                        image_path = os.path.abspath(best_meme_data['image_ref'])
                        self.yuki.last_sent_meme[chat_id] = best_meme_data['id']

                        # 发送 CQ 码
                        cq_code = f"[CQ:image,file=file:///{image_path},sub_type=1]"
                        await self.sender.send(chat_id, cq_code, mode=send_mode)

                        # 存入截屏缓冲
                        if shot_live_buffer:
                            try:
                                shot_live_buffer.append(
                                    chat_id,
                                    name=cfg.ROBOT_NAME.title(),
                                    raw_text="[表情包]",
                                    content="[表情包]",
                                    segments=[{"type": "image", "data": {"file": image_path}}],
                                    user_id=cfg.SELF_QQ,
                                    is_bot=True,
                                )
                            except Exception as exc:
                                logger.debug(f"[ShotMemory] 记录表情包到截屏缓冲失败: {exc}")

                        # 因为检索已经耗时，这里的强制睡眠可以大幅缩短
                        await asyncio.sleep(2.0)
            else:
                # -------- 遇到纯文本：直接发送 -> 记录截屏 --------
                await self.sender.send(chat_id, part, mode=send_mode)

                if shot_live_buffer:
                    try:
                        bot_name = cfg.ROBOT_NAME.title()
                        shot_live_buffer.append(
                            chat_id,
                            name=bot_name,
                            raw_text=part,
                            # 保持与接收消息相同的 content 格式习惯，方便后续统一读取
                            content=f'【"{bot_name}"】说: {part}',
                            # 严格遵守 Napcat 文本分段格式
                            segments=[{'type': 'text', 'data': {'text': part}}],
                            user_id=cfg.SELF_QQ,
                            is_bot=True,
                            # 机器人的发送没有真实 message_id，可以留空或填入自定义的标识
                            message_id=None
                        )
                    except Exception as exc:
                        logger.debug(f"[ShotMemory] 记录文本到截屏缓冲失败: {exc}")

                # 文本发送极快，给一个极短的睡眠防止被平台判定为刷屏
                await asyncio.sleep(0.5)

        logger.info(f"[Pipeline] 发送完成，内容: {answer_text[:80]}")
        return context

    async def finalize_conversation(self, context):
        """保存回复上下文，并在历史过长时触发总结。"""
        chat_id = context["chat_id"]
        history_dict = context["history_dict"]
        answer_text = context["answer_text"]

        logger.info(f"[Pipeline] {cfg.ROBOT_NAME.title()} 正在保存上下文")
        self.history_manager.append_to_log(chat_id, cfg.ROBOT_NAME.title(), answer_text)
        history_dict[chat_id].append({
            "role": "assistant",
            "content": context["answer_raw"],
            "time": context["current_time_str"],
        })
        self.history_manager.save(history_dict)
        logger.info("[Pipeline] 上下文保存完成")

        # 记录本次处理完成时间，用于冷启动判断
        self.last_process_end_time[chat_id] = time.time()

        # 递减用户映射表 TTL
        self.yuki.user_mapping.tick(chat_id)

        # 递增图片索引轮次，清理过期图片
        if self.image_store:
            self.image_store.tick()

        if len(history_dict[chat_id]) > cfg.DIARY_MAX_LENGTH:
            history_snapshot = history_dict[chat_id].copy()
            history_dict[chat_id] = [history_dict[chat_id][0]]  # 保留系统提示词
            self.history_manager.save(history_dict)

            asyncio.create_task(self._background_summarize(chat_id, history_snapshot))

        # 破冰模式：递增失败计数
        if context.get("ice_break"):
            async with self.yuki.lock:
                self.yuki.ice_break_fail_count[chat_id] = self.yuki.ice_break_fail_count.get(chat_id, 0) + 1
            logger.info(f"[Pipeline] {chat_id} 破冰计数递增至 {self.yuki.ice_break_fail_count[chat_id]}")

        return context

    async def _background_summarize(self, chat_id, history_snapshot):
        """后台处理摘要，不阻塞主流程。"""
        try:
            summarized_list = await self.engine.do_summarize(chat_id, history_snapshot)
            history_dict = self.history_manager.load()
            history_dict[chat_id] = summarized_list
            self.history_manager.save(history_dict)
            logger.info(f"[Pipeline] [{chat_id}] 日记写入完成，历史已同步")
        except Exception as e:
            logger.error(f"[Pipeline] [{chat_id}] 后台摘要失败: {e}")