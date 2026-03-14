# bot_main.py
# by: Eganchiyu
import json
import asyncio
import websockets
import datetime
import time
import re

# 导入核心模块和工具类
from yuki_core import YukiState, HistoryManager, BASE_SETTING
from message_utils import CQCodeParser, MessageSender
from meme_processor import MemeProcessor
from config import RETRIEVAL_TOP_K, KEEP_LAST_DIALOGUE
from config import DIARY_IDLE_SECONDS, DIARY_MIN_TURNS, DIARY_MAX_LENGTH

# 从 config 导入 API 配置和目标配置
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
from config import NAPCAT_WS_URL, TARGET_QQ, TARGET_GROUPS
from config import (
    DEBOUNCE_TIME, DIARY_THRESHOLD, 
    MIN_ACTIVE_ENERGY, COST_PER_REPLY, 
    MAX_MESSAGE_LENGTH
)

# 初始化全局变量：消息缓冲和定时任务
message_buffer = {}
buffer_tasks = {}
real_time_debounce_time = DEBOUNCE_TIME

async def summarize_memory(chat_id, history):
    '''根据当前对话历史写日记，并存入记忆库，返回更新后的历史'''

    print(f"[System] [{chat_id}] 记忆有点长了，Yuki 正在写日记回顾...")
    dialogue_msgs = [msg for msg in history if msg["role"] != "system"]
    content_to_summarize = json.dumps(dialogue_msgs, ensure_ascii=False)
    time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    summary_prompt = (
        f"你现在是 Yuki。请以 Yuki 的口吻写一篇 200 字以内的日记，总结这段对话。"
        f"要求真实记录，尤其是完整叙述和性格概述，不要删减重要内容。"
        f"当前时间：{time_str}。\n"
        f"注意：如果对话中有提到性格、喜好、习惯等细节，请务必写入日记，这些是Yuki记忆的重要组成部分。"
        f"日记格式要求：\n 不用加标题、天气、颜文字和时间戳，直接正文开头。"
    )
    
    try:
        response = yuki.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": f"{BASE_SETTING}"},
                {"role": "user", "content": (
                    f"以下是需要总结的对话内容：\n{content_to_summarize}\n\n"
                    f"---任务指令---\n"
                    f"{summary_prompt}"
                )}
            ]
        )

        diary_content = response.choices[0].message.content
        diary_content = re.sub(r'\s*FINISHED\s*$', '', diary_content, flags=re.IGNORECASE)
        diary_content = f"【日记({time_str})】：\n{diary_content}"
        memory_rag.save_diary(diary_content, chat_id=chat_id)
        print(f"[System] 日记已存入记忆库：{diary_content}")
        
        new_history_json = (
            [msg for msg in history if msg["role"] == "system"] +
            dialogue_msgs[-KEEP_LAST_DIALOGUE:]
        )
        return new_history_json
    
    except Exception as e:
        print(f"[System ERROR] 写日记失败: {e}")
        return history

