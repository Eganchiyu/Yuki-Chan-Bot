# core/engine.py
import json
import random
import re
import asyncio
import datetime
import time
from typing import Any
from core.prompts import BASE_SETTING, SUMMARY_PROMPT
from config import COST_PER_REPLY, MIN_ACTIVE_ENERGY, KEEP_LAST_DIALOGUE, DIARY_IDLE_SECONDS, DIARY_MIN_TURNS
from prompts import build_ice_break_prompt


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
            Yuki_Answer = self.llm.robust_api_call(
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

            result = self.llm.robust_api_call(
                model="deepseek-chat",
                messages=messages,
                max_tokens=10,
                temperature=0.6
            ).strip().upper()
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
            diary_content = self.llm.robust_api_call(
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
        """单独的异步轮询，监控每个群的冷场情况"""
        while True:
            # 每隔 10-20 分钟检查一次，不需要太频繁
            await asyncio.sleep(random.randint(600, 1200))

            async with self.yuki.lock:
                for cid in list(self.yuki.group_activity.keys()):
                    # 获取归一化后的数据
                    activity = self.yuki.group_activity.get(cid, 0.0)
                    desire = self.yuki.desire_to_start_topic.get(cid, 0)

                    # 判断：冷场(activity < 0.5) 且 想说话(desire > 70)
                    if activity < 0.5 and desire > 70:
                        # 最后的随机骰子，增加灵动感
                        if random.random() < 0.8:
                            print(f"[IceBreak] 发现冷场群 {cid}，准备主动出击！")
                            asyncio.create_task(self.break_ice(cid))

    async def break_ice(self, chat_id: str) -> str:
        # 总构建发送Deepseek补全的信息
        # 加载上下文信息
        history_dict = self.history.load()
        # 如果不存在则初始化
        if chat_id not in history_dict:
            return None

        recent_msgs = history_dict[chat_id][-5:]
        context_text = "".join([m['content'] for m in recent_msgs if m['role'] == 'user'])

        # 2. 结合当前时间感
        now_hour = datetime.datetime.now().hour
        time_label = "深夜" if 1 <= now_hour <= 5 else "日常"

        # 3. 混合构建：时间感 + 最近聊到的模糊语义
        # 这样既能触发关键词匹配，又能让向量搜索找到氛围相近的日记
        query = f"{time_label}氛围下，关于 {context_text[:30]} 的记忆或有趣瞬间"

        # 根据上文长度动态决定提取多少词
        dynamic_top_k = 5
        if len(query) > 50:
            dynamic_top_k = 8  # 信息量大，多抓一点锚点词

        relevant_diaries = self.rag.search_diaries(query, chat_id=chat_id, top_k=dynamic_top_k)
        print(f"[System] 检索到 {len(relevant_diaries)} 条相关日记:")
        prompt = build_ice_break_prompt(chat_id, relevant_diaries, history_dict)
        # 发送对话补全到DeepSeek
        print(f"[System] Yuki 正在破冰...")
        try:
            Yuki_Answer = self.llm.robust_api_call(
                model="deepseek-chat",
                messages=prompt,
                temperature=0.8,  # 降低温度，让它说话更稳、更常用
                top_p=0.9,  # 稍微收窄采样范围，过滤冷门词
                frequency_penalty=0.2,  # 极低的惩罚，允许它说大白话
                max_tokens=60  # 强制短句，短句更容易显自然
            )
            Yuki_Answer = re.sub(r'\s*FINISHED\s*$', '', Yuki_Answer, flags=re.IGNORECASE)
            self.history.append_to_log(chat_id, "Yuki", Yuki_Answer)
            history_dict[chat_id].append({"role": "assistant", "content": Yuki_Answer})
            self.history.save(history_dict)
            self.yuki.consume_energy()
            print(f"[System] Yuki 正在发送消息...(剩余精力: {self.yuki.energy:.1f})")
            await self.sender.send(chat_id, Yuki_Answer, mode="group")
        except Exception as e:
            print(f"Deepseek 调用失败: {e}")
            return f"API 接口调用失败"