# modules/QQNapcatListen/commands.py
"""QQ 群聊与私聊入站指令处理器（/开启 /关闭 /强制关闭 /重启 /刷新 /切换 /查询 /深思 及 SFT 打标）。"""
import asyncio
import re

from config import cfg
from core import status as status_cmd
from core.sft_logger import sft_trace_logger
from init import default_group_active, save_group_state
from modules.QQNapcatListen.host_ipc import _refresh_flow, _restart_flow
from network.napcat import extract_reply_ids
from utils.logger import get_logger

logger = get_logger("napcat_listen")

AUTONOMOUS_COMMANDS = ("/深思", "/工坊状态", "/强制放行", "/自主轮")


def switch_llm_route(target: str | None = None) -> str:
    """主备/多渠道切换（仅内存生效），返回给机主的提示文案。"""
    from utils.llm_client import reset_route_state

    try:
        swapped = cfg.swap_llm_route(target) if target else cfg.swap_llm_route()
    except ValueError as exc:
        return f"切换失败啦：{exc}"
    reset_route_state()

    if getattr(cfg, "_use_providers_queue", lambda: False)() and len(cfg.providers) >= 2:
        routes = cfg.get_llm_routes()
        head = routes[0]
        next_route = routes[1] if len(routes) >= 2 else head
        logger.warning(
            f"[Switch] 多渠道队列已切换，当前首选={head.name}({head.model}) 次选={next_route.name}({next_route.model})"
        )
        return (
            f"已经切换到 [{head.name}] 模型啦（{head.model}），"
            f"出事就自动顺延到 {next_route.name}（{next_route.model}），重启后回配置设定~"
        )

    role = "备用" if swapped else "主"
    logger.warning(
        f"[Switch] 主备线路已对调，当前主模型={cfg.model.llm} 备用={cfg.model.backup}（{role}线路上线）"
    )
    return (
        f"已经换成{role}模型啦（{cfg.model.llm}），"
        f"出事就自动退到 {cfg.model.backup}，重启后会切回配置里的设定~"
    )


def _set_group_active(pipeline, gateway, group_id, gid_str, opening: bool) -> None:
    """切换群聊的应答开关，群聊 /关闭 /开启 与 /强制关闭 共用。"""
    pipeline.group_active_state[gid_str] = opening
    save_group_state(pipeline.group_active_state)
    logger.warning(f"[Switch] {gid_str} 群应答开关 -> {'开' if opening else '休眠'}")
    if opening:
        asyncio.create_task(gateway.send(group_id, f"{cfg.ROBOT_NAME.title()} 重新上线", mode="group"))
        return
    cancel_pending = getattr(pipeline, "cancel_pending", None)
    if callable(cancel_pending):
        cancel_pending(gid_str)
    else:
        pipeline.yuki.message_buffer[gid_str] = []
        task = getattr(pipeline, "_timer_tasks", {}).get(gid_str) or getattr(
            pipeline.yuki, "buffer_tasks", {}
        ).get(gid_str)
        if task and not task.done():
            task.cancel()
    asyncio.create_task(
        gateway.send(group_id, f"{cfg.ROBOT_NAME.title()} 已进入休眠模式，不打扰大家啦~", mode="group")
    )


def handle_status_command(gateway, pipeline, chat_id, gid_str, user_id, raw_msg, send_mode="group") -> bool:
    """处理 /查询（别名 /状态、/status）：关键词式状态简报，全员可用但分层脱敏。"""
    if not status_cmd.match_status_command(raw_msg):
        return False
    text = status_cmd.build_status_text(
        pipeline.yuki,
        gid_str,
        group_active=bool(pipeline.group_active_state.get(gid_str, default_group_active())),
        is_master=cfg.is_master_qq(user_id),
    )
    asyncio.create_task(gateway.send(chat_id, text, mode=send_mode))
    logger.info(f"[Status] {gid_str} 状态查询 by {user_id}: {text}")
    return True


