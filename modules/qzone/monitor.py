# modules/qzone/monitor.py
"""
QZone 社交监控器

后台常驻任务，定期轮询自己的说说，处理新评论和点赞。
"""

import asyncio
import json
import random
import re
import time
import urllib.request
import urllib.parse
from typing import Optional, List

from utils.http_client import urlopen
from utils.logger import get_logger
from core.reply_format import clean_visible_reply

logger = get_logger("qzone_monitor")

# ── HTTP 工具 ──────────────────────────────────────────────

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

def _compute_g_tk(p_skey: str) -> int:
    h = 5381
    for ch in p_skey:
        h += (h << 5) + ord(ch)
    return h & 0x7FFFFFFF


def _extract_cookie(cookies: str, name: str) -> Optional[str]:
    m = re.search(rf"{name}=([^;]+)", cookies)
    return m.group(1) if m else None


# 认证缓存（同一轮轮询内复用）
_auth_cache = {"cookies": None, "g_tk": None, "uin": None, "ts": 0}


def _parse_jsonp(raw: str) -> Optional[dict]:
    for pat in [r"_preloadCallback\((.*)\);?$", r"frameElement\.callback\((.*)\)", r"\{.*\}"]:
        m = re.search(pat, raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1) if "(" in pat else m.group(0))
            except json.JSONDecodeError:
                pass
    return None


async def _get_auth(connector, force_refresh=False) -> tuple:
    """获取认证信息: (cookies, g_tk, uin)。30秒内缓存复用。

    这里只需要 call()，网关内部已有常驻 reader 负责收响应，不必（也不能）
    自己再迭代一次 listen()：那样会抢主监听的事件，finally 里的 close()
    还会把主连接关掉。
    """
    import time as _time
    now = _time.time()
    if not force_refresh and _auth_cache["cookies"] and now - _auth_cache["ts"] < 30:
        return _auth_cache["cookies"], _auth_cache["g_tk"], _auth_cache["uin"]

    cookie_resp = await connector.get_cookies("user.qzone.qq.com")
    if not cookie_resp or cookie_resp.get("status") != "ok":
        raise RuntimeError(f"Cookie 获取失败: {(cookie_resp or {}).get('message', '')}")
    cookies = cookie_resp["data"]["cookies"]
    p_skey = _extract_cookie(cookies, "p_skey")
    if not p_skey:
        raise RuntimeError("Cookie 缺少 p_skey")
    g_tk = _compute_g_tk(p_skey)

    login_resp = await connector.get_login_info()
    if not login_resp or login_resp.get("status") != "ok":
        raise RuntimeError("登录信息获取失败")
    uin = str(login_resp["data"]["user_id"])

    _auth_cache.update({"cookies": cookies, "g_tk": g_tk, "uin": uin, "ts": now})
    return cookies, g_tk, uin


def _http_get(url: str, params: dict, cookies: str, referer: str) -> str:
    full = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full)
    req.add_header("Cookie", cookies)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", referer)
    return urlopen(req, timeout=15).read().decode("utf-8", errors="replace")


# ── API 封装 ───────────────────────────────────────────────

async def fetch_my_moods(connector, num: int = 10) -> List[dict]:
    """获取自己的说说列表（含评论）。"""
    cookies, g_tk, uin = await _get_auth(connector)
    params = {
        "uin": uin, "ftype": "0", "sort": "0", "pos": "0", "num": str(num),
        "replynum": "20", "g_tk": str(g_tk), "code_version": "1",
        "format": "jsonp", "need_private_comment": "1", "callback": "_preloadCallback",
    }
    url = "https://user.qzone.qq.com/proxy/domain/taotao.qq.com/cgi-bin/emotion_cgi_msglist_v6"
    raw = _http_get(url, params, cookies, f"https://user.qzone.qq.com/{uin}")
    data = _parse_jsonp(raw)
    if not data or data.get("code") != 0:
        logger.warning(f"[QZoneMonitor] 获取说说列表失败: {(data or {}).get('message', '解析失败')}")
        return []
    return data.get("msglist", [])


