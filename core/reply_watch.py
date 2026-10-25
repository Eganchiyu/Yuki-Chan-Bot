# core/reply_watch.py
"""回复订阅：Yuki 期待回音时，到点没等到就由系统替她补一句。

1. 回复发出后按「像在等回答的程度」自动评分，够高就静默登记一个待回执（下限 30 秒），
   时长 = 最近一小段时间的平均消息间隔 + 20 秒。Yuki 完全无感，不需要工具、不会多说话。
2. 期间任何真人新消息进会话即视为得到回应，订阅直接取消，走正常流程。
3. 到点还没人说话，就注入一条「XX 秒到啦～没有人回复」，按正常 enqueue 让 Yuki 回答；
   最多自动提醒两次，之后订阅自然结束。
"""
import asyncio
import datetime
import random
import re
import time

from utils.logger import get_logger

logger = get_logger("reply_watch")

MIN_TIMEOUT_SECONDS = 30.0
MAX_FOLLOWUPS = 2
EVENT_SOURCE = "yuki.reply_watch"

# --- 自动订阅判定 ---
ENABLED = True
# 评分权重：结尾问句 + 触发词 + 精力 + 生物钟 + 活跃度
QUESTION_WEIGHT = 0.40
TRIGGER_WORD_WEIGHT = 0.15
ENERGY_WEIGHT = 0.05
BIOCLOCK_WEIGHT = 0.15
ACTIVITY_WEIGHT = 0.15
# 随机化幅度与门槛：分数加一点抖动后过线才订阅
SCORE_JITTER = 0.10
SCORE_THRESHOLD = 0.55

# 等待时长 = 最近平均消息间隔 + 20 秒，数据不足时用默认值
WAIT_EXTRA_SECONDS = 20.0
DEFAULT_WAIT_SECONDS = 60.0
RECENT_INTERVAL_SAMPLES = 8

# 只收「明确在求回应」的词；呢/嘛 是陈述语气口癖，不算
TRIGGER_WORDS = (
    "吗", "好不好", "对不对", "是不是", "行不行", "在吗",
    "有人", "理我", "回我", "回答我", "要不要", "你猜",
)
_MEME_TAG_RE = re.compile(r"\[MEME:[^\]]*\]")

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


def _visible_text(text: str) -> str:
    """去掉表情包标记，只看真正发出去的字。"""
    return _MEME_TAG_RE.sub("", text or "").strip()


def is_question(text: str) -> bool:
    """是否以问号收尾（半个问号也算）。"""
    clean = _visible_text(text).rstrip("～~ 　\n")
    return clean.endswith("?") or clean.endswith("？")


def hit_trigger_word(text: str) -> bool:
    clean = _visible_text(text)
    return any(word in clean for word in TRIGGER_WORDS)


def expectation_score(text, energy_ratio=0.0, bioclock_ratio=0.5, activity_ratio=0.0) -> float:
    """合成一个 0~1.1 的「像在等人回答」评分。"""
    score = 0.0
    if is_question(text):
        score += QUESTION_WEIGHT
    if hit_trigger_word(text):
        score += TRIGGER_WORD_WEIGHT
    score += ENERGY_WEIGHT * max(0.0, min(1.0, float(energy_ratio)))
    score += BIOCLOCK_WEIGHT * max(0.0, min(1.0, float(bioclock_ratio)))
    score += ACTIVITY_WEIGHT * max(0.0, min(1.0, float(activity_ratio)))
    return score


def estimate_wait_seconds(timestamps) -> float:
    """最近平均消息间隔 + 20 秒；样本不足时回落到默认等待。"""
    times = sorted(float(ts) for ts in (timestamps or []))[-RECENT_INTERVAL_SAMPLES:]
    if len(times) < 2:
        return DEFAULT_WAIT_SECONDS
    gaps = [later - earlier for earlier, later in zip(times, times[1:]) if later > earlier]
    if not gaps:
        return DEFAULT_WAIT_SECONDS
    return sum(gaps) / len(gaps) + WAIT_EXTRA_SECONDS


def auto_subscribe(chat_id, mode, callback, text, energy_ratio=0.0, bioclock_ratio=0.5,
                   activity_ratio=0.0, recent_times=None) -> dict | None:
    """回复发出后自动判定是否该等她一句回应，返回订阅状态或 None。"""
    if not ENABLED or not _visible_text(text) or callback is None:
        return None
    if get_watch(chat_id) is not None:
        return None

    score = expectation_score(text, energy_ratio, bioclock_ratio, activity_ratio)
    rolled = score + random.uniform(-SCORE_JITTER, SCORE_JITTER)
    if rolled < SCORE_THRESHOLD:
        logger.debug(f"[ReplyWatch] 不订阅 chat_id={chat_id} score={score:.2f} rolled={rolled:.2f}")
        return None

    wait = estimate_wait_seconds(recent_times)
    watch = subscribe(chat_id, mode, callback, timeout_seconds=wait)
    logger.info(
        f"[ReplyWatch] 自动订阅 chat_id={chat_id} score={score:.2f} rolled={rolled:.2f} wait={watch['timeout_seconds']:.0f}s"
    )
    return watch


def reset_reply_watch():
    """测试用：清空所有订阅。"""
    for task in list(_tasks.values()):
        task.cancel()
    _tasks.clear()
    _watches.clear()
