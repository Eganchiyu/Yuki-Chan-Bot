# main.py
# by: Eganchiyu
import asyncio
import re
import time
import datetime
import sys

from sympy import true

from core.brain import YukiState
from core.engine import YukiEngine
from core.history_manager import HistoryManager
from modules.message.CQProtocol import smart_truncate
from modules.message.CQParser import CQCodeParser
from modules.vision.processor import MemeProcessor
from network.ws_connection import BotConnector
from network.ws_sender import MessageSender
from config import cfg
from webui import build_ui
import os
from utils.logger import setup_logging, get_logger

setup_logging(debug=cfg.DEBUG)
logger = get_logger("main")
# 初始化全局变量：消息缓冲和定时任务
real_time_debounce_time = cfg.DEBOUNCE_TIME

def check_config():
    """在启动前进行最后的物理检查"""
    if not os.path.exists("configs/config.yaml"):
        env_choice = input("检测到尚未进行基础配置，是否现在运行配置向导？(y/n): ")
        if env_choice.lower() == 'y':
            from setup import quick_setup
            quick_setup(0)  # 以刷新模式运行
        else:
            logger.warning("请手动运行 python setup.py 后再启动。")
            sys.exit(0)

    required_files = ["configs/config.yaml", "blacklist.txt", "./models/text2vec-base-chinese/config.json"]
    for f in required_files:
        if not os.path.exists(f):
            # 抛出异常，触发下面的错误引导
            raise FileNotFoundError(f"关键配置文件或模型缺失: {f}")

