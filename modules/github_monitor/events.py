# modules/github_monitor/events.py
"""GitHub Events API 批量获取 + 速率限制检测。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .client import GitHubClient

logger = logging.getLogger(__name__)

_MAX_EVENTS_PER_PAGE = 30
_DEFAULT_RETRIES = 3


async def fetch_repo_events(
    client: GitHubClient,
    owner: str,
    repo: str,
    *,
    per_page: int = _MAX_EVENTS_PER_PAGE,
    max_retries: int = _DEFAULT_RETRIES,
) -> list[dict[str, Any]]:
    """调用 GitHub Events API 拉取仓库最新事件列表，自动处理 403/429 重试。"""
    from urllib.parse import quote

    path = f"/repos/{quote(owner)}/{quote(repo)}/events"
    params: dict[str, int] = {"per_page": per_page}

    for attempt in range(1, max_retries + 1):
        resp = await client.get(path, params=params)

        if resp.status_code in (403, 429):
            logger.warning(
                "[GitHubMonitor] %s/%s API %d（速率限制？第%d/%d次）",
                owner, repo, resp.status_code, attempt, max_retries,
            )
            if attempt < max_retries:
                await asyncio.sleep(2.0 * attempt)
                continue
            return []

        if resp.status_code == 200:
            data = resp.json()
            events_list: list[dict[str, Any]] = data if isinstance(data, list) else []
            logger.debug("[GitHubMonitor] %s/%s 获取到 %d 条事件", owner, repo, len(events_list))
            return events_list

        logger.error("[GitHubMonitor] %s/%s Events API 返回 %d", owner, repo, resp.status_code)
        if attempt < max_retries:
            await asyncio.sleep(2.0 * attempt)
            continue
        return []

    return []


async def fetch_compare_commits(
    client: GitHubClient,
    owner: str,
    repo: str,
    before: str,
    head: str,
) -> list[dict[str, Any]]:
    """通过 Compare API 获取一次 PushEvent 涉及的提交列表。"""
    from urllib.parse import quote

    if not before or not head or before == head:
        return []

    path = (
        f"/repos/{quote(owner)}/{quote(repo)}/compare/"
        f"{quote(before)}...{quote(head)}"
    )
    try:
        resp = await client.get(path)
    except Exception as exc:
        logger.warning("[GitHubMonitor] %s/%s Compare API 请求失败: %s", owner, repo, exc)
        return []

    if resp.status_code != 200:
        logger.warning(
            "[GitHubMonitor] %s/%s Compare API 返回 %d",
            owner,
            repo,
            resp.status_code,
        )
        return []

    data = resp.json()
    commits = data.get("commits", []) if isinstance(data, dict) else []
    return commits if isinstance(commits, list) else []
