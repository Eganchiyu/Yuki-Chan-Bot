import re
from typing import Dict, Optional

from network.connection import BotConnector
from modules.message.formatter import CQProtocol

class CQCodeParser:
    def __init__(self, connector: BotConnector):
        # 💡 这里不再用 super()，而是直接把工具存起来
        self.connector = connector
        self.nickname_cache: Dict[str, str] = {}
        self.protocol = CQProtocol()  # 内部组合算法工具
        self.meta = CQMetaGetter(connector)

    async def get_user_nickname(self, user_id: str) -> str:
        if user_id in self.nickname_cache:
            return self.nickname_cache[user_id]
        if user_id.lower() == "all":
            return "全体成员"
        user_info = await self.meta.get_user_info(user_id)
        if user_info and user_info.get("nickname"):
            nickname = user_info["nickname"]
            self.nickname_cache[user_id] = nickname
            return nickname
        return f"用户{user_id}"

    async def parse_At_CQ_codes(self, text: str) -> str:
        uids = self.protocol.extract_at_uids(text)
        for uid in set(uids):
            name = await self.get_user_nickname(uid)
            text = self.protocol.replace_at_placeholder(text, uid, name)
        return text

    async def parse_Reply_CQ_codes(self, content: str) -> str:
        """替换文本中所有的回复CQ码"""
        mids = self.protocol.extract_reply_matches(content)
        for mid in mids:
            text_data = await self.meta.get_reply_text(mid)
            reply_data = self.protocol.replace_reply_placeholder(text_data)
            content = content.replace(f"[CQ:reply,id={mid}]", reply_data)
        return content

    async def parse_all_cq_codes(self, text: str) -> str:
        text = await self.parse_Reply_CQ_codes(text)
        text = await self.parse_At_CQ_codes(text)
        text = self.protocol.replace_other_CQ_codes(text)
        return text



class CQMetaGetter:
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
            print(f"获取用户信息失败: {e}")
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
            print(f"获取回复消息失败: {e}")
        return None