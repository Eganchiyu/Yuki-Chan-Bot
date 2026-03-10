# bot_main.py
import json
import asyncio
import websockets
import message_utils
import datetime
import time
import re

from yuki_core import YukiState, HistoryManager, BASE_SETTING
from message_utils import CQCodeParser, MessageSender
from meme_processor import MemeProcessor
from config import RETRIEVAL_TOP_K, KEEP_LAST_DIALOGUE
# ------------------- 日记触发检查（空闲+轮数/保底） -------------------
from config import DIARY_IDLE_SECONDS, DIARY_MIN_TURNS, DIARY_MAX_LENGTH
# 导入配置参数
from config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, NAPCAT_WS_URL,
    TARGET_QQ, TARGET_GROUPS, DEBOUNCE_TIME, DIARY_THRESHOLD,
    MIN_ACTIVE_ENERGY, COST_PER_REPLY, MAX_MESSAGE_LENGTH, 
    MESSAGE_TRUNCATE_SUFFIX, FILTER_LONG_MESSAGES
)


async def summarize_memory(chat_id, history):
    print(f"[System] [{chat_id}] 记忆有点长了，Yuki 正在写日记回顾...")
    # 提取对话内容（不包括系统消息）
    dialogue_msgs = [msg for msg in history if msg["role"] != "system"]
    content_to_summarize = json.dumps(dialogue_msgs, ensure_ascii=False)
    time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    summary_prompt = f"你现在是 Yuki。请以 Yuki 的口吻写一篇 200 字以内的日记，总结这段对话。要求真实记录，尤其是完整叙述和性格概述。当前时间：{time_str}"
    try:
        response = yuki.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": f"{BASE_SETTING}"},
                {"role": "user", "content": f"{summary_prompt}\n\n内容如下：\n{content_to_summarize}"}
            ]
        )
        diary_entry = response.choices[0].message.content
        # 存入向量记忆库
        memory_rag.save_diary(diary_entry, chat_id=chat_id)
        print(f"[System] 日记已存入记忆库：{diary_entry[:50]}...")
        # 构建新历史：保留系统消息 + 新日记作为系统消息 + 最近 KEEP_LAST_DIALOGUE 条对话
        system_messages = [msg for msg in history if msg["role"] == "system"]
        new_diary_node = {"role": "system", "content": f"【日记({time_str})】：\n{diary_entry}"}
        recent_dialogue = dialogue_msgs[-KEEP_LAST_DIALOGUE:] # if len(dialogue_msgs) > KEEP_LAST_DIALOGUE else dialogue_msgs
        new_history = system_messages + [new_diary_node] + recent_dialogue
        return new_history
    except Exception as e:
        print(f"写日记失败: {e}")
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
            role_name = "" if msg["role"] == "user" else "Yuki说:"
            dialogue_text += f"{role_name}{msg['content']}\n"

        energy_desc = "精力充沛，很愿意找人聊天" if current_e > 90 else "精力正常，偶尔会回复消息" if current_e > 60 else "疲惫，只想接少数有趣的话题" if current_e > 30 else "非常疲惫，只有认为必须发言时才发言"

        check_prompt = (
            f"【Yuki的当前状态】\n精力值：{current_e:.1f}/100 ({energy_desc})，发言消耗{COST_PER_REPLY}点精力\n\n"
            f"请分析对话氛围，判断现在是否要发言。判断依据：当前发言者是不是说完了要说的全部内容、感兴趣程度、提问对象等，应合理判断氛围\n注意：如果对方表述不完整或模糊，如[图片]，可以不发言"
            f"如果要发言，请回答'YES'。如果想继续潜水观察，请回答'NO'。"
        )

        messages = ([{"role": "system", "content": f"{yuki.get_setting('group')}"}] +
                    [{"role": "system", "content": f"最近对话：\n{dialogue_text}"}] +
                    [{"role": "user", "content": check_prompt}])

        print(f"[System] 构建的messages: {messages}")

        response = yuki.client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            max_tokens=10,
            temperature=0.7
        )

        result = response.choices[0].message.content.strip().upper()
        return "YES" in result
    except Exception as e:
        print(f"[ERROR] 判定失败原因: {e}")
        return False

async def clean_cq_code(text: str, group_id: str = None) -> str:
    """
    清理CQ码，解析@为用户名，并对动画表情进行AI理解
    可传入群号 group_id 以在解析 @ 时使用群名片
    """
    print(f"[System] 解析CQ码中")
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

    # 传入 group_id 以解析 @ 时使用群名片
    parsed_text = await message_processor.parse_all_cq_codes(final_text, group_id)
    return parsed_text

