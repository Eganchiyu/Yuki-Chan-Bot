import asyncio
import time

import core.brain
from config import cfg
from core.session_pipeline import IncomingMessage
from init import save_group_state
from modules.message.CQProtocol import smart_truncate
from modules.message.GetMeta import MetaGetter
from modules.shot_memory import shot_live_buffer

connector = None
sender = None
yuki = None
engine = None
history_manager = None
session_pipeline = None
group_active_state = None
logger = None
meta_getter = None


def configure_runtime(components: dict, pipeline, active_state: dict, runtime_logger):
    """注入运行期组件，避免监听层反向导入 main.py。"""
    global connector, sender, yuki, engine, history_manager
    global session_pipeline, group_active_state, logger, meta_getter

    connector = components["connector"]
    sender = components["sender"]
    yuki = components["yuki"]
    engine = components["engine"]
    history_manager = components["history_manager"]
    session_pipeline = pipeline
    group_active_state = active_state
    logger = runtime_logger
    meta_getter = MetaGetter(connector)


async def start_background_tasks(mode: str):
    """启动后台常驻任务。"""
    if mode in {"group", "mixed"}:
        asyncio.create_task(yuki.decay_heartbeat())
    asyncio.create_task(engine.idle_diary_checker())
    asyncio.create_task(engine.ice_break_monitor())
    from core.maid.maid_worker import maid_worker
    asyncio.create_task(maid_worker(engine, yuki, sender, history_manager))

    # QZone 社交监控（默认关闭，见 configs/config.yaml 的 qzone_monitor.enabled）
    # ⚠️ 启用前必须先完成 NapCat 接收侧整合：当前 modules/qzone/monitor.py 在缺少
    #    连接时会临时自建 connector.listen() 再 close()，与主监听循环抢占同一条
    #    WebSocket，开启后会饿死主监听。
    if cfg.qzone_monitor.enabled:
        try:
            from modules.qzone.monitor import ensure_monitor_started
            asyncio.create_task(ensure_monitor_started(connector, engine, getattr(engine, 'rag', None)))
            logger.info("[NapCat] QZone 社交监控已启动")
        except Exception as e:
            logger.warning(f"[NapCat] QZone 监控启动失败: {e}")

    # GitHub 仓库监控（默认关闭，见 configs/config.yaml 的 github_monitor.enabled）
    if cfg.github_monitor.enabled:
        try:
            from modules.github_monitor import ensure_monitor_started
            asyncio.create_task(ensure_monitor_started(session_pipeline))
            logger.info("[NapCat] GitHub 仓库监控已启动")
        except Exception as e:
            logger.warning(f"[NapCat] GitHub 监控启动失败: {e}")

    logger.info("[NapCat] 已启动后台辅助任务 (日记检查/破冰/精力衰减)")


def _is_bot_sender_name(sender_name: str) -> bool:
    """根据 NapCat 显示名判断是否为机器人账号。"""
    return "BOT" in (sender_name or "") or "机器人" in (sender_name or "")


def _build_private_message(user_id, raw_message, sender_info, message_id, segments=None) -> IncomingMessage:
    """把 NapCat 私聊事件转换为管线入站消息。"""
    sender_name = sender_info.get("nickname") or sender_info.get("card") or "私聊用户"
    return IncomingMessage(
        name=sender_name,
        content=raw_message,
        raw_text=raw_message,
        user_id=int(user_id) if user_id is not None else None,
        message_id=message_id,
        is_bot=_is_bot_sender_name(sender_name),
        source="napcat.private",
        owner_id=str(user_id),
        tags={"private"},
        segments=list(segments or []),
    )


def _build_group_message(group_id, raw_message, sender_name, user_id, message_id, segments) -> IncomingMessage:
    """把 NapCat 群聊事件转换为管线入站消息。"""
    return IncomingMessage(
        name=sender_name,
        content=f'【"{sender_name}"】说: {raw_message}',
        raw_text=raw_message,
        user_id=int(user_id) if user_id is not None else None,
        message_id=message_id,
        is_bot=_is_bot_sender_name(sender_name),
        source="napcat.group",
        owner_id=str(group_id),
        tags={"group"},
        segments=list(segments or []),
    )


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


