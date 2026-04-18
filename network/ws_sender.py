import json
import os
import asyncio
from config import MAX_RETRIES
from network.ws_connection import BotConnector
from utils.logger import get_logger

logger = get_logger("ws_sender")

class MessageSender:
    def __init__(self, connector: BotConnector):
        self.connector = connector

    async def send(self, chat_id, message, mode="private"):
        """闭环发送：失败自动触发重连"""
        for attempt in range(MAX_RETRIES):
            try:
                ws = await self.connector.ensure_connection()
                action = "send_private_msg" if mode == "private" else "send_group_msg"
                params = {
                    "message": message,
                    "user_id" if mode == "private" else "group_id": int(chat_id)
                }
                await ws.send(json.dumps({"action": action, "params": params}))
                return # 发送成功，跳出
            except Exception as e:
                logger.error(f"[Sender] 发送失败 (尝试 {attempt+1}): {e}")
                self.connector.websocket = None # 标记连接失效
                if attempt == MAX_RETRIES - 1: raise e # 如果第二次还失败，抛出错误
                await asyncio.sleep(1)

    async def send_local_image(self, chat_id, local_path, mode="private"):
        abs_path = os.path.abspath(local_path)
        cq_image = f"[CQ:image,file=file:///{abs_path}]"
        await self.send(chat_id, cq_image, mode=mode)

