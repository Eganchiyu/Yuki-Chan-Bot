# modules/github_monitor/monitor.py
"""
GitHub 仓库监控器

后台常驻任务，定期轮询 GitHub Events API，检测 Issue / PR / Comment 等事件，
通过 session_pipeline.enqueue_message() 推送到 Yuki 消息管道。

使用方式:
    from modules.github_monitor import ensure_monitor_started
    await ensure_monitor_started(session_pipeline)
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Dict, List, Optional

from config import cfg
from modules.github_monitor.client import GitHubClient, github_headers
from modules.github_monitor.events import fetch_repo_events
from modules.github_monitor.state import (
    add_seen_event_id,
    get_last_event_id,
    get_seen_event_ids,
    load_state,
    save_state,
    update_last_event_id,
)
from utils.logger import get_logger

logger = get_logger("github_monitor")

# 默认轮询间隔（秒）
_DEFAULT_POLL_INTERVAL = 300
# 首次同步时跳过多少条历史事件
_HISTORY_SKIP_COUNT = 30


class GitHubRepoConfig:
    """单个仓库的监控配置。"""

    def __init__(
        self,
        owner: str,
        repo: str,
        token: str = "",
        poll_interval: int = _DEFAULT_POLL_INTERVAL,
        chat_id: str = "",
        modes: Optional[List[str]] = None,
    ):
        self.owner = owner
        self.repo = repo
        self.token = token
        self.poll_interval = poll_interval
        self.chat_id = chat_id
        self.modes = modes or ["group"]

    @property
    def key(self) -> str:
        return f"{self.owner}/{self.repo}"


class GitHubMonitor:
    """
    GitHub 仓库监控器。

    职责：
    1. 定期轮询配置仓库的 Events API
    2. 去重检测新事件
    3. 过滤关注的事件类型（Issue / PR / Comment）
    4. 通过 enqueue_message 推送到 Yuki 消息管道
    """

    def __init__(
        self,
        session_pipeline,
        repos: Optional[List[GitHubRepoConfig]] = None,
    ):
        self.session_pipeline = session_pipeline
        self.repos: List[GitHubRepoConfig] = repos or []
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def add_repo(self, repo: GitHubRepoConfig) -> None:
        self.repos.append(repo)

    async def start(self) -> None:
        if self._running:
            return
        if not self.repos:
            logger.warning("[GitHubMonitor] 没有配置任何仓库，不启动监控")
            return
        self._running = True
        self._task = asyncio.create_task(self._main_loop())
        logger.info("[GitHubMonitor] 监控已启动，共 %d 个仓库", len(self.repos))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("[GitHubMonitor] 监控已停止")

    async def _main_loop(self) -> None:
        """主轮询循环：每个仓库按各自间隔独立轮询。"""
        # 仓库 -> 下次轮询时间戳
        next_polls: Dict[str, float] = {
            repo.key: time.time() + random.uniform(0, 30)
            for repo in self.repos
        }

        while self._running:
            now = time.time()
            tasks = []

            for repo in self.repos:
                if now >= next_polls.get(repo.key, 0):
                    tasks.append(self._poll_repo(repo))
                    next_polls[repo.key] = now + repo.poll_interval

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            await asyncio.sleep(min(10, min(
                next_polls.get(r.key, now + 60) - now
                for r in self.repos
            ) if self.repos else 10))

    async def _poll_repo(self, repo: GitHubRepoConfig) -> None:
        """单次轮询一个仓库。"""
        token = repo.token or getattr(getattr(cfg, "api", None), "github_token", "") or ""
        state = load_state()

        try:
            async with GitHubClient(token=token) as client:
                events = await fetch_repo_events(client, repo.owner, repo.repo)
        except Exception as e:
            logger.error(f"[GitHubMonitor] {repo.key} 轮询异常: {e}")
            return

        if not events:
            return

        seen_ids = get_seen_event_ids(state, repo.key)
        new_events: List[dict] = []

        for ev in events:
            evt_id = str(ev.get("id", ""))
            if not evt_id:
                continue
            if evt_id in seen_ids:
                continue
            new_events.append(ev)

        if not new_events:
            logger.debug("[GitHubMonitor] %s 无新事件", repo.key)
            return

        # 首次同步：跳过最早的历史事件，避免开群就刷屏
        last_id = get_last_event_id(state, repo.key)
        if last_id is None:
            new_events = new_events[_HISTORY_SKIP_COUNT:]
            if not new_events:
                logger.info("[GitHubMonitor] %s 首次同步完成，已跳过历史事件", repo.key)
                # 仍然记录最新的 id 避免下次再扫
                if events:
                    update_last_event_id(state, repo.key, str(events[0].get("id", "")))
                return

        logger.info(
            "[GitHubMonitor] %s 发现 %d 条新事件", repo.key, len(new_events)
        )

        for ev in reversed(new_events):  # 从旧到新推送
            await self._dispatch_event(repo, ev)
            evt_id = str(ev.get("id", ""))
            if evt_id:
                add_seen_event_id(state, repo.key, evt_id)
                update_last_event_id(state, repo.key, evt_id)

    async def _dispatch_event(self, repo: GitHubRepoConfig, ev: dict) -> None:
        """将单个事件推送到消息管道。"""
        event_type = ev.get("type", "")
        actor = ev.get("actor", {}).get("login", "someone")
        payload = ev.get("payload", {})
        repo_url = f"https://github.com/{repo.key}"

        # 只处理关注的事件类型
        if event_type not in {
            "IssuesEvent",
            "PullRequestEvent",
            "IssueCommentEvent",
            "PullRequestReviewCommentEvent",
            "PushEvent",
        }:
            return

        action = payload.get("action", "")
        # 过滤无意义的事件
        if event_type == "PushEvent" and action == "published":
            return

        # 构建消息内容
        title = self._extract_title(payload, event_type)
        if not title:
            return

        content = f"[GitHub] [{repo.key}] {actor} {self._format_action(event_type, action)}: {title}\n{repo_url}"

        # 推送到每个关联的 chat_id
        chat_ids = [repo.chat_id] if repo.chat_id else getattr(
            getattr(cfg, "github_monitor", None), "default_chat_ids", []
        ) or []

        if not chat_ids:
            logger.warning("[GitHubMonitor] %s 事件未配置 chat_id，跳过推送", repo.key)
            return

        for cid in chat_ids:
            for mode in repo.modes:
                message_obj = {
                    "name": "GitHubMonitor",
                    "content": content,
                    "raw_text": content,
                    "is_bot": True,
                    "user_id": None,
                    "message_id": None,
                }
                try:
                    await self.session_pipeline.enqueue_message(
                        str(cid),
                        mode,
                        message_obj=message_obj,
                        debounce_flag=False,
                        force_reply=True,
                        ice_break=False,
                    )
                    logger.debug("[GitHubMonitor] 已推送到 %s (%s)", cid, mode)
                except Exception as e:
                    logger.error(f"[GitHubMonitor] 推送失败 (cid={cid}): {e}")

    @staticmethod
    def _extract_title(payload: dict, event_type: str) -> str:
        """从 payload 中提取事件标题。"""
        if event_type in ("IssuesEvent", "IssueCommentEvent"):
            issue = payload.get("issue", {})
            return issue.get("title", "")
        if event_type in ("PullRequestEvent", "PullRequestReviewCommentEvent"):
            pr = payload.get("pull_request", {})
            return pr.get("title", "")
        if event_type == "PushEvent":
            commits = payload.get("commits", [])
            if commits:
                return commits[0].get("message", "")[:80]
        return ""

    @staticmethod
    def _format_action(event_type: str, action: str) -> str:
        """将 GitHub action 翻译为简短中文。"""
        mapping = {
            "IssuesEvent": {
                "opened": "开了 Issue",
                "closed": "关闭了 Issue",
                "reopened": "重开了 Issue",
                "labeled": "给 Issue 打了标签",
                "assigned": "被指派了 Issue",
            },
            "PullRequestEvent": {
                "opened": "开了 PR",
                "closed": "关闭了 PR",
                "merged": "合并了 PR",
                "reopened": "重开了 PR",
                "synchronize": "更新了 PR",
            },
            "IssueCommentEvent": {
                "created": "评论了 Issue",
                "edited": "编辑了 Issue 评论",
                "deleted": "删除了 Issue 评论",
            },
            "PullRequestReviewCommentEvent": {
                "created": "评论了 PR",
            },
            "PushEvent": {
                "": "推送了代码",
            },
        }
        return mapping.get(event_type, {}).get(action, action or "有活动")


# ==================== 便捷入口 ====================

_monitor_instance: Optional[GitHubMonitor] = None


async def ensure_monitor_started(
    session_pipeline,
    repos: Optional[List[GitHubRepoConfig]] = None,
) -> None:
    """确保监控器已启动（单例）。"""
    global _monitor_instance

    if _monitor_instance is not None:
        return

    if repos is None:
        repos = _load_repos_from_config()

    if not repos:
        logger.warning("[GitHubMonitor] 配置中未找到任何监控仓库")
        return

    _monitor_instance = GitHubMonitor(session_pipeline, repos)
    await _monitor_instance.start()


def _load_repos_from_config() -> List[GitHubRepoConfig]:
    """从 config 加载仓库列表。"""
    repos_cfg = getattr(getattr(cfg, "github_monitor", None), "repos", []) or []
    default_chat_ids = getattr(getattr(cfg, "github_monitor", None), "default_chat_ids", []) or []
    default_token = getattr(getattr(cfg, "github_monitor", None), "github_token", "") or ""
    default_interval = getattr(getattr(cfg, "github_monitor", None), "poll_interval", _DEFAULT_POLL_INTERVAL) or _DEFAULT_POLL_INTERVAL

    repos: List[GitHubRepoConfig] = []
    for r in repos_cfg:
        owner = str(r.get("owner", "")).strip()
        repo = str(r.get("repo", "")).strip()
        if not owner or not repo:
            continue
        repos.append(GitHubRepoConfig(
            owner=owner,
            repo=repo,
            token=str(r.get("token", default_token)).strip(),
            poll_interval=int(r.get("poll_interval", default_interval)),
            chat_id=str(r.get("chat_id", "")).strip(),
            modes=r.get("modes", ["group"]),
        ))
    return repos
