import asyncio, json
from core.ncm_login import generate_qr, save_pending, poll_login, save_cookie, clear_pending

async def main():
    qr = await generate_qr()
    if not qr.get("success"):
        print("QR_FAIL:", qr.get("message"), flush=True); return
    save_pending(qr["unikey"])
    print("QR_READY:", qr["image_path"], flush=True)
    r = await poll_login(qr["unikey"], timeout_seconds=170)
    print("POLL:", json.dumps({k: v for k, v in r.items() if k != "cookie"}, ensure_ascii=False), flush=True)
    if r.get("success"):
        print("SAVE_COOKIE:", save_cookie(r["cookie"]), flush=True)
        clear_pending()

asyncio.run(main())
