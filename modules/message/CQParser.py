from typing import Dict

from modules.message.GetMeta import MetaGetter
from network.connection import BotConnector
from modules.message.CQProtocol import CQProtocol

class CQCodeParser:
    """
    调用CQMetaGetter获取原json格式数据，解码数据后调用CQProtocol替换CQ码，返回解析后的原字符串
    """
    def __init__(self, connector: BotConnector):
        self.connector = connector
        self.nickname_cache: Dict[str, str] = {}
        self.protocol = CQProtocol()
        self.meta = MetaGetter(connector)

    async def get_user_nickname(self, user_id: str) -> str:
        """
        调用CQMetaGetter获取用户昵称

        """
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
        reply_buffer = self.protocol.extract_reply_matches(content)
        for mid in reply_buffer:
            text_data = await self.meta.get_reply_text(mid)
            reply_data = self.protocol.replace_reply_placeholder(text_data)
            content = content.replace(f"[CQ:reply,id={mid}]", reply_data)
        return content

    async def parse_all_cq_codes(self, text: str) -> str:
        text = await self.parse_Reply_CQ_codes(text)
        text = await self.parse_At_CQ_codes(text)
        text = self.protocol.replace_other_CQ_codes(text)
        return text