async def main_process(chat_id, mode, debounce_flag=True, force_reply=None):
    """处理缓冲中的消息，进行API交互和回复 """
    global real_time_debounce_time
    if debounce_flag:
        await asyncio.sleep(real_time_debounce_time)  # 防抖等待，合并短时间内的多条消息
    else:
        await asyncio.sleep(0.5)
    real_time_debounce_time = cfg.DEBOUNCE_TIME  # 重置防抖时间，准备处理下一轮消息
    message_objs = yuki.pop_buffer(chat_id)  # 此时拿到的是 list[dict]
    if not message_objs and not force_reply:
        return
    # 提高群聊的活跃度
    first_time = time.time()
    await yuki.boost_activity(chat_id)
    # 视觉理解总处理
    all_contents = [m["content"] for m in message_objs]
    combined_text = "\n".join(all_contents)

    # 接收返回的 modified_text 和 字典列表 images_info
    modified_text, images_info = meme_processor.extract_urls_from_text(combined_text)

    if images_info:
        understood_contents = []
        for img in images_info:
            url = img["url"]
            is_meme = img["is_meme"]

            # 1. 看图权限：无论是不是表情包，都让视觉模型（VLM）看一眼并理解
            result = await meme_processor.understand_from_url(url, llm)
            understood_contents.append(result)

            # 2. 存图权限：【核心防线】只有确认为表情包 (is_meme 为 True)，才允许后台偷图入库！
            if is_meme and hasattr(engine, 'sticker_manager'):
                clean_url = url.replace("&amp;", "&")  # 清洗 URL 防 400 报错
                # asyncio.create_task(
                #     engine.sticker_manager.ingest_sticker(image_ref=clean_url, chat_id=chat_id, owner="群友")
                # )
            elif not is_meme:
                logger.info("[System] 拦截到非表情包图片，仅作视觉理解，不入库学习。")

        combined_text = modified_text
        for content in understood_contents:
            combined_text = combined_text.replace("[图片占位符]", content, 1)

    # 剩下的CQ码文本解析（@、回复等）交给 parser
    combined_text = await parser.parse_all_cq_codes(combined_text)
    combined_text = combined_text.replace("\n", "  ").strip()
    logger.info(f"[{chat_id}] 收到消息{combined_text}")
    history_manager.append_to_log(chat_id, "User/Group", combined_text)

    logger.info("[System] 加载上下文信息...")
    # 加载上下文信息
    history_dict = history_manager.load()
    chat_id = str(chat_id)

    # 【修复后】稳健的系统提示词初始化与注入
    if chat_id not in history_dict or not history_dict[chat_id]:
        # 情况1：完全没记录，或者列表为空，直接初始化一个包含 system prompt 的新列表
        history_dict[chat_id] = [{"role": "system", "content": yuki.get_setting(mode)}]
    elif history_dict[chat_id][0].get("role") != "system":
        # 情况2：有记录但第一条不是 system prompt，则在最前面插入（而不是覆盖掉用户原本的消息）
        history_dict[chat_id].insert(0, {"role": "system", "content": yuki.get_setting(mode)})
    # 添加当前消息到上下文池
    current_time_str = datetime.datetime.now().strftime("%Y年%m月%d日%H:%M")
    history_dict[chat_id].append({
        "role": "user",
        "content": combined_text,
        "time": current_time_str  # 新增独立字段
    })

    logger.info("[System] 加载完成")

    if (mode == "group") and (not await engine.decide_to_reply(history_dict[chat_id], message_objs, chat_id,force_reply = force_reply)):
        # 保存获取的上下文信息
        history_manager.save(history_dict)
        logger.info(f"[System] {cfg.ROBOT_NAME.title()} 决定继续潜水...")
        return

    logger.info(f"[System] {cfg.ROBOT_NAME.title()} 正在回忆...")

    # 检索相关记忆总用法（包含关键词提取和语义向量匹配）
    dynamic_top_k = 10 if len(combined_text) > 100 else 8
    relevant_diaries = memory_rag.search_diaries(combined_text, chat_id=chat_id, top_k=dynamic_top_k)
    logger.info(f"[System] 检索到 {len(relevant_diaries)} 条相关日记:")

    logger.info(f"检索完成，用时 {(time.time()-first_time):.2f}")

    Yuki_answer_raw, Yuki_Answer, voice = await engine.api_reply(chat_id, combined_text, history_dict, mode, relevant_diaries)

    logger.info(f"{cfg.ROBOT_NAME.title()}打字完成！")
    if mode == "group":
        yuki.consume_energy(chat_id)
    logger.info(f"[System] {cfg.ROBOT_NAME.title()} 正在发送消息...(剩余精力: {yuki.energy[chat_id]:.1f})")

    if not voice:
        # 使用正则拆分文本和表情包，() 会将匹配到的 CQ 码也保留在列表中
        parts = re.split(r'(\[CQ:image,[^\]]*?sub_type=1\])', Yuki_Answer, flags=re.IGNORECASE)

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # 依次发送拆分出来的文字块和表情包
            await sender.send(chat_id, part, mode=mode)

            # 增加一个微小的延迟，模拟人类“发完字再点表情包”的节奏感
            await asyncio.sleep(1.0)

    else:
        await sender.send(chat_id, voice, mode=mode)

    logger.info(f"[System] 发送完成！全量内容：{Yuki_Answer}")
    logger.info(f"[System] {cfg.ROBOT_NAME.title()}正在保存上下文...")
    # 保存回复到上下文
    history_manager.append_to_log(chat_id, cfg.ROBOT_NAME.title(), Yuki_Answer)
    history_dict[chat_id].append({
        "role": "assistant", 
        "content": Yuki_answer_raw,
        "time": current_time_str  # 新增独立字段
    })
    history_manager.save(history_dict)
    logger.info("[System] 保存完成")

    # 日记触发检查：如果历史过长，强制写日记
    if len(history_dict[chat_id]) > cfg.DIARY_MAX_LENGTH:
        summarized_list = await engine.do_summarize(chat_id, history_dict[chat_id])
        history_dict[chat_id] = summarized_list
        history_manager.save(history_dict)
        logger.info(f"[{chat_id}] 日记写入完成，全量历史已同步。")


