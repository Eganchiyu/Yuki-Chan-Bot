# network/snowluma.py
"""SnowLuma（OneBot 11）接入层。

SnowLuma 与 NapCat 同为 OneBot 11 正向 WebSocket，收发、帧路由、文件与
CQ 工具全部复用 NapCatGateway，这里只覆盖真正有差异的部分：

    * 鉴权：SnowLuma 读 Authorization: Bearer（NapCat 走 ?access_token=）；
    * 事件：SnowLuma 默认 messageFormat=array，raw_message 缺失时按段还原成
      CQ 文本，保证上层 IncomingMessage 仍拿到统一的 raw_message；
    * 戳一戳：优先 send_poke，未实现时回退 group_poke。

配置沿用 configs/config.yaml 的 connection.napcat_ws_url / napcat_ws_token，
切换后端时把这两项改成 SnowLuma wsServers 的地址与 accessToken 即可
（wsServers 默认 ws://127.0.0.1:3001，role 必须是 Universal，路径固定 /）。

用法（替换 network.napcat.NapCatGateway）：
    from network.snowluma import SnowLumaGateway
    gateway = SnowLumaGateway()

注意：SnowLuma 跑在 Docker / 远端时看不到宿主机路径，send_local_image /
send_local_file 需要把目录挂进容器，或改用 URL。
"""
from urllib.parse import urlparse

import websockets

from network.napcat import NapCatGateway
from utils.http_client import create_ssl_context
from utils.logger import get_logger

logger = get_logger("snowluma")

# CQ 码转义：文本段只转义 & [ ]，参数值额外转义逗号
_CQ_TEXT_ESCAPE = str.maketrans({
    "&": "&amp;",
    "[": "&#91;",
    "]": "&#93;",
})
_CQ_PARAM_ESCAPE = str.maketrans({
    "&": "&amp;",
    "[": "&#91;",
    "]": "&#93;",
    ",": "&#44;",
})


def segments_to_cq(segments) -> str:
    """把 OneBot 消息段数组还原成 CQ 码文本。"""
    parts = []
    for seg in segments or []:
        if not isinstance(seg, dict):
            continue
        seg_type = seg.get("type")
        data = seg.get("data") or {}
        if seg_type == "text":
            parts.append(str(data.get("text", "")).translate(_CQ_TEXT_ESCAPE))
            continue
        params = ",".join(
            f"{key}={str(value).translate(_CQ_PARAM_ESCAPE)}"
            for key, value in data.items()
        )
        parts.append(f"[CQ:{seg_type}{',' + params if params else ''}]")
    return "".join(parts)


def ensure_raw_message(event: dict) -> None:
    """SnowLuma 只保证 message 段数组；缺失 raw_message 时就地补齐。"""
    if not isinstance(event, dict):
        return
    if event.get("post_type") not in {"message", "message_sent"}:
        return
    if event.get("raw_message"):
        return

    message = event.get("message")
    if isinstance(message, str):
        event["raw_message"] = message
    elif isinstance(message, list):
        event["raw_message"] = segments_to_cq(message)


class SnowLumaGateway(NapCatGateway):
    """SnowLuma 正向 WebSocket 网关。"""

    async def _connect(self):
        """返回一个真正 OPEN 的连接；鉴权走 Bearer 请求头。"""
        async with self._connect_lock:
            if self._is_open(self.websocket):
                return self.websocket
            if self.websocket is not None:
                logger.warning("[SnowLuma] 连接已失效，正在重建")
                self.websocket = None

            url = self.ws_url
            kwargs = {}
            if self.ws_token:
                kwargs["additional_headers"] = {"Authorization": f"Bearer {self.ws_token}"}
            if urlparse(url).scheme == "wss":
                kwargs["ssl"] = create_ssl_context()

            self.websocket = await websockets.connect(
                url, ping_interval=20, ping_timeout=60, close_timeout=10, **kwargs
            )
            logger.info(f"[SnowLuma] 连接已建立: {self.ws_url}")
            return self.websocket

    async def listen(self):
        """在父类事件流上补齐 raw_message 后再交给上层。"""
        async for event in super().listen():
            ensure_raw_message(event)
            yield event

    async def send_poke(self, user_id, group_id):
        """戳一戳：SnowLuma 的 send_poke 自动路由，失败回退 group_poke。"""
        params = {"user_id": int(user_id), "group_id": int(group_id)}
        result = await self.call("send_poke", params)
        if result and result.get("retcode") == 0:
            return result

        logger.warning("[SnowLuma] send_poke 不可用，回退 group_poke")
        result = await self.call("group_poke", params)
        if result is None:
            return {"status": "failed", "message": "请求超时"}
        return result
