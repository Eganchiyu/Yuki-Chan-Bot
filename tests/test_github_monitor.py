# tests/test_github_monitor.py
"""GitHub Monitor 离线测试：状态持久化 + 事件渲染（不联网）。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.github_monitor.monitor import GitHubMonitor, GitHubRepoConfig
from modules.github_monitor.state import load_state, save_state


# ====================  fixtures  ====================

@pytest.fixture()
def tmp_state_dir(monkeypatch):
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


# ====================  Monitor 核心逻辑测试  ====================

class TestGitHubMonitorLogic:
    @pytest.mark.asyncio
    async def test_push_event_fetches_and_displays_compare_commits(self, fake_session_pipeline, tmp_path, monkeypatch):
        """Events API 只返回 before/head 时，应通过 Compare API 展示提交详情。"""
        from modules.github_monitor import card_renderer
        monkeypatch.setattr(card_renderer, "CARD_DIR", tmp_path / "github_monitor")
        repo = GitHubRepoConfig(owner="owner", repo="repo", chat_ids=["chat"])
        monitor = GitHubMonitor(fake_session_pipeline, [repo])
        monitor._client = MagicMock()
        monitor._client.get = AsyncMock()
        compare_response = MagicMock(status_code=200)
        compare_response.json.return_value = {
            "commits": [
                {
                    "sha": "1234567890abcdef",
                    "commit": {
                        "message": "Add feature",
                        "author": {"name": "Alice"},
                    },
                    "author": {"login": "alice"},
                },
                {
                    "sha": "abcdef1234567890",
                    "commit": {
                        "message": "Fix bug",
                        "author": {"name": "Bob"},
                    },
                    "author": {"login": "bob"},
                },
            ]
        }
        monitor._client.get.return_value = compare_response

        await monitor._dispatch_event(repo, {
            "type": "PushEvent",
            "actor": {"login": "pusher"},
            "payload": {
                "ref": "refs/heads/main",
                "before": "before-sha",
                "head": "head-sha",
            },
        })

        content = fake_session_pipeline.enqueue_message.call_args.kwargs["message_obj"]["content"]
        assert "2 commit(s) to main" in content
        assert "1234567 Alice: Add feature" in content
        assert "abcdef1 Bob: Fix bug" in content
        assert "unknown" not in content
        monitor._client.get.assert_awaited_once()