async def process_messages(chat_id, websocket, mode):
    await asyncio.sleep(DEBOUNCE_TIME)
    messages = yuki.message_buffer.get(chat_id, [])
    if not messages: return

    print(f"[System] 收到消息，准备处理... (chat_id={chat_id})")

    raw_combined_text = "\n".join(messages)
    # 如果是群聊模式，传入 chat_id 作为群号
    group_id = chat_id if mode == "group" else None
    combined_text = await clean_cq_code(raw_combined_text, group_id)

    yuki.message_buffer[chat_id] = []
    if chat_id in yuki.buffer_tasks: del yuki.buffer_tasks[chat_id]

    history_manager.append_to_log(chat_id, "User/Group", combined_text)

    history_dict = history_manager.load()
    cid = str(chat_id)

    if cid not in history_dict:
        history_dict[cid] = [{"role": "system", "content": yuki.get_setting(mode)}]

    history_dict[cid].append({"role": "user", "content": combined_text})
    yuki.last_message_time[cid] = time.time()  # 新增
    history_manager.save(history_dict)

    if mode == "group":
        if not await should_i_reply(history_dict[cid], combined_text):
            print("[System] Yuki 决定继续潜水...")
            return

    try:
        print("[System] Yuki 决定回复！")
        print(f"[System] Yuki 正在回忆...")

        # ------------------- RAG 检索：根据当前用户消息查找相关日记 ------------------------

        # 从历史中提取最近 N 条非系统消息作为检索 query
        # QUERY_HISTORY_COUNT = 8  # 可配置
        # 取最后 QUERY_HISTORY_COUNT 条（避免过滤后数量不足）
        # [-QUERY_HISTORY_COUNT * 2:]
        non_system_msgs = [msg for msg in history_dict[cid] if msg["role"] != "system"]

        query_msgs = non_system_msgs
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
        # ---------- 新增调试打印 ----------
        print(f"[System] 检索到 {len(relevant_diaries)} 条相关日记:")
        for i, diary in enumerate(relevant_diaries, 1):
            # 只打印前100字符，避免刷屏
            preview = diary[:100] + "..." if len(diary) > 100 else diary
            print(f"  回忆 {i}: {preview}")
        # ---------------------------------


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

        # 4. 确保最后一条是当前用户消息（如果最近对话中已有，则不重复）
        # if not recent_msgs or recent_msgs[-1]["role"] != "user" or recent_msgs[-1]["content"] != combined_text:
        #     combined_API_message.append({"role": "user", "content": combined_text})

        # --------------------- 发送对话补全到DeepSeek ----------------------
        print(f"[System] Yuki 正在打字...(剩余精力: {yuki.energy:.1f})")
        response = yuki.client.chat.completions.create(
            model="deepseek-chat",
            messages=combined_API_message  # 使用新构建的消息列表
        )
        Yuki_Answer = response.choices[0].message.content
        Yuki_Answer = re.sub(r'\s*FINISHED\s*$', '', Yuki_Answer, flags=re.IGNORECASE)

        if mode == "group":
            yuki.consume_energy()

        history_manager.append_to_log(chat_id, "Yuki", Yuki_Answer)
        history_dict[cid].append({"role": "assistant", "content": Yuki_Answer})
        history_manager.save(history_dict)

        sender = MessageSender(websocket)
        print(f"[System] Yuki 正在发送消息...(剩余精力: {yuki.energy:.1f})")
        await sender.send(chat_id, Yuki_Answer, mode=mode)
    except Exception as e:
        print(f"Deepseek 调用失败: {e}")

        # ------------------- 日记触发检查（空闲+轮数/保底） -------------------
    # 保底触发：历史总长度超过 DIARY_MAX_LENGTH 时强制写日记
    if len(history_dict[cid]) >= DIARY_MAX_LENGTH and cid not in yuki.writing_diary:
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
        print(f"⏰ 后台检查中时间中...{now}")  # 调试输出
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
            if non_system_count < DIARY_MIN_TURNS:
                continue  # 轮数不足

            # 满足条件，触发写日记
            print(f"⏰ 后台检查：群 {cid} 空闲 {idle_seconds:.1f} 秒，轮数 {non_system_count}，触发写日记")
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
                    manage_buffer(data.get("user_id"), data.get("raw_message"), websocket, "private")
                
                elif mode == "group" and msg_type == "group":
                    group_id = data.get("group_id")
                    # 如果 TARGET_GROUPS 为空列表，则接收所有群；否则只接收列表中的群
                    if not TARGET_GROUPS or group_id in TARGET_GROUPS:
                        sender = data.get("sender", {})
                        sender_name = sender.get("card") or sender.get("nickname") or "未知路人"
                        manage_buffer(group_id, f"【“{sender_name}”】说: {data.get('raw_message')}", websocket, "group")
                # elif mode == "group" and msg_type == "group" and data.get("group_id") == TARGET_GROUP:
                #     sender = data.get("sender", {})
                #     # 优先使用群名片，若没有则用个人昵称
                #     sender_name = sender.get("card") or sender.get("nickname") or "未知路人"
                #     manage_buffer(data.get("group_id"), f"{sender_name}说: {data.get('raw_message')}", websocket, "group")
        except:
            await asyncio.sleep(3)

def manage_buffer(chat_id, content, websocket, mode):
    # 1. 预处理：调用工具函数进行截断（如果有需要）
    if FILTER_LONG_MESSAGES:
        content = message_utils.smart_truncate(content, MAX_MESSAGE_LENGTH, MESSAGE_TRUNCATE_SUFFIX)
    
    # 2. 状态维护：进入缓冲区
    if chat_id not in yuki.message_buffer: 
        yuki.message_buffer[chat_id] = []
    yuki.message_buffer[chat_id].append(content)
    
    # 3. 异步调度：防抖逻辑
    if chat_id in yuki.buffer_tasks: 
        yuki.buffer_tasks[chat_id].cancel()
    
    yuki.buffer_tasks[chat_id] = asyncio.create_task(
        process_messages(chat_id, websocket, mode)
    )

if __name__ == "__main__":
    print("[System] Yuki 正在初始化...")
    start_time = time.time()
    # 初始化各模块
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
    
    asyncio.run(main_logic("private" if choice == "1" else "group"))