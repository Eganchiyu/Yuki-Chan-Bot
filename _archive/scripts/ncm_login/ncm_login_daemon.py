"""网易云扫码登录守护：二维码过期就自动刷新同一个 PNG，直到登录成功。

用户只需反复打开/刷新 /home/asumi/Yuki/output/ncm/ncm_qr_login.png 来扫码。
状态写在 output/ncm/login_status.txt，日志在 output/ncm/login_daemon.log。
"""
import asyncio
import json
import time

import qrcode

from core.ncm_login import (
    QR_LOGIN_API,
    QR_URL_TEMPLATE,
    _base_config,
    _post_eapi,
    _extract_cookie_from_set_cookie,
    clear_pending,
    generate_qr,
    save_cookie,
    save_pending,
)

LOG = "/home/asumi/Yuki/output/ncm/login_daemon.log"
STATUS = "/home/asumi/Yuki/output/ncm/login_status.txt"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def status(state: str, extra: dict | None = None) -> None:
    payload = {"state": state, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    if extra:
        payload.update(extra)
    try:
        with open(STATUS, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError as e:
        log(f"写状态失败: {e}")


def ascii_qr(url: str) -> None:
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)


async def poll_once(unikey: str, budget: int) -> tuple[str, str]:
    """返回 (结果, cookie)。结果: 'ok' / 'expired' / 'timeout'。"""
    start = time.time()
    while time.time() - start < budget:
        try:
            code, data, set_cookie = await _post_eapi(
                QR_LOGIN_API, {"key": unikey, "type": 1, "header": json.dumps(_base_config())}
            )
        except Exception as e:
            log(f"轮询异常（忽略）: {type(e).__name__}")
            await asyncio.sleep(3)
            continue

        c = data.get("code")
        if c == 803:
            cookie = _extract_cookie_from_set_cookie(set_cookie)
            if cookie and "MUSIC_U=" in cookie:
                return "ok", cookie
            log(f"803 但 Cookie 缺 MUSIC_U: {sorted(k for k, _ in [])}")
            return "expired", ""
        if c == 800:
            return "expired", ""
        if c == 802:
            status("scanned", {"unikey": unikey})
            log("已扫码，等待手机确认…")
        await asyncio.sleep(3)
    return "timeout", ""


async def main() -> int:
    rounds = 0
    while rounds < 20:
        rounds += 1
        qr = await generate_qr()
        if not qr.get("success"):
            log(f"生成二维码失败: {qr.get('message')}")
            status("qr_failed", {"message": qr.get("message")})
            await asyncio.sleep(5)
            continue

        unikey = qr["unikey"]
        url = QR_URL_TEMPLATE.format(unikey=unikey)
        save_pending(unikey)
        status("waiting_scan", {"unikey": unikey, "qr_url": url, "png": qr["image_path"]})
        log(f"第 {rounds} 张二维码已就绪 -> {qr['image_path']}")
        ascii_qr(url)
        log(f"QR_URL: {url}")

        result, cookie = await poll_once(unikey, budget=150)
        if result == "ok":
            saved = save_cookie(cookie)
            clear_pending()
            log(f"登录成功，Cookie 已保存: {saved}")
            status("logged_in", {"cookie_files": saved if isinstance(saved, list) else str(saved)})
            return 0
        log(f"本轮结束: {result}，刷新二维码")

    status("gave_up")
    log("重试次数用尽，放弃")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
