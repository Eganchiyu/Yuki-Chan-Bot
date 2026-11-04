# core/ncm_login.py
"""网易云音乐二维码登录模块（eapi 接口，零第三方依赖）。

流程：
1. generate_qr() 生成二维码 unikey 并渲染 PNG 图片
2. 用户用网易云音乐 App 扫码
3. poll_login(unikey) 轮询登录状态，成功后从 Set-Cookie 提取完整 Cookie
4. save_cookie() 写入 cookie 文件（与 tools.py 中 ncm_* 工具共用）
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import subprocess
import time
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode, urlparse

from config import cfg

# eapi 常量（与 Netease_url 项目一致）
AES_KEY = b"e82ckenh8dichen8"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Safari/537.36 Chrome/91.0.4472.164 "
    "NeteaseMusicDesktop/2.10.2.200154"
)
QR_UNIKEY_API = "https://interface3.music.163.com/eapi/login/qrcode/unikey"
QR_LOGIN_API = "https://interface3.music.163.com/eapi/login/qrcode/client/login"
QR_URL_TEMPLATE = "https://music.163.com/login?codekey={unikey}"


def _cookie_file() -> str:
    """返回 cookie 文件路径（与 tools.py 共用配置）。"""
    return os.path.abspath(
        os.path.expanduser(getattr(cfg.paths, "ncm_cookie_file", "~/.cache/ncm_cookie.txt"))
    )


def _qr_image_path() -> str:
    """返回二维码图片保存路径。"""
    out_dir = os.path.abspath(
        os.path.expanduser(getattr(cfg.paths, "ncm_download_dir", "./output/ncm"))
    )
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, "ncm_qr_login.png")


def _pending_file() -> str:
    """返回待扫码状态文件路径（与二维码图片同目录）。"""
    return os.path.join(os.path.dirname(_qr_image_path()), ".ncm_qr_pending.json")


def save_pending(unikey: str) -> None:
    """记录正在等待扫码的二维码状态（跨调用持久化）。"""
    try:
        with open(_pending_file(), "w", encoding="utf-8") as f:
            json.dump({"unikey": unikey, "created_at": time.time()}, f, ensure_ascii=False)
    except OSError:
        pass


def load_pending() -> Optional[dict]:
    """读取待扫码状态；无记录或已过期返回 None。"""
    try:
        with open(_pending_file(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - data.get("created_at", 0) > 180:
            return None
        return data
    except (OSError, json.JSONDecodeError):
        return None


def clear_pending() -> None:
    """清除待扫码状态。"""
    try:
        os.remove(_pending_file())
    except OSError:
        pass


def aes_ecb_encrypt_hex(data: bytes) -> str:
    """AES-128-ECB 加密（PKCS7 padding），返回 hex。用系统 openssl，零依赖。"""
    proc = subprocess.run(
        ["openssl", "enc", "-aes-128-ecb", "-K", AES_KEY.hex(), "-nosalt", "-nopad"],
        input=data,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"openssl AES 加密失败: {proc.stderr.decode(errors='replace')}")
    return proc.stdout.hex()


def _pkcs7(data: bytes, block_size: int = 16) -> bytes:
    pad = block_size - len(data) % block_size
    return data + bytes([pad]) * pad


def encrypt_params(url: str, payload: dict) -> str:
    """eapi 参数加密：url_path + MD5 摘要 + AES-ECB。"""
    url_path = urlparse(url).path.replace("/eapi/", "/api/")
    digest = hashlib.md5(
        f"nobody{url_path}use{json.dumps(payload)}md5forencrypt".encode()
    ).hexdigest()
    params = f"{url_path}-36cd479b6b5-{json.dumps(payload)}-36cd479b6b5-{digest}"
    return aes_ecb_encrypt_hex(_pkcs7(params.encode()))


def _base_config() -> dict:
    return {
        "os": "pc",
        "appver": "",
        "osver": "",
        "deviceId": "pyncm!",
        "requestId": str(random.randrange(20000000, 30000000)),
    }


async def _post_eapi(url: str, payload: dict, cookies: dict | None = None) -> tuple[int, dict, str]:
    """POST eapi 接口，返回 (http状态, json, set_cookie原文)。

    set_cookie 收集响应里的全部 Set-Cookie 头（多条用换行分隔），
    避免只取第一条导致登录后保存的 Cookie 缺少 MUSIC_U / __csrf 等字段。
    """
    import aiohttp

    params = encrypt_params(url, payload)
    headers = {
        "User-Agent": UA,
        "Referer": "https://music.163.com/",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            url,
            headers=headers,
            cookies=cookies or {},
            data={"params": params},
        ) as resp:
            text = await resp.text()
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = {}
            set_cookie_headers = resp.headers.getall("Set-Cookie", [])
            return resp.status, data, "\n".join(set_cookie_headers)


async def generate_qr() -> dict:
    """生成二维码登录 unikey 并渲染 PNG 图片。

    Returns:
        {"success": bool, "unikey": str, "image_path": str, "message": str}
    """
    status, data, _ = await _post_eapi(QR_UNIKEY_API, {"type": 1, "header": json.dumps(_base_config())})
    if status != 200 or data.get("code") != 200 or not data.get("unikey"):
        return {"success": False, "message": f"生成二维码失败: {data.get('message', status)}"}

    unikey = data["unikey"]
    image_path = _qr_image_path()
    try:
        import qrcode
    except ImportError:
        return {
            "success": False,
            "message": "缺少 qrcode 库，请运行: conda activate yuki && pip install qrcode",
        }

    qr = qrcode.QRCode(border=2, box_size=10)
    qr.add_data(QR_URL_TEMPLATE.format(unikey=unikey))
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    try:
        img.save(image_path)
    except Exception as e:
        return {"success": False, "message": f"二维码图片保存失败: {e}"}

    return {
        "success": True,
        "unikey": unikey,
        "image_path": image_path,
        "message": "二维码已生成，请用网易云音乐 App 扫码登录（有效期约3分钟）",
    }


async def poll_login(unikey: str, timeout_seconds: int = 180, interval: float = 3.0) -> dict:
    """轮询二维码登录状态，成功后返回完整 cookie 字符串。

    Returns:
        {"success": bool, "cookie": str|None, "message": str}
    """
    start = time.time()
    while time.time() - start < timeout_seconds:
        status, data, set_cookie = await _post_eapi(
            QR_LOGIN_API,
            {"key": unikey, "type": 1, "header": json.dumps(_base_config())},
        )
        code = data.get("code")

        if code == 803:  # 登录成功
            cookie_str = _extract_cookie_from_set_cookie(set_cookie)
            if not cookie_str or "MUSIC_U=" not in cookie_str:
                return {"success": False, "message": "登录成功但未获取到 MUSIC_U Cookie"}
            return {"success": True, "cookie": cookie_str, "message": "登录成功"}

        if code == 800:  # 二维码过期
            return {"success": False, "message": "二维码已过期，请重新生成"}

        if code == 802:  # 已扫码待确认
            await asyncio.sleep(interval)
            continue

        if code == 801:  # 等待扫码
            await asyncio.sleep(interval)
            continue

        # 其他状态
        await asyncio.sleep(interval)

    return {"success": False, "message": "登录超时，请重新生成二维码"}


def _extract_cookie_from_set_cookie(set_cookie: str) -> str:
    """从 Set-Cookie 响应头提取关键 cookie 为字符串。

    只保留对接口调用有用的字段：MUSIC_U / __csrf / NMTID / JSESSIONID-WYYY / os。
    支持多条 Set-Cookie（按行分隔）；用 SimpleCookie 解析，避免 Expires 里的逗号
    把 Cookie 切断。
    """
    if not set_cookie:
        return ""
    wanted = ("MUSIC_U", "__csrf", "NMTID", "JSESSIONID-WYYY", "os")
    values: dict[str, str] = {}
    for header in set_cookie.splitlines():
        header = header.strip()
        if not header:
            continue
        jar = SimpleCookie()
        try:
            jar.load(header)
        except Exception:
            continue
        for name, morsel in jar.items():
            if name in wanted:
                values[name] = morsel.value
    # 兼容早期只传单条、逗号拼接的 Set-Cookie 文本
    for chunk in set_cookie.replace("\n", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        for name in wanted:
            prefix = f"{name}="
            if name not in values and chunk.startswith(prefix):
                values[name] = chunk.split(";", 1)[0][len(prefix):]
                break
    return "; ".join(f"{name}={values[name]}" for name in wanted if name in values)


def save_cookie(cookie_str: str) -> bool:
    """把 cookie 写入配置文件（600 权限）。"""
    if not cookie_str or not cookie_str.strip():
        return False
    path = _cookie_file()
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(cookie_str.strip() + "\n")
        os.chmod(path, 0o600)
        return True
    except OSError:
        return False


def cookie_exists() -> bool:
    """检查 cookie 文件是否存在且非空。"""
    path = Path(_cookie_file())
    return path.is_file() and path.stat().st_size > 10