def handle_force_close_command(gateway, pipeline, group_id, gid_str, raw_msg) -> bool:
    """处理 /强制关闭：任何人可用，但必须连发两次（60 秒内）才真正休眠本群。"""
    if not status_cmd.match_force_close_command(raw_msg):
        return False

    if not status_cmd.is_force_close_confirmed(gid_str):
        status_cmd.mark_force_close_pending(gid_str)
        asyncio.create_task(
            gateway.send(
                group_id,
                f"真的要关掉人家吗…60 秒内再发一次 /强制关闭 就睡啦（{cfg.ROBOT_NAME.title()} 会停在这个群不说话）",
                mode="group",
            )
        )
        logger.info(f"[ForceClose] {gid_str} 第一次确认请求")
        return True

    status_cmd.clear_force_close(gid_str)
    logger.warning(f"[ForceClose] {gid_str} 二次确认完成，强制休眠该群")
    _set_group_active(pipeline, gateway, group_id, gid_str, opening=False)
    return True


def _autonomous(pipeline):
    return getattr(pipeline, "autonomous", None)


def handle_autonomous_command(
    pipeline, gateway, chat_id, gid_str, user_id, raw_msg, send_mode: str = "group"
) -> bool:
    """处理 /深思、/工坊状态、/强制放行、/自主轮 开|关（主人限定）。"""
    msg_clean = raw_msg.strip()
    head = msg_clean.split()[0] if msg_clean else ""
    if head not in AUTONOMOUS_COMMANDS:
        return False

    coordinator = _autonomous(pipeline)
    if coordinator is None:
        asyncio.create_task(gateway.send(chat_id, "自主轮还没装好哦～", mode=send_mode))
        return True

    if not cfg.is_master_qq(user_id):
        asyncio.create_task(
            gateway.send(chat_id, "只有哥哥大人才能安排我一个人的时间哦！", mode=send_mode)
        )
        return True

    if head == "/工坊状态":
        text = coordinator.status_text(gid_str)
        asyncio.create_task(gateway.send(chat_id, text, mode=send_mode))
        logger.info(f"[Autonomous] {gid_str} 状态查询 by {user_id}")
        return True

    if head == "/强制放行":
        result = coordinator.force_release(gid_str)
        text = "好，我马上回来～" if result.get("ok") else "现在没有在独处哦，群里照常。"
        asyncio.create_task(gateway.send(chat_id, text, mode=send_mode))
        logger.warning(f"[Autonomous] {gid_str} 强制放行 by {user_id}: {result}")
        return True

    if head == "/自主轮":
        parts = msg_clean.split()
        action = parts[1] if len(parts) > 1 else ""
        if action not in {"开", "关"}:
            asyncio.create_task(
                gateway.send(chat_id, "用法：/自主轮 开 或 /自主轮 关", mode=send_mode)
            )
            return True
        from modules.autonomous.storage import state_store

        state_store.set_group_override(gid_str, action == "开")
        if action == "关":
            coordinator.force_release(gid_str)
            text = "这个群的自主轮关掉啦，以后不会自己跑去独处了。"
        else:
            text = "好，这个群以后我可以自己去待一会儿想事情啦～"
        asyncio.create_task(gateway.send(chat_id, text, mode=send_mode))
        logger.warning(f"[Autonomous] {gid_str} 运行时开关 -> {action} by {user_id}")
        return True

    if send_mode == "group" and not pipeline.group_active_state.get(gid_str, default_group_active()):
        asyncio.create_task(
            gateway.send(
                chat_id,
                "这个群现在是休眠状态哦，先发 /开启 让我上线，我再去独处想事情～",
                mode=send_mode,
            )
        )
        return True

    async def _start_deep_think():
        result = await coordinator.start_run(gid_str, trigger="manual", mode_arg="group")
        if result.get("ok"):
            await gateway.send(
                chat_id,
                "嗯…我去一个人的地方待一会儿，翻翻日记想想事情。这段时间群里我先不说话，"
                "想完了会把想到的东西拿回来给你看。",
                mode=send_mode,
            )
        else:
            await gateway.send(chat_id, str(result.get("reason") or "现在不太方便"), mode=send_mode)

    asyncio.create_task(_start_deep_think())
    logger.warning(f"[Autonomous] {gid_str} /深思 by {user_id}")
    return True


