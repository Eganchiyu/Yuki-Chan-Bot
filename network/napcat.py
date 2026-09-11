# network/napcat.py
"""NapCat（OneBot 11）接入层：连接、帧路由、出站动作，统一在这一个文件里。

边界：只做传输 + 协议，不 import core / modules 的业务代码。

出站：
    await gateway.send(chat_id, "文本", mode="group")
    await gateway.send_local_image / send_local_file / send_local_voice(...)
    await gateway.send_poke(user_id, group_id)
    await gateway.download_file(file_id) / get_cookies() / get_login_info()
    await gateway.call("get_msg", {"message_id": 1})      # 通用动作原语

入站：
    async for event in gateway.listen(): ...              # 只产出事件帧

并发模型（关键）：一个常驻 reader 协程独占 WebSocket 读端，
    * echo 命中 _pending   -> 唤醒对应的 call()
    * 带 post_type 的帧    -> 投进 _events 队列，供 listen() 消费
因此"发"不再依赖"有人正在收"，API 响应也不会混进事件流。
"""
import asyncio
import base64
import json
import os
import re
import uuid
from datetime import datetime
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import websockets

from config import cfg
from utils.http_client import create_ssl_context
from utils.logger import get_logger

logger = get_logger("napcat")

# 下载文件统一落到 workspace/，小女仆可直接访问
DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workspace")

RECONNECT_DELAY = 3.0      # 断线后的重连间隔（秒）
EVENT_QUEUE_MAX = 2000     # 入站事件队列上限，满了丢最旧的一条
DEFAULT_TIMEOUT = 5.0      # call() 默认等待响应的秒数


def _is_private(mode: str) -> bool:
    return mode in {"private", "master_private"}


# ==================== CQ 码文本工具（纯函数，无 I/O） ====================

def smart_truncate(content, max_len=None, suffix="..."):
    """超长消息智能截断，保持 CQ 码完整。"""
    max_len = max_len or cfg.MAX_MESSAGE_LENGTH
    if len(content) <= max_len:
        return content

    logger.info(f"[NapCat] 检测到超长消息 ({len(content)} 字符)")
    parts = re.split(r'(\[CQ:.*?\])', content)
    result = []
    for part in parts:
        if not part:
            continue
        if part.startswith("[CQ:") and part.endswith("]"):
            result.append(part)
        elif len(part) > 100:
            result.append(part[:40] + suffix + part[-40:])
        else:
            result.append(part)

    content = "".join(result)
    logger.info(f"[NapCat] 压缩后长度: {len(content)} 字符")
    return content


def replace_other_cq_codes(text: str) -> str:
    """多媒体码换成占位符，保留可继续处理的 ID。"""
    text = re.sub(r'\[CQ:image[^\]]*\]', '[图片]', text)
    text = re.sub(r'\[CQ:face[^\]]*\]', '[表情]', text)
    text = re.sub(r'\[CQ:record,file=([^\],]+)[^\]]*\]', r'[语音:file_id=\1]', text)
    text = re.sub(r'\[CQ:video,[^\]]*(?:file|url)=([^,\]]+)[^\]]*\]', r'[视频:file_id=\1]', text)
    text = re.sub(r'\[CQ:video[^\]]*\]', '[视频]', text)
    text = re.sub(r'\[CQ:file,id=([^],]+)[^\]]*\]', r'[文件:file_id=\1]', text)
    text = re.sub(r'\[CQ:file,file=([^],]+)[^\]]*\]', r'[文件:file_id=\1]', text)
    text = re.sub(r'\[CQ:forward,id=([^,\]]+)[^\]]*\]', r'[合并转发:id=\1]', text)
    text = re.sub(r'\[CQ:json[^\]]*\]', '[小程序]', text)
    text = re.sub(r'\[CQ:xml[^\]]*\]', '[XML富文本]', text)
    return text


def extract_at_uids(text: str) -> list:
    """取出文本里所有被 @ 的 QQ（含 all）。"""
    return re.findall(r'\[CQ:at,qq=(\d+|all)\]', text)


def replace_at_placeholder(text: str, qq, nickname: str) -> str:
    return re.sub(rf'\[CQ:at,qq={qq}[^\]]*\]', f"@{nickname}", text)


def extract_reply_ids(text: str) -> list:
    return re.findall(r'\[CQ:reply,id=(\d+)\]', text)


