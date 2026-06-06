# core/session_pipeline.py
import asyncio
import datetime
import re
import time

from config import cfg
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
        self.group_active_state = group_active_state
        self.debounce_time_by_chat = {}
        self.stages = [
            self.prepare_message_batch,
            self.normalize_incoming_content,
            self.prepare_chat_context,
            self.decide_reply_action,
            self.retrieve_memories,
            self.generate_reply,
            self.send_reply,
            self.finalize_conversation,
        ]

    def wake_quickly(self, chat_id):
        """被直接点名时缩短当前群聊防抖时间。"""
        self.debounce_time_by_chat[str(chat_id)] = 3

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
                debounce_flag = False
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
        }
        for stage in self.stages:
            context = await stage(context)
            if context.get("stop"):
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
            logger.info(f"[IceBreak] {chat_id} 跳过防抖，注入破冰上下文")
            return context

        if context["debounce_flag"]:
            debounce_time = self.debounce_time_by_chat.pop(str(chat_id), cfg.DEBOUNCE_TIME)
            await asyncio.sleep(debounce_time)
        else:
            await asyncio.sleep(0.5)

        if mode == "group" and not self.group_active_state.get(str(chat_id), True):
            logger.info(f"[System] [{chat_id}] 协程醒来，但群已被静音，丢弃遗留消息并退出。")
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
        all_contents = [m["content"] for m in message_objs]
        combined_text = "\n".join(all_contents)

        modified_text, images_info = self.meme_processor.extract_urls_from_text(combined_text)
        if images_info:
            understood_contents = []
            for img in images_info:
                url = img["url"]
                is_meme = img["is_meme"]
                result = await self.meme_processor.understand_from_url(url)
                understood_contents.append(result)

                if is_meme and hasattr(self.engine, "sticker_manager"):
                    pass
                elif not is_meme:
                    logger.info("[System] 拦截到非表情包图片，仅作视觉理解，不入库学习。")

            combined_text = modified_text
            for content in understood_contents:
                combined_text = combined_text.replace("[图片占位符]", content, 1)

        combined_text = await self.parser.parse_all_cq_codes(combined_text)
        combined_text = combined_text.replace("\n", "  ").strip()
        logger.info(f"[{chat_id}] 收到消息{combined_text}")
        self.history_manager.append_to_log(chat_id, "User/Group", combined_text)

        context["combined_text"] = combined_text
        return context

    async def prepare_chat_context(self, context):
        """加载上下文，确保系统提示词存在，并追加当前用户消息。"""
        logger.info("[System] 加载上下文信息...")
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
        logger.info("[System] 加载完成")
        return context

    async def decide_reply_action(self, context):
        """群聊中判断是否继续回复；潜水时保留用户上下文。"""
        # 破冰模式强制回复，跳过决策
        if context.get("ice_break"):
            return context

        chat_id = context["chat_id"]
        mode = context["mode"]
        history_dict = context["history_dict"]

        if mode == "group" and not await self.engine.decide_to_reply(
            history_dict[chat_id],
            context["message_objs"],
            chat_id,
            force_reply=context["force_reply"],
        ):
            self.history_manager.save(history_dict)
            logger.info(f"[System] {cfg.ROBOT_NAME.title()} 决定继续潜水...")
            context["stop"] = True
        return context

    async def retrieve_memories(self, context):
        """根据输入长度动态检索相关日记。"""
        logger.info(f"[System] {cfg.ROBOT_NAME.title()} 正在回忆...")
        chat_id = context["chat_id"]
        combined_text = context["combined_text"]
        dynamic_top_k = 10 if len(combined_text) > 100 else 8
        relevant_diaries = self.memory_rag.search_diaries(
            combined_text,
            chat_id=chat_id,
            top_k=dynamic_top_k,
        )
        logger.info(f"[System] 检索到 {len(relevant_diaries)} 条相关日记:")
        logger.info(f"检索完成，用时 {(time.time() - context['first_time']):.2f}")

        context["relevant_diaries"] = relevant_diaries
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
        )
        logger.info(f"{cfg.ROBOT_NAME.title()}打字完成！")

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

        if mode == "group":
            self.yuki.consume_energy(chat_id)
        logger.info(f"[System] {cfg.ROBOT_NAME.title()} 正在发送消息...(剩余精力: {self.yuki.energy[chat_id]:.1f})")

        if not voice:
            parts = re.split(r"(\[CQ:image,[^\]]*?sub_type=1\])", answer_text, flags=re.IGNORECASE)
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                await self.sender.send(chat_id, part, mode=mode)
                await asyncio.sleep(1.0)
        else:
            await self.sender.send(chat_id, voice, mode=mode)

        logger.info(f"[System] 发送完成！全量内容：{answer_text}")
        return context

    async def finalize_conversation(self, context):
        """保存回复上下文，并在历史过长时触发总结。"""
        chat_id = context["chat_id"]
        history_dict = context["history_dict"]
        answer_text = context["answer_text"]

        logger.info(f"[System] {cfg.ROBOT_NAME.title()}正在保存上下文...")
        self.history_manager.append_to_log(chat_id, cfg.ROBOT_NAME.title(), answer_text)
        history_dict[chat_id].append({
            "role": "assistant",
            "content": context["answer_raw"],
            "time": context["current_time_str"],
        })
        self.history_manager.save(history_dict)
        logger.info("[System] 保存完成")

        if len(history_dict[chat_id]) > cfg.DIARY_MAX_LENGTH:
            summarized_list = await self.engine.do_summarize(chat_id, history_dict[chat_id])
            history_dict[chat_id] = summarized_list
            self.history_manager.save(history_dict)
            logger.info(f"[{chat_id}] 日记写入完成，全量历史已同步。")

        # 破冰模式：递增失败计数（下次收到非 bot 消息时由 feed_message 重置）
        if context.get("ice_break"):
            async with self.yuki.lock:
                self.yuki.ice_break_fail_count[chat_id] = self.yuki.ice_break_fail_count.get(chat_id, 0) + 1
            logger.info(f"[IceBreak] {chat_id} 破冰计数递增至 {self.yuki.ice_break_fail_count[chat_id]}")

        return context