async def should_i_reply(history, current_text):
    """使用API判断是否需要回复群聊，加入精力值逻辑"""

    current_e = yuki.update_energy()

    if any(keyword in current_text for keyword in ["主人", "哥哥", "Yuki", "yuki"]):
        print(f"[System] 检测到关键召唤，Yuki 强制清醒 (当前精力: {current_e:.1f})")
        return True

    if current_e < MIN_ACTIVE_ENERGY:
        print(f"[System] Yuki 太累了... 正在潜水回复体力 (当前精力: {current_e:.1f})")
        return False

    try:
        print(f"[System] 正在构建判定消息... (当前精力: {current_e:.1f})")
        # system_context = [msg for msg in history if msg.get("role") == "system"]
        recent_dialogue = [msg for msg in history if msg.get("role") != "system"][-10:]

        dialogue_text = ""
        for msg in recent_dialogue:
            role_name = "" if msg["role"] == "user" else "【Yuki】说:"
            dialogue_text += f"{role_name}{msg['content']}\n\n"

        energy_desc = "精力充沛，很愿意找人聊天" if current_e > 90 else "精力正常，会选择性接有趣的话题" if current_e > 45 else "疲惫，只想接少数有趣的话题" if current_e > 25 else "非常疲惫，只有认为必须发言时才发言"

        check_prompt = (
            f"请分析对话上下文和氛围，判断现在是否要发言。yuki对感兴趣的话题会冒泡，但是会避免过于频繁地打扰大家。对主人和yuki的直接称呼会增加发言倾向。请综合考虑对话内容、氛围和当前精力，判断yuki是否应该发言。\n\n"
            f"如果要发言，请回答'YES'。如果想继续潜水观察，请回答'NO'。"
        )

        messages = [
            {"role": "system", "content": yuki.get_setting('group')},
            {"role": "user", "content": (
                f"/----最近对话----/："
                f"\n\n{dialogue_text}\n\n"
                f"{check_prompt}"
            )}
        ]

        messages = [
            {"role": "system", "content": f"{yuki.get_setting('group')}\n你现在需要根据精力值和氛围决定是否发言。"},
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

        response = yuki.client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            max_tokens=10,
            temperature=0.7
        )

        result = response.choices[0].message.content.strip().upper()
        result = re.sub(r'\s*FINISHED\s*$', '', result, flags=re.IGNORECASE)

        return ("YES" in result)
    except Exception as e:
        print(f"[ERROR] 判定失败原因: {e}")
        return False

async def clean_cq_code(text):
    """处理消息中的CQ码，提取图片URL并调用meme_processor理解，返回最终文本"""
    modified_text, image_urls = meme_processor.extract_urls_from_text(text)

    if image_urls:
        understood_contents = []
        for url in image_urls:
            result = await meme_processor.understand_from_url(url)
            understood_contents.append(result)

        final_text = modified_text
        for content in understood_contents:
            final_text = final_text.replace("[图片占位符]", content, 1)
    else:
        final_text = text

    parsed_text = await message_processor.parse_all_cq_codes(final_text)
    return parsed_text

