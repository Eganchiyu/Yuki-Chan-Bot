# message_utils.py
import re
import json
import asyncio
import websockets
from typing import Optional, Dict
from config import NAPCAT_WS_URL


class CQCodeParser:
    def __init__(self, ws_url: str = NAPCAT_WS_URL):
        self.ws_url = ws_url
        self.nickname_cache: Dict[str, str] = {}
        self.websocket = None

    async def ensure_connection(self):
        if self.websocket is None:
            self.websocket = await websockets.connect(self.ws_url)
        return self.websocket

    async def send_request(self, action: str, params: dict, echo: str) -> Optional[Dict]:
        try:
            ws = await self.ensure_connection()
            request = {"action": action, "params": params, "echo": echo}
            await ws.send(json.dumps(request))
            try:
                while True:
                    response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(response)
                    if data.get("echo") == echo:
                        return data
            except asyncio.TimeoutError:
                print(f"[CQCodeParser] 请求 {action} 超时")
        except Exception as e:
            print(f"[CQCodeParser] 发送请求失败: {e}")
            try:
                await self.close()
            except:
                pass
            self.websocket = None
        return None

    async def get_user_info(self, user_id: str) -> Optional[Dict]:
        try:
            uid = int(user_id) if user_id.isdigit() else user_id
            response = await self.send_request(
                "get_stranger_info",
                {"user_id": uid, "no_cache": False},
                f"get_user_{user_id}"
            )
            if response and response.get("retcode") == 0:
                return response.get("data")
        except Exception as e:
            print(f"[CQCodeParser] 获取用户信息失败: {e}")
        return None
    async def get_group_member_info(self, group_id: str, user_id: str) -> Optional[Dict]:
        """获取群成员信息"""
        try:
            uid = int(user_id) if user_id.isdigit() else user_id
            gid = int(group_id) if group_id.isdigit() else group_id
            response = await self.send_request(
                "get_group_member_info",
                {"group_id": gid, "user_id": uid, "no_cache": False},
                f"get_group_member_{group_id}_{user_id}"
            )
            if response and response.get("retcode") == 0:
                return response.get("data")
        except Exception as e:
            print(f"[CQCodeParser] 获取群成员信息失败: {e}")
        return None
    async def get_user_nickname(self, user_id: str, group_id: str = None) -> str:
        """获取用户昵称，如果提供群号则优先使用群名片"""
        # 如果提供了群号，尝试从群成员缓存中获取
        if group_id:
            cache_key = f"{group_id}_{user_id}"
            if cache_key in self.nickname_cache:
                return self.nickname_cache[cache_key]
            # 获取群成员信息
            member_info = await self.get_group_member_info(group_id, user_id)
            if member_info:
                # 优先使用群名片 (card)，如果没有则使用昵称 (nickname)
                nickname = member_info.get("card") or member_info.get("nickname") or f"用户{user_id}"
                self.nickname_cache[cache_key] = nickname
                return nickname
            # 如果获取失败，回退到个人昵称（继续执行下面的逻辑）

        # 原逻辑：获取个人昵称
        if user_id in self.nickname_cache:
            return self.nickname_cache[user_id]
        if user_id.lower() == "all":
            return "全体成员"
        user_info = await self.get_user_info(user_id)
        if user_info and user_info.get("nickname"):
            nickname = user_info["nickname"]
            self.nickname_cache[user_id] = nickname
            return nickname
        return f"用户{user_id}"

    async def parse_at_cq_codes(self, text: str, group_id: str = None) -> str:
        """解析 @ CQ 码，将 QQ 号替换为昵称，可指定群号以使用群名片"""
        if not text:
            return text
        pattern = r'\[CQ:at,qq=(\d+|all)[^\]]*\]'
        matches = list(re.finditer(pattern, text))
        if not matches:
            return text
        result = text
        for match in reversed(matches):
            cq_code = match.group(0)
            qq = match.group(1)
            nickname = await self.get_user_nickname(qq, group_id)
            result = result[:match.start()] + f"@{nickname}" + result[match.end():]
        return result


    async def parse_all_cq_codes(self, text: str, group_id: str = None) -> str:
        """解析所有 CQ 码，可指定群号用于 @ 解析"""
        text = await self.parse_at_cq_codes(text, group_id)
        text = re.sub(r'\[CQ:image[^\]]*\]', '[图片]', text)
        text = re.sub(r'\[CQ:face[^\]]*\]', '[表情]', text)
        text = re.sub(r'\[CQ:record[^\]]*\]', '[语音]', text)
        text = re.sub(r'\[CQ:video[^\]]*\]', '[视频]', text)
        text = re.sub(r'\[CQ:file[^\]]*\]', '[文件]', text)
        return text

    async def close(self):
        if self.websocket:
            await self.websocket.close()
            self.websocket = None


class MessageSender:
    def __init__(self, websocket):
        self.websocket = websocket

    async def send(self, chat_id, message, mode="private"):
        action = "send_private_msg" if mode == "private" else "send_group_msg"
        params = {"message": message, "user_id" if mode == "private" else "group_id": int(chat_id)}
        await self.websocket.send(json.dumps({"action": action, "params": params}))


def smart_truncate(content, max_len, suffix="..."):
    """
    智能截断逻辑：保留CQ码完整性，仅截断长文本
    """
    import re
    if len(content) <= max_len:
        return content
        
    parts = re.split(r'(\[CQ:.*?\])', content)
    result = []
    total_len = 0

    for part in parts:
        if not part: continue
        is_cq = part.startswith('[CQ:') and part.endswith(']')
        part_len = len(part)

        if is_cq:
            if total_len + part_len <= max_len:
                result.append(part)
                total_len += part_len
            else:
                break
        else:
            if total_len + part_len <= max_len:
                result.append(part)
                total_len += part_len
            else:
                available = max_len - total_len - len(suffix)
                if available > 0:
                    result.append(part[:available] + suffix)
                break
    return ''.join(result)