def replace_reply_placeholder(data) -> str:
    """把被引用消息渲染成一行可读文本。"""
    if not data:
        logger.error("[NapCat] 引用历史回复消息解析失败")
        return "【引用不明历史消息】"
    sender = (data.get("sender") or {}).get("nickname", "人")
    text = re.sub(r'\[CQ:.*?\]', '', data.get("raw_message", ""))
    return f"【引用{sender}的消息: {smart_truncate(text)}】"


def _normalize_forward(data) -> list:
    """兼容不同 NapCat 版本合并转发响应的嵌套层级。"""
    if isinstance(data, dict):
        for key in ("messages", "message", "content"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        if isinstance(data.get("data"), dict):
            return _normalize_forward(data["data"])
    if isinstance(data, list):
        return data
    return []


class NapCatGateway:
    """NapCat 正向 WebSocket 的唯一持有者。"""

    def __init__(self, ws_url: str = None, ws_token: str = None):
        self.ws_url = ws_url or cfg.NAPCAT_WS_URL
        self.ws_token = cfg.NAPCAT_WS_TOKEN if ws_token is None else ws_token
        self.websocket = None
        self.stats = {
            "frames": 0, "events": 0, "dropped": 0,
            "reconnects": 0, "calls": 0, "call_failures": 0,
        }

        self._connect_lock = asyncio.Lock()
        self._pending: dict = {}                      # echo -> Future
        self._events: asyncio.Queue = asyncio.Queue()
        self._member_cache: dict = {}                 # (group_id, user_id) -> 群成员信息
        self._reader_task = None
        self._closed = False

        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    # ==================== 连接 ====================

    def _url_with_token(self) -> str:
        """token 拼到 access_token 查询参数上。"""
        if not self.ws_token:
            return self.ws_url
        parsed = urlparse(self.ws_url)
        query = parse_qs(parsed.query)
        query.setdefault("access_token", [self.ws_token])
        return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))

    @staticmethod
    def _is_open(ws) -> bool:
        if ws is None:
            return False
        try:
            from websockets.protocol import State
        except Exception:
            return bool(getattr(ws, "open", False))
        return getattr(ws, "state", None) == State.OPEN

    async def _connect(self):
        """返回一个真正 OPEN 的连接；失效则重建。"""
        async with self._connect_lock:
            if self._is_open(self.websocket):
                return self.websocket
            if self.websocket is not None:
                logger.warning("[NapCat] 连接已失效，正在重建")
                self.websocket = None

            url = self._url_with_token()
            kwargs = {"ssl": create_ssl_context()} if urlparse(url).scheme == "wss" else {}
            self.websocket = await websockets.connect(
                url, ping_interval=20, ping_timeout=60, close_timeout=10, **kwargs
            )
            logger.info(f"[NapCat] 连接已建立: {self.ws_url}")
            return self.websocket

    async def close(self):
        self._closed = True
        if self._reader_task is not None:
            self._reader_task.cancel()
            self._reader_task = None
        if self.websocket is not None:
            try:
                await self.websocket.close()
            except Exception:
                pass
            self.websocket = None

    # ==================== 读端：常驻 reader + 帧路由 ====================

    def _ensure_reader(self):
        if self._reader_task is None or self._reader_task.done():
            self._reader_task = asyncio.create_task(self._reader())

    async def _reader(self):
        """唯一消费 WebSocket 读端的地方；自身负责重连，不向外抛异常。"""
        while not self._closed:
            try:
                ws = await self._connect()
                async for raw in ws:
                    self._route(raw)
                logger.warning("[NapCat] 连接被对端关闭")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"[NapCat] 读取中断: {exc}")

            # 正常关闭与异常走同一条重连路径，避免对端秒关时热循环
            self.stats["reconnects"] += 1
            self.websocket = None
            if not self._closed:
                await asyncio.sleep(RECONNECT_DELAY)

    def _route(self, raw):
        """同步路由一帧：响应 -> Future，事件 -> 队列，其它 -> 丢弃。绝不阻塞读端。"""
        try:
            frame = json.loads(raw)
        except (TypeError, ValueError):
            logger.debug(f"[NapCat] 非法帧已忽略: {str(raw)[:200]}")
            return
        self.stats["frames"] += 1

        echo = frame.get("echo")
        if echo is not None:
            future = self._pending.pop(echo, None)
            if future is not None and not future.done():
                future.set_result(frame)
                return
            if "post_type" not in frame:          # 超时后才回来的响应
                logger.debug(f"[NapCat] 迟到的响应已忽略: echo={echo}")
                return

        if "post_type" not in frame:
            logger.debug(f"[NapCat] 未知帧已忽略: {str(frame)[:200]}")
            return

        self.stats["events"] += 1
        try:
            self._events.put_nowait(frame)
        except asyncio.QueueFull:
            self._events.get_nowait()             # 丢最旧的，保证读端不被拖住
            self._events.put_nowait(frame)
            self.stats["dropped"] += 1

    async def listen(self):
        """入站事件流（响应帧不会出现在这里）。只应由一个消费者迭代。"""
        self._ensure_reader()
        while not self._closed:
            yield await self._events.get()

    # ==================== 请求-响应原语 ====================

    async def call(self, action: str, params: dict, timeout: float = DEFAULT_TIMEOUT):
        """发送一个 OneBot 动作并等待它的响应；超时或异常返回 None。"""
        self.stats["calls"] += 1
        echo = f"{action}_{uuid.uuid4().hex[:8]}"
        future = asyncio.get_running_loop().create_future()
        self._pending[echo] = future
        try:
            self._ensure_reader()
            ws = await self._connect()
            await ws.send(json.dumps({"action": action, "params": params, "echo": echo}, ensure_ascii=False))
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self.stats["call_failures"] += 1
            logger.warning(f"[NapCat] {action} 等待响应超时（{timeout}s）")
            return None
        except Exception as exc:
            self.stats["call_failures"] += 1
            logger.error(f"[NapCat] {action} 调用失败: {exc}")
            return None
        finally:
            self._pending.pop(echo, None)

    # ==================== 出站动作 ====================

    async def send(self, chat_id, message, mode="private"):
        """发送文本或 CQ 码。流式回复走这里：发完即返回，不等响应。"""
        is_private = _is_private(mode)
        action = "send_private_msg" if is_private else "send_group_msg"
        params = {"message": message, "user_id" if is_private else "group_id": int(chat_id)}
        for attempt in range(cfg.MAX_RETRIES):
            try:
                ws = await self._connect()
                await ws.send(json.dumps({"action": action, "params": params}, ensure_ascii=False))
                return
            except Exception as exc:
                logger.error(f"[NapCat] 发送失败（第 {attempt + 1} 次）: {exc}")
                self.websocket = None
                if attempt == cfg.MAX_RETRIES - 1:
                    raise
                await asyncio.sleep(1)

    async def send_local_image(self, chat_id, local_path, mode="private"):
        await self.send(chat_id, f"[CQ:image,file=file:///{os.path.abspath(local_path)}]", mode=mode)

    async def send_local_file(self, chat_id, local_path, mode="private"):
        await self.send(chat_id, f"[CQ:file,file=file:///{os.path.abspath(local_path)}]", mode=mode)

    async def send_local_voice(self, chat_id, local_path, mode="group"):
        await self.send(chat_id, f"[CQ:record,file=file:///{os.path.abspath(local_path)}]", mode=mode)

    async def send_poke(self, user_id, group_id):
        """戳一戳（仅群聊）。返回 NapCat 响应字典。"""
        logger.info(f"[NapCat] 发送戳一戳: user={user_id}, group={group_id}")
        result = await self.call("send_poke", {"user_id": int(user_id), "group_id": int(group_id)})
        if result is None:
            logger.warning("[NapCat] 戳一戳请求超时或失败")
            return {"status": "failed", "message": "请求超时"}
        logger.info(f"[NapCat] 戳一戳结果: status={result.get('status')} {result.get('message', '')}")
        return result

    # ==================== 文件与登录信息 ====================

    async def get_file(self, file_id: str):
        """按 file_id 取文件信息（可能含 base64 / url / 本地路径）。"""
        return await self.call("get_file", {"file_id": file_id})

    async def download_file(self, file_id: str, filename: str = None) -> dict:
        """按 file_id 取回文件并落到 workspace/。

        返回 {"success", "file_path", "filename", "error"}；只拿到 URL 时返回 url 字段。
        """
        result = await self.get_file(file_id) or {}
        if result.get("status") != "ok":
            return {"success": False, "file_path": None, "filename": None,
                    "error": result.get("message", "获取文件失败")}

        data = result.get("data") or {}
        content = None
        if data.get("base64"):
            try:
                content = base64.b64decode(data["base64"])
                logger.info(f"[NapCat] 从 base64 解码文件，大小 {len(content)} bytes")
            except Exception as exc:
                logger.error(f"[NapCat] base64 解码失败: {exc}")

        local_path = data.get("file")
        if content is None and local_path and os.path.exists(local_path):
            try:
                with open(local_path, "rb") as handle:
                    content = handle.read()
                logger.info(f"[NapCat] 从本地路径读取文件: {local_path}")
            except Exception as exc:
                logger.error(f"[NapCat] 读取本地文件失败: {exc}")

        name = filename or data.get("file_name") or f"file_{datetime.now():%Y%m%d_%H%M%S}_{str(file_id)[:8]}"

        if content is None:
            if data.get("url"):
                return {"success": True, "file_path": None, "filename": name,
                        "url": data["url"], "error": None}
            return {"success": False, "file_path": None, "filename": None, "error": "无法获取文件内容"}

        save_path = os.path.join(DOWNLOAD_DIR, name)
        try:
            with open(save_path, "wb") as handle:
                handle.write(content)
        except Exception as exc:
            logger.error(f"[NapCat] 保存文件失败: {exc}")
            return {"success": False, "file_path": None, "filename": None, "error": f"保存文件失败: {exc}"}

        logger.info(f"[NapCat] 文件已保存: {save_path}")
        return {"success": True, "file_path": os.path.abspath(save_path), "filename": name, "error": None}

    async def get_cookies(self, domain: str = "user.qzone.qq.com"):
        """取指定域名的 Cookie（含 p_skey / bkn 供 QQ 空间使用）。"""
        return await self.call("get_cookies", {"domain": domain})

    async def get_login_info(self):
        """取当前登录账号信息（user_id、nickname）。"""
        return await self.call("get_login_info", {})

    # ==================== 群 / 成员 / 消息查询 ====================

    async def get_member_info(self, group_id, user_id):
        """群成员信息（含群名片 card），进程内缓存。"""
        key = (str(group_id), str(user_id))
        if key in self._member_cache:
            return self._member_cache[key]

        resp = await self.call("get_group_member_info", {
            "group_id": int(group_id) if str(group_id).isdigit() else group_id,
            "user_id": int(user_id) if str(user_id).isdigit() else user_id,
            "no_cache": False,
        })
        data = resp.get("data") if resp and resp.get("retcode") == 0 else None
        if isinstance(data, dict):
            self._member_cache[key] = data
        return data

    async def get_member_name(self, group_id, user_id) -> str:
        """群名片优先，其次昵称。"""
        if str(user_id) == "all":
            return "全体成员"
        info = await self.get_member_info(group_id, user_id)
        if info:
            name = info.get("card") or info.get("nickname")
            if name:
                return name
        return f"用户{user_id}"

    async def get_msg(self, message_id):
        """取单条消息（用于解析回复引用）。"""
        resp = await self.call("get_msg", {"message_id": int(message_id)})
        return resp.get("data") if resp and resp.get("status") == "ok" else None

    async def get_forward_messages(self, forward_id) -> tuple:
        """取合并转发内容。NapCat 各版本参数名不同，三套依次尝试。

        返回 (消息列表, 原始响应)，两者都可能是空的。
        """
        last = None
        for params in ({"id": forward_id}, {"message_id": forward_id}, {"forward_id": forward_id}):
            last = await self.call("get_forward_msg", params, timeout=60)
            if last and last.get("status") == "ok":
                messages = _normalize_forward(last.get("data"))
                if messages:
                    return messages, last
        return [], last

    async def get_group_meta(self, group_id) -> dict:
        """群名与群备注（两个 action 二选一，取决于 NapCat 版本）。"""
        meta = {"group_id": str(group_id), "group_name": f"群聊 {group_id}", "group_remark": ""}
        for action in ("get_group_detail_info", "get_group_info"):
            resp = await self.call(action, {"group_id": int(group_id)}, timeout=5)
            data = resp.get("data") if resp else None
            if isinstance(data, dict):
                meta["group_name"] = data.get("group_name") or meta["group_name"]
                meta["group_remark"] = data.get("group_remark") or meta["group_remark"]
                return meta
        return meta

    async def parse_cq_codes(self, text: str, group_id) -> str:
        """把 @ 与回复 CQ 码替换成可读文本（图片等交给上层处理）。"""
        for mid in dict.fromkeys(extract_reply_ids(text)):
            text = text.replace(f"[CQ:reply,id={mid}]", replace_reply_placeholder(await self.get_msg(mid)))
        for uid in dict.fromkeys(extract_at_uids(text)):
            text = replace_at_placeholder(text, uid, await self.get_member_name(group_id, uid))
        return replace_other_cq_codes(text)
