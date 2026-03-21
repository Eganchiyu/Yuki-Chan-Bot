# main.py
# by: Eganchiyu
import asyncio
import time

from core.brain import YukiState
from core.engine import YukiEngine
from core.history_manager import HistoryManager
from modules.message.CQProtocol import smart_truncate
from modules.message.CQParser import CQCodeParser
from modules.vision.processor import MemeProcessor
from network.ws_connection import BotConnector
from network.ws_sender import MessageSender
from network.api_request import ApiCall
from config import *

# 初始化全局变量：消息缓冲和定时任务
real_time_debounce_time = DEBOUNCE_TIME

async def main_process(chat_id, mode):
    """处理缓冲中的消息，进行API交互和回复 """
    global real_time_debounce_time
    await asyncio.sleep(real_time_debounce_time)  # 防抖等待，合并短时间内的多条消息
    real_time_debounce_time = DEBOUNCE_TIME  # 重置防抖时间，准备处理下一轮消息
    messages = yuki.pop_buffer(chat_id)
    if not messages: return

    # 视觉理解总处理
    combined_text = "\n".join(messages)
    modified_text, image_urls = meme_processor.extract_urls_from_text(combined_text)
    if image_urls:
        understood_contents = []
        for url in image_urls:
            result = await meme_processor.understand_from_url(url, llm)
            understood_contents.append(result)

        combined_text = modified_text
        for content in understood_contents:
            combined_text = combined_text.replace("[图片占位符]", content, 1)

    # 剩下的CQ码文本解析（@、回复等）交给 parser
    combined_text = await parser.parse_all_cq_codes(combined_text)
    combined_text = combined_text.replace("\n", "  ").strip()
    print(f"[{chat_id}] 收到消息{combined_text}")
    history_manager.append_to_log(chat_id, "User/Group", combined_text)


    # 加载上下文信息
    history_dict = history_manager.load()
    chat_id = str(chat_id)
    # 如果不存在则初始化
    if chat_id not in history_dict:
        history_dict[chat_id] = [{"role": "system", "content": yuki.get_setting(mode)}]
    # 添加当前消息到上下文池
    history_dict[chat_id].append({"role": "user", "content": combined_text})

    if (mode == "group") and (not await engine.decide_to_reply(history_dict[chat_id], combined_text, chat_id)): # 判定是否回复
        # 保存获取的上下文信息
        history_manager.save(history_dict)
        print("[System] Yuki 决定继续潜水...")
        return

    print(f"[System] Yuki 正在回忆...")

    # 检索相关记忆总用法（包含关键词提取和语义向量匹配）
    relevant_diaries = memory_rag.search_diaries(combined_text, chat_id=chat_id)
    print(f"[System] 检索到 {len(relevant_diaries)} 条相关日记:")

    Yuki_Answer = await engine.api_reply(chat_id, combined_text, history_dict, mode, relevant_diaries)

    # 保存回复到上下文
    history_manager.append_to_log(chat_id, "Yuki", Yuki_Answer)
    history_dict[chat_id].append({"role": "assistant", "content": Yuki_Answer})
    history_manager.save(history_dict)

    if mode == "group":
        yuki.consume_energy()
    print(f"[System] Yuki 正在发送消息...(剩余精力: {yuki.energy:.1f})")
    await sender.send(chat_id, Yuki_Answer, mode=mode)

    # 提高群聊的活跃度
    await yuki.boost_activity(chat_id)



    # 日记触发检查：如果历史过长，强制写日记
    if len(history_dict[chat_id]) > DIARY_MAX_LENGTH:
        summarized_list = await engine.do_summarize(chat_id, history_dict[chat_id])

        # 2. 【核心修改】将压缩后的“局部列表”更新回“全量字典”的一个分支
        history_dict[chat_id] = summarized_list

        # 3. 保存整个大字典
        history_manager.save(history_dict)
        print(f"[{chat_id}] 日记写入完成，全量历史已同步。")

