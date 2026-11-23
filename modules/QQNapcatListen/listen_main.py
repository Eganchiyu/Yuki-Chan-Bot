"""NapCat 入站适配：把事件翻译成会话管道的消息，并做入站策略判定。

宿主机文件 IPC 与斜杠指令处理器已分别拆分至同目录 `host_ipc.py` 与 `commands.py`，
本模块保留主监听循环并重导出所有原符号，确保现有调用与单测 100% 兼容。
"""
import asyncio
import time

from config import cfg
from core.session_pipeline import IncomingMessage
from init import default_group_active
from modules.QQNapcatListen.commands import (
    AUTONOMOUS_COMMANDS,
    _autonomous,
    _extract_quoted_message_id,
    _resolve_sft_logger,
    _set_group_active,
    handle_art_gacha_command,
    handle_autonomous_command,
    handle_emoji_like_event,
    handle_force_close_command,
    handle_group_switch,
    handle_private_command,
    handle_sft_quote_label,
    handle_status_command,
    switch_llm_route,
)
from modules.QQNapcatListen.host_ipc import (
    MAX_RESTART_PER_HOUR,
    NETFORCE_WAIT_SECONDS,
    RESTART_NOTICE_MAX_AGE,
    _NETFORCE_PENDING_DIR,
    _NETFORCE_RESULT_FILE,
    _RESTART_NOTICE_FILE,
    _ROOT,
    _STAGING_DIR,
    _SUPERVISOR_STATE,
    _format_netforce_reply,
    _pop_restart_notice,
    _read_netforce_result,
    _recent_restart_count,
    _refresh_flow,
    _restart_flow,
    _wait_netforce_result,
    _write_netforce_request,
    _write_restart_notice,
    request_container_restart,
    send_pending_restart_notice,
)
from modules.shot_memory import shot_live_buffer
from network.napcat import mentions_self, smart_truncate
from utils.logger import get_logger

logger = get_logger("napcat_listen")


async def start_background_tasks(gateway, pipeline, mode: str):
    """启动后台常驻任务。"""
    yuki, engine = pipeline.yuki, pipeline.engine

    if mode in {"group", "mixed"}:
        asyncio.create_task(yuki.decay_heartbeat())
    asyncio.create_task(engine.idle_diary_checker())
    asyncio.create_task(engine.ice_break_monitor())

    from core.maid.maid_worker import maid_worker
    asyncio.create_task(maid_worker(engine, yuki, gateway, pipeline.history_manager))

    asyncio.create_task(send_pending_restart_notice(gateway))

    from core.maid.maid_resume import report_orphaned_results
    asyncio.create_task(report_orphaned_results(engine, yuki, pipeline.history_manager))

    if cfg.qzone_monitor.enabled:
        try:
            from modules.qzone.monitor import ensure_monitor_started
            asyncio.create_task(ensure_monitor_started(gateway, engine, getattr(engine, "rag", None)))
            logger.info("[NapCat] QZone 社交监控已启动")
        except Exception as e:
            logger.warning(f"[NapCat] QZone 监控启动失败: {e}")

    if cfg.github_monitor.enabled:
        try:
            from modules.github_monitor import ensure_monitor_started
            asyncio.create_task(ensure_monitor_started(pipeline))
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


async def handle_poke_event(gateway, pipeline, data: dict, mode: str):
    """处理戳一戳事件：只把"戳 Yuki"记进管线，按普通消息入队（不插队）。"""
    if mode == "mixed":
        mode = "group"
    group_id = data.get("group_id")
    poker_id = data.get("user_id")
    target_id = data.get("target_id")

    if not target_id or int(target_id) != cfg.SELF_QQ:
        return
    if poker_id and int(poker_id) == cfg.SELF_QQ:
        return

    gid_str = str(group_id)
    if not pipeline.group_active_state.get(gid_str, default_group_active()):
        return

    if cfg.TARGET_GROUPS and group_id not in cfg.TARGET_GROUPS:
        return

    poker_name = "某人"
    if poker_id:
        info = await gateway.get_member_info(gid_str, str(poker_id)) or {}
        poker_name = info.get("card") or info.get("nickname") or "某人"

    logger.info(f"[NapCat] 戳一戳事件: {poker_name}({poker_id}) 戳了戳 {cfg.ROBOT_NAME}({target_id}) (群:{gid_str})")

    await pipeline.enqueue_message(
        gid_str,
        mode,
        message_obj=IncomingMessage(
            name=poker_name,
            content=f"[{poker_name} 戳了戳 {cfg.ROBOT_NAME}]",
            raw_text="[戳一戳]",
            user_id=int(poker_id) if poker_id else None,
            is_bot=False,
            source="napcat.notice.poke",
            owner_id=gid_str,
            tags={"group", "poke"},
        ),
    )