async def process_messages(chat_id, websocket, mode):
    """处理缓冲中的消息，进行API交互和回复 """
    global real_time_debounce_time
    await asyncio.sleep(real_time_debounce_time)  # 防抖等待，合并短时间内的多条消息
    messages = yuki.message_buffer.get(chat_id, [])
    if not messages: return

    combined_text = await clean_cq_code("\n".join(messages))
    combined_text = combined_text.replace("\n", " ").strip()

    print(f"[{chat_id}] 收到消息{combined_text}")
    yuki.message_buffer[chat_id] = []
    if chat_id in yuki.buffer_tasks: del yuki.buffer_tasks[chat_id]

    history_manager.append_to_log(chat_id, "User/Group", combined_text)

    history_dict = history_manager.load()
    cid = str(chat_id)

    if cid not in history_dict:
        history_dict[cid] = [{"role": "system", "content": yuki.get_setting(mode)}]

    history_dict[cid].append({"role": "user", "content": combined_text})
    history_manager.save(history_dict)

    if mode == "group":
        if not await should_i_reply(history_dict[cid], combined_text): # 判定是否回复
            print("[System] Yuki 决定继续潜水...")
            return

    try:
        print("[System] Yuki 决定回复！")
        print(f"[System] Yuki 正在回忆...")

        # ------------------- RAG 检索：根据当前用户消息查找相关日记 ------------------------
        query_msgs = [msg for msg in history_dict[cid] if msg["role"] != "system"]
        query_parts = []
        for msg in query_msgs:
            role_prefix = "" if msg["role"] == "user" else "Yuki说:"
            query_parts.append(f"{role_prefix}{msg['content']}|")
        query = "\n".join(query_parts)

        # 如果 query 为空（比如全是系统消息），则 fallback 到当前消息
        if not query.strip():
            query = combined_text
        relevant_diaries = memory_rag.search_memory(
            query, 
            chat_id = cid,
            top_k = RETRIEVAL_TOP_K, 
            threshold = DIARY_THRESHOLD
        )
        print(f"[System] 检索到 {len(relevant_diaries)} 条相关日记:")
        for i, diary in enumerate(relevant_diaries, 1):
            preview = diary[:50] + "..." if len(diary) > 100 else diary
            preview = preview.replace('\n', ' ')
            print(f"[Diary Debug]回忆 {i}: {preview}")
        # ----------------------- 构建API消息列表 ----------------------------
        #
        # 1. 基础人设（取历史第一个系统消息）
        system_prompt = history_dict[cid][0]["content"] if history_dict[cid] and history_dict[cid][0][
            "role"] == "system" else yuki.get_setting(mode)
        combined_API_message = [{"role": "system", "content": system_prompt}]

        # 2. 插入检索到的日记作为系统消息
        for diary in relevant_diaries:
            combined_API_message.append({"role": "system", "content": f"【回忆】{diary}"})

        # 3. 加入最近KEEP_LAST_DIALOGUE条对话（不包括系统消息）
        recent_msgs = [msg for msg in history_dict[cid][-KEEP_LAST_DIALOGUE-1:-1] if msg["role"] != "system"]
        combined_API_message.extend(recent_msgs)
        combined_API_message.append({"role": "user", "content": f" (当前时间:{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}){combined_text}"})

        # --------------------- 发送对话补全到DeepSeek ----------------------
        print(f"[System] Yuki 正在打字...(剩余精力: {yuki.energy:.1f})")
        response = yuki.client.chat.completions.create(
            model="deepseek-chat",
            messages=combined_API_message  # 使用新构建的消息列表
        )
        Yuki_Answer = response.choices[0].message.content
        Yuki_Answer = re.sub(r'\s*FINISHED\s*$', '', Yuki_Answer, flags=re.IGNORECASE)

        real_time_debounce_time = DEBOUNCE_TIME  # 重置防抖时间，准备处理下一轮消息

        history_manager.append_to_log(chat_id, "Yuki", Yuki_Answer)
        history_dict[cid].append({"role": "assistant", "content": Yuki_Answer})
        history_manager.save(history_dict)

        sender = MessageSender(websocket)
        if mode == "group":
            yuki.consume_energy()
        print(f"[System] Yuki 正在发送消息...(剩余精力: {yuki.energy:.1f})")
        await sender.send(chat_id, Yuki_Answer, mode=mode)
    except Exception as e:
        print(f"Deepseek 调用失败: {e}")

    # --------------------- 日记触发检查：如果历史过长，强制写日记 ----------------------
    effective_history = [message for message in history_dict[cid] if message["role"] != "system"]

    if len(effective_history) >= DIARY_MAX_LENGTH and cid not in yuki.writing_diary:
        print(f"[System] 历史长度达到保底阈值 {DIARY_MAX_LENGTH}，触发写日记")
        yuki.writing_diary.add(cid)
        try:
            history_dict[cid] = await summarize_memory(chat_id, history_dict[cid])
            history_manager.save(history_dict)
        finally:
            yuki.writing_diary.discard(cid)


async def idle_diary_checker():
    """后台任务，每30秒检查一次空闲群聊"""
    while True:
        await asyncio.sleep(30)  # 检查间隔，可根据需要调整
        now = time.time()
        print(f"[System] 后台检查中... ({datetime.datetime.now().strftime('%H:%M:%S')})")
        history_dict = history_manager.load()
        for cid, last_msg in list(yuki.last_message_time.items()):
            # 跳过正在写日记的群聊
            if cid in yuki.writing_diary:
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
            if non_system_count < DIARY_MIN_TURNS :  # 如果轮数不足但空闲时间已经是阈值的两倍，不输出
                if idle_seconds < DIARY_IDLE_SECONDS * 2:
                    print(
                        f"[System] 群 {cid} 空闲 {idle_seconds:.1f} 秒，但对话轮数仅 {non_system_count}，继续观察..."
                        f"({datetime.datetime.now().strftime('%H:%M:%S')})"
                    )
                continue  # 轮数不足

            # 满足条件，触发写日记
            print(f"[System] 后台检查：群 {cid} 空闲 {idle_seconds:.1f} 秒，轮数 {non_system_count}，触发写日记")
            yuki.writing_diary.add(cid)
            try:
                new_history = await summarize_memory(int(cid), history_dict[cid])
                history_dict[cid] = new_history
                history_manager.save(history_dict)
            finally:
                yuki.writing_diary.discard(cid)

