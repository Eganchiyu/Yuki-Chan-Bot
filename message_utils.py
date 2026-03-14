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
                print(f"请求 {action} 超时")
        except Exception as e:
            print(f"发送请求失败: {e}")
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
            print(f"获取用户信息失败: {e}")
        return None

    async def get_user_nickname(self, user_id: str) -> str:
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

    async def parse_at_cq_codes(self, text: str) -> str:
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
            nickname = await self.get_user_nickname(qq)
            result = result[:match.start()] + f"@{nickname}" + result[match.end():]
        return result
    
    async def get_reply_text(self, msg_id: str) -> str:
        """获取被回复消息的文本内容"""
        try:
            # 使用已有的 send_request 访问 NapCat 接口
            res = await self.send_request("get_msg", {"message_id": int(msg_id)}, f"rp_{msg_id}")
            if res and res.get("status") == "ok":
                data = res.get("data", {})
                sender = data.get("sender", {}).get("nickname", "人")
                text = re.sub(r'\[CQ:.*?\]', '', data.get("raw_message", "")) # 只要前20字文本
                return f"【引用{sender}的消息: {text}】"
        except Exception as e:
            print(f"获取回复消息失败: {e}") 
            pass
        return "[引用消息]"

    async def replace_reply_all(self, content: str) -> str:
        """替换文本中所有的回复CQ码"""
        matches = re.findall(r'\[CQ:reply,id=(\d+)\]', content)
        for mid in matches:
            rep_text = await self.get_reply_text(mid)
            content = content.replace(f"[CQ:reply,id={mid}]", rep_text)
        return content

    async def parse_all_cq_codes(self, text: str) -> str:
        text = await self.replace_reply_all(text)
        text = await self.parse_at_cq_codes(text)
        text = re.sub(r'\[CQ:image[^\]]*\]', '[图片]', text)
        text = re.sub(r'\[CQ:face[^\]]*\]', '[表情]', text)
        text = re.sub(r'\[CQ:record[^\]]*\]', '[语音]', text)
        text = re.sub(r'\[CQ:video[^\]]*\]', '[视频]', text)
        text = re.sub(r'\[CQ:file[^\]]*\]', '[文件]', text)
        text = re.sub(r'\[CQ:json[^\]]*\]', '[小程序]', text)
        
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
    保留原有调试好的逻辑：智能截断超长消息并保留CQ码完整性
    """
    import re
    # 如果没超过长度，直接原样返回，不做任何处理
    if len(content) <= max_len:
        return content

    # --- 以下是你调试好的原始算法逻辑，完全不动 ---
    print(f"[System] 检测到超长消息 ({len(content)} 字符)，进行智能截断")
    parts = re.split(r'(\[CQ:.*?\])', content)
    result = []
    total_len = 0

    for part in parts:
        if not part:
            continue
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

    new_content = ''.join(result)
    print(f"[System] 截断后长度: {len(new_content)} 字符")
    return new_content

    