def _parse_switch_target(msg_clean: str) -> tuple[bool, str | None]:
    if msg_clean == "/切换":
        return True, None
    if msg_clean.startswith("/切换 "):
        return True, msg_clean[3:].strip() or None
    return False, None


def handle_group_switch(pipeline, gateway, group_id, gid_str, user_id, raw_msg):
    """处理群聊开关/重启/刷新/切换指令，返回 True 表示已拦截。"""
    msg_clean = raw_msg.strip()
    is_switch, switch_target = _parse_switch_target(msg_clean)
    cmd_key = "/切换" if is_switch else msg_clean
    if cmd_key not in {"/关闭", "/开启", "/重启", "/刷新", "/切换"}:
        return False

    if not cfg.is_master_qq(user_id):
        hint = {
            "/关闭": "只有哥哥大人才能关掉我哦！",
            "/开启": "只有哥哥大人才能唤醒我哦！",
            "/重启": "只有哥哥大人才能重启我哦！",
            "/刷新": "只有哥哥大人才能刷新网络哦！",
            "/切换": "只有哥哥大人才能给我换模型哦！",
        }[cmd_key]
        asyncio.create_task(gateway.send(group_id, hint, mode="group"))
        return True

    if cmd_key == "/刷新":
        asyncio.create_task(_refresh_flow(gateway, group_id, mode="group"))
        return True

    if cmd_key == "/切换":
        text = switch_llm_route(switch_target)
        asyncio.create_task(gateway.send(group_id, text, mode="group"))
        return True

    if cmd_key == "/重启":
        asyncio.create_task(_restart_flow(gateway, group_id))
        return True

    _set_group_active(pipeline, gateway, group_id, gid_str, opening=cmd_key == "/开启")
    return True


def handle_private_command(gateway, pipeline, user_id, raw_msg) -> bool:
    """私聊侧指令：/刷新、/切换、/查询（/开启 /关闭 /重启 仍只在群里生效）。"""
    msg_clean = raw_msg.strip()
    if msg_clean in {"/工坊状态", "/强制放行"}:
        return handle_autonomous_command(
            pipeline, gateway, user_id, "", user_id, msg_clean, send_mode="private"
        )
    is_switch, switch_target = _parse_switch_target(msg_clean)
    cmd_key = "/切换" if is_switch else msg_clean
    if cmd_key not in {"/刷新", "/切换", "/查询", "/状态", "/status"}:
        return False

    if cmd_key in {"/查询", "/状态", "/status"}:
        text = status_cmd.build_status_text(
            pipeline.yuki,
            user_id,
            group_active=True,
            is_master=cfg.is_master_qq(user_id),
        )
        asyncio.create_task(gateway.send(user_id, text, mode="private"))
        return True

    if not cfg.is_master_qq(user_id):
        hint = "只有哥哥大人才能刷新网络哦！" if cmd_key == "/刷新" else "只有哥哥大人才能给我换模型哦！"
        asyncio.create_task(gateway.send(user_id, hint, mode="private"))
        return True
    if cmd_key == "/切换":
        text = switch_llm_route(switch_target)
        asyncio.create_task(gateway.send(user_id, text, mode="private"))
        return True
    asyncio.create_task(_refresh_flow(gateway, user_id, mode="private"))
    return True


