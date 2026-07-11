# modules/github_monitor/state.py
"""GitHub Monitor 状态持久化：记录每个仓库已处理的最新 event id。"""

from __future__ import annotations

import json
import os
import time
from typing import Dict, List, Optional

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


def get_last_event_id(state: dict, repo_key: str) -> Optional[str]:
    return state.get("repos", {}).get(repo_key, {}).get("last_event_id")


def update_last_event_id(state: dict, repo_key: str, event_id: str) -> None:
    state.setdefault("repos", {}).setdefault(repo_key, {})["last_event_id"] = event_id
    state["last_poll"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    save_state(state)


def get_seen_event_ids(state: dict, repo_key: str) -> set[str]:
    return set(state.get("repos", {}).get(repo_key, {}).get("seen_ids", []))


def add_seen_event_id(state: dict, repo_key: str, event_id: str, max_ids: int = 200) -> None:
    repo_state = state.setdefault("repos", {}).setdefault(repo_key, {})
    seen = list(repo_state.get("seen_ids", []))
    if event_id not in seen:
        seen.append(event_id)
    if len(seen) > max_ids:
        seen = seen[-max_ids:]
    repo_state["seen_ids"] = seen
    save_state(state)
