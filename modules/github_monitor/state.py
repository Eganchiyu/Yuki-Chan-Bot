# modules/github_monitor/state.py
"""GitHub Monitor 状态持久化：记录每个仓库已处理的最新 event id。"""

from __future__ import annotations

import json
import os

from utils.logger import get_logger

logger = get_logger("github_monitor_state")

STATE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "workspace",
    "github_monitor_state.json",
)


def _ensure_dir() -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"repos": {}, "last_poll": ""}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("repos", {})
        return data
    except Exception as e:
        logger.error(f"[GitHubMonitor] 加载状态失败: {e}")
        return {"repos": {}, "last_poll": ""}


def save_state(state: dict) -> None:
    _ensure_dir()
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[GitHubMonitor] 保存状态失败: {e}")
