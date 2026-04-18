from typing import Optional, Dict

from network.ws_connection import BotConnector
from utils.logger import get_logger

logger = get_logger("message_meta")


class MetaGetter:
    def __init__(self, connector: BotConnector):
        self.connector = connector

    async def get_user_info(self, user_id: str) -> Optional[Dict]:
        try:
            uid = int(user_id) if user_id.isdigit() else user_id
            response:dict = await self.connector.send_request(
                "get_stranger_info",
                {"user_id": uid, "no_cache": False},
                f"get_user_{user_id}"
            )
            if response and response.get("retcode") == 0:
                return response.get("data")
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
        return None

    async def get_reply_text(self, msg_id: str) -> Optional[dict]:
        """获取被回复消息的文本内容"""
        try:
            # 使用已有的 send_request 访问 NapCat 接口
            response:dict = await self.connector.send_request(
                "get_msg",
                {"message_id": int(msg_id)},
                f"rp_{msg_id}"
            )
            if response and response.get("status") == "ok":
                return response.get("data")
        except Exception as e:
            logger.error(f"获取回复消息失败: {e}")
        return None
