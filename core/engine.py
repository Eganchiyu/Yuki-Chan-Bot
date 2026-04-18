# core/engine.py
import json
import random
import re
import asyncio
import datetime
import time
from typing import Any
from core.prompts import BASE_SETTING, SUMMARY_PROMPT, build_chat_context
from config import *
from core.prompts import build_ice_break_prompt
from core.maid import maid_evolution_loop
from utils.logger import get_logger

logger = get_logger("engine")


class YukiEngine:
    def __init__(self, llm, rag, history_manager, yuki_state, sender):
        self.llm = llm
        self.rag = rag
        self.history = history_manager
        self.yuki = yuki_state
        self.sender = sender
        self.maid = None  # 后面再赋值
        self.process_callback = None  # 预留回调接口

    async def api_reply(self, chat_id: str, combined_text: str, history_dict: dict, mode, relevant_diaries: list[Any]) -> str:
        # 总构建发送Deepseek补全的信息
        combined_API_message = await build_chat_context(self.yuki,
                                                        chat_id,
                                                        combined_text,
                                                        history_dict,
                                                        mode,
                                                        relevant_diaries
                                                        )
        await asyncio.sleep(0.2)
        # 发送对话补全到DeepSeek
        logger.info("[System] Yuki 正在打字...")
        try:
            Yuki_Answer = await self.llm.robust_api_call(
                model=LLM_MODEL,
                messages=combined_API_message,
                temperature=0.7,  # 降低温度，让它说话更稳、更常用
                top_p=0.75,  # 稍微收窄采样范围，过滤冷门词
                frequency_penalty=0.05,  # 极低的惩罚，允许它说大白话
                presence_penalty=0.0,  # 不强迫它聊新话题
                max_tokens=100  # 强制短句，短句更容易显自然
            )
            Yuki_Answer = re.sub(r'\s*FINISHED\s*$', '', Yuki_Answer, flags=re.IGNORECASE)
            delegate_match = re.search(r'\[DELEGATE_TO_MAID:(.+?)\]', Yuki_Answer, re.DOTALL)
            if delegate_match:
                task_desc = delegate_match.group(1).strip()
                # 移除标签，干净回复发给用户
                Yuki_Answer = re.sub(r'\[DELEGATE_TO_MAID:.+?\]', '', Yuki_Answer, flags=re.DOTALL).strip()

                # 扔进小女仆队列（非阻塞）
                await self.yuki.maid_task_queue.put({
                    "goal": task_desc,
                    "chat_id": chat_id
                })
                logger.info(f"📤 已委托小女仆：{task_desc}")
            return Yuki_Answer
        except Exception as e:
            logger.error(f"调用失败: {e}")
            return f"API 接口调用失败"

    async def decide_to_reply(self, history, message_objs, chat_id,force_reply = False):
        """判断是否回复群聊"""
        # 1. 更新并获取当前群聊的欲望值
        current_e = self.yuki.update_energy(chat_id)
        self.yuki.update_desire_to_reply(chat_id)
        desire = self.yuki.desire_to_start_topic.get(str(chat_id), 0)

        if force_reply:
            return True

        human_calling = any(
            not m["is_bot"] and any(kw in m["raw_text"].lower() for kw in keywords)
            for m in message_objs
        )

        # B. 检查是否【只有机器人】在艾特 Yuki（循环风险）
        bot_calling_only = all(
            m["is_bot"] for m in message_objs
            if any(kw in m["raw_text"].lower() for kw in keywords)
        )

        # 逻辑干预：
        if human_calling:
            logger.info("[System] 检测到人类关键召唤，Yuki 强制清醒")
            return True

        if bot_calling_only and any(any(kw in m["raw_text"].lower() for kw in keywords) for m in message_objs):
            desire *= 0.7  # 你的核心诉求：欲望乘 0.7
            logger.info(f"[System] 检测到仅有 BOT 在召唤 Yuki，为了防止无限套娃，本次放行。欲望打折：{desire:.1}%")

        # --- 强干预层 ---
        if desire >= 80:
            logger.info(f"[Decision] {chat_id} 欲望爆表({desire}%)，强制回复！")
            return True
        if desire <= 30:
            logger.info(f"[Decision] {chat_id} 欲望低迷({desire}%)，拒绝营业。")
            return False

        if current_e < MIN_ACTIVE_ENERGY:
            logger.info(f"[System] Yuki 太累了... 正在潜水回复体力 (当前精力: {current_e:.1f})")
            return False

        try:
            logger.info(f"[System] 正在构建判定消息... (当前精力: {current_e:.1f})")
            recent_dialogue = [msg for msg in history if msg.get("role") != "system"][-10:]

            dialogue_text = ""
            for msg in recent_dialogue:
                role_name = "" if msg["role"] == "user" else "【Yuki】说:"
                dialogue_text += f"{role_name}{msg['content']}\n\n"

            energy_desc = "精力充沛，很愿意找人聊天" if current_e > 90 else "精力正常，会选择性接有趣的话题" if current_e > 45 else "疲惫，只想接少数有趣的话题" if current_e > 25 else "非常疲惫，只有认为必须发言时才发言"

            check_prompt = (
                f"请分析对话上下文和氛围，判断现在是否要发言。yuki对感兴趣的话题会冒泡，但是会避免过于频繁地打扰大家。对主人和yuki的直接称呼会增加发言倾向。请综合考虑对话内容、氛围和当前精力，判断yuki是否应该发言。\n\n"
                f"如果要发言，请回答 'YES'。如果想继续潜水观察，请回答 'NO'。"
            )

            messages = [
                {"role": "system", "content": f"{self.yuki.get_setting('group')}\n你现在需要根据精力值和氛围决定是否发言。"},
                {"role": "user", "content": (
                    f"--- 观察背景 ---\n"
                    f"最近对话内容：\n{dialogue_text}\n\n"
                    f"--- 自身状态 ---\n"
                    f"精力值：{current_e:.1f}/100 ({energy_desc})\n"
                    f"发言消耗{COST_PER_REPLY}点精力\n\n"
                    f"--- 决策指令 ---\n"
                    f"{check_prompt}"
                )}
            ]
            logger.debug(f"[DEBUG] \n {messages}")
            logger.info(f"[System] 判定消息构建完成，正在发送API请求... (当前精力: {current_e:.1f})")

            raw_response = await self.llm.robust_api_call(
                model=LLM_MODEL,
                messages=messages,
                max_tokens=10,
                temperature=0.6
            )

            # 2. 拿到字符串后再进行各种清洗
            result = raw_response.strip().upper()
            result = re.sub(r'\s*FINISHED\s*$', '', result, flags=re.IGNORECASE)

            return "YES" in result
        except Exception as e:
            logger.error(f"[ERROR] 判定失败原因: {e}")
            return False

    async def do_summarize(self, chat_id, history):
        logger.info(f"[System] [{chat_id}] 记忆有点长了，Yuki 正在写日记回顾...")
        dialogue_msgs = [msg for msg in history if msg["role"] != "system"]
        content_to_summarize = json.dumps(dialogue_msgs, ensure_ascii=False)
        try:
            diary_content = await self.llm.robust_api_call(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": f"{BASE_SETTING}"},
                    {"role": "user", "content": (
                        f"以下是需要总结的对话内容：\n{content_to_summarize}\n\n"
                        f"---任务指令---\n"
                        f"{SUMMARY_PROMPT}"
                    )}
                ],
                temperature=0.7,
                top_p=0.8,
                frequency_penalty=0.1,  # 极低的惩罚，允许它说大白话
                presence_penalty=0.0,
                max_tokens=200
            )
            diary_content = re.sub(r'\s*FINISHED\s*$', '', diary_content, flags=re.IGNORECASE)
            diary_content = f"【日记({datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})】：\n{diary_content}"
            self.rag.save_diary(diary_content, chat_id=chat_id)
            logger.info(f"[System] 日记已存入记忆库：{diary_content}")

            return [msg for msg in history if msg["role"] == "system"] + dialogue_msgs[-KEEP_LAST_DIALOGUE:]

        except Exception as e:
            logger.error(f"[System ERROR] 写日记失败: {e}")
            return history

    async def idle_diary_checker(self):
        """后台任务，每30秒检查一次空闲群聊"""
        while True:
            await asyncio.sleep(30)  # 检查间隔，可根据需要调整
            now = time.time()
            logger.debug(f"⏰ 后台检查中时间中...{now}")  # 调试输出
            history_dict = self.history.load()
            for cid, last_msg in list(self.yuki.last_message_time.items()):
                # 跳过正在写日记的群聊
                if cid in self.yuki.writing_diary:
                    continue

                # 计算空闲时间
                idle_seconds = now - last_msg
                if idle_seconds < DIARY_IDLE_SECONDS:
                    continue  # 空闲时间不足

                # 检查对话轮数
                if cid not in history_dict:
                    continue
                non_system_msgs = [msg for msg in history_dict[cid] if msg["role"] != "system"]
                non_system_count = len(non_system_msgs)
                if non_system_count < DIARY_MIN_TURNS:
                    continue  # 轮数不足

                # 满足条件，触发写日记
                logger.info(f"⏰ 后台检查：群 {cid} 空闲 {idle_seconds:.1f} 秒，轮数 {non_system_count}，触发写日记")
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
            target_list = [str(gid) for gid in TARGET_GROUPS]
            logger.info(f"已加载{len(target_list)}条数据")
            pending_ice_break = []

            async with self.yuki.lock:
                for cid in target_list:

                    self.yuki.update_energy(chat_id=cid)
                    self.yuki.update_desire_to_reply(cid)
                    activity = self.yuki.group_activity.get(cid, 0.0)
                    desire = self.yuki.desire_to_start_topic.get(cid, 0)

                    logger.info(f"正在检查{cid}：群聊活跃度{activity} | 发言欲望{desire}")

                    # 获取当前的失败次数，默认为 0
                    fail_count = self.yuki.ice_break_fail_count.get(cid, 0)
                    logger.info(f"[IceBreak] {cid} 破冰失败次数为 {fail_count}")

                    # 修改判定条件：只有失败次数 < 2 时才允许破冰
                    if activity < 0.5 and desire > 75 and fail_count < 2:
                        if random.random() < 0.8:
                            pending_ice_break.append(cid)
                    elif fail_count >= 2:
                        logger.info(f"[IceBreak] {cid} 连续两次破冰无果，进入自闭模式，等待群友先开口。")

            for cid in pending_ice_break:
                logger.info(f"[IceBreak] 目标群 {cid} 触发冷场唤醒")
                asyncio.create_task(self.break_ice(cid))




    async def break_ice(self, chat_id: str) -> str:
        # 1. 异步加载历史 (假设 load 是同步的，我们用线程池跑它)
        # 如果 history.load 很快，可以暂时保留同步，但 save 必须小心
        history_dict = self.history.load()

        if chat_id not in history_dict:
            return None

        # 2. 构造 Query 逻辑 (保持你的原汁原味)
        recent_msgs = history_dict[chat_id][-5:]
        context_text = "".join([m['content'] for m in recent_msgs if m['role'] != 'system'])
        now_hour = datetime.datetime.now().hour
        query = f"{context_text}"

        dynamic_top_k = 8 if len(query) > 50 else 5

        # 3. RAG 检索
        relevant_diaries = self.rag.search_diaries(query, chat_id=chat_id, top_k=dynamic_top_k)

        prompt = build_ice_break_prompt(chat_id, relevant_diaries, history_dict)

        logger.info(f"[System] Yuki 正在破冰... (Query: {query})")
        try:
            # 4. API 调用
            Yuki_Answer = await self.llm.robust_api_call(
                model=LLM_MODEL,
                messages=prompt,
                temperature=0.8,
                top_p=0.9,
                frequency_penalty=0.2,
                max_tokens=60
            )

            # 清理与记录
            Yuki_Answer = re.sub(r'\s*FINISHED\s*$', '', Yuki_Answer, flags=re.IGNORECASE)

            # 5. 持久化数据 (注意：在异步中尽量减少频繁 save)
            self.history.append_to_log(chat_id, "Yuki", Yuki_Answer)
            history_dict[chat_id].append({"role": "assistant", "content": Yuki_Answer})
            self.history.save(history_dict)

            # 6. 消耗精力
            async with self.yuki.lock:
                self.yuki.consume_energy(chat_id)
                current_energy = self.yuki.energy[chat_id]

            logger.info(f"[System] 破冰成功！发送给 {chat_id} (剩余精力: {current_energy:.1f})")
            await self.sender.send(chat_id, Yuki_Answer, mode="group")

        except Exception as e:
            logger.error(f"Deepseek 破冰调用失败: {e}")
            return f"API 调用失败"

