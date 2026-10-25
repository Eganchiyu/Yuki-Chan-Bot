# core/reply_watch.py
"""回复订阅：Yuki 期待回音时，到点没等到就由系统替她补一句。

1. 工具 `subscribe_reply(time)` 为当前会话登记一个「待回执」，下限 30 秒。
2. 期间任何真人新消息进会话即视为得到回应，订阅直接取消，走正常流程。
3. 到点还没人说话，就注入一条「XX 秒到啦～没有人回复」，按正常 enqueue 让 Yuki 回答；
   最多自动提醒两次，之后订阅自然结束。
"""
import asyncio
import datetime
import time

from utils.logger import get_logger

logger = get_logger("reply_watch")

MIN_TIMEOUT_SECONDS = 30.0
MAX_FOLLOWUPS = 2
EVENT_SOURCE = "yuki.reply_watch"

_watches: dict[str, dict] = {}
_tasks: dict[str, asyncio.Task] = {}


def is_human_incoming(message_obj) -> bool:
    """判断入站消息是否来自真人（机器人、定时事件、订阅事件都不算）。"""
    if message_obj is None:
        return False
    getter = message_obj.get if isinstance(message_obj, dict) else lambda key, default=None: getattr(
        message_obj, key, default
    )
    if getter("is_timer_event") or getter("is_reply_watch_event") or getter("is_bot"):
        return False
    source = str(getter("source") or "")
    if source and not source.startswith("napcat"):
        return False
    return True


def subscribe(chat_id, mode, callback, timeout_seconds=60):
    """登记（或覆盖）一个会话的回复订阅，返回对模型可见的状态。"""
    if callback is None:
        raise ValueError("missing_callback")

    chat_id = str(chat_id)
    try:
        timeout = max(float(timeout_seconds), float(MIN_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        raise ValueError("invalid_timeout")
    if timeout <= 0:
        raise ValueError("invalid_timeout")

    _drop(chat_id, "replaced")
    watch = {
        "chat_id": chat_id,
        "mode": mode,
        "callback": callback,
        "timeout_seconds": timeout,
        "followups": 0,
        "status": "waiting",
    }
    _watches[chat_id] = watch
    _schedule(chat_id)
    logger.info(f"[ReplyWatch] 订阅建立 chat_id={chat_id} timeout={timeout:.0f}s")
    return _public(watch)


def resolve(chat_id, reason="human_message"):
    """真人消息到达：不需要再提醒了。"""
    return _drop(chat_id, reason)


def get_watch(chat_id):
    watch = _watches.get(str(chat_id))
    return _public(watch) if watch else None


def _public(watch: dict) -> dict:
    return {
        "chat_id": watch["chat_id"],
        "mode": watch["mode"],
        "timeout_seconds": watch["timeout_seconds"],
        "followups": watch["followups"],
        "max_followups": MAX_FOLLOWUPS,
        "status": watch["status"],
    }


def _drop(chat_id, reason):
    watch = _watches.pop(str(chat_id), None)
    task = _tasks.pop(str(chat_id), None)
    if task is not None:
        task.cancel()
    if watch:
        watch["status"] = reason
        logger.info(f"[ReplyWatch] 订阅结束 chat_id={chat_id} reason={reason} followups={watch['followups']}")
    return _public(watch) if watch else None


def _schedule(chat_id):
    watch = _watches.get(chat_id)
    if not watch or watch["status"] != "waiting":
        return
    _tasks[chat_id] = asyncio.create_task(_fire_later(chat_id, watch["timeout_seconds"]))


async def _fire_later(chat_id, delay):
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return

    watch = _watches.get(chat_id)
    if not watch or watch["status"] != "waiting":
        return
    # 自己注入的这轮不算「新消息」
    _tasks.pop(chat_id, None)
    watch["followups"] += 1
    watch["status"] = "fired"

    event = {
        "content": f"【等待超时】{watch['timeout_seconds']:.0f}秒到啦～没有人回复。",
        "raw_text": "",
        "name": "系统",
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": EVENT_SOURCE,
        "is_reply_watch_event": True,
    }
    logger.info(f"[ReplyWatch] 到点提醒 chat_id={chat_id} 第 {watch['followups']}/{MAX_FOLLOWUPS} 次")
    asyncio.create_task(_dispatch(watch["callback"], chat_id, watch["mode"], event))

    # 还有提醒额度就继续计时；期间有人回复会被 resolve 掐掉
    if watch["followups"] < MAX_FOLLOWUPS and _watches.get(chat_id) is watch:
        watch["status"] = "waiting"
        _schedule(chat_id)
    elif _watches.get(chat_id) is watch:
        _watches.pop(chat_id, None)
        logger.info(f"[ReplyWatch] 提醒次数用尽 chat_id={chat_id}")


async def _dispatch(callback, chat_id, mode, event):
    try:
        await callback(chat_id, mode, message_obj=event, debounce_flag=False, force_reply=True)
    except Exception as exc:
        logger.error(f"[ReplyWatch] 到点提醒注入失败 chat_id={chat_id}: {exc}")


def reset_reply_watch():
    """测试用：清空所有订阅。"""
    for task in list(_tasks.values()):
        task.cancel()
    _tasks.clear()
    _watches.clear()
