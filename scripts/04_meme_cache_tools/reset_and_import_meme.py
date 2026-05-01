import os
import asyncio
import json

from config import cfg
from network.api_request import ApiCall
from modules.stickers.manager import StickerManager
from utils.logger import get_logger

logger = get_logger("stickers")


async def reset_and_import():
    print("=" * 50)
    print("⚠️ 正在安全重置表情包库（严格保留日记记忆）")
    print("=" * 50)

    # 1. 初始化 Manager
    dummy_llm = ApiCall(cfg.LLM_API_KEY, cfg.LLM_BASE_URL)
    manager = StickerManager(dummy_llm)

    # 2. 安全清空 stickers 集合，绝对不碰 diaries 集合！
    try:
        # 只删掉名为 "stickers" 的集合
        manager.client.delete_collection("stickers")
        print("✅ 旧表情包向量数据已从数据库中精准剥离清除。")

        # 重新建立一个空的 stickers 集合绑定到 manager
        manager.collection = manager.client.get_or_create_collection(
            name="stickers",
            metadata={"hnsw:space": "cosine"}
        )
    except Exception as e:
        print(f"ℹ️ 清理集合时出现提示（可能是已经空了）: {e}")

    # 3. 执行导入逻辑
    json_path = "manual_stickers.json"

    if not os.path.exists(json_path):
        print(f"❌ 找不到打标文件：{json_path}")
        print("请把你要导入的 JSON 数据保存为 manual_stickers.json 并放在同目录下。")
        return

    print(f"\n📦 开始从 {json_path} 批量导入打标数据...")

    # 直接调用我们在 manager.py 里面写好的方法
    await manager.manual_batch_ingest_from_json(json_path)

    print("\n🎉 导入流程全部完成！Yuki 的记忆安然无恙。")
    print(f"当前数据库中的表情包总量: {manager.collection.count()} 张")


if __name__ == "__main__":
    try:
        asyncio.run(reset_and_import())
    except KeyboardInterrupt:
        print("\n已强制退出。")