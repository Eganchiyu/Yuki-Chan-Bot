# utils/http_client.py
"""统一 HTTP/SSL 客户端工具。"""
from __future__ import annotations

import os
import ssl
import urllib.request
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
    os.environ.setdefault("SSL_CERT_FILE", cafile)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", cafile)
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


def urlopen(url_or_request: str | urllib.request.Request, **kwargs: Any):
    """使用统一 SSL 上下文发起 urllib 请求。"""
    kwargs.setdefault("context", create_ssl_context())
    return urllib.request.urlopen(url_or_request, **kwargs)


def requests_verify() -> str:
    """返回 requests/httpx 可用的 verify CA 文件路径。"""
    return configure_ssl_environment()


configure_ssl_environment()
