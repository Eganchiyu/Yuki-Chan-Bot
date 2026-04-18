# ws_connection.py
import json
import asyncio
import websockets
from typing import Optional, Dict
from config import NAPCAT_WS_URL
from asyncio import Future
from utils.logger import get_logger

logger = get_logger("ws_connection")

class BotConnector:
    def __init__(self, ws_url: str = NAPCAT_WS_URL):
        self.ws_url = ws_url
        self.websocket = None
        self._lock = asyncio.Lock()
        # 新增：用于存放等待响应的 Future 对象
        self._response_futures: Dict[str, Future] = {}

    async def ensure_connection(self):
        """最兼容的版本判断：确保返回一个真正 OPEN 的连接"""
        async with self._lock:
            # 使用 hasattr 进行安全检查，或者直接判断对象是否存在
            # 核心逻辑：如果对象不存在，或者对象的状态不是 OPEN (1)
            is_alive = False
            if self.websocket is not None:
                try:
                    # websockets 库最通用的检查方式是查看其 protocol 状态机
                    # 或者直接检查 connection 状态
                    from websockets.protocol import State
                    is_alive = self.websocket.state == State.OPEN
                except Exception:
                    # 如果找不到 State 枚举，回退到最原始的尝试
                    try:
                        is_alive = not self.websocket.closed
                    except AttributeError:
                        try:
                            is_alive = self.websocket.open
                        except AttributeError:
                            is_alive = False  # 属性全无，视为失效

            if not is_alive:
                if self.websocket is not None:
                    logger.warning("[Network] 检测到连接状态异常，正在重建...")

                self.websocket = await websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=60,
                    close_timeout=10
                )
                logger.info(f"[Network] 全局连接已建立: {self.ws_url}")

            return self.websocket

    async def listen(self):
        """闭环监听：统一接收并分发消息"""
        while True:
            try:
                ws = await self.ensure_connection()
                async for message in ws:
                    data = json.loads(message)

                    # 关键逻辑：检查是否有正在等待这个 echo 的请求
                    echo = data.get("echo")
                    if echo and echo in self._response_futures:
                        future = self._response_futures.pop(echo)
                        if not future.done():
                            future.set_result(data)

                    # 正常的事件流抛出
                    yield data
            except Exception as e:
                logger.error(f"[Network] 监听异常: {e}")
                self.websocket = None
                await asyncio.sleep(3)

    async def close(self):
        """优雅关闭"""
        async with self._lock:
            if self.websocket:
                await self.websocket.close()
                self.websocket = None

    async def send_request(self, action: str, params: dict, echo: str) -> Optional[Dict]:
        try:
            ws = await self.ensure_connection()

            # 1. 注册 Future
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            self._response_futures[echo] = future

            request = {"action": action, "params": params, "echo": echo}
            await ws.send(json.dumps(request))

            try:
                # 2. 等待结果 (这里才需要 await)
                return await asyncio.wait_for(future, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(f"请求 {action} 超时 (echo: {echo})")
                return None
            finally:
                # 3. 无论成功还是超时，都要清理字典
                # pop 是同步操作，不需要 await
                self._response_futures.pop(echo, None)

        except Exception as e:
            logger.error(f"网络异常: {e}")
            self._response_futures.pop(echo, None)
            return None