async def napcat_listen(gateway, pipeline, mode: str = "mixed"):
    """NapCat 输入适配层：接收 QQ 事件并 feed 到会话管道。"""
    engine = pipeline.engine
    await start_background_tasks(gateway, pipeline, mode)

    logger.info(f"[NapCat] 准备连接服务端 | 模式: {mode}")
    while True:
        try:
            async for data in gateway.listen():
                if data.get("post_type") == "meta_event" and data.get("meta_event_type") == "heartbeat":
                    is_online = (data.get("status") or {}).get("online", False)
                    if not is_online and engine.napcat_online:
                        logger.warning("[NapCat] 检测到客户端离线，已挂起后台破冰与日记任务。")
                        engine.napcat_online = False
                    elif is_online and not engine.napcat_online:
                        logger.info("[NapCat] 检测到客户端重新上线，恢复后台常驻任务。")
                        engine.napcat_online = True
                    continue

                if not engine.napcat_online:
                    continue

                if (
                    data.get("post_type") == "notice"
                    and data.get("notice_type") == "notify"
                    and data.get("sub_type") == "poke"
                ):
                    asyncio.create_task(handle_poke_event(gateway, pipeline, data, mode))
                    continue

                if data.get("post_type") == "notice" and data.get("notice_type") == "group_msg_emoji_like":
                    handle_emoji_like_event(pipeline, data)
                    continue

                if data.get("post_type") != "message":
                    continue

                msg_type = data.get("message_type")
                raw_msg = data.get("raw_message")
                user_id = data.get("user_id")

                if msg_type == "private" and mode in {"private", "group", "mixed"}:
                    if handle_private_command(gateway, pipeline, user_id, raw_msg):
                        continue
                    if handle_sft_quote_label(pipeline, user_id, user_id, raw_msg, data.get("message")):
                        continue
                    private_mode = "master_private" if cfg.is_master_qq(user_id) else "private"
                    private_sender = data.get("sender", {})
                    private_name = private_sender.get("nickname") or private_sender.get("card") or "私聊用户"
                    if handle_art_gacha_command(
                        pipeline,
                        gateway,
                        user_id,
                        user_id,
                        raw_msg,
                        sender_name=private_name,
                        message_id=data.get("message_id"),
                        segments=data.get("message"),
                        send_mode=private_mode,
                    ):
                        continue
                    await feed_message(
                        pipeline,
                        gateway,
                        user_id,
                        raw_msg,
                        private_mode,
                        message_obj=_build_private_message(
                            user_id,
                            raw_msg,
                            private_sender,
                            data.get("message_id"),
                            data.get("message"),
                        ),
                    )

                elif msg_type == "group" and mode in {"group", "mixed"}:
                    group_id = data.get("group_id")
                    gid_str = str(group_id)

                    if cfg.TARGET_GROUPS and group_id not in cfg.TARGET_GROUPS:
                        continue
                    if handle_status_command(gateway, pipeline, group_id, gid_str, user_id, raw_msg):
                        continue
                    if handle_force_close_command(gateway, pipeline, group_id, gid_str, raw_msg):
                        continue
                    if handle_autonomous_command(pipeline, gateway, group_id, gid_str, user_id, raw_msg):
                        continue
                    if handle_group_switch(pipeline, gateway, group_id, gid_str, user_id, raw_msg):
                        continue
                    if handle_sft_quote_label(pipeline, group_id, user_id, raw_msg, data.get("message")):
                        continue
                    if not pipeline.group_active_state.get(gid_str, default_group_active()):
                        continue

                    sender_info = data.get("sender", {})
                    name = sender_info.get("card") or sender_info.get("nickname") or "路人"
                    if name == cfg.MASTER_NAME and not cfg.is_master_qq(user_id):
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

                    if handle_art_gacha_command(
                        pipeline,
                        gateway,
                        group_id,
                        user_id,
                        raw_msg,
                        sender_name=name,
                        message_id=data.get("message_id"),
                        segments=data.get("message"),
                        send_mode="group",
                    ):
                        continue

                    await feed_message(
                        pipeline,
                        gateway,
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
    pipeline,
    gateway,
    chat_id,
    content,
    mode,
    raw_message="",
    sender_name="",
    user_id=None,
    message_id=None,
    message_obj=None,
):
    """标准化后写入对应 chat_id 的会话缓冲，并按需唤醒会话泵。"""
    yuki, engine = pipeline.yuki, pipeline.engine
    cid_str = str(chat_id)

    if message_obj:
        incoming_message = IncomingMessage.from_mapping(message_obj)
    else:
        incoming_message = IncomingMessage(
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
        asyncio.create_task(gateway.send_local_image(chat_id, "utils/yuki_help.png", mode=mode))
        logger.info("[NapCat] 已发送帮助图")
        pipeline.history_manager.append_session_message(
            chat_id, "user", f"(请求帮助文档: {incoming_message.content})"
        )
        pipeline.history_manager.append_session_message(chat_id, "assistant", "(已发送帮助文档图片)")
        return

    if incoming_message.is_bot and (
        not incoming_message.user_id or incoming_message.user_id not in cfg.TARGET_WHITELIST
    ):
        return

    called = not incoming_message.is_bot and (
        cfg.ROBOT_NAME.lower() in incoming_message.raw_text.lower()
        or mentions_self(incoming_message.segments, incoming_message.raw_text, cfg.SELF_QQ)
    )
    await pipeline.enqueue_message(
        cid_str,
        mode,
        message_obj=incoming_message,
        debounce_flag=not called,
        force_reply=True if called else None,
    )