async def napcat_listen(mode):
    # 启动后台常驻任务
    if mode == "group":
        asyncio.create_task(yuki.decay_heartbeat())
    asyncio.create_task(engine.idle_diary_checker())
    asyncio.create_task(engine.ice_break_monitor())
    from core.engine import maid_worker
    asyncio.create_task(maid_worker(engine, yuki, sender, history_manager))
    # for chat_id in TARGET_GROUPS:
    #     print(f"[System] 初始化{chat_id}精力为{yuki.update_energy(chat_id)}")
    logger.info("[System] 已启动后台辅助任务 (日记检查/破冰/精力衰减)")

    logger.info(f"[System] 准备连接 NapCat 服务端 | 模式: {mode}")
    while True:
        try:
            async for data in connector.listen():
                if data.get("post_type") != "message":
                    continue

                msg_type = data.get("message_type")
                raw_msg = data.get("raw_message")
                user_id = data.get("user_id")

                if mode == "private" and msg_type == "private" and user_id == cfg.TARGET_QQ:
                    await manage_buffer(user_id, raw_msg, mode)

                elif mode == "group" and msg_type == "group":
                    group_id = data.get("group_id")
                    # 检查目标群白名单
                    if not cfg.TARGET_GROUPS or group_id in cfg.TARGET_GROUPS:
                        sender_info = data.get("sender", {})
                        name = sender_info.get("card") or sender_info.get("nickname") or "路人"
                        is_fake = name == cfg.MASTER_NAME and user_id != cfg.TARGET_QQ
                        if is_fake:
                            logger.warning(
                                f"[System] 检测到疑似冒充消息，已替换发送者姓名。原始姓名: {name}, QQ: {user_id}")
                            name = f"{name}(冒充)"
                        # 将消息存入缓冲区并触发主进程
                        await manage_buffer(
                            group_id,
                            f"【“{name}”】说: {raw_msg}",
                            mode,
                            raw_message=raw_msg,
                            sender_name=name,  # 传入姓名用于标识
                            user_id=int(user_id)
                        )

        except Exception as e:
            # 这里捕获的是 listen 循环抛出的致命异常（如代码逻辑错误或持续的连接失败）
            logger.error(f"监听主循环发生非预期崩溃: {e}")
            logger.info("[System] 5 秒后将尝试重启监听进程...")
            await asyncio.sleep(5)

async def manage_buffer(chat_id, content, mode, raw_message='', sender_name = '',user_id = None):
    global real_time_debounce_time
    cid_str = str(chat_id)
    # === 新增：捕捉群友正反馈（RLHF） ===
    # 如果Yuki刚发了表情包，且这句话是群友发的
    # 判定是否为机器人（可以根据名称含 BOT，或者特定的 QQ 号判定）
    is_bot = "BOT" in sender_name or "机器人" in sender_name
    if cid_str in yuki.last_sent_meme and not is_bot:
        # 定义正反馈触发词
        feedback_words = ["哈", "草", "233", "笑", "蚌埠", "确实", "典", "好图", "偷了"]
        # 如果消息包含触发词，或者群友紧接着也发了一张图（斗图）
        if any(fw in raw_message for fw in feedback_words) or "[CQ:image" in raw_message:
            meme_id = yuki.last_sent_meme.pop(cid_str)  # 弹出记录，防止一张图被无限加分
            if hasattr(engine, 'sticker_manager'):
                engine.sticker_manager.add_preference(meme_id)
    # ==================================
    # --- 新增：只要收到消息，就重置该群的破冰失败计数 ---
    if cid_str in yuki.ice_break_fail_count:
        if yuki.ice_break_fail_count[cid_str] > 0:
            logger.info(f"[IceBreak] {cid_str} 收到新消息，重置破冰计数器。")
        yuki.ice_break_fail_count[cid_str] = 0

    if real_time_debounce_time <= 0:
        real_time_debounce_time = cfg.DEBOUNCE_TIME  # 重置防抖时间，避免长时间关闭防抖导致过度频繁响应

    cid_str = str(chat_id)
    yuki.last_message_time[str(cid_str)] = time.time()

    content = smart_truncate(content, max_len=cfg.MAX_MESSAGE_LENGTH, suffix='...')

    # --- 拦截帮助指令并存入历史 ---
    if raw_message in ['help', '/help', 'yuki帮助', 'yuki功能', '帮助', '功能']:
        await sender.send_local_image(chat_id, "utils/yuki_help.png", mode=mode)
        logger.info("[System] 已记录并发送帮助图")
        history_manager.append_chat(chat_id, "user", f"(请求帮助文档: {content})")
        history_manager.append_chat(chat_id, "assistant", "(已发送帮助文档图片)")
        return 
    # 入队


    if chat_id not in yuki.message_buffer:
        yuki.message_buffer[chat_id] = []
    if (not ("BOT" in sender_name)):
        yuki.message_buffer[chat_id].append({
            "name": sender_name,
            "content": content,  # 这是带 【“姓名”】说: 的完整格式
            "raw_text": raw_message,  # 这是原始纯文本
            "is_bot": is_bot
        })

    if cfg.ROBOT_NAME.lower() in raw_message.lower():  # 使用原始文本判断，更准确
        real_time_debounce_time = 5
    if chat_id in yuki.buffer_tasks: yuki.buffer_tasks[chat_id].cancel()
    yuki.buffer_tasks[chat_id] = asyncio.create_task(main_process(chat_id, mode))

