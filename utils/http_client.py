# utils/http_client.py
"""统一 HTTP/SSL 客户端工具。"""
from __future__ import annotations

import asyncio
import functools
import os
import socket
import ssl
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import aiohttp

_SSL_CONTEXT: ssl.SSLContext | None = None
_CA_FILE: str | None = None


def get_ca_file() -> str:
    """获取统一 CA 文件路径，优先使用环境变量，否则使用 certifi。"""
    cafile = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if cafile and os.path.exists(cafile):
        return cafile

    try:
        import certifi

        return certifi.where()
    except Exception:
        default_cafile = ssl.get_default_verify_paths().cafile
        if default_cafile and os.path.exists(default_cafile):
            return default_cafile
        raise RuntimeError("无法找到可用的 CA 证书文件")


def configure_ssl_environment() -> str:
    """为 requests/urllib/httpx 等库设置统一 CA 环境变量。"""
    cafile = get_ca_file()
    os.environ["SSL_CERT_FILE"] = cafile
    os.environ["REQUESTS_CA_BUNDLE"] = cafile
    return cafile


def create_ssl_context() -> ssl.SSLContext:
    """创建统一 SSL 上下文，默认使用 certifi CA，避免依赖损坏的系统证书存储。"""
    global _SSL_CONTEXT, _CA_FILE
    cafile = configure_ssl_environment()
    if _SSL_CONTEXT is not None and _CA_FILE == cafile:
        return _SSL_CONTEXT

    _CA_FILE = cafile
    _SSL_CONTEXT = ssl.create_default_context(cafile=cafile)
    return _SSL_CONTEXT


def create_tcp_connector(**kwargs: Any) -> aiohttp.TCPConnector:
    """创建统一 SSL 配置的 aiohttp TCPConnector。"""
    kwargs.setdefault("ssl", create_ssl_context())
    return aiohttp.TCPConnector(**kwargs)


class DedicatedDnsResolver(aiohttp.abc.AbstractResolver):
    """独立线程池的域名解析器。

    aiohttp 默认的 ThreadedResolver 走 loop.getaddrinfo，用的是事件循环的默认
    ThreadPoolExecutor —— 与 asyncio.to_thread 共用（8 核只有 12 个 worker）。
    一旦有 to_thread 任务卡住，所有域名解析就会排队，表现为连接阶段超时。
    这里给解析单独开一个小线程池，彻底与业务线程隔离。
    """

    def __init__(self, max_workers: int = 4, timeout: float = 8.0) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="dns-resolver"
        )
        self._timeout = timeout

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list:
        loop = asyncio.get_running_loop()
        func = functools.partial(
            socket.getaddrinfo,
            host,
            port,
            family=family,
            type=socket.SOCK_STREAM,
            flags=socket.AI_ADDRCONFIG,
        )
        infos = await asyncio.wait_for(
            loop.run_in_executor(self._executor, func), timeout=self._timeout
        )
        results = []
        for fam, _, proto, _, address in infos:
            if fam == socket.AF_INET6 and len(address) >= 2:
                results.append(
                    {
                        "hostname": host,
                        "host": address[0],
                        "port": port,
                        "family": fam,
                        "proto": proto,
                        "flags": socket.AI_NUMERICHOST | socket.AI_NUMERICSERV,
                    }
                )
            else:
                results.append(
                    {
                        "hostname": host,
                        "host": address[0],
                        "port": address[1] if len(address) > 1 else port,
                        "family": fam,
                        "proto": proto,
                        "flags": socket.AI_NUMERICHOST | socket.AI_NUMERICSERV,
                    }
                )
        if not results:
            raise OSError(f"getaddrinfo() 未返回任何地址: {host}")
        return results

    async def close(self) -> None:
        self._executor.shutdown(wait=False)


def create_dns_resolver(**kwargs: Any) -> DedicatedDnsResolver:
    """创建独立线程池的解析器（供长连接复用的全局会话使用）。"""
    return DedicatedDnsResolver(**kwargs)


def urlopen(url_or_request: str | urllib.request.Request, **kwargs: Any):
    """使用统一 SSL 上下文发起 urllib 请求。"""
    kwargs.setdefault("context", create_ssl_context())
    return urllib.request.urlopen(url_or_request, **kwargs)


def requests_verify() -> str:
    """返回 requests/httpx 可用的 verify CA 文件路径。"""
    return configure_ssl_environment()


configure_ssl_environment()
