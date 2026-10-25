# core/reply_watch.py
"""回复订阅：Yuki 期待回音时，超时后由她自己决定补一句或收尾。

工作方式：
1. 工具 `subscribe_reply` 为当前会话登记一个「待回执」，下限 30 秒。
2. 期间任何人类新消息进入会话即视为得到回应，订阅结束、不再追击。
3. 超时则通过 process_callback 强行触发一轮回复（类似定时任务到点），
   让 Yuki 自己决定说什么；追加次数达到上限后订阅自动结束。
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


def _now_text() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def is_human_incoming(message_obj) -> bool:
    """判断入站消息是否来自真人（机器人、定时事件、订阅事件都不算）。"""
    if message_obj is None:
        return False
    getter = message_obj.get if isinstance(message_obj, dict) else lambda key, default=None: getattr(
        message_obj, key, default
    )
    if getter("is_timer_event") or getter("is_reply_watch_event"):
        return False
    if getter("is_bot"):
        return False
    source = str(getter("source") or "")
    if source and not source.startswith("napcat"):
        return False
    return True


def _public(watch: dict) -> dict:
    """对模型可见的订阅状态，去掉回调等不可序列化字段。"""
    return {
        "chat_id": watch["chat_id"],
        "mode": watch["mode"],
        "expectation": watch["expectation"],
        "timeout_seconds": watch["timeout_seconds"],
        "max_followups": watch["max_followups"],
        "followups": watch["followups"],
        "status": watch["status"],
        "started_at": datetime.datetime.fromtimestamp(watch["started_at"]).strftime("%Y-%m-%d %H:%M:%S"),
        "next_fire_at": (
            datetime.datetime.fromtimestamp(watch["next_fire_at"]).strftime("%Y-%m-%d %H:%M:%S")
            if watch["next_fire_at"]
            else None
        ),
    }


def get_watch(chat_id):
    watch = _watches.get(str(chat_id))
    return _public(watch) if watch else None


def start_watch(chat_id, mode, callback, timeout_seconds=60, max_followups=MAX_FOLLOWUPS, expectation=None):
    """登记（或覆盖）一个会话的回复订阅，返回对模型可见的状态。"""
    if callback is None:
        raise ValueError("missing_callback")

    chat_id = str(chat_id)
    try:
        timeout = float(timeout_seconds)
    except (TypeError, ValueError):
        raise ValueError("invalid_timeout")
    if timeout <= 0:
        raise ValueError("invalid_timeout")
    timeout = max(timeout, float(MIN_TIMEOUT_SECONDS))

    try:
        followups = int(max_followups)
    except (TypeError, ValueError):
        raise ValueError("invalid_max_followups")
    followups = max(0, min(followups, MAX_FOLLOWUPS))

    _drop(chat_id, "replaced")
    watch = {
        "chat_id": chat_id,
        "mode": mode,
        "callback": callback,
        "expectation": (expectation or "").strip(),
        "timeout_seconds": timeout,
        "max_followups": followups,
        "followups": 0,
        "status": "waiting",
        "started_at": time.time(),
        "next_fire_at": None,
    }
    _watches[chat_id] = watch
    _schedule(chat_id)
    logger.info(
        f"[ReplyWatch] 订阅建立 chat_id={chat_id} timeout={timeout:.0f}s max_followups={followups} "
        f"expectation={watch['expectation'] or '-'}"
    )
    return _public(watch)


def resolve_watch(chat_id, reason="human_message") -> dict | None:
    """人类消息到达，视为得到回应。"""
    return _drop(chat_id, reason)


def cancel_watch(chat_id, reason="cancelled") -> dict | None:
    """主动放弃等待。"""
    return _drop(chat_id, reason)


def _drop(chat_id, reason):
    watch = _watches.pop(str(chat_id), None)
    task = _tasks.pop(str(chat_id), None)
    if task is not None:
        task.cancel()
    if watch:
        watch["status"] = reason
        watch["next_fire_at"] = None
        logger.info(f"[ReplyWatch] 订阅结束 chat_id={chat_id} reason={reason} followups={watch['followups']}")
    return _public(watch) if watch else None


def _schedule(chat_id):
    watch = _watches.get(chat_id)
    if not watch or watch["status"] != "waiting":
        return
    delay = watch["timeout_seconds"]
    watch["next_fire_at"] = time.time() + delay
    _tasks[chat_id] = asyncio.create_task(_fire_later(chat_id, delay))


async def _fire_later(chat_id, delay):
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return

    watch = _watches.get(chat_id)
    if not watch or watch["status"] != "waiting":
        return
    # 自己触发的这轮不算「新消息」
    _tasks.pop(chat_id, None)
    watch["followups"] += 1
    watch["status"] = "fired"
    watch["next_fire_at"] = None

    event = {
        "content": _build_event_text(watch),
        "raw_text": "",
        "name": "系统",
        "time": _now_text(),
        "source": EVENT_SOURCE,
        "is_reply_watch_event": True,
    }
    logger.info(
        f"[ReplyWatch] 超时追击 chat_id={chat_id} 第 {watch['followups']}/{watch['max_followups']} 次"
    )
    asyncio.create_task(_dispatch(watch["callback"], chat_id, watch["mode"], event))

    # 追击发出后若还有额度，继续计时；期间收到人类消息会被 resolve_watch 掐掉
    if watch["followups"] < watch["max_followups"] and _watches.get(chat_id) is watch:
        watch["status"] = "waiting"
        _schedule(chat_id)
    elif _watches.get(chat_id) is watch:
        _watches.pop(chat_id, None)
        logger.info(f"[ReplyWatch] 追击次数用尽 chat_id={chat_id}")


async def _dispatch(callback, chat_id, mode, event):
    try:
        await callback(chat_id, mode, message_obj=event, debounce_flag=False, force_reply=True)
    except Exception as exc:
        logger.error(f"[ReplyWatch] 触发追击回复失败 chat_id={chat_id}: {exc}")


def _build_event_text(watch) -> str:
    expectation = f"（你在等的是：{watch['expectation']}）" if watch["expectation"] else ""
    return (
        f"【等待超时】距你上一次说话已经过去 {watch['timeout_seconds']:.0f} 秒，还没有人回应你{expectation}。"
        f"这是第 {watch['followups']}/{watch['max_followups']} 次追击机会：可以补一句、换个说法追问，也可以说一句收尾的话。"
        f"如果你还想继续等，回复后就不用管；如果不想再追了，回复完调用 subscribe_reply(action='cancel')。"
    )


def reset_reply_watch():
    """测试用：清空所有订阅。"""
    for task in list(_tasks.values()):
        task.cancel()
    _tasks.clear()
    _watches.clear()