if __name__ == "__main__":
    import os
    import atexit
    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")

    _cleanup_done = False

    def _do_cleanup():
        """同步清理资源：关闭 ProviderRegistry 释放 aiohttp Session"""
        global _cleanup_done
        if _cleanup_done:
            return
        _cleanup_done = True
        logger.info("[System] 正在清理资源...")
        try:
            cfg._save_raw()
            logger.info("[System] 配置已自动对齐保存")
        except Exception as e:
            logger.error(f"[System] 保存配置时出错: {e}")
        try:
            from providers.registry import ProviderRegistry
            loop = asyncio.new_event_loop()
            loop.run_until_complete(ProviderRegistry().close_all())
            loop.close()
            logger.info("[System] 资源清理完成")
        except Exception as e:
            logger.error(f"[System] 清理资源时出错: {e}")

    atexit.register(_do_cleanup)

    try:
        logger.info("[System] 请确保已运行setup.py进行初始化配置！")
        logger.info(f"[System] {cfg.ROBOT_NAME.title()} 正在初始化...")
        start_time = time.time()

        # 加载与Napcat通信的Websocket服务
        connector = BotConnector(cfg.NAPCAT_WS_URL, cfg.NAPCAT_WS_TOKEN)
        # 实例化消息发送器
        sender = MessageSender(connector)
        # 实例化CQ码处理器
        parser = CQCodeParser(connector)
        
        # 实例化表情处理器
        meme_processor = MemeProcessor()
        # 实例化Yuki状态
        yuki = YukiState()
        # 实例化LLM请求器
        llm = ApiCall(cfg.LLM_API_KEY, cfg.LLM_BASE_URL)
        from modules.stickers.manager import StickerManager

        sticker_manager = StickerManager(llm)
        # 实例化历史记录管理器
        history_manager = HistoryManager()
        logger.info("[System] 开始初始化记忆系统（RAG）...")
        from modules.memory.rag import MemoryRAG
        # 初始化向量记忆库
        memory_rag = MemoryRAG()
        # 实例化Yuki主引擎（内部自动从 ProviderRegistry 获取 default provider）
        engine = YukiEngine(memory_rag, history_manager, yuki, sender)
        engine.process_callback = main_process
        engine.sticker_manager = sticker_manager
        # 在 engine = YukiEngine(...) 之后
        success = False
        try:
            webui = build_ui()
            webui.launch(
                server_name="127.0.0.1",
                server_port=1314,
                prevent_thread_lock=True,
                quiet=True,
                theme=webui._ui_theme,
                css=webui._ui_css
            )
            success = True
        except Exception as e:
            success = False
            logger.error(f"[WebUI] 启动失败: {e}")
        end_time = time.time()
        logger.info(f"[System] 初始化完成，耗时 {end_time - start_time:.1f} 秒")
        if success: logger.info("[WebUI] 控制面板已在后台线程启动: http://127.0.0.1:1314")
        choice = input("[System] 选择模式：1. 私聊模式  2. 群聊模式（默认）\n请输入数字: ").strip()
        if choice != "2":
            # 初始化巡检名单，预载历史中的群聊ID和最后消息时间，确保后台检查能正常工作
            h_dict = history_manager.load()
            for cid in cfg.TARGET_GROUPS:
                yuki.last_message_time[str(cid)] = time.time()
                current_e = yuki.update_energy(str(cid))
                yuki.update_desire_to_reply(str(cid))
                logger.info(
                    f"[System] 预热群组 {str(cid)}: 精力 {current_e:.1f}, 初始欲望 {yuki.desire_to_start_topic.get(str(cid), 0)}%")
            logger.debug(f"已预载 {len(yuki.last_message_time)} 个群组到巡检名单")
        asyncio.run(napcat_listen("private" if choice == "1" else "group"))

    except KeyboardInterrupt:
        logger.info("[System] 收到中断信号，正在退出...")
        sys.exit(0)

    except (FileNotFoundError, ImportError, KeyError) as e:
        logger.error("=" * 50)
        logger.error("启动失败：环境配置似乎不完整")
        logger.error(f"具体错误: {e}")
        logger.error("-" * 50)
        logger.error("💡 建议操作：")
        logger.error("   请运行 [ python setup.py ] 进行一键修复/配置。")
        logger.error("   该脚本会自动安装依赖、生成配置文件并下载模型。")
        logger.error("=" * 50 + "\n")
        sys.exit(1)

    except Exception as e:
        logger.critical(f"发生未知致命错误: {e}")
        # 这里可以选择记录日志
        sys.exit(1)

    finally:
        _do_cleanup()
