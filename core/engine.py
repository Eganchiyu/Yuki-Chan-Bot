# core/engine.py
import asyncio
import datetime
import json
import os
import random
import re
import requests
import time
from typing import Any, Optional

from config import cfg
from core.prompts import get_base_setting, get_summary_prompt, build_chat_context
from core.toolchain import FunctionRegistry, ToolCallManager, ToolContext, ToolRuntime
from core.tools import TOOL_SPECS
from modules.debug.context_snapshot import context_snapshot_store
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
        self.napcat_online = True

    @staticmethod
    def _clean_visible_reply(content):
        """清理工具链期间可对外发送的回复文本。"""
        if not content:
            return ""
        clean_content = re.sub(r'\s*FINISHED\s*$', '', content, flags=re.IGNORECASE).strip()
        clean_content = re.sub(r'<layout>.*?</layout>', '', clean_content, flags=re.DOTALL).strip()
        return clean_content

    def _merge_pending_messages(self, chat_id, tool_messages):
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

    async def _send_tool_thought(self, chat_id, mode, content, sent_thoughts, tool_names=None):
        """实时发送工具链中模型产生的阶段性文本。"""
        clean_content = self._clean_visible_reply(content)
        if not clean_content or clean_content in sent_thoughts:
            return ""
        # 只在调用小女仆时添加表情符号
        display_content = re.sub(r'\[MEME:.+?\]', '', clean_content, flags=re.DOTALL).strip()
        if tool_names and "delegate_to_maid" in tool_names:
            display_content = clean_content + " | (๑•̀ㅂ•́)و💻"
        if display_content:
            if mode == "desktop_pet":
                from modules.LiveYukiL2D.server import broadcast
                await broadcast({"type": "say", "text": display_content})
            else:
                # master_private 使用私聊 API 发送
                send_mode = "private" if mode == "master_private" else mode
                await self.sender.send(chat_id, display_content, mode=send_mode)
        sent_thoughts.add(clean_content)
        logger.info(f"[ToolChain] 实时发送阶段性文本 chat_id={chat_id}: {clean_content}")
        return clean_content

    async def _chat_with_tools(self, chat_id, combined_text, session, mode, messages, message_objs=None):
        """执行支持多轮工具调用的 LLM 对话。"""
        context = ToolContext(
            chat_id=str(chat_id),
            mode=mode,
            session=session,
            combined_text=combined_text,
            runtime=ToolRuntime(sender=self.sender, yuki_state=self.yuki,
                                image_store=getattr(self, "image_store", None)),
            metadata={
                "process_callback": self.process_callback,
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

                    sent_content = await self._send_tool_thought(
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
                    answer = self._clean_visible_reply(response_message.get("content"))
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
                self._merge_pending_messages(chat_id, tool_messages)

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

    async def api_reply(self, chat_id: str, combined_text: str, session: list, mode,
                        relevant_diaries: list[Any],
                        ice_break: bool = False, debug_snapshot_id: Optional[str] = None,
                        message_objs: Optional[list[dict]] = None) -> str:

        combined_API_message = await build_chat_context(self.yuki,
                                                        chat_id,
                                                        combined_text,
                                                        {str(chat_id): session},
                                                        mode,
                                                        relevant_diaries,
                                                        ice_break=ice_break
                                                        )
        if debug_snapshot_id:
            try:
                context_snapshot_store.update(
                    debug_snapshot_id,
                    built_messages=combined_API_message,
                    tool_context={
                        "tools_enabled": True,
                        "tool_count": len(self.tool_registry.get_tools()),
                        "max_rounds": self.tool_manager.max_rounds,
                    },
                )
            except Exception as exc:
                logger.debug(f"[ContextDebug] 记录 LLM messages 失败: {exc}")

        # await asyncio.sleep(0.2)
        # 发送对话补全到DeepSeek
        logger.info(f"[Engine] {cfg.ROBOT_NAME.title()} 正在打字...")
        try:
            Yuki_Answer_raw, Yuki_Answer = await self._chat_with_tools(
                chat_id,
                combined_text,
                session,
                mode,
                combined_API_message,
                message_objs=message_objs,
            )
            Yuki_Answer = re.sub(r'<layout>.*?</layout>', '', Yuki_Answer, flags=re.DOTALL).strip()
            Yuki_Answer = re.sub(r'\n+', ' ', Yuki_Answer).strip()



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

    async def decide_to_reply(self, history, message_objs, chat_id, force_reply=False, rag_interest=0.0):
        """
        [精力核心融合版] 混合硬性规则与加权积分引擎
        以精力值为基底，削弱话题惯性，维持中等主人依赖。
        """
        cid = str(chat_id)

        # ==========================================
        # 1. 基础属性更新与话题激素计算
        # ==========================================
        current_e = self.yuki.update_energy(chat_id)
        self.yuki.update_desire_to_reply(chat_id)
        desire = self.yuki.desire_to_start_topic.get(cid, 0)

        # 激素系统：加快自然衰减（由 0.75 降至 0.60），降低 RAG 刺激增量，防止话题热度居高不下
        if not hasattr(self.yuki, 'topic_hormone'):
            self.yuki.topic_hormone = {}

        current_hormone = self.yuki.topic_hormone.get(cid, 0.0)
        new_hormone = current_hormone * 0.60 + (rag_interest * 10)
        new_hormone = min(new_hormone, 100.0)
        self.yuki.topic_hormone[cid] = new_hormone

        # ==========================================
        # 2. 消息特征解析
        # ==========================================
        human_calling = False
        bot_calling_only = True
        question_mark = False
        is_master = False

        master_identifiers = [cfg.MASTER_NAME, "池宇健"]
        master_qq_str = str(cfg.TARGET_QQ)

        for m in message_objs:
            raw_text = m.get("raw_text", "").lower()
            if not m.get("is_bot"):
                bot_calling_only = False

            if any(kw in raw_text for kw in cfg.keywords):
                if not m.get("is_bot"):
                    human_calling = True

            if any(q in raw_text for q in ["?", "？", "吗", "呢", "怎么", "什么", "谁", "为什么"]):
                question_mark = True

            if any(mid in raw_text for mid in master_identifiers) or master_qq_str in raw_text or m.get(
                    "user_id") == cfg.TARGET_QQ:
                is_master = True

        # ==========================================
        # 3. 强干预层 (精力一票否决/强制通过)
        # ==========================================
        if force_reply or human_calling:
            logger.info(f"[Decision] 触发强制回复或直接召唤，立即响应")
            return True

        if bot_calling_only and any(any(kw in m["raw_text"].lower() for kw in cfg.keywords) for m in message_objs):
            self.yuki.desire_to_start_topic[cid] *= 0.5
            logger.info(f"[Decision] 防套娃机制触发：纯 BOT 召唤，静默")
            return False

        # 高精力强制活跃区 (根据你的具体设定，假设 > 85 为极高)
        if current_e >= 85:
            logger.info(f"[Decision] 精力充沛({current_e:.1f})，强制开启活跃模式")
            return True

        # 低精力强制潜水区 (除非有主人特权)
        if current_e < cfg.MIN_ACTIVE_ENERGY and not is_master:
            logger.info(f"[Decision] 精力枯竭({current_e:.1f})且无哥哥大人在场，拒绝回复")
            return False

        # ==========================================
        # 4. 模糊地带：以精力为基础的积分计算
        # ==========================================
        reply_score = 0.0

        # A. 精力基底权重 (占比 40%) - 精力越高，底气越足
        reply_score += current_e * 0.4

        # B. 表达欲望权重 (占比 20%)
        reply_score += desire * 0.2

        # C. 话题匹配度修正 (占比 20%) - 大幅削弱，避免持续被高热度裹挟
        reply_score += new_hormone * 0.2

        # D. 疑问句微调 (+10) - 保持基础的对答礼貌
        if question_mark:
            reply_score += 10

        # E. 主人依赖修正 (中等水准 +15) - 相比之前的 +25 有所克制
        if is_master:
            reply_score += 20
            logger.debug(f"[Decision] 检测到哥哥大人发言，触发中等依赖修正 +15")

        # ==========================================
        # 5. 最终决断
        # ==========================================
        threshold = 55.0  # 及格线可以根据实测微调
        will_reply = reply_score >= threshold

        logger.info(
            f"[Decision] 模糊地带判定 | 精力:{current_e:.1f} 激素:{new_hormone:.1f} 欲:{desire:.1f} "
            f"主人:{is_master} | 总分:{reply_score:.1f}/{threshold} -> 发言:{will_reply}"
        )
        return will_reply

    # ==================================================================================
    # 【待启用】非线性精力融合版 decide_to_reply
    # 设计思路：
    #   - 精力值为基底，非线性幂函数 f(e) = 100×(e/100)^0.7
    #   - 精力=0 时得分=0，精力=100 时得分=100，全程平滑连续
    #   - 其他项（参与度、主人、疑问句）作为乘法修正系数，不是加法
    #   - 叫名字时强制通过 + engagement=100 + 精力boost
    #   - 阈值=50
    #
    # 配套改动（brain.py）：
    #   - self.engagement = {}                          # 新增参与度状态
    #   - update_energy: 参与度>40时精力恢复×1.5
    #   - consume_energy: 参与度>60时消耗减半
    #   - update_desire_to_reply: 精力=0时欲望归零
    #   - decay_engagement: 每轮衰减×0.7，<5时清除
    #
    # 配套改动（session_pipeline.py finalize_conversation）：
    #   - self.yuki.decay_engagement(chat_id)
    #
    # 阈值选择参考（α=0.7）：
    #   阈值=40: 无加成需精力>27, 被叫后>22, 全加成>16 (太爱说话)
    #   阈值=50: 无加成需精力>37, 被叫后>30, 全加成>22 (推荐)
    #   阈值=55: 无加成需精力>43, 被叫后>35, 全加成>25 (平衡)
    #   阈值=60: 无加成需精力>48, 被叫后>40, 全加成>28 (偏安静)
    # ==================================================================================
    #
    # async def decide_to_reply(self, history, message_objs, chat_id, force_reply=False, rag_interest=0.0):
    #     """
    #     [非线性精力融合版]
    #     score = f(energy) × correction(engagement, question, master)
    #     f(e) = 100 × (e/100)^0.7
    #     """
    #     cid = str(chat_id)
    #
    #     # --- 1. 基础属性更新 ---
    #     current_e = self.yuki.update_energy(chat_id)
    #     self.yuki.update_desire_to_reply(chat_id)
    #
    #     # --- 2. 消息特征解析 ---
    #     human_calling = False
    #     bot_calling_only = True
    #     question_mark = False
    #     is_master = False
    #
    #     master_identifiers = [cfg.MASTER_NAME, "池宇健"]
    #     master_qq_str = str(cfg.TARGET_QQ)
    #
    #     for m in message_objs:
    #         raw_text = m.get("raw_text", "").lower()
    #         if not m.get("is_bot"):
    #             bot_calling_only = False
    #         if any(kw in raw_text for kw in cfg.keywords):
    #             if not m.get("is_bot"):
    #                 human_calling = True
    #         if raw_text.rstrip().endswith(('?', '？')):
    #             question_mark = True
    #         if any(mid in raw_text for mid in master_identifiers) or master_qq_str in raw_text or m.get("user_id") == cfg.TARGET_QQ:
    #             is_master = True
    #
    #     # --- 3. 硬性规则：叫名字强制通过 ---
    #     if force_reply or human_calling:
    #         if human_calling:
    #             self.yuki.engagement[cid] = 100.0
    #             if cid in self.yuki.energy:
    #                 boost = min(15.0, cfg.MAX_ENERGY - self.yuki.energy[cid])
    #                 self.yuki.energy[cid] += boost
    #                 logger.info(f"[Decision] 被叫到名字，精力值 +{boost:.1f} -> {self.yuki.energy[cid]:.1f}")
    #         logger.info(f"[Decision] 触发强制回复或直接召唤，立即响应")
    #         return True
    #
    #     if bot_calling_only and any(any(kw in m["raw_text"].lower() for kw in cfg.keywords) for m in message_objs):
    #         self.yuki.desire_to_start_topic[cid] *= 0.5
    #         logger.info(f"[Decision] 防套娃机制触发：纯 BOT 召唤，静默")
    #         return False
    #
    #     # --- 4. 非线性融合积分 ---
    #     energy_score = 100.0 * (current_e / 100.0) ** 0.7
    #
    #     engagement = self.yuki.engagement.get(cid, 0.0)
    #     correction = 1.0
    #     correction += 0.15 * (engagement / 100.0)
    #     correction += 0.15 * float(question_mark)
    #     correction += 0.15 * float(is_master)
    #
    #     if is_master:
    #         self.yuki.engagement[cid] = max(engagement, 60.0)
    #
    #     reply_score = energy_score * correction
    #
    #     # --- 5. 阈值判定 ---
    #     threshold = 50.0
    #     will_reply = reply_score >= threshold
    #
    #     logger.info(
    #         f"[Decision] 精力:{current_e:.1f} 基底:{energy_score:.1f} "
    #         f"参与:{engagement:.1f} 主人:{is_master} 问:{question_mark} "
    #         f"修正:{correction:.2f} | 总分:{reply_score:.1f}/{threshold} -> 发言:{will_reply}"
    #     )
    #     return will_reply
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
            if not getattr(self, 'napcat_online', True):
                continue
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
                    await self._summarize_idle_session(cid, history_dict[cid])
                finally:
                    self.yuki.writing_diary.discard(cid)

    async def _summarize_idle_session(self, chat_id, session):
        """摘要单个空闲会话并按会话粒度回写。"""
        new_session = await self.do_summarize(int(chat_id), session)
        self.history.replace_session(chat_id, new_session)

    async def ice_break_monitor(self):
        while True:
            await asyncio.sleep(random.randint(600, 1800))
            if not getattr(self, 'napcat_online', True):
                continue
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
