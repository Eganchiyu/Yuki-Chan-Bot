import asyncio
import time

from config import cfg
from main import yuki, engine, sender, history_manager, logger, connector, group_active_state, \
    main_process
from init import save_group_state
from modules.message.CQProtocol import smart_truncate


async def start_background_tasks(mode: str):
    """启动后台常驻任务"""
    if mode == "group":
        asyncio.create_task(yuki.decay_heartbeat())
    asyncio.create_task(engine.idle_diary_checker())
    asyncio.create_task(engine.ice_break_monitor())
    from core.engine import maid_worker
    asyncio.create_task(maid_worker(engine, yuki, sender, history_manager))
    logger.info("[System] 已启动后台辅助任务 (日记检查/破冰/精力衰减)")


def handle_group_switch(group_id, gid_str, user_id, raw_msg):
    """处理群聊开关指令，返回 True 表示已拦截"""
    msg_clean = raw_msg.strip()
    
    if msg_clean == '/关闭':
        if user_id == cfg.TARGET_QQ:
            group_active_state[gid_str] = False
            save_group_state(group_active_state)
            if group_id in yuki.message_buffer:
                yuki.message_buffer[group_id] = []
            if group_id in yuki.buffer_tasks:
                yuki.buffer_tasks[group_id].cancel()
            asyncio.create_task(
                sender.send(group_id, f"{cfg.ROBOT_NAME.title()} 已进入休眠模式，不打扰大家啦~", mode="group")
            )
        else:
            asyncio.create_task(
                sender.send(group_id, "只有哥哥大人才能关掉我哦！", mode="group")
            )
        return True
    
    elif msg_clean == '/开启':
        if user_id == cfg.TARGET_QQ:
            group_active_state[gid_str] = True
            save_group_state(group_active_state)
            asyncio.create_task(
                sender.send(group_id, f"{cfg.ROBOT_NAME.title()} 重新上线", mode="group")
            )
        else:
            asyncio.create_task(
                sender.send(group_id, "只有哥哥大人才能唤醒我哦！", mode="group")
            )
        return True
    
    return False


async def napcat_listen(mode: str):
    await start_background_tasks(mode)

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
                    gid_str = str(group_id)

                    # 检查目标群白名单
                    if not cfg.TARGET_GROUPS or group_id in cfg.TARGET_GROUPS:

                        # 处理开关指令
                        if handle_group_switch(group_id, gid_str, user_id, raw_msg):
                            continue

                        # 状态检查：如果该群被主人标记为 False，则直接无视所有消息
                        if not group_active_state.get(gid_str, True):
                            continue

                        sender_info = data.get("sender", {})
                        name = sender_info.get("card") or sender_info.get("nickname") or "路人"
                        is_fake = name == cfg.MASTER_NAME and user_id != cfg.TARGET_QQ
                        if is_fake:
                            logger.warning(
                                f"[System] 检测到疑似冒充消息，已替换发送者姓名。原始姓名: {name}, QQ: {user_id}")
                            name = f"{name}(冒充)"
                        
                        await manage_buffer(
                            group_id,
                            f'【"{name}"】说: {raw_msg}',
                            mode,
                            raw_message=raw_msg,
                            sender_name=name,
                            user_id=int(user_id)
                        )

        except Exception as e:
            logger.error(f"监听主循环发生非预期崩溃: {e}")
            logger.info("[System] 5 秒后将尝试重启监听进程...")
            await asyncio.sleep(5)


async def manage_buffer(chat_id, content, mode, raw_message='', sender_name='', user_id=None):
    global real_time_debounce_time
    cid_str = str(chat_id)
    
    # 捕捉群友正反馈（RLHF）
    is_bot = "BOT" in sender_name or "机器人" in sender_name
    if cid_str in yuki.last_sent_meme and not is_bot:
        feedback_words = ["哈", "草", "233", "笑", "蚌埠", "确实", "典", "好图", "偷了"]
        if any(fw in raw_message for fw in feedback_words):
            meme_id = yuki.last_sent_meme.pop(cid_str)
            if hasattr(engine, 'sticker_manager'):
                engine.sticker_manager.add_preference(meme_id)
    
    # 清空破冰失败计数器
    if (cid_str in yuki.ice_break_fail_count) and not is_bot:
        if yuki.ice_break_fail_count[cid_str] > 0:
            logger.info(f"[IceBreak] {cid_str} 收到新消息，重置破冰计数器。")
        yuki.ice_break_fail_count[cid_str] = 0

    if real_time_debounce_time <= 0:
        real_time_debounce_time = cfg.DEBOUNCE_TIME

    cid_str = str(chat_id)
    yuki.last_message_time[str(cid_str)] = time.time()

    content = smart_truncate(content, max_len=cfg.MAX_MESSAGE_LENGTH, suffix='...')

    # 拦截帮助指令并存入历史
    if raw_message in ['help', '/help', 'yuki帮助', 'yuki功能', '帮助', '功能']:
        await sender.send_local_image(chat_id, "utils/yuki_help.png", mode=mode)
        logger.info("[System] 已记录并发送帮助图")
        history_manager.append_chat(chat_id, "user", f"(请求帮助文档: {content})")
        history_manager.append_chat(chat_id, "assistant", "(已发送帮助文档图片)")
        return
    
    # 入队
    if chat_id not in yuki.message_buffer:
        yuki.message_buffer[chat_id] = []
    if (not ("BOT" in sender_name)) or (user_id and user_id == 1390249127) or (user_id and user_id == 3385516316):
        yuki.message_buffer[chat_id].append({
            "name": sender_name,
            "content": content,
            "raw_text": raw_message,
            "is_bot": is_bot
        })

    if cfg.ROBOT_NAME.lower() in raw_message.lower():
        real_time_debounce_time = 3
    if chat_id in yuki.buffer_tasks:
        yuki.buffer_tasks[chat_id].cancel()
    yuki.buffer_tasks[chat_id] = asyncio.create_task(main_process(chat_id, mode))
