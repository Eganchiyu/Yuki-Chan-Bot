from typing import Optional, Dict

from network.napcat import NapCatGateway
from utils.logger import get_logger

logger = get_logger("message_meta")


class MetaGetter:
    def __init__(self, connector: NapCatGateway):
        self.connector = connector

    async def get_group_member_info(self, group_id: str, user_id: str) -> Optional[Dict]:
        """获取群成员信息（含群名片 card）"""
        try:
            gid = int(group_id) if str(group_id).isdigit() else group_id
            uid = int(user_id) if user_id.isdigit() else user_id
            response:dict = await self.connector.call(
                "get_group_member_info",
                {"group_id": gid, "user_id": uid, "no_cache": False},
            )
            if response and response.get("retcode") == 0:
                return response.get("data")
        except Exception as e:
            logger.error(f"获取群成员信息失败: {e}")
        return None

    async def get_reply_text(self, msg_id: str) -> Optional[dict]:
        """获取被回复消息的文本内容"""
        try:
            response:dict = await self.connector.call(
                "get_msg",
                {"message_id": int(msg_id)},
            )
            if response and response.get("status") == "ok":
                return response.get("data")
        except Exception as e:
            logger.error(f"获取回复消息失败: {e}")
        return None
