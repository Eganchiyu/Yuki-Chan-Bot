# tests/test_github_monitor.py
"""GitHub Monitor 集成测试：覆盖首次同步、去重、并发安全和客户端复用。"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from modules.github_monitor.client import GitHubClient
from modules.github_monitor.events import fetch_repo_events
from modules.github_monitor.monitor import GitHubMonitor, GitHubRepoConfig
from modules.github_monitor.state import STATE_FILE, load_state, save_state


# ====================  fixtures  ====================

@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def monitor_config(project_root: Path):
    """从 configs/config.yaml 加载真实配置。"""
    config_path = project_root / "configs" / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg


@pytest.fixture(scope="session")
def github_token(monitor_config) -> str:
    token = monitor_config.get("github_monitor", {}).get("github_token", "") or ""
    if not token:
        pytest.skip("config.yaml 中未配置 github_token，跳过需要真实 API 的测试")
    return token


@pytest.fixture()
def tmp_state_dir(monkeypatch, project_root: Path):
    """将状态文件临时重定向到 tmp 目录，避免污染真实状态。"""
    tmp_dir = tempfile.mkdtemp(prefix="github_monitor_test_")
    tmp_state = Path(tmp_dir) / "github_monitor_state.json"
    import modules.github_monitor.state as state_module
    monkeypatch.setattr(state_module, "STATE_FILE", str(tmp_state))
    yield tmp_state
    if tmp_state.exists():
        tmp_state.unlink()
    try:
        os.rmdir(str(tmp_dir))
    except OSError:
        pass


@pytest.fixture()
def fake_session_pipeline():
    """伪造 session_pipeline，仅记录推送消息。"""
    pipeline = MagicMock()
    pipeline.enqueue_message = MagicMock()
    return pipeline


# ====================  基础 I/O 测试  ====================

class TestStatePersistence:
    def test_load_state_returns_empty_when_missing(self, tmp_state_dir):
        state = load_state()
        assert state == {"repos": {}, "last_poll": ""}

    def test_save_and_load_roundtrip(self, tmp_state_dir):
        state = {
            "repos": {
                "owner/repo": {
                    "last_event_id": "evt_1",
                    "seen_ids": ["evt_1", "evt_2"],
                }
            },
            "last_poll": "2026-01-01T00:00:00",
        }
        save_state(state)
        loaded = load_state()
        assert loaded["repos"]["owner/repo"]["last_event_id"] == "evt_1"
        assert loaded["repos"]["owner/repo"]["seen_ids"] == ["evt_1", "evt_2"]


# ====================  客户端测试  ====================

class TestGitHubClient:
    @pytest.mark.asyncio
    async def test_client_reuse(self, github_token: str):
        """同一个 client 实例可连续请求，验证长连接可用。"""
        async with GitHubClient(token=github_token) as client:
            resp = await client.get("/rate_limit")
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_fetch_repo_events(self, github_token: str, monitor_config):
        """使用真实 API 拉取配置中的仓库事件。"""
        repo_cfg = monitor_config["github_monitor"]["repos"][0]
        owner = repo_cfg["owner"]
        repo = repo_cfg["repo"]

        async with GitHubClient(token=github_token) as client:
            events = await fetch_repo_events(client, owner, repo)

        assert isinstance(events, list)
        if events:
            assert "id" in events[0]
            assert "type" in events[0]


# ====================  Monitor 核心逻辑测试  ====================

class TestGitHubMonitorLogic:
    @pytest.mark.asyncio
    async def test_first_sync_populates_seen_ids(self, github_token: str, fake_session_pipeline, tmp_state_dir):
        """首次同步时，所有拉取到的事件 ID 都应写入 seen_ids，且不推送消息。"""
        repo = GitHubRepoConfig(
            owner="Eganchiyu",
            repo="Yuki-Chan-Bot",
            token=github_token,
            poll_interval=300,
        )
        monitor = GitHubMonitor(fake_session_pipeline, [repo])
        monitor._state = load_state()
        monitor._client = GitHubClient(token=github_token)

        await monitor._poll_repo(repo)

        # 验证状态已写入
        state = load_state()
        repo_state = state["repos"].get(repo.key, {})
        assert "last_event_id" in repo_state
        assert len(repo_state.get("seen_ids", [])) > 0
        # 首次同步不应推送任何消息
        fake_session_pipeline.enqueue_message.assert_not_called()
        await monitor._client.close()

    @pytest.mark.asyncio
    async def test_no_duplicate_push_after_first_sync(self, github_token: str, fake_session_pipeline, tmp_state_dir):
        """完成首次同步后，再次轮询同一批事件时不应重复推送。"""
        repo = GitHubRepoConfig(
            owner="Eganchiyu",
            repo="Yuki-Chan-Bot",
            token=github_token,
            poll_interval=300,
        )
        monitor = GitHubMonitor(fake_session_pipeline, [repo])
        monitor._state = load_state()
        monitor._client = GitHubClient(token=github_token)

        # 第一次：首次同步
        await monitor._poll_repo(repo)
        fake_session_pipeline.enqueue_message.reset_mock()

        # 第二次：应检测不到新事件
        await monitor._poll_repo(repo)
        fake_session_pipeline.enqueue_message.assert_not_called()
        await monitor._client.close()

    @pytest.mark.asyncio
    async def test_client_is_reused(self, github_token: str, fake_session_pipeline):
        """start/stop 生命周期中，应只创建一次 GitHubClient。"""
        repo = GitHubRepoConfig(
            owner="Eganchiyu",
            repo="Yuki-Chan-Bot",
            token=github_token,
            poll_interval=300,
        )
        monitor = GitHubMonitor(fake_session_pipeline, [repo])

        await monitor.start()
        assert monitor._client is not None
        first_client = monitor._client

        # 再次调用 start 不应创建新 client
        await monitor.start()
        assert monitor._client is first_client

        await monitor.stop()
        assert monitor._client is None

    @pytest.mark.asyncio
    async def test_concurrent_polls_do_not_corrupt_state(self, github_token: str, fake_session_pipeline, tmp_state_dir):
        """并发轮询多个仓库时，状态文件不应出现覆盖丢失。"""
        repos = [
            GitHubRepoConfig(
                owner="Eganchiyu",
                repo="Yuki-Chan-Bot",
                token=github_token,
                poll_interval=300,
            ),
            GitHubRepoConfig(
                owner="Eganchiyu",
                repo="Yuki-Chan-Bot",
                token=github_token,
                poll_interval=300,
            ),
        ]
        monitor = GitHubMonitor(fake_session_pipeline, repos)
        monitor._state = load_state()
        monitor._client = GitHubClient(token=github_token)

        # 并发执行两次轮询（同一仓库）
        await asyncio.gather(
            monitor._poll_repo(repos[0]),
            monitor._poll_repo(repos[1]),
        )

        state = load_state()
        repo_state = state["repos"].get(repos[0].key, {})
        assert "last_event_id" in repo_state
        assert len(repo_state.get("seen_ids", [])) > 0
        await monitor._client.close()
