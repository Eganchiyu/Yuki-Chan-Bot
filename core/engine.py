# core/engine.py
import asyncio
import datetime
import json
import os
import random
import re
import requests
import time
from typing import Any

from config import cfg
from core.maid import build_maid_report, maid_evolution_loop
from core.prompts import get_base_setting, get_summary_prompt, build_chat_context
from core.toolchain import FunctionRegistry, ToolCallManager, ToolContext, ToolRuntime
from core.tools import TOOL_SPECS
from utils.llm_client import llm_chat, llm_chat_raw
from utils.logger import get_logger

logger = get_logger("engine")


class YukiEngine:
    def __init__(self, rag, history_manager, yuki_state, sender):
        self.rag = rag
        self.history = history_manager
        self.yuki = yuki_state
        self.sender = sender
        self.maid = None  # 后面再赋值
        self.process_callback = None  # 预留回调接口
        self.sticker_manager = None
        self.tool_registry = FunctionRegistry()
        self.tool_registry.scan_and_register(TOOL_SPECS)
        self.tool_manager = ToolCallManager(self.tool_registry)

    @staticmethod
    def _clean_visible_reply(content):
        """清理工具链期间可对外发送的回复文本。"""
        if not content:
            return ""
        clean_content = re.sub(r'\s*FINISHED\s*$', '', content, flags=re.IGNORECASE).strip()
        return re.sub(r'<布局>.*?</布局>', '', clean_content, flags=re.DOTALL).strip()

    @staticmethod
    def _append_session_message(history_dict, chat_id, role, content, **extra):
        """把工具链产生的新上下文写入当前 session。"""
        if not content:
            return
        cid = str(chat_id)
        history_dict.setdefault(cid, [])
        item = {
            "role": role,
            "content": content,
            "time": datetime.datetime.now().strftime("%Y年%m月%d日%H:%M"),
        }
        item.update(extra)
        history_dict[cid].append(item)

    def _merge_pending_messages(self, chat_id, history_dict, tool_messages):
        """工具调用间隙合并同群新消息，避免消息流分叉。"""
        pending_objs = self.yuki.message_buffer.get(chat_id) or self.yuki.message_buffer.get(str(chat_id))
        if not pending_objs:
            return
        pending_objs = self.yuki.pop_buffer(chat_id)
        pending_text = "\n".join([m["content"] for m in pending_objs]).replace("\n", "  ").strip()
        if not pending_text:
            return
        logger.info(f"[ToolChain] {chat_id} 合并工具调用期间新增消息: {pending_text}")
        self._append_session_message(history_dict, chat_id, "user", pending_text, is_pending_during_tool=True)
        tool_messages.append({"role": "user", "content": f"【工具调用期间新增消息】{pending_text}"})

    async def _send_tool_thought(self, chat_id, mode, content, sent_thoughts):
        """实时发送工具链中模型产生的阶段性文本。"""
        clean_content = self._clean_visible_reply(content)
        if not clean_content or clean_content in sent_thoughts:
            return ""
        await self.sender.send(chat_id, clean_content, mode=mode)
        sent_thoughts.add(clean_content)
        logger.info(f"[ToolChain] 实时发送阶段性文本 chat_id={chat_id}: {clean_content}")
        return clean_content

    async def _chat_with_tools(self, chat_id, combined_text, history_dict, mode, messages):
        """执行支持多轮工具调用的 LLM 对话。"""
        context = ToolContext(
            chat_id=str(chat_id),
            mode=mode,
            history_dict=history_dict,
            combined_text=combined_text,
            runtime=ToolRuntime(sender=self.sender, yuki_state=self.yuki),
            metadata={"process_callback": self.process_callback},
        )
        self.tool_manager.start_session(str(chat_id), combined_text)
        tool_messages = list(messages)
        sent_thoughts = set()

        try:
            for _ in range(self.tool_manager.max_rounds):
                response_message = await llm_chat_raw(
                    messages=tool_messages,
                    model=cfg.LLM_MODEL,
                    temperature=0.8,
                    top_p=0.8,
                    frequency_penalty=0.05,
                    presence_penalty=0.2,
                    max_tokens=220,
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

                    sent_content = await self._send_tool_thought(
                        chat_id,
                        mode,
                        response_message.get("content"),
                        sent_thoughts,
                    )
                    if sent_content:
                        self._append_session_message(
                            history_dict,
                            chat_id,
                            "assistant",
                            sent_content,
                            is_tool_thought=True,
                            sent_realtime=True,
                        )
                else:
                    answer = self._clean_visible_reply(response_message.get("content"))
                    return answer, answer

                tool_messages.append(response_message)
                tool_result_messages = await self.tool_manager.execute_tool_calls(tool_calls, context)
                for tool_result_message in tool_result_messages:
                    self._append_session_message(
                        history_dict,
                        chat_id,
                        "tool",
                        tool_result_message.get("content"),
                        name=tool_result_message.get("name"),
                        tool_call_id=tool_result_message.get("tool_call_id"),
                    )
                tool_messages.extend(tool_result_messages)
                self._merge_pending_messages(chat_id, history_dict, tool_messages)

            fallback = await llm_chat(
                messages=tool_messages,
                model=cfg.LLM_MODEL,
                temperature=0.8,
                top_p=0.8,
                max_tokens=220,
            )
            fallback = self._clean_visible_reply(fallback)
            return fallback, fallback
        finally:
            self.tool_manager.finish_session(str(chat_id))

    async def api_reply(self, chat_id: str, combined_text: str, history_dict: dict, mode,
                        relevant_diaries: list[Any], ice_break: bool = False) -> str:
        # 总构建发送Deepseek补全的信息
        combined_API_message = await build_chat_context(self.yuki,
                                                        chat_id,
                                                        combined_text,
                                                        history_dict,
                                                        mode,
                                                        relevant_diaries,
                                                        ice_break=ice_break
                                                        )

        await asyncio.sleep(0.2)
        # 发送对话补全到DeepSeek
        logger.info(f"[Engine] {cfg.ROBOT_NAME.title()} 正在打字...")
        try:
            Yuki_Answer_raw, Yuki_Answer = await self._chat_with_tools(
                chat_id,
                combined_text,
                history_dict,
                mode,
                combined_API_message,
            )
            Yuki_Answer = re.sub(r'<布局>.*?</布局>', '', Yuki_Answer, flags=re.DOTALL).strip()
            Yuki_Answer = re.sub(r'\n+', ' ', Yuki_Answer).strip()

            # === 新增：拦截表情包搜索请求 ===
            meme_match = re.search(r'\[MEME_SEARCH:(.+?)\]', Yuki_Answer, re.DOTALL)
            if meme_match and getattr(self, 'sticker_manager', None):
                search_query = meme_match.group(1).strip()
                # 擦除文字中的标签
                Yuki_Answer = re.sub(r'\[MEME_SEARCH:.+?\]', '', Yuki_Answer, flags=re.DOTALL).strip()

                # 呼叫大管家：进行 RAG 检索 + 积热重排
                best_meme_data = await self.sticker_manager.get_suitable_sticker(search_query, chat_id)

                if best_meme_data:
                    import os
                    image_path = os.path.abspath(best_meme_data['image_ref'])
                    # 记录这次发了啥，为后续捕捉正反馈做准备
                    self.yuki.last_sent_meme[chat_id] = best_meme_data['id']

                    # 追加 CQ 码，subType=1 伪装成真实表情包
                    Yuki_Answer += f"\n[CQ:image,file=file:///{image_path},sub_type=1]"
            # ==============================
            # # ==========================================
            # # 新增：截获文本并请求本地 GPT-SoVITS API
            # # ==========================================

            # # 1. 清洗文本（过滤动作描写和换行）
            # clean_text = re.sub(r'\[.*?\]|【.*?】|\(.*?\)|（.*?）|\*.*?\*', '', Yuki_Answer)
            # clean_text = clean_text.strip().replace('\n', '，')
            # if not clean_text:
            #     clean_text = "um..."

            # # ==========================================
            # # [外挂] 翻译模块：将中文转换为日语
            # # ==========================================
            # logger.info(f"[System] 正在调用翻译 API 将文本转为日文...")
            # try:
            #     # # 复用现有的 LLM 接口，要求其直接输出日文，免去注册其他 API 的麻烦
            #     # translate_msgs = [
            #     #     {"role": "system",
            #     #      "content": "你是一个翻译API。请保持输入的风格，将输入翻译为口语化的日文（日本語）。请直接输出日文翻译结果，绝对不要输出任何解释、引号或拼音。"},
            #     #     {"role": "user", "content": clean_text}
            #     # ]
            #     #
            #     # # 调用 LLM 进行翻译（使用较低的 temperature 保证翻译准确性）
            #     # translated_text = await self.llm.robust_api_call(
            #     #     model=cfg.LLM_MODEL,
            #     #     messages=translate_msgs,
            #     #     temperature=0.2,
            #     #     max_tokens=100
            #     # )

            #     # translated_text = translated_text.strip()
            #     translated_text = clean_text
            #     if translated_text:
            #         clean_text = translated_text
            #         logger.info(f"[System] 翻译完成: {clean_text}")
            # except Exception as e:
            #     logger.error(f"[System] 翻译 API 调用失败，将降级使用原文本: {e}")

            # # ==========================================
            # # 语音合成功能（已禁用）
            # # 需要配置本地 SoVITS 服务才能使用
            # # ==========================================
            return Yuki_Answer_raw, Yuki_Answer, ""
        except Exception as e:
            logger.error(f"[Engine] LLM 调用失败: {e}")
            return "API 接口调用失败", ""

    async def decide_to_reply(self, history, message_objs, chat_id,force_reply = False):
        """判断是否回复群聊"""
        # 1. 更新并获取当前群聊的欲望值
        current_e = self.yuki.update_energy(chat_id)
        self.yuki.update_desire_to_reply(chat_id)
        desire = self.yuki.desire_to_start_topic.get(str(chat_id), 0)

        if force_reply:
            return True

        human_calling = any(
            not m["is_bot"] and any(kw in m["raw_text"].lower() for kw in cfg.keywords)
            for m in message_objs
        )

        # B. 检查是否【只有机器人】在艾特 Yuki（循环风险）
        bot_calling_only = all(
            m["is_bot"] for m in message_objs
            if any(kw in m["raw_text"].lower() for kw in cfg.keywords)
        )

        # 逻辑干预：
        if human_calling:
            logger.info(f"[Engine] 检测到人类关键召唤，{cfg.ROBOT_NAME.title()} 强制清醒")
            return True

        if bot_calling_only and any(any(kw in m["raw_text"].lower() for kw in cfg.keywords) for m in message_objs):
            desire *= 0.7  # 你的核心诉求：欲望乘 0.7
            logger.info(f"[Engine] 检测到 BOT 召唤 {cfg.ROBOT_NAME.title()}，防套娃降欲: {desire:.1f}%")

        # --- 强干预层 ---
        if desire >= 80:
            logger.info(f"[Decision] {chat_id} 欲望爆表({desire:.1f}%)，强制回复")
            return True
        if desire <= 20:
            logger.info(f"[Decision] {chat_id} 欲望低迷({desire:.1f}%)，跳过回复")
            return False

        if current_e < cfg.MIN_ACTIVE_ENERGY:
            logger.info(f"[Engine] {cfg.ROBOT_NAME.title()} 精力不足，潜水恢复中 (精力: {current_e:.1f})")
            return False

        try:
            logger.info(f"[Engine] 正在构建判定消息 (精力: {current_e:.1f})")
            recent_dialogue = [msg for msg in history if msg.get("role") != "system"][-10:]

            dialogue_text = ""
            for msg in recent_dialogue:
                role_name = "" if msg["role"] == "user" else f"【{cfg.ROBOT_NAME.title()}】说:"
                dialogue_text += f"{role_name}{msg['content']}\n\n"

            energy_desc = "精力充沛，很愿意找人聊天" if current_e > 90 else "精力正常，会选择性接有趣的话题" if current_e > 45 else "疲惫，只想接少数有趣的话题" if current_e > 25 else "非常疲惫，只有认为必须发言时才发言"

            check_prompt = (
                f"请分析对话上下文和氛围，判断现在是否要发言。{cfg.ROBOT_NAME}对感兴趣的话题会冒泡，但是会避免过于频繁地打扰大家。对{cfg.MASTER_NAME}和{cfg.ROBOT_NAME}的直接称呼会增加发言倾向。请综合考虑对话内容、氛围和当前精力，判断{cfg.ROBOT_NAME}是否应该发言。\n\n"
                f"如果要发言，请回答 'YES'。如果想继续潜水观察，请回答 'NO'。"
            )

            messages = [
                {"role": "system", "content": f"{self.yuki.get_setting('group')}\n你现在需要根据精力值和氛围决定是否发言。"},
                {"role": "user", "content": (
                    f"--- 观察背景 ---\n"
                    f"最近对话内容：\n{dialogue_text}\n\n"
                    f"--- 自身状态 ---\n"
                    f"精力值：{current_e:.1f}/100 ({energy_desc})\n"
                    f"发言消耗{cfg.COST_PER_REPLY}点精力\n\n"
                    f"--- 决策指令 ---\n"
                    f"{check_prompt}"
                )}
            ]
            logger.debug(f"[Engine] 判定消息内容:\n {messages}")
            logger.info(f"[Engine] 判定消息构建完成，发送 API 请求 (精力: {current_e:.1f})")

            raw_response = await llm_chat(
                messages=messages,
                model=cfg.LLM_MODEL,
                max_tokens=10,
                temperature=0.6
            )

            # 2. 拿到字符串后再进行各种清洗
            result = raw_response.strip().upper()
            result = re.sub(r'\s*FINISHED\s*$', '', result, flags=re.IGNORECASE)

            return "YES" in result
        except Exception as e:
            logger.error(f"[Engine] 判定失败: {e}")
            return False

    async def do_summarize(self, chat_id, history):
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
                max_tokens=200
            )
            diary_content = re.sub(r'\s*FINISHED\s*$', '', diary_content, flags=re.IGNORECASE)
            diary_content = f"【日记({datetime.datetime.now().strftime('%Y-%m-%d %H:%M')})】：\n{diary_content}"
            self.rag.save_diary(diary_content, chat_id=chat_id)
            logger.info(f"[Engine] 日记已存入记忆库: {diary_content[:60]}...")

            return [msg for msg in history if msg["role"] == "system"] + dialogue_msgs[-cfg.KEEP_LAST_DIALOGUE:]

        except Exception as e:
            logger.error(f"[Engine] 写日记失败: {e}")
            return history

    async def idle_diary_checker(self):
        """后台任务，每30秒检查一次空闲群聊"""
        while True:
            await asyncio.sleep(30)  # 检查间隔，可根据需要调整
            now = time.time()
            logger.debug(f"[Engine] 后台检查中... {now}")
            history_dict = self.history.load()
            for cid, last_msg in list(self.yuki.last_message_time.items()):
                # 跳过正在写日记的群聊
                if cid in self.yuki.writing_diary:
                    continue

                # 计算空闲时间
                idle_seconds = now - last_msg
                if idle_seconds < cfg.DIARY_IDLE_SECONDS:
                    continue  # 空闲时间不足

                # 检查对话轮数
                if cid not in history_dict:
                    continue
                non_system_msgs = [msg for msg in history_dict[cid] if msg["role"] != "system"]
                non_system_count = len(non_system_msgs)
                if non_system_count < cfg.DIARY_MIN_TURNS:
                    continue  # 轮数不足

                # 满足条件，触发写日记
                logger.info(f"[Engine] 群 {cid} 空闲 {idle_seconds:.0f}s，轮数 {non_system_count}，触发日记")
                self.yuki.writing_diary.add(cid)
                try:
                    new_history = await self.do_summarize(int(cid), history_dict[cid])
                    history_dict[cid] = new_history
                    self.history.save(history_dict)
                finally:
                    self.yuki.writing_diary.discard(cid)

    async def ice_break_monitor(self):
        while True:
            await asyncio.sleep(random.randint(600, 1800))
            target_list = [str(gid) for gid in cfg.TARGET_GROUPS]
            logger.info(f"[Engine] 已加载 {len(target_list)} 个目标群组")
            pending_ice_break = []

            async with self.yuki.lock:
                for cid in target_list:

                    self.yuki.update_energy(chat_id=cid)
                    self.yuki.update_desire_to_reply(cid)
                    activity = self.yuki.group_activity.get(cid, 0.0)
                    desire = self.yuki.desire_to_start_topic.get(cid, 0)

                    logger.info(f"[Engine] 群 {cid} 活跃度={activity:.2f} 欲望={desire:.1f}%")

                    # 获取当前的失败次数，默认为 0
                    fail_count = self.yuki.ice_break_fail_count.get(cid, 0)
                    logger.info(f"[Engine] {cid} 破冰失败次数: {fail_count}")

                    # 修改判定条件：只有失败次数 < 2 时才允许破冰
                    if activity < 0.5 and desire > 75 and fail_count < 2:
                        if random.random() < 0.8:
                            pending_ice_break.append(cid)
                    elif fail_count >= 2:
                        logger.info(f"[Engine] {cid} 连续破冰无果，进入自闭模式，等待群友先开口")

            for cid in pending_ice_break:
                logger.info(f"[IceBreak] 群 {cid} 触发冷场唤醒，走主管道")
                if self.process_callback is not None:
                    asyncio.create_task(self.process_callback(cid, "group", debounce_flag=False, force_reply=True, ice_break=True))
                else:
                    logger.warning(f"[IceBreak] process_callback 未设置，无法触发破冰")



