"""
QQ空间说说发布模块

支持纯文本和带图说说。每次操作自动刷新认证信息。
"""

import re
import json
import base64
import urllib.request
import urllib.parse
from typing import Optional, List
from utils.logger import get_logger

logger = get_logger("qzone")

PUBLISH_URL = "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_publish_v6"
UPLOAD_URL = "https://up.qzone.qq.com/cgi-bin/upload/cgi_upload_image"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def _compute_g_tk(p_skey: str) -> int:
    h = 5381
    for ch in p_skey:
        h += (h << 5) + ord(ch)
    return h & 0x7FFFFFFF


def _extract_cookie(cookies: str, name: str) -> Optional[str]:
    m = re.search(rf"{name}=([^;]+)", cookies)
    return m.group(1) if m else None


def _parse_jsonp(raw: str) -> Optional[dict]:
    """解析 JSONP / frameElement.callback(...) 响应。"""
    for pattern in [
        r"frameElement\.callback\((.*)\)",
        r"_Callback\((.*)\)",
        r"callback\((.*)\)",
    ]:
        m = re.search(pattern, raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


async def _get_auth(connector) -> tuple:
    """获取 (cookies, g_tk, uin, skey, p_skey)。"""
    cookie_resp = await connector.get_cookies("user.qzone.qq.com")
    if not cookie_resp or cookie_resp.get("status") != "ok":
        raise RuntimeError(f"获取 Cookie 失败: {(cookie_resp or {}).get('message', '无响应')}")

    cookies = cookie_resp["data"]["cookies"]
    p_skey = _extract_cookie(cookies, "p_skey")
    skey = _extract_cookie(cookies, "skey")
    if not p_skey:
        raise RuntimeError("Cookie 缺少 p_skey")

    g_tk = _compute_g_tk(p_skey)

    login_resp = await connector.get_login_info()
    if not login_resp or login_resp.get("status") != "ok":
        raise RuntimeError("获取登录信息失败")
    uin = str(login_resp["data"]["user_id"])

    return cookies, g_tk, uin, skey, p_skey


def _http_post(url: str, data: dict, cookies: str, referer: str,
               content_type: str = "application/x-www-form-urlencoded;charset=UTF-8") -> str:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Cookie", cookies)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", referer)
    req.add_header("Content-Type", content_type)
    req.add_header("Origin", "https://user.qzone.qq.com")
    resp = urllib.request.urlopen(req, timeout=30)
    return resp.read().decode("utf-8", errors="replace")


async def _upload_image(connector, image_path: str, cookies: str,
                        g_tk: int, uin: str, skey: str, p_skey: str) -> dict:
    """上传图片到 QZone 服务器，返回 {lloc, bo, url}。"""
    with open(image_path, "rb") as f:
        image_data = f.read()
    picfile_b64 = base64.b64encode(image_data).decode()

    data = {
        "filename": "image.jpg", "uin": uin, "skey": skey,
        "zzpaneluin": uin, "zzpanelkey": "", "p_uin": uin, "p_skey": p_skey,
        "qzonetoken": "", "uploadtype": "1", "albumtype": "7", "exttype": "0",
        "refer": "shuoshuo", "output_type": "jsonhtml", "charset": "utf-8",
        "output_charset": "utf-8", "upload_hd": "1", "hd_width": "2048",
        "hd_height": "10000", "hd_quality": "96",
        "backUrls": "http://upbak.photo.qzone.qq.com/cgi-bin/upload/cgi_upload_image",
        "url": f"{UPLOAD_URL}?g_tk={g_tk}",
        "base64": "1", "jsonhtml_callback": "callback",
        "picfile": picfile_b64,
        "qzreferrer": f"https://user.qzone.qq.com/{uin}",
    }

    raw = _http_post(f"{UPLOAD_URL}?g_tk={g_tk}", data, cookies,
                     f"https://user.qzone.qq.com/{uin}")

    result = _parse_jsonp(raw)
    if not result or "data" not in result:
        raise RuntimeError(f"图片上传响应解析失败: {raw[:200]}")

    d = result["data"]
    lloc = d.get("lloc", "")
    if not lloc:
        raise RuntimeError(f"图片上传未返回 lloc: {d}")

    bo = d.get("bo", "")
    if not bo:
        url = d.get("url", "")
        bo_m = re.search(r"&bo=([^&]+)", url)
        bo = bo_m.group(1) if bo_m else ""

    return {"lloc": lloc, "bo": bo, "url": d.get("url", "")}


async def publish_mood(connector, content: str, visible: int = 1,
                       image_paths: List[str] = None) -> dict:
    """
    发布 QQ 空间说说。

    Args:
        connector: BotConnector 实例
        content: 说说文本
        visible: 1=公开 4=仅自己
        image_paths: 图片本地路径列表（可选，最多支持多张）

    Returns:
        {"success": True, "tid": "...", "time": "...", "content": "..."}
    """
    try:
        cookies, g_tk, uin, skey, p_skey = await _get_auth(connector)
    except RuntimeError as e:
        return {"success": False, "code": -1, "message": str(e)}

    referer = f"https://user.qzone.qq.com/{uin}"

    # 构造发布参数
    publish_data = {
        "syn_tweet_verson": "1", "paramstr": "1", "pic_template": "",
        "richtype": "", "richval": "",
        "special_url": "", "subrichtype": "",
        "pic_bo": "", "who": "1",
        "con": content,
        "feedversion": "1", "ver": "1", "ugc_right": str(visible),
        "to_sign": "0", "hostuin": uin,
        "code_version": "1", "format": "fs",
        "qzreferrer": referer,
    }

    # 如果有图片，上传并设置参数
    if image_paths:
        llocs = []
        bos = []
        for path in image_paths:
            try:
                img_info = await _upload_image(connector, path, cookies, g_tk, uin, skey, p_skey)
                llocs.append(img_info["lloc"])
                if img_info["bo"]:
                    bos.append(img_info["bo"])
                logger.info(f"[QZone] 图片上传成功: {path}")
            except Exception as e:
                logger.error(f"[QZone] 图片上传失败: {path} - {e}")
                return {"success": False, "code": -1, "message": f"图片上传失败: {e}"}

        if llocs:
            # richval: ,<lloc>,<lloc>,<lloc>,,<w>,<h>,,<w>,<h>
            # 这里用 0,0 让服务器自动处理尺寸
            parts = [""]
            for lloc in llocs:
                parts.extend([lloc, lloc, lloc])
            parts.extend(["", "0", "0", "", "0", "0"])
            publish_data["richtype"] = "1"
            publish_data["subrichtype"] = "1"
            publish_data["richval"] = ",".join(parts)
            if bos:
                publish_data["pic_bo"] = "\t".join(bos)

    # 发布
    try:
        raw = _http_post(f"{PUBLISH_URL}?g_tk={g_tk}", publish_data, cookies, referer)
    except Exception as e:
        return {"success": False, "code": -1, "message": f"HTTP 请求失败: {e}"}

    result = _parse_jsonp(raw)
    if not result:
        return {"success": False, "code": -1, "message": f"响应解析失败"}

    code = result.get("code")
    if code == 0:
        tid = result.get("t1_tid") or result.get("tid", "")
        logger.info(f"[QZone] 说说发布成功: tid={tid}")
        return {
            "success": True,
            "tid": tid,
            "time": result.get("t1_time", ""),
            "content": result.get("content", content),
            "has_image": bool(image_paths),
        }

    return {
        "success": False,
        "code": code,
        "message": result.get("message") or result.get("msg", "未知错误"),
    }
