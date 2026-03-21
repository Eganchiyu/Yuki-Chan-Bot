# core/engine.py
import json
import random
import re
import asyncio
import datetime
import time
from typing import Any
from core.prompts import BASE_SETTING, SUMMARY_PROMPT
from config import *
from core.prompts import build_ice_break_prompt


class YukiEngine:
    def __init__(self, llm, rag, history_manager, yuki_state, sender):
        self.llm = llm
        self.rag = rag
        self.history = history_manager
        self.yuki = yuki_state
        self.sender = sender

    async def api_reply(self, chat_id: str, combined_text: str, history_dict: dict, mode, relevant_diaries: list[Any]) -> str:
        # 总构建发送Deepseek补全的信息
        combined_API_message = await self.build_chat_context(
            chat_id,
            combined_text,
            history_dict,
            mode,
            relevant_diaries
        )

        # 发送对话补全到DeepSeek
        print(f"[System] Yuki 正在打字...")
        try:
            Yuki_Answer = await self.llm.robust_api_call(
                model="deepseek-chat",
                messages=combined_API_message,
                temperature=0.7,  # 降低温度，让它说话更稳、更常用
                top_p=0.75,  # 稍微收窄采样范围，过滤冷门词
                frequency_penalty=0.05,  # 极低的惩罚，允许它说大白话
                presence_penalty=0.0,  # 不强迫它聊新话题
                max_tokens=100  # 强制短句，短句更容易显自然
            )
            Yuki_Answer = re.sub(r'\s*FINISHED\s*$', '', Yuki_Answer, flags=re.IGNORECASE)
            return Yuki_Answer
        except Exception as e:
            print(f"Deepseek 调用失败: {e}")
            return f"API 接口调用失败"

    async def decide_to_reply(self, history, current_text, chat_id):
        """判断是否回复群聊"""
        """
            三段式决策：强干预 -> 弱判定 -> 逻辑判定
            """
        # 1. 更新并获取当前群聊的欲望值
        self.yuki.update_energy()
        self.yuki.update_desire_to_reply(chat_id)
        desire = self.yuki.desire_to_start_topic.get(str(chat_id), 0)

        # --- 强干预层 ---
        if desire >= 80:
            print(f"[Decision] {chat_id} 欲望爆表({desire}%)，强制回复！")
            return True
        if desire <= 30:
            print(f"[Decision] {chat_id} 欲望低迷({desire}%)，拒绝营业。")
            return False

        current_e = self.yuki.update_energy()

        if any(keyword in current_text for keyword in ["主人", "哥哥", "Yuki", "yuki"]):
            print(f"[System] 检测到关键召唤，Yuki 强制清醒 (当前精力: {current_e:.1f})")
            return True

        if current_e < MIN_ACTIVE_ENERGY:
            print(f"[System] Yuki 太累了... 正在潜水回复体力 (当前精力: {current_e:.1f})")
            return False

        try:
            print(f"[System] 正在构建判定消息... (当前精力: {current_e:.1f})")
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
            print(f"[DEBUG] \n {messages}")
            print(f"[System] 判定消息构建完成，正在发送API请求... (当前精力: {current_e:.1f})")

            raw_response = await self.llm.robust_api_call(
                model="deepseek-chat",
                messages=messages,
                max_tokens=10,
                temperature=0.6
            )

            # 2. 拿到字符串后再进行各种清洗
            result = raw_response.strip().upper()
            result = re.sub(r'\s*FINISHED\s*$', '', result, flags=re.IGNORECASE)

            return "YES" in result
        except Exception as e:
            print(f"[ERROR] 判定失败原因: {e}")
            return False

    async def do_summarize(self, chat_id, history):
        print(f"[System] [{chat_id}] 记忆有点长了，Yuki 正在写日记回顾...")
        dialogue_msgs = [msg for msg in history if msg["role"] != "system"]
        content_to_summarize = json.dumps(dialogue_msgs, ensure_ascii=False)
        try:
            diary_content = await self.llm.robust_api_call(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": f"{BASE_SETTING}"},
                    {"role": "user", "content": (
                        f"以下是需要总结的对话内容：\n{content_to_summarize}\n\n"
                        f"---任务指令---\n"
                        f"{SUMMARY_PROMPT}"
                    )}
                ],
                temperature=0.7,  # 降低温度，让它说话更稳、更常用
                top_p=0.8,  # 稍微收窄采样范围，过滤冷门词
                frequency_penalty=0.1,  # 极低的惩罚，允许它说大白话
                presence_penalty=0.0,  # 不强迫它聊新话题
                max_tokens=200  # 强制短句，短句更容易显自然
            )
            diary_content = re.sub(r'\s*FINISHED\s*$', '', diary_content, flags=re.IGNORECASE)
            diary_content = f"【日记({datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})】：\n{diary_content}"
            self.rag.save_diary(diary_content, chat_id=chat_id)
            print(f"[System] 日记已存入记忆库：{diary_content}")

            return [msg for msg in history if msg["role"] == "system"] + dialogue_msgs[-KEEP_LAST_DIALOGUE:]

        except Exception as e:
            print(f"[System ERROR] 写日记失败: {e}")
            return history

    async def idle_diary_checker(self):
        """后台任务，每30秒检查一次空闲群聊"""
        while True:
            await asyncio.sleep(30)  # 检查间隔，可根据需要调整
            now = time.time()
            print(f"⏰ 后台检查中时间中...{now}")  # 调试输出
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
                print(f"⏰ 后台检查：群 {cid} 空闲 {idle_seconds:.1f} 秒，轮数 {non_system_count}，触发写日记")
                self.yuki.writing_diary.add(cid)
                try:
                    new_history = await self.do_summarize(int(cid), history_dict[cid])
                    history_dict[cid] = new_history
                    self.history.save(history_dict)
                finally:
                    self.yuki.writing_diary.discard(cid)


    async def build_chat_context(self, chat_id: str, combined_text: str, history_dict: dict, mode,relevant_diaries: list[Any]) -> list[dict[str, str | Any]]:
        # 这里的 diary 现在是字典，我们要取出 ['content']
        for i, diary_obj in enumerate(reversed(relevant_diaries), 1):
            content = diary_obj['content']  # 提取文本内容
            # preview = content[:50] + "..." if len(content) > 100 else content
            preview = content
            preview = preview.replace('\n', ' ')
            print(f"[Diary Debug]回忆 {i}: {preview}")

        # 1. 基础人设
        system_prompt = history_dict[chat_id][0]["content"] if history_dict[chat_id] and history_dict[chat_id][0][
            "role"] == "system" else self.yuki.get_setting(mode)
        combined_API_message = [{"role": "system", "content": system_prompt}]

        # 2. 插入检索到的日记
        for diary_obj in reversed(relevant_diaries):
            content = diary_obj['content']  # 提取文本内容
            combined_API_message.append({"role": "system", "content": f"【回忆】{content}"})

        # --- 调试输出：打印加权分和匹配到的关键词信息 ---
        for i, diary_obj in enumerate(relevant_diaries[:3], 1):
            # 打印加权分和匹配到的关键词信息
            print(f"[RAG-Debug] 回忆 {i} | 得分: {diary_obj['score']:.2f} | 详情: {diary_obj['debug']}")

        # 3. 加入最近KEEP_LAST_DIALOGUE条对话（不包括系统消息）
        recent_msgs = [msg for msg in history_dict[chat_id][-KEEP_LAST_DIALOGUE - 1:-1] if msg["role"] != "system"]
        combined_API_message.extend(recent_msgs)
        combined_API_message.append(
            {"role": "user", "content": f" (当前时间:{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}){combined_text}"})
        return combined_API_message

    async def ice_break_monitor(self):
        await asyncio.sleep(2)
        while True:
            target_list = [str(gid) for gid in TARGET_GROUPS]
            # 用来存放通过判定的群组，避免在锁内执行长任务
            pending_ice_break = []

            async with self.yuki.lock:
                # --- 锁内只做纯数值计算和判定 ---
                for cid in target_list:
                    activity = self.yuki.group_activity.get(cid, 0.0)
                    self.yuki.update_energy()
                    self.yuki.update_desire_to_reply(cid)
                    desire = self.yuki.desire_to_start_topic.get(cid, 0)

                    if activity < 0.5 and desire > 75:
                        if random.random() < 0.8:
                            pending_ice_break.append(cid)
            # --- 锁已释放 ---

            # 执行破冰任务
            for cid in pending_ice_break:
                print(f"[IceBreak] 目标群 {cid} 触发冷场唤醒！")
                # 异步抛出，不等待它执行完，直接进入下一个循环的 sleep
                asyncio.create_task(self.break_ice(cid))

            # 巡检周期
            await asyncio.sleep(random.randint(600, 1200))

    async def break_ice(self, chat_id: str) -> str:
        # 1. 异步加载历史 (假设 load 是同步的，我们用线程池跑它)
        # 如果 history.load 很快，可以暂时保留同步，但 save 必须小心
        history_dict = self.history.load()

        if chat_id not in history_dict:
            return None

        # 2. 构造 Query 逻辑 (保持你的原汁原味)
        recent_msgs = history_dict[chat_id][-5:]
        context_text = "".join([m['content'] for m in recent_msgs if m['role'] == 'user'])
        now_hour = datetime.datetime.now().hour
        time_label = "深夜" if 1 <= now_hour <= 5 else "日常"
        query = f"{time_label}氛围下，关于 {context_text[:30]} 的记忆或有趣瞬间"

        dynamic_top_k = 8 if len(query) > 50 else 5

        # 3. RAG 检索
        relevant_diaries = self.rag.search_diaries(query, chat_id=chat_id, top_k=dynamic_top_k)

        # 注意：这里调用的是我们刚刚写好的那个 context 构造函数
        prompt = build_ice_break_prompt(chat_id, relevant_diaries, history_dict)

        # print(f"[Engine Debug] 构建的prompt内容：{prompt}")

        print(f"[System] Yuki 正在破冰... (Query: {query})")
        try:
            # 4. API 调用
            Yuki_Answer = await self.llm.robust_api_call(
                model="deepseek-chat",
                messages=prompt,
                temperature=0.8,  # 降低温度，让它说话更稳、更常用
                top_p=0.9,  # 稍微收窄采样范围，过滤冷门词
                frequency_penalty=0.2,  # 极低的惩罚，允许它说大白话
                max_tokens=60  # 强制短句，短句更容易显自然
            )

            # 清理与记录
            Yuki_Answer = re.sub(r'\s*FINISHED\s*$', '', Yuki_Answer, flags=re.IGNORECASE)

            # 5. 持久化数据 (注意：在异步中尽量减少频繁 save)
            self.history.append_to_log(chat_id, "Yuki", Yuki_Answer)
            history_dict[chat_id].append({"role": "assistant", "content": Yuki_Answer})
            self.history.save(history_dict)

            # 6. 【核心修复】安全地消耗精力
            async with self.yuki.lock:
                self.yuki.consume_energy()
                current_energy = self.yuki.energy

            print(f"[System] 破冰成功！发送给 {chat_id} (剩余精力: {current_energy:.1f})")
            await self.sender.send(chat_id, Yuki_Answer, mode="group")

        except Exception as e:
            print(f"Deepseek 破冰调用失败: {e}")
            return f"API 调用失败"