async def main_logic(mode):
    asyncio.create_task(idle_diary_checker())   # 启动后台检查
    print("[System] 已启动后台空闲日记检查任务")
    print(f"[System] 连接 NapCat 服务端 | 模式: {mode} | 初始精力: {yuki.energy}")
    async for websocket in websockets.connect(NAPCAT_WS_URL):
        try:
            async for message in websocket:
                data = json.loads(message)
                if data.get("post_type") != "message": continue

                msg_type = data.get("message_type")
                if mode == "private" and msg_type == "private" and data.get("user_id") == TARGET_QQ:
                    await manage_buffer(data.get("user_id"), data.get("raw_message"), websocket, "private")
                
                elif mode == "group" and msg_type == "group":
                    group_id = data.get("group_id")
                    if not TARGET_GROUPS or group_id in TARGET_GROUPS: # 如果 TARGET_GROUPS 为空列表，则接收所有群；否则只接收列表中的群
                        sender = data.get("sender", {})
                        sender_name = sender.get("card") or sender.get("nickname") or "未知路人"
                        await manage_buffer(group_id, f"【“{sender_name}”】说: {data.get('raw_message')}", websocket, "group")
        except:
            await asyncio.sleep(3)

async def manage_buffer(chat_id, content, websocket, mode):
    global message_buffer, buffer_tasks, real_time_debounce_time

    if real_time_debounce_time <= 0:
        real_time_debounce_time = DEBOUNCE_TIME  # 重置防抖时间，避免长时间关闭防抖导致过度频繁响应

    cid_str = str(chat_id)
    yuki.last_message_time[str(cid_str)] = time.time()
    if len(content) > MAX_MESSAGE_LENGTH:
        print(f"[System] 检测到超长消息 ({len(content)} 字符)")
        parts = re.split(r'(\[CQ:.*?\])', content)
        result = []
        
        for part in parts:
            if not part:
                continue

            if part.startswith('[CQ:') and part.endswith(']'):
                result.append(part)

            else:
                if len(part) > 100:
                    half = 40
                    part = part[:half] + '……' + part[-half:]
                result.append(part)
        
        content = ''.join(result)
        print(f"[System] 压缩后长度: {len(content)} 字符")
    
    # 入队
    
    if chat_id not in yuki.message_buffer: yuki.message_buffer[chat_id] = []
    yuki.message_buffer[chat_id].append(content)
    if "yuki" in content.lower():
        real_time_debounce_time = 0.1  # 提升召唤消息的响应速度
    if chat_id in yuki.buffer_tasks: yuki.buffer_tasks[chat_id].cancel()
    yuki.buffer_tasks[chat_id] = asyncio.create_task(process_messages(chat_id, websocket, mode))
    await asyncio.sleep(1)  # 确保任务已启动
    real_time_debounce_time = DEBOUNCE_TIME  # 重置为默认防抖时间

if __name__ == "__main__":
    print("[System] Yuki 正在初始化...")
    start_time = time.time()
    message_processor = CQCodeParser(NAPCAT_WS_URL)
    meme_processor = MemeProcessor()
    yuki = YukiState(DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL)
    history_manager = HistoryManager()
    print("[System] 开始初始化记忆系统（RAG）...")
    from memory_rag import MemoryRAG
    memory_rag = MemoryRAG()
    end_time = time.time()
    print(f"[System] 初始化完成，耗时 {end_time - start_time:.1f} 秒")
    choice = input("[System] 选择模式：1. 私聊模式  2. 群聊模式（默认）\n请输入数字: ").strip()
    if choice == "2":
        # 初始化巡检名单，预载历史中的群聊ID和最后消息时间，确保后台检查能正常工作
        h_dict = history_manager.load()
        for cid in h_dict.keys():
            yuki.last_message_time[str(cid)] = time.time()
        print(f"DEBUG: 已预载 {len(yuki.last_message_time)} 个群组到巡检名单")
    asyncio.run(main_logic("private" if choice == "1" else "group"))