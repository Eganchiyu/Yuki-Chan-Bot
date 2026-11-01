"""生成二维码登录：打印可扫的 ASCII 二维码，容错轮询，成功即写 cookie。"""
import asyncio, json, sys, time
import qrcode

from core.ncm_login import generate_qr, save_pending, poll_login, save_cookie, clear_pending, QR_URL_TEMPLATE, _post_eapi, QR_LOGIN_API, _base_config, _extract_cookie_from_set_cookie


def print_ascii(url: str) -> None:
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)


async def poll_resilient(unikey: str, total: int = 170) -> dict:
    """逐次轮询，单次网络异常不致命。"""
    start = time.time()
    while time.time() - start < total:
        try:
            status, data, set_cookie = await _post_eapi(
                QR_LOGIN_API, {"key": unikey, "type": 1, "header": json.dumps(_base_config())}
            )
        except Exception as e:
            print(f"[warn] 轮询网络异常，稍后重试: {type(e).__name__}", flush=True)
            await asyncio.sleep(3)
            continue
        code = data.get("code")
        if code == 803:
            cookie = _extract_cookie_from_set_cookie(set_cookie)
            if not cookie or "MUSIC_U=" not in cookie:
                return {"success": False, "message": "登录成功但未取到 MUSIC_U"}
            return {"success": True, "cookie": cookie, "message": "登录成功"}
        if code == 800:
            return {"success": False, "message": "二维码已过期"}
        if code == 802:
            print("[info] 已扫码，等待手机确认…", flush=True)
        await asyncio.sleep(3)
    return {"success": False, "message": "轮询超时"}


async def main() -> int:
    qr = await generate_qr()
    if not qr.get("success"):
        print("QR_FAIL:", qr.get("message"), flush=True)
        return 1
    save_pending(qr["unikey"])
    print_ascii(QR_URL_TEMPLATE.format(unikey=qr["unikey"]))
    print(f"QR_URL: {QR_URL_TEMPLATE.format(unikey=qr['unikey'])}", flush=True)
    print(f"QR_PNG: {qr['image_path']}", flush=True)
    r = await poll_resilient(qr["unikey"])
    print("RESULT:", json.dumps({k: v for k, v in r.items() if k != "cookie"}, ensure_ascii=False), flush=True)
    if r.get("success"):
        print("SAVE_COOKIE:", save_cookie(r["cookie"]), flush=True)
        clear_pending()
    return 0 if r.get("success") else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
