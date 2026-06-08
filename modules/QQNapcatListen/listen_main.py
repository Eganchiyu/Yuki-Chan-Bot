import asyncio
import time

from config import cfg
from init import save_group_state
from modules.message.CQProtocol import smart_truncate

connector = None
sender = None
yuki = None
engine = None
history_manager = None
session_pipeline = None
group_active_state = None
logger = None


def configure_runtime(components: dict, pipeline, active_state: dict, runtime_logger):
    """注入运行期组件，避免监听层反向导入 main.py。"""
    global connector, sender, yuki, engine, history_manager
    global session_pipeline, group_active_state, logger

    connector = components["connector"]
    sender = components["sender"]
    yuki = components["yuki"]
    engine = components["engine"]
    history_manager = components["history_manager"]
    session_pipeline = pipeline
    group_active_state = active_state
    logger = runtime_logger


async def start_background_tasks(mode: str):
    """启动后台常驻任务。"""
    if mode == "group":
        asyncio.create_task(yuki.decay_heartbeat())
    asyncio.create_task(engine.idle_diary_checker())
    asyncio.create_task(engine.ice_break_monitor())
    from core.engine import maid_worker
    asyncio.create_task(maid_worker(engine, yuki, sender, history_manager))
    logger.info("[NapCat] 已启动后台辅助任务 (日记检查/破冰/精力衰减)")


def handle_group_switch(group_id, gid_str, user_id, raw_msg):
    """处理群聊开关指令，返回 True 表示已拦截。"""
    msg_clean = raw_msg.strip()

    if msg_clean == "/关闭":
        if user_id == cfg.TARGET_QQ:
            group_active_state[gid_str] = False
            save_group_state(group_active_state)
            yuki.message_buffer[gid_str] = []
            task = yuki.buffer_tasks.get(gid_str)
            if task and not task.done():
                task.cancel()
            asyncio.create_task(
                sender.send(group_id, f"{cfg.ROBOT_NAME.title()} 已进入休眠模式，不打扰大家啦~", mode="group")
            )
        else:
            asyncio.create_task(sender.send(group_id, "只有哥哥大人才能关掉我哦！", mode="group"))
        return True

    if msg_clean == "/开启":
        if user_id == cfg.TARGET_QQ:
            group_active_state[gid_str] = True
            save_group_state(group_active_state)
            asyncio.create_task(sender.send(group_id, f"{cfg.ROBOT_NAME.title()} 重新上线", mode="group"))
        else:
            asyncio.create_task(sender.send(group_id, "只有哥哥大人才能唤醒我哦！", mode="group"))
        return True

    return False


async def napcat_listen(mode: str):
    """NapCat 输入适配层：接收 QQ 消息并 feed 到会话管道。"""
    await start_background_tasks(mode)

    logger.info(f"[NapCat] 准备连接服务端 | 模式: {mode}")
    while True:
        try:
            async for data in connector.listen():
                if data.get("post_type") != "message":
                    continue

                msg_type = data.get("message_type")
                raw_msg = data.get("raw_message")
                user_id = data.get("user_id")

                if mode == "private" and msg_type == "private" and user_id == cfg.TARGET_QQ:
                    await feed_message(user_id, raw_msg, mode)

                elif mode == "group" and msg_type == "group":
                    group_id = data.get("group_id")
                    gid_str = str(group_id)

                    if cfg.TARGET_GROUPS and group_id not in cfg.TARGET_GROUPS:
                        continue
                    if handle_group_switch(group_id, gid_str, user_id, raw_msg):
                        continue
                    if not group_active_state.get(gid_str, True):
                        continue

                    sender_info = data.get("sender", {})
                    name = sender_info.get("card") or sender_info.get("nickname") or "路人"
                    is_fake = name == cfg.MASTER_NAME and user_id != cfg.TARGET_QQ
                    if is_fake:
                        logger.warning(
                            f"[NapCat] 检测到疑似冒充消息，已替换发送者姓名。原始姓名: {name}, QQ: {user_id}"
                        )
                        name = f"{name}(冒充)"

                    await feed_message(
                        group_id,
                        f'【"{name}"】说: {raw_msg}',
                        mode,
                        raw_message=raw_msg,
                        sender_name=name,
                        user_id=int(user_id),
                    )

        except Exception as e:
            logger.error(f"[NapCat] 监听主循环崩溃: {e}")
            logger.info("[NapCat] 5 秒后尝试重启监听进程")
            await asyncio.sleep(5)


async def feed_message(chat_id, content, mode, raw_message="", sender_name="", user_id=None):
    """将标准化后的消息放入对应 chat_id 的会话缓冲，并按需唤醒会话泵。"""
    cid_str = str(chat_id)
    is_bot = "BOT" in sender_name or "机器人" in sender_name

    if cid_str in yuki.last_sent_meme and not is_bot:
        feedback_words = ["哈", "草", "233", "笑", "蚌埠", "确实", "典", "好图", "偷了"]
        if any(fw in raw_message for fw in feedback_words):
            meme_id = yuki.last_sent_meme.pop(cid_str)
            if hasattr(engine, "sticker_manager"):
                engine.sticker_manager.add_preference(meme_id)

    if cid_str in yuki.ice_break_fail_count and not is_bot:
        if yuki.ice_break_fail_count[cid_str] > 0:
            logger.info(f"[NapCat] {cid_str} 收到新消息，重置破冰计数器")
        yuki.ice_break_fail_count[cid_str] = 0

    yuki.last_message_time[cid_str] = time.time()
    content = smart_truncate(content, max_len=cfg.MAX_MESSAGE_LENGTH, suffix="...")

    if raw_message in ["help", "/help", "yuki帮助", "yuki功能", "帮助", "功能"]:
        await sender.send_local_image(chat_id, "utils/yuki_help.png", mode=mode)
        logger.info("[NapCat] 已发送帮助图")
        history_manager.append_chat(chat_id, "user", f"(请求帮助文档: {content})")
        history_manager.append_chat(chat_id, "assistant", "(已发送帮助文档图片)")
        return

    if cfg.ROBOT_NAME.lower() in raw_message.lower():
        session_pipeline.wake_quickly(cid_str)

    if not is_bot or (user_id and user_id in cfg.TARGET_WHITELIST):
        message_obj = {
            "name": sender_name,
            "content": content,
            "raw_text": raw_message,
            "is_bot": is_bot,
        }
    else:
        message_obj = None

    await session_pipeline.enqueue_message(cid_str, mode, message_obj=message_obj)
