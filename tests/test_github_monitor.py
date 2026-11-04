"""GitHub Monitor 离线测试：状态持久化与 PushEvent Compare API 渲染。"""
from unittest.mock import AsyncMock, MagicMock

from modules.github_monitor import card_renderer, state as state_module
from modules.github_monitor.monitor import GitHubMonitor, GitHubRepoConfig
from modules.github_monitor.state import load_state, save_state


def test_state_persistence_roundtrip(tmp_path, monkeypatch):
    """状态文件缺失时返回空状态，保存后可完整读回。"""
    monkeypatch.setattr(state_module, "STATE_FILE", str(tmp_path / "github_monitor_state.json"))
    assert load_state() == {"repos": {}, "last_poll": ""}

    state = {
        "repos": {"owner/repo": {"last_event_id": "evt_1", "seen_ids": ["evt_1", "evt_2"]}},
        "last_poll": "2026-01-01T00:00:00",
    }
    save_state(state)
    loaded = load_state()
    assert loaded["repos"]["owner/repo"]["last_event_id"] == "evt_1"
    assert loaded["repos"]["owner/repo"]["seen_ids"] == ["evt_1", "evt_2"]


async def test_push_event_fetches_and_displays_compare_commits(tmp_path, monkeypatch):
    """Events API 仅含 before/head 时，通过 Compare API 补全提交详情并推送到管线。"""
    monkeypatch.setattr(card_renderer, "CARD_DIR", tmp_path / "github_monitor")
    pipeline = MagicMock()
    repo = GitHubRepoConfig(owner="owner", repo="repo", chat_ids=["chat"])
    monitor = GitHubMonitor(pipeline, [repo])

    compare_response = MagicMock(status_code=200)
    compare_response.json.return_value = {
        "commits": [
            {
                "sha": "1234567890abcdef",
                "commit": {"message": "Add feature", "author": {"name": "Alice"}},
                "author": {"login": "alice"},
            },
            {
                "sha": "abcdef1234567890",
                "commit": {"message": "Fix bug", "author": {"name": "Bob"}},
                "author": {"login": "bob"},
            },
        ]
    }
    monitor._client = MagicMock()
    monitor._client.get = AsyncMock(return_value=compare_response)

    await monitor._dispatch_event(repo, {
        "type": "PushEvent",
        "actor": {"login": "pusher"},
        "payload": {"ref": "refs/heads/main", "before": "before-sha", "head": "head-sha"},
    })

    content = pipeline.enqueue_message.call_args.kwargs["message_obj"]["content"]
    assert "2 commit(s) to main" in content
    assert "1234567 Alice: Add feature" in content
    assert "abcdef1 Bob: Fix bug" in content
    assert "unknown" not in content
    monitor._client.get.assert_awaited_once()