# core/engine.py 末尾新增（或替换原来的 maid_worker）

async def maid_worker(engine, yuki_state, sender, history_manager):
    """小女仆后台常驻 Worker - 完成后交还给 engine 触发正常回复流程"""
    while True:
        task = await yuki_state.maid_task_queue.get()
        goal = task["goal"]
        chat_id = str(task["chat_id"])
        mode = task.get("mode", "group")   # 默认群聊

        # 更新当前任务状态（让 {cfg.ROBOT_NAME.title()} 能感知到“小女仆正在干这个”）
        yuki_state.maid_current_tasks[chat_id] = goal

        logger.info(f"[Maid] 开始后台任务: {goal} (chat_id={chat_id})")

        # 非阻塞执行（线程池运行同步的 ollama 循环）
        result_dict = await maid_evolution_loop(
            user_goal=goal,
            chat_id=chat_id
        )

        # 清除任务状态
        yuki_state.maid_current_tasks.pop(chat_id, None)

        # 构造汇报内容
        report = build_maid_report(goal, result_dict)

        logger.info(f"[Maid] 任务完成，准备交还主流程 (chat_id={chat_id})")

        # === 关键修改部分 ===
        try:
            # 1. 加载当前历史
            history_dict = history_manager.load()
            if chat_id not in history_dict:
                history_dict[chat_id] = [{"role": "system", "content": yuki_state.get_setting(mode)}]

            current_time_str = datetime.datetime.now().strftime("%Y年%m月%d日%H:%M")

            # 2. 把小女仆汇报作为 assistant 消息写入历史（这样 {cfg.ROBOT_NAME.title()} 下次看到的就是“自己”的汇报）
            history_dict[chat_id].append({
                "role": "user",
                "content": report,
                "time": current_time_str,
                "is_maid_report": True   # 可选标记，方便以后过滤
            })

            # 3. 保存到 chat_history.json
            history_manager.save(history_dict)

            # 4. 强制触发 main_process，让 {cfg.ROBOT_NAME.title()} 自然思考并决定是否回复
            #    （main_process 会读取最新历史、检索 RAG、决定是否发言等）
            if engine.process_callback is not None:
                asyncio.create_task(
                    engine.process_callback(chat_id, mode, debounce_flag=False,force_reply=True)
                )
                logger.info(f"[Maid] 已触发主流程 (chat_id={chat_id})")
            else:
                logger.warning(f"[Maid] process_callback 未设置，无法触发回复流程")

            logger.info(f"[Maid] 汇报已交还主流程 (chat_id={chat_id})")

        except Exception as e:
            logger.error(f"[Maid] 处理汇报时出错: {e}")

        finally:
            yuki_state.maid_task_queue.task_done()