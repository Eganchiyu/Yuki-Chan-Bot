import json
import os
import asyncio
import uuid
import base64
from datetime import datetime
from config import cfg
from network.ws_connection import BotConnector
from utils.logger import get_logger

logger = get_logger("ws_sender")

# 文件下载目录 - 保存到 workspace 供小女仆直接访问
DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workspace")


class MessageSender:
    def __init__(self, connector: BotConnector):
        self.connector = connector
        # 确保下载目录存在
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    @staticmethod
    def _is_private_mode(mode):
        return mode in {"private", "master_private"}

    async def send(self, chat_id, message, mode="private"):
        """闭环发送：失败自动触发重连"""
        for attempt in range(cfg.MAX_RETRIES):
            try:
                ws = await self.connector.ensure_connection()
                is_private = self._is_private_mode(mode)
                action = "send_private_msg" if is_private else "send_group_msg"
                params = {
                    "message": message,
                    "user_id" if is_private else "group_id": int(chat_id)
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

    async def send_local_file(self, chat_id, local_path, mode="private"):
        """发送本地普通文件。"""
        abs_path = os.path.abspath(local_path)
        cq_file = f"[CQ:file,file=file:///{abs_path}]"
        await self.send(chat_id, cq_file, mode=mode)

    async def send_local_voice(self, chat_id, local_path, mode="group"):
        """发送本地生成的语音文件"""
        abs_path = os.path.abspath(local_path)
        # QQ 的语音 CQ 码是 [CQ:record]
        cq_record = f"[CQ:record,file=file:///{abs_path}]"
        await self.send(chat_id, cq_record, mode=mode)

    async def send_poke(self, user_id, group_id):
        """
        发送戳一戳请求。

        Args:
            user_id: 目标用户 QQ 号
            group_id: 群号

        Returns:
            dict: NapCat 响应结果，包含 status 和 message
        """
        echo = f"poke_{uuid.uuid4().hex[:8]}"
        params = {
            "user_id": int(user_id),
            "group_id": int(group_id),
        }

        logger.info(f"[Sender] 发送戳一戳: user={user_id}, group={group_id}")
        result = await self.connector.send_request("send_poke", params, echo)

        if result:
            status = result.get("status", "unknown")
            message = result.get("message", "")
            logger.info(f"[Sender] 戳一戳结果: status={status}, message={message}")
            return result
        else:
            logger.warning("[Sender] 戳一戳请求超时或失败")
            return {"status": "failed", "message": "请求超时"}

    async def get_file(self, file_id: str) -> dict:
        """
        通过 file_id 获取文件信息。

        Args:
            file_id: 文件 ID

        Returns:
            dict: NapCat 响应结果，包含文件信息（可能有 base64、url、file 等）
        """
        echo = f"get_file_{uuid.uuid4().hex[:8]}"
        params = {
            "file_id": file_id,
        }

        logger.info(f"[Sender] 获取文件: file_id={file_id}")
        result = await self.connector.send_request("get_file", params, echo)

        if result:
            logger.info(f"[Sender] 获取文件结果: status={result.get('status', 'unknown')}")
            return result
        else:
            logger.warning("[Sender] 获取文件请求超时或失败")
            return {"status": "failed", "message": "请求超时"}

    async def download_file(self, file_id: str, filename: str = None) -> dict:
        """
        下载文件并保存到本地。

        Args:
            file_id: 文件 ID
            filename: 保存的文件名（可选，默认自动生成）

        Returns:
            dict: {
                "success": bool,
                "file_path": str,  # 绝对路径
                "filename": str,   # 文件名
                "error": str       # 错误信息（如果有）
            }
        """
        # 1. 获取文件信息
        result = await self.get_file(file_id)

        if result.get("status") != "ok":
            return {
                "success": False,
                "file_path": None,
                "filename": None,
                "error": result.get("message", "获取文件失败")
            }

        # 2. 从返回数据中提取文件内容
        data = result.get("data", {})
        file_content = None
        file_url = None
        original_filename = data.get("file_name", "")

        # 尝试从 base64 获取
        if "base64" in data:
            try:
                file_content = base64.b64decode(data["base64"])
                logger.info(f"[Sender] 从 base64 解码文件，大小: {len(file_content)} bytes")
            except Exception as e:
                logger.error(f"[Sender] base64 解码失败: {e}")

        # 尝试从 url 获取
        if not file_content and "url" in data:
            file_url = data["url"]
            logger.info(f"[Sender] 文件 URL: {file_url}")

        # 尝试从 file 路径获取
        if not file_content and "file" in data:
            file_path = data["file"]
            if os.path.exists(file_path):
                try:
                    with open(file_path, "rb") as f:
                        file_content = f.read()
                    logger.info(f"[Sender] 从本地路径读取文件: {file_path}")
                except Exception as e:
                    logger.error(f"[Sender] 读取本地文件失败: {e}")

        # 3. 确定文件名
        if not filename:
            if original_filename:
                filename = original_filename
            else:
                # 根据 file_id 生成文件名
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"file_{timestamp}_{file_id[:8]}"

        # 4. 保存文件
        save_path = os.path.join(DOWNLOAD_DIR, filename)

        if file_content:
            try:
                with open(save_path, "wb") as f:
                    f.write(file_content)
                logger.info(f"[Sender] 文件已保存: {save_path}")
                return {
                    "success": True,
                    "file_path": os.path.abspath(save_path),
                    "filename": filename,
                    "error": None
                }
            except Exception as e:
                logger.error(f"[Sender] 保存文件失败: {e}")
                return {
                    "success": False,
                    "file_path": None,
                    "filename": None,
                    "error": f"保存文件失败: {str(e)}"
                }
        elif file_url:
            # 返回 URL，让调用者决定如何处理
            return {
                "success": True,
                "file_path": None,
                "filename": filename,
                "url": file_url,
                "error": None
            }
        else:
            return {
                "success": False,
                "file_path": None,
                "filename": None,
                "error": "无法获取文件内容"
            }

    async def send_forward_message(self, chat_id, nodes: list, mode="group"):
        """发送合并转发消息（聊天记录形式）

        Args:
            chat_id: 群号或用户ID
            nodes: 消息节点列表，每个节点格式:
                {"uin": "123456", "name": "显示名", "content": [...消息段...]}
                content 中的消息段格式:
                {"type": "text", "data": {"text": "文字"}}
                {"type": "image", "data": {"file": "file:///path"}}
                {"type": "file", "data": {"file": "file:///path", "name": "文件名"}}
            mode: "private" 或 "group"

        Returns:
            dict: NapCat 响应结果
        """
        echo = f"forward_{uuid.uuid4().hex[:8]}"

        # 构造节点消息
        message_nodes = []
        for node in nodes:
            node_data = {
                "type": "node",
                "data": {
                    "uin": str(node.get("uin", chat_id)),
                    "content": node.get("content", []),
                }
            }
            # 可选的 nickname 字段
            if "name" in node:
                node_data["data"]["nickname"] = node["name"]
            message_nodes.append(node_data)

        is_private = self._is_private_mode(mode)
        action = "send_private_forward_msg" if is_private else "send_group_forward_msg"
        params = {
            "messages": message_nodes,
            "user_id" if is_private else "group_id": int(chat_id),
        }

        logger.info(f"[Sender] 发送合并转发: {len(message_nodes)} 个节点, mode={mode}")
        result = await self.connector.send_request(action, params, echo, timeout=60)

        if result:
            status = result.get("status", "unknown")
            logger.info(f"[Sender] 合并转发结果: status={status}")
            return result
        else:
            logger.warning("[Sender] 合并转发请求超时或失败")
            return {"status": "failed", "message": "请求超时"}

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
    from utils.http_client import requests_verify

    print("正在获取 NapCat 支持的 AI 音色列表...")
    # 从配置中获取 NapCat HTTP 地址，测试群号使用配置中的第一个群组
    BASE_URL = cfg.NAPCAT_WS_URL.replace("ws://", "http://").replace(":3001", ":3004")
    TEST_GROUP_ID = str(cfg.TARGET_GROUPS[0]) if cfg.TARGET_GROUPS else "000000000"

    try:
        res = requests.post(
            f"{BASE_URL}/get_ai_characters",
            json={"group_id": str(TEST_GROUP_ID), "chat_type": 1},
            verify=requests_verify(),
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
