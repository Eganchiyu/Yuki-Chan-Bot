# utils/http_client.py
"""HTTP 客户端工具。"""
import os
import ssl
from typing import Optional

import aiohttp


_SSL_CONTEXT: Optional[ssl.SSLContext] = None


def create_ssl_context() -> ssl.SSLContext:
    """创建 SSL 上下文，优先使用文件 CA，避免读取损坏的 Windows 证书存储。"""
    global _SSL_CONTEXT
    if _SSL_CONTEXT is not None:
        return _SSL_CONTEXT

    cafile = os.environ.get("SSL_CERT_FILE")
    if not cafile or not os.path.exists(cafile):
        try:
            import certifi

            cafile = certifi.where()
        except Exception:
            cafile = ssl.get_default_verify_paths().cafile

    if cafile and os.path.exists(cafile):
        _SSL_CONTEXT = ssl.create_default_context(cafile=cafile)
    else:
        _SSL_CONTEXT = ssl.create_default_context()
    return _SSL_CONTEXT


def create_tcp_connector(**kwargs) -> aiohttp.TCPConnector:
    """创建统一 SSL 配置的 aiohttp TCPConnector。"""
    kwargs.setdefault("ssl", create_ssl_context())
    return aiohttp.TCPConnector(**kwargs)
