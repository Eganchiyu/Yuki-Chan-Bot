# modules/qzone/state.py
"""
QZone 社交状态持久化

管理已发布的说说、已处理的评论、点赞记录等。
"""

import json
import os
import time
from typing import Dict, List, Optional
from utils.logger import get_logger

logger = get_logger("qzone_state")

STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "workspace", "qzone_state.json")


def _ensure_dir():
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)


def load_state() -> dict:
    """加载持久化状态。"""
    if not os.path.exists(STATE_FILE):
        return {"posts": {}, "last_poll": "", "seen_feed_keys": []}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 兼容旧格式
        data.setdefault("seen_feed_keys", [])
        return data
    except Exception as e:
        logger.error(f"[QZoneState] 加载状态失败: {e}")
        return {"posts": {}, "last_poll": "", "seen_feed_keys": []}


def save_state(state: dict):
    """保存状态到文件。"""
    _ensure_dir()
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[QZoneState] 保存状态失败: {e}")


def register_post(state: dict, tid: str, content: str,
                  source_chat: str = "", chat_context: List[str] = None):
    """记录一条新发布的说说。"""
    state.setdefault("posts", {})[tid] = {
        "content": content,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_chat": source_chat,
        "chat_context": chat_context or [],
        "seen_comments": [],
        "liked_users": [],
    }
    save_state(state)
    logger.info(f"[QZoneState] 注册说说 tid={tid}")


def get_tracked_tids(state: dict) -> List[str]:
    """获取所有正在追踪的说说 ID。"""
    return list(state.get("posts", {}).keys())


def mark_comments_seen(state: dict, tid: str, comment_tids: List[int]):
    """标记评论为已处理。"""
    post = state.get("posts", {}).get(tid)
    if post is None:
        return
    for ctid in comment_tids:
        if ctid not in post["seen_comments"]:
            post["seen_comments"].append(ctid)
    save_state(state)


def mark_user_liked(state: dict, tid: str, user_uin: int):
    """记录已回赞的用户。"""
    post = state.get("posts", {}).get(tid)
    if post is None:
        return
    if user_uin not in post["liked_users"]:
        post["liked_users"].append(user_uin)
    save_state(state)


def get_post_context(state: dict, tid: str) -> dict:
    """获取说说的上下文信息。"""
    return state.get("posts", {}).get(tid, {})


def update_last_poll(state: dict):
    """更新最后轮询时间。"""
    state["last_poll"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    save_state(state)


def add_seen_feed_keys(state: dict, keys: list):
    """添加已处理的好友动态 key。"""
    existing = set(state.get("seen_feed_keys", []))
    for k in keys:
        existing.add(k)
    # 限制大小
    key_list = list(existing)
    if len(key_list) > 500:
        key_list = key_list[-200:]
    state["seen_feed_keys"] = key_list
    save_state(state)