def handle_art_gacha_command(
    pipeline,
    gateway,
    chat_id,
    user_id,
    raw_msg: str,
    *,
    sender_name: str = "",
    message_id=None,
    segments=None,
    send_mode: str = "group",
) -> bool:
    """处理 /抽图（含 /抽图 <附言>）：跳过进入与抽卡环节，直接进入创作模式并抽卡交给大模型绘画。"""
    msg_clean = (raw_msg or "").strip()
    if msg_clean != "/抽图" and not (
        msg_clean.startswith("/抽图") and len(msg_clean) > 3 and msg_clean[3].isspace()
    ):
        return False

    from core.session_pipeline import IncomingMessage

    cid_str = str(chat_id)
    name = sender_name or ("私聊用户" if send_mode != "group" else "群友")
    content = f'【"{name}"】说: {msg_clean}' if send_mode == "group" else msg_clean
    mode_tag = "group" if send_mode == "group" else "private"
    incoming = IncomingMessage(
        name=name,
        content=content,
        raw_text=msg_clean,
        user_id=int(user_id) if user_id is not None else None,
        message_id=message_id,
        is_bot=False,
        source=f"napcat.{mode_tag}.art_gacha",
        owner_id=cid_str,
        tags={mode_tag, "art_gacha_jump"},
        segments=list(segments or []),
    )
    asyncio.create_task(
        pipeline.enqueue_message(
            cid_str,
            send_mode,
            message_obj=incoming,
            debounce_flag=False,
            force_reply=True,
        )
    )
    logger.info(f"[ArtGachaCmd] {cid_str} 触发 /抽图 ({send_mode}) by {user_id}")
    return True


def _resolve_sft_logger(pipeline):
    sft_logger = getattr(pipeline, "sft_logger", None)
    return sft_logger if sft_logger is not None and hasattr(sft_logger, "record_label") else sft_trace_logger


def handle_emoji_like_event(pipeline, data: dict) -> list[dict]:
    """处理 NapCat 群贴表情通知（group_msg_emoji_like），仅采信主人打标。"""
    user_id = data.get("user_id")
    if not cfg.is_master_qq(user_id):
        return []

    group_id = str(data.get("group_id") or "")
    message_id = data.get("message_id")
    is_add = bool(data.get("is_add", True))
    likes = data.get("likes")
    if not isinstance(likes, list) or not likes:
        if data.get("emoji_id") is not None:
            likes = [{"emoji_id": data.get("emoji_id")}]
        else:
            likes = []

    logger.info(
        f"[NapCat] 收到主人贴表情事件: group={group_id} mid={message_id} "
        f"is_add={is_add} likes={likes}"
    )
    sft_logger = _resolve_sft_logger(pipeline)
    recorded = []
    for item in likes:
        if not isinstance(item, dict):
            continue
        emoji_id = item.get("emoji_id")
        if emoji_id is None:
            continue
        rec = sft_logger.record_label(
            message_id=message_id,
            chat_id=group_id,
            user_id=user_id,
            emoji_id=emoji_id,
            is_add=is_add,
            source="emoji_like",
        )
        if rec:
            recorded.append(rec)
    return recorded


def _extract_quoted_message_id(raw_msg: str, segments) -> str | None:
    for seg in segments or []:
        if isinstance(seg, dict) and seg.get("type") == "reply":
            mid = (seg.get("data") or {}).get("id")
            if mid is not None and str(mid).strip():
                return str(mid).strip()
    ids = extract_reply_ids(raw_msg or "")
    return ids[0] if ids else None


def handle_sft_quote_label(pipeline, chat_id, user_id, raw_msg: str, segments=None) -> bool:
    """私聊/群聊备用打标：主人引用 Yuki 消息发 /good 或 /bad 时静默记录，不进聊天上下文。"""
    if not cfg.is_master_qq(user_id):
        return False
    reply_id = _extract_quoted_message_id(raw_msg, segments)
    if not reply_id:
        return False
    cmd = re.sub(r"\[CQ:[^\]]+\]", "", raw_msg or "").strip().lower()
    if cmd in {"/good", "/perfect", "/赞"}:
        label = "perfect"
    elif cmd in {"/bad", "/差", "/踩"}:
        label = "bad"
    else:
        return False

    sft_logger = _resolve_sft_logger(pipeline)
    rec = sft_logger.record_label(
        message_id=reply_id,
        chat_id=str(chat_id),
        user_id=user_id,
        emoji_id=cmd,
        is_add=True,
        label=label,
        source="quote_cmd",
    )
    return rec is not None
