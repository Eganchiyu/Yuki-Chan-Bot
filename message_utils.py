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
            # 增加 ping_interval 和 ping_timeout 防止 1011 错误（心跳超时）
            self.websocket = await websockets.connect(
                self.ws_url, 
                ping_interval=20, 
                ping_timeout=20
            )
        return self.websocket

    async def send_request(self, action: str, params: dict, echo: str) -> Optional[Dict]:
        try:
            ws = await self.ensure_connection()
            request = {"action": action, "params": params, "echo": echo}
            await ws.send(json.dumps(request))
            try:
                # 增加一个计数器，避免死循环导致 keepalive 失效
                retry_count = 0
                while retry_count < 10: 
                    response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(response)
                    if data.get("echo") == echo:
                        return data
                    retry_count += 1
            except asyncio.TimeoutError:
                print(f"[CQCodeParser] 请求 {action} 超时")
        except Exception as e:
            print(f"[CQCodeParser] 发送请求失败: {e}")
            self.websocket = None # 出错时重置，下次会自动重连
        return None

    async def get_user_info(self, user_id: str) -> Optional[Dict]:
        try:
            uid = int(user_id) if str(user_id).isdigit() else user_id
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
        try:
            uid = int(user_id) if str(user_id).isdigit() else user_id
            gid = int(group_id) if str(group_id).isdigit() else group_id
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
        # 统一转为字符串处理，防止 int 导致的缓存 Key 冲突或方法缺失
        u_str = str(user_id)
        g_str = str(group_id) if group_id else None

        if g_str:
            cache_key = f"{g_str}_{u_str}"
            if cache_key in self.nickname_cache:
                return self.nickname_cache[cache_key]
            
            member_info = await self.get_group_member_info(g_str, u_str)
            if member_info:
                nickname = member_info.get("card") or member_info.get("nickname") or f"用户{u_str}"
                self.nickname_cache[cache_key] = nickname
                return nickname

        if u_str in self.nickname_cache:
            return self.nickname_cache[u_str]
        
        if u_str.lower() == "all":
            return "全体成员"
            
        user_info = await self.get_user_info(u_str)
        if user_info and user_info.get("nickname"):
            nickname = user_info["nickname"]
            self.nickname_cache[u_str] = nickname
            return nickname
        return f"用户{u_str}"

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