async def fetch_mood_comments(connector, tid: str, uin: str) -> List[dict]:
    """获取单条说说的评论列表。"""
    cookies, g_tk, _ = await _get_auth(connector)
    # 用 msglist 接口带 replynum 就能拿到评论，不需要单独接口
    # 这里复用 fetch_my_moods 已经够用
    return []


async def fetch_friend_feeds(connector, count: int = 10) -> List[dict]:
    """获取好友动态列表（含图片 URL）。"""
    import re as _re
    cookies, g_tk, uin = await _get_auth(connector)
    params = {
        "uin": uin, "scope": "0", "view": "1", "filter": "all",
        "flag": "1", "applist": "all", "pagenum": "1", "count": str(count),
        "format": "json", "g_tk": str(g_tk), "useutf8": "1", "outputhtmlfeed": "1",
    }
    url = "https://user.qzone.qq.com/proxy/domain/ic2.qzone.qq.com/cgi-bin/feeds/feeds3_html_more"
    raw = _http_get(url, params, cookies, f"https://user.qzone.qq.com/{uin}")

    items = raw.split("{ver:")
    feeds = []
    for item_raw in items[1:]:
        def get(field):
            m = _re.search(rf"{field}:\s*'([^']*)'", item_raw)
            if not m:
                m = _re.search(rf"{field}:\s*(\d+)", item_raw)
            return m.group(1) if m else ""

        appid = get("appid")
        if appid == "6600":
            continue

        # 提取文本内容
        content = ""
        html_m = _re.search(r"html:'(.*?)'(?:,|\s*\})", item_raw, _re.DOTALL)
        if html_m:
            html_c = html_m.group(1)
            html_c = _re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), html_c)
            html_c = html_c.replace('\\"', '"').replace("\\/", "/")
            infos = _re.findall(r'class="f-info[^"]*"[^>]*>(.*?)</div>', html_c, _re.DOTALL)
            texts = [_re.sub(r'<[^>]+>', '', info).strip() for info in infos]
            content = "\n".join(t for t in texts if t)

            # 提取图片 URL（data-originurl 或 src 中的图片）
            image_urls = _re.findall(r'data-originurl="([^"]*)"', html_c)
            if not image_urls:
                image_urls = _re.findall(r'src="(https?://[^"]*(?:photo|pic)[^"]*)"', html_c)
            # 过滤头像和小图标
            image_urls = [u for u in image_urls if "qlogo" not in u and len(u) > 30]
        else:
            image_urls = []

        feeds.append({
            "key": get("key"),
            "appid": appid,
            "opuin": get("opuin"),
            "nickname": get("nickname"),
            "remark": get("remark"),
            "abstime": get("abstime"),
            "feedstime": get("feedstime").strip(),
            "content": content,
            "image_urls": image_urls,
        })

    return feeds


async def describe_image(url: str, connector=None) -> Optional[str]:
    """下载图片并用 vision 模型描述。"""
    try:
        # 下载图片
        req = urllib.request.Request(url)
        req.add_header("User-Agent", UA)
        cookies = None
        if connector:
            try:
                cookie_resp = await connector.get_cookies("user.qzone.qq.com")
                if cookie_resp and cookie_resp.get("status") == "ok":
                    cookies = cookie_resp["data"]["cookies"]
            except Exception:
                pass
        if cookies:
            req.add_header("Cookie", cookies)

        resp = urlopen(req, timeout=10)
        image_data = resp.read()

        # 压缩
        from modules.vision.processor import MemeProcessor
        b64 = MemeProcessor.compress_image(image_data, max_size=512, quality=60)
        if not b64:
            return None

        # vision_chat
        from utils.llm_client import vision_chat
        if not vision_chat:
            return None

        messages = [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": "用一句话简短描述这张图片的内容。不超过20字。"},
            ],
        }]
        result = await vision_chat(messages)
        return result.strip() if result else None

    except Exception as e:
        logger.debug(f"[QZoneMonitor] 图片描述失败: {e}")
        return None