async def handle_poke_event(data: dict, mode: str):
    """处理戳一戳事件，将被戳信息注入消息管线。"""
    if mode == "mixed":
        mode = "group"
    group_id = data.get("group_id")
    poker_id = data.get("user_id")       # 戳人者
    target_id = data.get("target_id")    # 被戳者

    # 屏蔽机器人自己发出的戳一戳：否则会回灌消息管线，导致再次触发对话
    if poker_id and int(poker_id) == cfg.SELF_QQ:
        return

    # # 只处理戳到 Yuki 的事件
    # if not target_id or int(target_id) != cfg.TARGET_QQ:
    #     return
    # # 私聊模式不处理群戳一戳
    # if mode == "private" or not group_id:
    #     return

    gid_str = str(group_id)
    if not group_active_state.get(gid_str, True):
        return

    # 群聊白名单兜底：非白名单群直接丢弃
    if cfg.TARGET_GROUPS and group_id not in cfg.TARGET_GROUPS:
        return

    # 查戳人者昵称
    poker_name = "某人"
    poked_name = "某人"
    if poker_id and meta_getter:
        member_info = await meta_getter.get_group_member_info(gid_str, str(poker_id))
        if member_info:
            poker_name = (member_info.get("card")
                          or member_info.get("nickname")
                          or "某人")
    
    if target_id == cfg.SELF_QQ:
        poked_name = cfg.ROBOT_NAME
    elif target_id and meta_getter:
        member_info = await meta_getter.get_group_member_info(gid_str, str(target_id))
        if member_info:
            poked_name = (member_info.get("card")
                            or member_info.get("nickname")
                            or "某人")
        
    logger.info(f"[NapCat] 戳一戳事件: {poker_name}({poker_id}) 戳了戳 {poked_name}({target_id}) (群:{gid_str})")



    await session_pipeline.enqueue_message(
        gid_str,
        mode,
        message_obj=IncomingMessage(
            name=poker_name,
            content=f'[{poker_name} 戳了戳 {poked_name}]',
            raw_text="[戳一戳]",
            user_id=int(poker_id) if poker_id else None,
            is_bot=False,
            source="napcat.notice.poke",
            owner_id=gid_str,
            tags={"group", "poke"},
        ),
    )


async def napcat_listen(mode: str):
    """NapCat 输入适配层：接收 QQ 消息并 feed 到会话管道。"""
    await start_background_tasks(mode)

    logger.info(f"[NapCat] 准备连接服务端 | 模式: {mode}")
    while True:
        try:
            async for data in connector.listen():
                logger.debug(f"[NapCat] 收到原始消息: {data}")
                # 戳一戳事件拦截（notice/notify/poke）
                if data.get("post_type") == "meta_event" and data.get("meta_event_type") == "heartbeat":
                    status = data.get("status", {})
                    is_online = status.get("online", False)
                    
                    if not is_online and engine.napcat_online:
                        logger.warning("[NapCat] 检测到客户端离线，已挂起后台破冰与日记任务。")
                        engine.napcat_online = False
                            
                    elif is_online and not engine.napcat_online:
                        logger.info("[NapCat] 检测到客户端重新上线，恢复后台常驻任务。")
                        engine.napcat_online = True
                            
                    continue  # 心跳包处理完毕，跳过后续逻辑

                if not engine.napcat_online:
                    continue

                if (data.get("post_type") == "notice"
                        and data.get("notice_type") == "notify"
                        and data.get("sub_type") == "poke"):
                    asyncio.create_task(handle_poke_event(data, mode))
                    continue

                if data.get("post_type") != "message":
                    continue

                msg_type = data.get("message_type")
                raw_msg = data.get("raw_message")
                user_id = data.get("user_id")

                if msg_type == "private" and mode in {"private", "group", "mixed"}:
                    await feed_message(
                        user_id,
                        raw_msg,
                        "master_private" if user_id == cfg.TARGET_QQ else "private",
                        message_obj=_build_private_message(
                            user_id,
                            raw_msg,
                            data.get("sender", {}),
                            data.get("message_id"),
                            data.get("message"),
                        ),
                    )

                elif msg_type == "group" and mode in {"group", "mixed"}:
                    group_id = data.get("group_id")
                    gid_str = str(group_id)

                    if cfg.TARGET_GROUPS and group_id not in cfg.TARGET_GROUPS:
                        continue
                    if handle_group_switch(group_id, gid_str, user_id, raw_msg):
                        continue
                    if not group_active_state.get(gid_str, True):
                        continue
                    
                    # logger.debug(f"[NapCat] 收到原始消息: {data}")
                    
                    sender_info = data.get("sender", {})
                    name = sender_info.get("card") or sender_info.get("nickname") or "路人"
                    is_fake = name == cfg.MASTER_NAME and user_id != cfg.TARGET_QQ
                    if is_fake:
                        logger.warning(
                            f"[NapCat] 检测到疑似冒充消息，已替换发送者姓名。原始姓名: {name}, QQ: {user_id}"
                        )
                        name = f"{name}(冒充)"

                    shot_live_buffer.append(
                        gid_str,
                        name=name,
                        raw_text=raw_msg,
                        content=f'【"{name}"】说: {raw_msg}',
                        segments=data.get("message"),
                        user_id=int(user_id),
                        message_id=data.get("message_id"),
                        is_bot=False,
                    )

                    await feed_message(
                        group_id,
                        raw_msg,
                        "group",
                        message_obj=_build_group_message(
                            group_id,
                            raw_msg,
                            name,
                            user_id,
                            data.get("message_id"),
                            data.get("message"),
                        ),
                    )

        except Exception as e:
            logger.error(f"[NapCat] 监听主循环崩溃: {e}")
            logger.info("[NapCat] 5 秒后尝试重启监听进程")
            await asyncio.sleep(5)


