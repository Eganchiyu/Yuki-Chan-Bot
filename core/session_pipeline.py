# core/session_pipeline.py
import asyncio
import datetime
import re
import time

from config import cfg
from modules.debug.context_snapshot import PIPELINE_STAGES, context_snapshot_store
from utils.logger import get_logger

logger = get_logger("session_pipeline")


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
        self.image_store = components.get("image_store")
        self.group_active_state = group_active_state
        self.debounce_time_by_chat = {}
        self.stages = [
            self.prepare_message_batch,
            self.normalize_incoming_content,
            self.prepare_chat_context,
            self.retrieve_memories,        # 先检索 RAG，为激素系统提供兴趣度
            self.decide_reply_action,      # 再决定是否回复，融合 rag_interest
            self.generate_reply,
            self.send_reply,
            self.finalize_conversation,
        ]

    def _mark_stage(self, context, stage_name, status="done", error=None):
        """轻量更新 Debug snapshot，不影响主管道。"""
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
                snapshot_id,
                stage=stage_name,
                stage_status=status,
                latency=latency,
                errors=errors,
            )
        except Exception as exc:
            logger.debug(f"[ContextDebug] 更新阶段快照失败: {exc}")

    def _update_snapshot(self, context, **fields):
        """安全更新 Debug snapshot。"""
        snapshot_id = context.get("debug_snapshot_id")
        if not snapshot_id:
            return
        try:
            context_snapshot_store.update(snapshot_id, **fields)
        except Exception as exc:
            logger.debug(f"[ContextDebug] 更新快照失败: {exc}")

    def wake_quickly(self, chat_id):
        """被直接点名时缩短当前群聊防抖时间。"""
        self.debounce_time_by_chat[str(chat_id)] = 0.1

    async def enqueue_message(
        self,
        chat_id,
        mode,
        message_obj=None,
        debounce_flag=True,
        force_reply=None,
        ice_break=False,
    ):
        """统一写入会话缓冲，并确保同一 chat_id 只有一个管道任务。"""
        cid = str(chat_id)
        if message_obj:
            self.yuki.message_buffer.setdefault(cid, [])
            self.yuki.message_buffer[cid].append(message_obj)

        current_task = self.yuki.buffer_tasks.get(cid)
        if current_task and not current_task.done():
            logger.info(f"[Pipeline] {cid} 管道运行中，新事件已入队等待合并处理。")
            return current_task

        task = asyncio.create_task(
            self.process_loop(cid, mode, debounce_flag, force_reply, ice_break)
        )
        self.yuki.buffer_tasks[cid] = task
        return task

    async def process_loop(self, chat_id, mode, debounce_flag=True, force_reply=None, ice_break=False):
        """持续消费同一 chat_id 的缓冲消息，直到当前缓冲为空。"""
        cid = str(chat_id)
        try:
            while True:
                await self.run_once(cid, mode, debounce_flag, force_reply, ice_break)
                debounce_flag = True
                force_reply = None
                ice_break = False  # 破冰只在第一轮执行

                if mode == "group" and not self.group_active_state.get(cid, True):
                    break
                if not self.yuki.message_buffer.get(cid):
                    break
                logger.info(f"[Pipeline] {cid} 检测到处理期间新增消息，准备合并进入下一轮。")
        finally:
            current_task = asyncio.current_task()
            if self.yuki.buffer_tasks.get(cid) is current_task:
                self.yuki.buffer_tasks.pop(cid, None)

    async def run_once(self, chat_id, mode, debounce_flag=True, force_reply=None, ice_break=False):
        """执行一次消息处理，任一阶段标记 stop 后终止本轮。"""
        context = {
            "chat_id": chat_id,
            "mode": mode,
            "debounce_flag": debounce_flag,
            "force_reply": force_reply,
            "ice_break": ice_break,
            "debug_started_at": time.time(),
            "debug_latency": {},
            "debug_errors": [],
        }
        try:
            context["debug_snapshot_id"] = context_snapshot_store.put({
                "chat_id": str(chat_id),
                "mode": mode,
                "stage": "run_once",
                "should_reply": None,
                "tool_context": {"pipeline_stages": PIPELINE_STAGES},
            })
        except Exception as exc:
            logger.debug(f"[ContextDebug] 创建快照失败: {exc}")
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

    async def prepare_message_batch(self, context):
        """防抖、静音拦截、读取消息缓冲。"""
        chat_id = context["chat_id"]
        mode = context["mode"]

        # 破冰模式：跳过防抖和缓冲区读取，构建合成输入
        if context.get("ice_break"):
            recent_msgs = self.history_manager.load().get(str(chat_id), [])[-5:]
            context_text = "".join([m['content'] for m in recent_msgs if m.get("role") != "system"])
            context["combined_text"] = context_text or "（群聊安静中）"
            context["message_objs"] = []
            context["first_time"] = time.time()
            await self.yuki.boost_activity(chat_id)
            logger.info(f"[Pipeline] {chat_id} 跳过防抖，注入破冰上下文")
            return context

        # 主人私聊：跳过防抖，直接处理
        if mode == "master_private":
            pass
        elif context["debounce_flag"]:
            debounce_time = self.debounce_time_by_chat.pop(str(chat_id), cfg.DEBOUNCE_TIME)
            await asyncio.sleep(debounce_time)
        else:
            await asyncio.sleep(0.5)

        if mode == "group" and not self.group_active_state.get(str(chat_id), True):
            logger.info(f"[Pipeline] {chat_id} 群已静音，丢弃消息并退出")
            self.yuki.pop_buffer(chat_id)
            context["stop"] = True
            return context

        cid = str(chat_id)
        if cid not in self.yuki.message_buffer:
            self.yuki.message_buffer[cid] = []

        message_objs = self.yuki.pop_buffer(cid)
        if not message_objs and not context["force_reply"]:
            context["stop"] = True
            return context

        context["first_time"] = time.time()
        context["message_objs"] = message_objs
        await self.yuki.boost_activity(chat_id)
        return context

    async def normalize_incoming_content(self, context):
        """合并消息、理解图片、解析 CQ 码，生成用户输入文本。"""
        # 破冰模式已在 prepare_message_batch 中设置 combined_text，直接跳过
        if context.get("ice_break"):
            return context

        chat_id = context["chat_id"]
        message_objs = context["message_objs"]

        # === 新增：更新用户昵称到QQ号的映射 ===
        for m in message_objs:
            if m.get("user_id") and m.get("name"):
                self.yuki.user_mapping.update(chat_id, m["name"], m["user_id"])
        # ========================================

        # 合并同一用户连续消息，去掉重复的 "【"xxx"】说:" 前缀
        merged_contents = []
        prev_uid = None
        for m in message_objs:
            uid = m.get("user_id")
            text = m["content"]
            if uid and uid == prev_uid and text.startswith("【"):
                # 同一用户连续消息，去掉前缀
                text = re.sub(r'^【"[^"]*"】说:\s*', '', text)
            merged_contents.append(text)
            prev_uid = uid
        combined_text = "\n".join(merged_contents)

        modified_text, images_info = self.meme_processor.extract_urls_from_text(combined_text)
        if images_info:
            understood_contents = []
            for img in images_info:
                url = img["url"]
                is_meme = img["is_meme"]
                result = await self.meme_processor.understand_from_url(url, is_meme=is_meme)

                desc = result.get("description", "未知图片/表情") if isinstance(result, dict) else result
                idx = result.get("index") if isinstance(result, dict) else None
                idx_tag = f"[img:{idx}]" if idx else ""

                if is_meme and desc:
                    understood_contents.append(f"[表情:{desc}]{idx_tag}")
                    logger.debug(f"[Pipeline_meme]收到[表情:{desc}]{idx_tag}")
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

        # 主人私聊模式：永远回复，跳过决策
        if context["mode"] == "master_private":
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
        # RAG 关闭时跳过检索，直接使用上下文
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
        self._update_snapshot(
            context,
            relevant_diaries=relevant_diaries,
        )
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
        voice = context["voice"]

        # master_private 使用私聊 API 发送
        send_mode = "private" if mode == "master_private" else mode

        if mode == "group":
            self.yuki.consume_energy(chat_id)
        logger.info(f"[Pipeline] {cfg.ROBOT_NAME.title()} 正在发送消息 (精力: {self.yuki.energy.get(chat_id, 0):.1f})")

        if not voice:
            parts = re.split(r"(\[CQ:image,[^\]]*?sub_type=1\])", answer_text, flags=re.IGNORECASE)
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                await self.sender.send(chat_id, part, mode=send_mode)
                if part.startswith("[CQ:image"):
                    await asyncio.sleep(3.0)
                else:
                    await asyncio.sleep(1.0)
        else:
            await self.sender.send(chat_id, voice, mode=send_mode)

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

        # === 新增：递减用户映射表 TTL ===
        self.yuki.user_mapping.tick(chat_id)
        # =================================

        # === 新增：递增图片索引轮次，清理过期图片 ===
        if self.image_store:
            self.image_store.tick()
        # ============================================

        if len(history_dict[chat_id]) > cfg.DIARY_MAX_LENGTH:
            summarized_list = await self.engine.do_summarize(chat_id, history_dict[chat_id])
            history_dict[chat_id] = summarized_list
            self.history_manager.save(history_dict)
            logger.info(f"[Pipeline] [{chat_id}] 日记写入完成，历史已同步")

        # 破冰模式：递增失败计数（下次收到非 bot 消息时由 feed_message 重置）
        if context.get("ice_break"):
            async with self.yuki.lock:
                self.yuki.ice_break_fail_count[chat_id] = self.yuki.ice_break_fail_count.get(chat_id, 0) + 1
            logger.info(f"[Pipeline] {chat_id} 破冰计数递增至 {self.yuki.ice_break_fail_count[chat_id]}")

        return context
