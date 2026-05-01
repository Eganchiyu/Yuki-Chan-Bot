import json
import os
import asyncio
from config import cfg
from network.ws_connection import BotConnector
from utils.logger import get_logger

logger = get_logger("ws_sender")


class MessageSender:
    def __init__(self, connector: BotConnector):
        self.connector = connector

    async def send(self, chat_id, message, mode="private"):
        """闭环发送：失败自动触发重连"""
        for attempt in range(cfg.MAX_RETRIES):
            try:
                ws = await self.connector.ensure_connection()
                action = "send_private_msg" if mode == "private" else "send_group_msg"
                params = {
                    "message": message,
                    "user_id" if mode == "private" else "group_id": int(chat_id)
                }
                await ws.send(json.dumps({"action": action, "params": params}))
                return  # 发送成功，跳出
            except Exception as e:
                logger.error(f"[Sender] 发送失败 (尝试 {attempt + 1}): {e}")
                self.connector.websocket = None  # 标记连接失效
                if attempt == cfg.MAX_RETRIES - 1: raise e  # 如果第二次还失败，抛出错误
                await asyncio.sleep(1)

    async def send_local_image(self, chat_id, local_path, mode="private"):
        abs_path = os.path.abspath(local_path)
        cq_image = f"[CQ:image,file=file:///{abs_path}]"
        await self.send(chat_id, cq_image, mode=mode)

    async def send_local_voice(self, chat_id, local_path, mode="group"):
        """发送本地生成的语音文件"""
        abs_path = os.path.abspath(local_path)
        # QQ 的语音 CQ 码是 [CQ:record]
        cq_record = f"[CQ:record,file=file:///{abs_path}]"
        await self.send(chat_id, cq_record, mode=mode)

    # ============ 新增的 AI 语音发送方法 ============
    async def send_ai_voice(self, chat_id, text, character_id, mode="group"):
        """闭环发送：将文本转为AI语音并发送（主要适配群聊）"""
        for attempt in range(cfg.MAX_RETRIES):
            try:
                ws = await self.connector.ensure_connection()
                # NapCat的AI语音发送动作
                action = "send_group_ai_record"
                params = {
                    "group_id": int(chat_id),
                    "character": str(character_id),
                    "text": text
                }
                await ws.send(json.dumps({"action": action, "params": params}))
                return
            except Exception as e:
                logger.error(f"[Sender] 发送AI语音失败 (尝试 {attempt + 1}): {e}")
                self.connector.websocket = None
                if attempt == cfg.MAX_RETRIES - 1: raise e
                await asyncio.sleep(1)


# ============ 查询支持音色的测试代码 ============
if __name__ == "__main__":
    import requests

    print("正在获取 NapCat 支持的 AI 音色列表...")
    # 替换为你实际的 NapCat HTTP 地址和任意一个你机器人所在的群号
    BASE_URL = "http://127.0.0.1:3004"
    TEST_GROUP_ID = "782427668"

    try:
        res = requests.post(
            f"{BASE_URL}/get_ai_characters",
            json={"group_id": str(TEST_GROUP_ID), "chat_type": 1}
        ).json()

        if res.get("status") == "ok":
            print("\n✅ 获取成功！可用的角色原始数据如下：")
            for char in res.get("data", []):
                # 直接打印整个字典，看看里面到底有哪些 Key
                print(f"[*] 原始数据: {char}")
            print("\n💡 提示: 请查看上面的原始数据，找出代表 ID 的字段名，填入 send_ai_voice 中。")
        else:
            print(f"❌ 获取失败: {res}")
    except Exception as e:
        print(f"❌ 请求失败，请检查 NapCat HTTP 服务是否开启 (默认3003端口): {e}")