async def feed_message(
    chat_id,
    content,
    mode,
    raw_message="",
    sender_name="",
    user_id=None,
    message_id=None,
    message_obj=None,
):
    """将标准化后的消息放入对应 chat_id 的会话缓冲，并按需唤醒会话泵。"""
    cid_str = str(chat_id)
    incoming_message = IncomingMessage.from_mapping(message_obj) if message_obj else IncomingMessage(
        name=sender_name,
        content=content,
        raw_text=raw_message,
        user_id=user_id,
        message_id=message_id,
        is_bot=_is_bot_sender_name(sender_name),
        owner_id=cid_str,
    )
    incoming_message.owner_id = incoming_message.owner_id or cid_str
    incoming_message.content = smart_truncate(
        incoming_message.content,
        max_len=cfg.MAX_MESSAGE_LENGTH,
        suffix="...",
    )

    if cid_str in yuki.last_sent_meme and not incoming_message.is_bot:
        feedback_words = ["哈", "草", "233", "笑", "蚌埠", "确实", "典", "好图", "偷了"]
        if any(word in incoming_message.raw_text for word in feedback_words):
            meme_id = yuki.last_sent_meme.pop(cid_str)
            if hasattr(engine, "sticker_manager"):
                engine.sticker_manager.add_preference(meme_id)

    if cid_str in yuki.ice_break_fail_count and not incoming_message.is_bot:
        if yuki.ice_break_fail_count[cid_str] > 0:
            logger.info(f"[NapCat] {cid_str} 收到新消息，重置破冰计数器")
        yuki.ice_break_fail_count[cid_str] = 0

    yuki.last_message_time[cid_str] = time.time()

    if incoming_message.raw_text in ["help", "/help", "yuki帮助", "yuki功能", "帮助", "功能"]:
        await sender.send_local_image(chat_id, "utils/yuki_help.png", mode=mode)
        logger.info("[NapCat] 已发送帮助图")
        history_manager.append_session_message(
            chat_id, "user", f"(请求帮助文档: {incoming_message.content})"
        )
        history_manager.append_session_message(chat_id, "assistant", "(已发送帮助文档图片)")
        return

    # ── /jm 指令拦截（暂时禁用）──
    # from modules.jm_downloader import handle_jm_command
    # if await handle_jm_command(chat_id, incoming_message.raw_text, sender, mode):
    #     return

    # 拦截 Bot 消息（白名单除外）
    if incoming_message.is_bot and (
        not incoming_message.user_id or incoming_message.user_id not in cfg.TARGET_WHITELIST
    ):
        return

    # 非 Bot 消息且提到 Yuki 时快速唤醒
    if not incoming_message.is_bot and cfg.ROBOT_NAME.lower() in incoming_message.raw_text.lower():
        session_pipeline.wake_quickly(cid_str)

    await session_pipeline.enqueue_message(cid_str, mode, message_obj=incoming_message)