# core/engine.py 末尾新增（或替换原来的 maid_worker）

async def maid_worker(engine, yuki_state, sender, history_manager):
    """小女仆后台常驻 Worker - 完成后交还给 engine 触发正常回复流程"""
    while True:
        task = await yuki_state.maid_task_queue.get()
        goal = task["goal"]
        chat_id = str(task["chat_id"])
        mode = task.get("mode", "group")   # 默认群聊

        # 更新当前任务状态（让 Yuki 能感知到“小女仆正在干这个”）
        yuki_state.maid_current_tasks[chat_id] = goal

        logger.info(f"🧹 小女仆开始后台工作: {goal} (chat_id: {chat_id})")

        # 非阻塞执行（线程池运行同步的 ollama 循环）
        result_dict = await maid_evolution_loop(
            user_goal=goal,
            chat_id=chat_id
        )

        # 清除任务状态
        yuki_state.maid_current_tasks.pop(chat_id, None)

        # 构造汇报内容
        report = f"【小女仆完成! 小女仆汇报】\n任务：「{goal}」\n结果：{result_dict.get('result', '未知结果')}"

        logger.info(f"✅ 小女仆任务完成，准备交还给主流程: {chat_id}")

        # === 关键修改部分 ===
        try:
            # 1. 加载当前历史
            history_dict = history_manager.load()
            if chat_id not in history_dict:
                history_dict[chat_id] = [{"role": "system", "content": yuki_state.get_setting(mode)}]

            current_time_str = datetime.datetime.now().strftime("%Y年%m月%d日%H:%M")

            # 2. 把小女仆汇报作为 assistant 消息写入历史（这样 Yuki 下次看到的就是“自己”的汇报）
            history_dict[chat_id].append({
                "role": "user",
                "content": report,
                "time": current_time_str,
                "is_maid_report": True   # 可选标记，方便以后过滤
            })

            # 3. 保存到 chat_history.json
            history_manager.save(history_dict)

            # 4. 强制触发 main_process，让 Yuki 自然思考并决定是否回复
            #    （main_process 会读取最新历史、检索 RAG、决定是否发言等）
            if engine.process_callback is not None:
                asyncio.create_task(
                    engine.process_callback(chat_id, mode, debounce_flag=False,force_reply=True)
                )
                logger.info(f"🚀 已通过 process_callback 触发 main_process (chat_id: {chat_id})")
            else:
                logger.warning(f"⚠️ process_callback 未设置，无法触发回复流程")

            logger.info(f"🚀 已将小女仆汇报交还给 main_process，强制触发回复流程 (chat_id: {chat_id})")

        except Exception as e:
            logger.error(f"❌ 处理小女仆汇报时出错: {e}")

        finally:
            yuki_state.maid_task_queue.task_done()