async def post_comment(connector, mood_tid: str, mood_uin: str, content: str) -> bool:
    """对说说发表评论。"""
    from modules.qzone.publisher import _http_post, _parse_jsonp
    cookies, g_tk, my_uin = await _get_auth(connector)

    url = f"https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_re_feeds?&g_tk={g_tk}"
    data = {
        "topicId": f"{mood_uin}_{mood_tid}__1",
        "feedsType": "100",
        "inCharset": "utf-8",
        "outCharset": "utf-8",
        "plat": "qzone",
        "source": "ic",
        "hostUin": mood_uin,
        "isSignIn": "",
        "platformid": "52",
        "uin": my_uin,
        "format": "fs",
        "ref": "feeds",
        "content": content,
        "richval": "",
        "richtype": "",
        "private": "0",
        "paramstr": "1",
        "qzreferrer": f"https://user.qzone.qq.com/{mood_uin}",
    }
    try:
        raw = _http_post(url, data, cookies, f"https://user.qzone.qq.com/{my_uin}")
        result = _parse_jsonp(raw)
        # 成功响应: code=0 或 ret=0
        code = (result or {}).get("code", (result or {}).get("ret", -1))
        if code == 0:
            logger.info(f"[QZoneMonitor] 评论成功: tid={mood_tid}")
            return True
        msg = (result or {}).get("msg", "") or (result or {}).get("message", "")
        logger.warning(f"[QZoneMonitor] 评论失败: code={code} msg={msg}")
        return False
    except Exception as e:
        logger.error(f"[QZoneMonitor] 评论异常: {e}")
        return False


async def like_mood(connector, mood_uin: str, uni_key: str, cur_key: str) -> bool:
    """点赞一条说说。"""
    from modules.qzone.publisher import _http_post, _parse_jsonp
    cookies, g_tk, my_uin = await _get_auth(connector)

    url = f"https://user.qzone.qq.com/proxy/domain/w.qzone.qq.com/cgi-bin/likes/internal_dolike_app?g_tk={g_tk}"
    data = {
        "qzreferrer": f"https://user.qzone.qq.com/{mood_uin}",
        "opuin": my_uin, "unikey": uni_key, "curkey": cur_key,
        "appid": "311", "from": "1", "typeid": "0",
        "abstime": str(int(time.time())),
        "fid": "", "active": "0", "format": "json", "fupdate": "1",
    }
    try:
        raw = _http_post(url, data, cookies, f"https://user.qzone.qq.com/{my_uin}")
        result = _parse_jsonp(raw)
        if result and result.get("code") == 0:
            logger.info(f"[QZoneMonitor] 点赞成功: {mood_uin}")
            return True
        logger.warning(f"[QZoneMonitor] 点赞失败: {(result or {}).get('message', '')}")
        return False
    except Exception as e:
        logger.error(f"[QZoneMonitor] 点赞异常: {e}")
        return False


# ── 监控主类 ───────────────────────────────────────────────