async def napcat_listen(mode):
    if mode == "group":
        asyncio.create_task(yuki.decay_heartbeat())
    # 启动日记检查
    asyncio.create_task(engine.idle_diary_checker())
    print("[System] 已启动后台空闲日记检查任务")
    print(f"[System] 连接 NapCat 服务端 | 模式: {mode} | 初始精力: {yuki.energy}")
    asyncio.create_task(engine.ice_break_monitor())
    async for data in connector.listen():
        if data.get("post_type") != "message": continue

        msg_type = data.get("message_type")
        raw_msg = data.get("raw_message")
        user_id = data.get("user_id")

        if mode == "private" and msg_type == "private" and user_id == TARGET_QQ:
            await manage_buffer(user_id, raw_msg, mode)

        elif mode == "group" and msg_type == "group":
            group_id = data.get("group_id")
            if not TARGET_GROUPS or group_id in TARGET_GROUPS:
                sender_info = data.get("sender", {})
                name = sender_info.get("card") or sender_info.get("nickname") or "路人"
                await manage_buffer(group_id, f"【“{name}”】说: {raw_msg}", mode, raw_message=raw_msg)

async def manage_buffer(chat_id, content, mode, raw_message=''):
    global real_time_debounce_time

    if real_time_debounce_time <= 0:
        real_time_debounce_time = DEBOUNCE_TIME  # 重置防抖时间，避免长时间关闭防抖导致过度频繁响应

    cid_str = str(chat_id)
    yuki.last_message_time[str(cid_str)] = time.time()

    content = smart_truncate(content, max_len=MAX_MESSAGE_LENGTH, suffix='...')

    # --- 拦截帮助指令并存入历史 ---
    if raw_message in ['help', '/help', 'yuki帮助', 'yuki功能', '帮助', '功能']:
        await sender.send_local_image(chat_id, "utils/yuki_help.png", mode=mode)
        print(f"[System] 已记录并发送帮助图")
        history_manager.append_chat(chat_id, "user", f"(请求帮助文档: {content})")
        history_manager.append_chat(chat_id, "assistant", "(已发送帮助文档图片)")
        return 
    # 入队
    
    if chat_id not in yuki.message_buffer: yuki.message_buffer[chat_id] = []
    yuki.message_buffer[chat_id].append(content)
    if "yuki" in content.lower():
        real_time_debounce_time = 5  # 提升召唤消息的响应速度
    if chat_id in yuki.buffer_tasks: yuki.buffer_tasks[chat_id].cancel()
    yuki.buffer_tasks[chat_id] = asyncio.create_task(main_process(chat_id, mode))

if __name__ == "__main__":
    print("[System] Yuki 正在初始化...")
    start_time = time.time()

    # 加载与Napcat通信的Websocket服务
    connector = BotConnector(NAPCAT_WS_URL)
    # 实例化消息发送器
    sender = MessageSender(connector)
    # 实例化CQ码处理器
    parser = CQCodeParser(connector)
    # 实例化表情处理器
    meme_processor = MemeProcessor()
    # 实例化Yuki状态
    yuki = YukiState()
    # 实例化LLM请求器
    llm = ApiCall(DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL)
    # 实例化历史记录管理器
    history_manager = HistoryManager()
    print("[System] 开始初始化记忆系统（RAG）...")
    from modules.memory.rag import MemoryRAG
    # 初始化向量记忆库
    memory_rag = MemoryRAG()
    # 实例化Yuki主引擎
    engine = YukiEngine(llm, memory_rag, history_manager, yuki, sender)
    end_time = time.time()
    print(f"[System] 初始化完成，耗时 {end_time - start_time:.1f} 秒")
    choice = input("[System] 选择模式：1. 私聊模式  2. 群聊模式（默认）\n请输入数字: ").strip()
    if choice == "2":
        # 初始化巡检名单，预载历史中的群聊ID和最后消息时间，确保后台检查能正常工作
        h_dict = history_manager.load()
        for cid in h_dict.keys():
            yuki.last_message_time[str(cid)] = time.time()
        print(f"DEBUG: 已预载 {len(yuki.last_message_time)} 个群组到巡检名单")
    asyncio.run(napcat_listen("private" if choice == "1" else "group"))