# modules/github_monitor/client.py
"""GitHub REST API 客户端（httpx.AsyncClient 封装）。"""

from __future__ import annotations

import httpx

_GITHUB_API_BASE = "https://api.github.com"
_DEFAULT_TIMEOUT = 30.0


def github_headers(token: str = "", *, extra_accept: str | None = None) -> dict[str, str]:
    headers: dict[str, str] = {
        "Accept": extra_accept or "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Yuki-GitHub-Monitor/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


class GitHubClient:
    def __init__(
        self,
        token: str = "",
        *,
        base_url: str = _GITHUB_API_BASE,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._token = token
        self._base_url = base_url
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=github_headers(token),
            timeout=httpx.Timeout(timeout),
        )

    async def __aenter__(self) -> GitHubClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._client.aclose()

    async def close(self) -> None:
        await self._client.aclose()

    async def get(self, path: str, **kwargs) -> httpx.Response:
        return await self._client.get(path, **kwargs)