class QZoneSocialMonitor:
    """
    QZone 社交监控器。

    职责：
    1. 定期轮询自己的说说，检测新评论
    2. 对新评论判断是否需要回复
    3. 用 LLM 生成回复内容
    4. 回赞新点赞的用户
    """

    def __init__(self, connector, engine=None, memory_rag=None):
        self.connector = connector
        self.engine = engine
        self.memory_rag = memory_rag
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._can_comment = False
        self._my_uin = ""  # 缓存自己的 uin

    async def start(self):
        """启动后台监控。"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("[QZoneMonitor] 社交监控已启动")

    async def stop(self):
        """停止监控。"""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self):
        """主轮询循环。"""
        await asyncio.sleep(30)
        logger.info("[QZoneMonitor] 开始轮询循环")

        # 缓存自己的 uin
        try:
            _, _, self._my_uin = await _get_auth(self.connector)
        except Exception:
            pass

        # 启动时验证评论 API 是否可用
        await self._validate_comment_api()

        while self._running:
            try:
                await self._poll_cycle()
            except Exception as e:
                logger.error(f"[QZoneMonitor] 轮询异常: {e}")
            interval = random.randint(180, 300)
            await asyncio.sleep(interval)

    async def _validate_comment_api(self):
        """启动时测试评论 API 是否可用。"""
        try:
            moods = await fetch_my_moods(self.connector, num=1)
            if not moods:
                logger.info("[QZoneMonitor] 无说说，跳过评论验证")
                return

            tid = moods[0].get("tid", "")
            uin = str(moods[0].get("uin", ""))
            if not tid:
                return

            # 直接调用 post_comment 测试
            success = await post_comment(self.connector, tid, uin, "测试")
            if success:
                self._can_comment = True
                logger.info("[QZoneMonitor] ✅ 评论 API 可用，已开启评论功能")
            else:
                self._can_comment = False
                logger.warning("[QZoneMonitor] ❌ 评论 API 不可用，评论功能已关闭")

        except Exception as e:
            self._can_comment = False
            logger.warning(f"[QZoneMonitor] 评论 API 验证失败: {e}，评论功能已关闭")

    async def _poll_cycle(self):
        """单次轮询：自己的说说 + 好友动态。"""
        from modules.qzone.state import (
            load_state, save_state, update_last_poll,
            mark_comments_seen, mark_user_liked, get_post_context,
        )

        state = load_state()
        tracked_tids = set(state.get("posts", {}).keys())

        # ── 自己的说说：检测新评论 ──
        moods = await fetch_my_moods(self.connector, num=10)
        if moods:
            for mood in moods:
                tid = mood.get("tid", "")
                if not tid:
                    continue
                comments = mood.get("commentlist", []) or []
                cmtnum = mood.get("cmtnum", 0)

                if tid not in tracked_tids and cmtnum > 0:
                    from modules.qzone.state import register_post
                    register_post(state, tid, mood.get("content", "")[:100])
                    tracked_tids.add(tid)

                if tid not in tracked_tids:
                    continue

                post_state = state.get("posts", {}).get(tid, {})
                seen = set(post_state.get("seen_comments", []))
                new_comments = [c for c in comments if c.get("tid") and c["tid"] not in seen]

                if new_comments:
                    logger.info(f"[QZoneMonitor] 自己说说 {tid[:16]}... 有 {len(new_comments)} 条新评论")
                    await self._handle_new_comments(state, tid, mood, new_comments)

        # ── 好友动态：选择性点赞/评论 ──
        try:
            from modules.qzone.state import add_seen_feed_keys
            feeds = await fetch_friend_feeds(self.connector, count=10)
            if feeds:
                seen_keys = set(state.get("seen_feed_keys", []))
                new_feeds = [f for f in feeds if f["key"] and f["key"] not in seen_keys]
                if new_feeds:
                    logger.info(f"[QZoneMonitor] 发现 {len(new_feeds)} 条新好友动态")
                    await self._handle_friend_feeds(new_feeds)
                    new_keys = [f["key"] for f in new_feeds]
                    add_seen_feed_keys(state, new_keys)
        except Exception as e:
            logger.warning(f"[QZoneMonitor] 好友动态获取失败: {e}")

        update_last_poll(state)
        logger.debug("[QZoneMonitor] 轮询完成")

    async def _handle_friend_feeds(self, feeds: list):
        """处理好友动态：有图片时先描述，再决策互动。"""
        for feed in feeds:
            nickname = feed.get("remark") or feed.get("nickname", "")
            content = feed.get("content", "")
            opuin = feed.get("opuin", "")
            key = feed.get("key", "")
            image_urls = feed.get("image_urls", [])

            if not content and not image_urls:
                continue

            # 有图片时，用 vision 描述图片
            image_desc = ""
            if image_urls:
                desc = await describe_image(image_urls[0], self.connector)
                if desc:
                    image_desc = desc
                    logger.info(f"[QZoneMonitor] 图片描述: {nickname} - {desc}")

            # 合并文本+图片描述作为完整内容
            full_content = content
            if image_desc:
                full_content = f"{content}\n[图片: {image_desc}]" if content else f"[图片: {image_desc}]"

            actions = await self._decide_feed_action(nickname, full_content)

            if "like" in actions:
                uni_key = f"http://user.qzone.qq.com/{opuin}/mood/{key}"
                success = await like_mood(self.connector, opuin, uni_key, uni_key)
                if success:
                    logger.info(f"[QZoneMonitor] 已点赞 {nickname}")

            if "comment" in actions and self._can_comment:
                comment_text = await self._generate_feed_comment(nickname, full_content)
                if comment_text:
                    success = await post_comment(self.connector, key, opuin, comment_text)
                    if success:
                        logger.info(f"[QZoneMonitor] 已评论 {nickname}: {comment_text[:30]}")

            if not actions:
                logger.debug(f"[QZoneMonitor] 跳过 {nickname} 的动态")

    async def _decide_feed_action(self, nickname: str, content: str) -> list:
        """LLM 决定对好友动态的互动方式。返回动作列表，如 ["like"] 或 ["like", "comment"]。"""
        if not self.engine:
            return []

        from core.prompts import get_base_setting
        base = get_base_setting()

        prompt = (
            "看到好友的 QQ 空间动态，决定怎么互动。\n"
            "你可以选择一个或多个动作（用逗号分隔）：\n"
            "- like：点赞（日常鼓励）\n"
            "- comment：评论（你有话说）\n"
            "- skip：什么都不做（不感兴趣）\n\n"
            f"{nickname} 的动态：{content[:100]}\n\n"
            "回答示例：like,comment 或 like 或 skip"
        )

        try:
            from utils.llm_client import llm_chat
            messages = [
                {"role": "system", "content": f"{base}\n\n你是互动决策器。回答一个或多个动作，逗号分隔。"},
                {"role": "user", "content": prompt},
            ]
            result = await llm_chat(messages, temperature=0.3, max_tokens=20)
            if result:
                answer = result.strip().lower()
                actions = []
                if "comment" in answer:
                    actions.append("comment")
                if "like" in answer:
                    actions.append("like")
                return actions
        except Exception as e:
            logger.error(f"[QZoneMonitor] 互动决策失败: {e}")

        return []

    async def _generate_feed_comment(self, nickname: str, content: str) -> Optional[str]:
        """LLM 生成对好友动态的评论。"""
        if not self.engine:
            return None

        from core.prompts import get_base_setting
        base = get_base_setting()

        prompt = (
            "看到好友的动态，生成一条简短的评论。\n"
            "评论要自然、不油腻，1-2句话。\n\n"
            f"{nickname} 的动态：{content[:100]}\n\n"
            "只输出评论内容，不要引号。"
        )

        try:
            from utils.llm_client import llm_chat
            messages = [
                {"role": "system", "content": f"{base}\n\n你正在给好友的 QQ 空间动态写评论。"},
                {"role": "user", "content": prompt},
            ]
            reply = await llm_chat(messages, temperature=0.7, max_tokens=60)
            if reply:
                return reply.strip().strip('"').strip("'")[:80]
        except Exception as e:
            logger.error(f"[QZoneMonitor] 评论生成失败: {e}")
        return None

    async def _handle_new_comments(self, state: dict, tid: str, mood: dict, new_comments: list):
        """处理新评论：合并评论列表，判断是否回复，最多回复一条。"""
        from modules.qzone.state import mark_comments_seen, get_post_context

        post_ctx = get_post_context(state, tid)
        source_chat = post_ctx.get("source_chat", "")
        chat_context = post_ctx.get("chat_context", [])
        mood_content = mood.get("content", "")
        mood_uin = str(mood.get("uin", ""))

        # 过滤掉自己的评论
        filtered = []
        for c in new_comments:
            commenter_uin = str(c.get("uin", ""))
            if commenter_uin == mood_uin or commenter_uin == self._my_uin:
                continue
            filtered.append(c)

        # 标记所有评论为已处理
        all_ctids = [c.get("tid", 0) for c in new_comments if c.get("tid")]
        mark_comments_seen(state, tid, all_ctids)

        if not filtered or not self._can_comment:
            return

        # 合并评论为一段上下文
        comment_summary = "；".join(
            f"{c.get('name', '?')}: {c.get('content', '')[:40]}"
            for c in filtered
        )

        # 判断是否值得回复
        should_reply = await self._should_reply(mood_content, comment_summary, "评论列表")
        if not should_reply:
            logger.info(f"[QZoneMonitor] 决定不回复说说 {tid[:16]}... 的评论")
            return

        # 生成一条回复
        reply = await self._generate_reply(
            mood_content, comment_summary, "评论列表", source_chat, chat_context,
        )
        if reply:
            success = await post_comment(self.connector, tid, mood_uin, reply)
            if success:
                logger.info(f"[QZoneMonitor] 已回复说说 {tid[:16]}...: {reply[:30]}")

    async def _should_reply(self, mood_content: str, comment_content: str,
                           commenter_name: str) -> bool:
        """用 LLM 判断是否应该回复这条评论。"""
        if not self.engine:
            return True

        from core.prompts import get_base_setting
        base = get_base_setting()

        prompt = (
            "现在有人评论了你的 QQ 空间说说，判断是否应该回复。\n"
            "回复规则：\n"
            "- 直接提问、@你、寻求互动 → 回复\n"
            "- 有趣的、有内容的评论 → 回复\n"
            "- 纯表情、'赞'、'好看'等无实质内容 → 不回复\n"
            "- 广告、无关内容 → 不回复\n\n"
            f"你的说说：{mood_content[:80]}\n"
            f"{commenter_name} 的评论：{comment_content[:80]}\n\n"
            "只回答 YES 或 NO。"
        )

        try:
            from utils.llm_client import llm_chat
            messages = [
                {"role": "system", "content": f"{base}\n\n你是回复决策器，只回答 YES 或 NO。"},
                {"role": "user", "content": prompt},
            ]
            result = await llm_chat(messages, temperature=0.1, max_tokens=5)
            if result:
                answer = result.strip().upper()
                return "YES" in answer
        except Exception as e:
            logger.error(f"[QZoneMonitor] 决策 LLM 调用失败: {e}")

        return False

    async def _generate_reply(self, mood_content: str, comment_content: str,
                              commenter_name: str, source_chat: str = "",
                              chat_context: list = None) -> Optional[str]:
        """用 LLM 生成评论回复。"""
        if not self.engine:
            return None

        from core.prompts import get_base_setting
        base = get_base_setting()

        system_prompt = (
            f"{base}\n\n"
            "现在有人评论了你的 QQ 空间说说，你需要生成一条自然、简短的回复。\n"
            "回复要符合你的性格，1-2 句话以内。"
        )

        context_parts = [f"你的说说内容：{mood_content}"]
        if chat_context:
            context_parts.append(f"发布说说时的群聊上下文：\n" + "\n".join(chat_context[-5:]))
        context_parts.append(f"{commenter_name} 的评论：{comment_content}")

        # 尝试从日记 RAG 检索相关记忆
        rag_context = ""
        if self.memory_rag:
            try:
                memories = self.memory_rag.search(comment_content, top_k=2)
                if memories:
                    rag_context = "\n相关记忆：" + "；".join(memories[:2])
            except Exception:
                pass

        if rag_context:
            context_parts.append(rag_context)

        user_prompt = "\n".join(context_parts)

        try:
            from utils.llm_client import llm_chat
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            reply = await llm_chat(messages, temperature=0.7, max_tokens=100)
            if reply:
                reply = reply.strip().strip('"').strip("'")
                # 清理可能的格式（含括号写错的 layout 变体）
                reply = clean_visible_reply(reply)
                return reply[:100]  # 限制长度
        except Exception as e:
            logger.error(f"[QZoneMonitor] LLM 生成回复失败: {e}")

        return None


# ── 便捷启动函数 ────────────────────────────────────────────

_monitor_instance: Optional[QZoneSocialMonitor] = None


async def ensure_monitor_started(connector, engine=None, memory_rag=None):
    """确保监控器已启动（幂等）。"""
    global _monitor_instance
    if _monitor_instance and _monitor_instance._running:
        return _monitor_instance
    _monitor_instance = QZoneSocialMonitor(connector, engine, memory_rag)
    await _monitor_instance.start()
    return _monitor_instance


def notify_new_post(tid: str, content: str, source_chat: str = "", chat_context: list = None):
    """外部调用：通知监控器记录一条新发布的说说。"""
    from modules.qzone.state import load_state, save_state, register_post
    state = load_state()
    register_post(state, tid, content, source_chat, chat_context)
    logger.info(f"[QZoneMonitor] 已记录新说说 tid={tid}")
