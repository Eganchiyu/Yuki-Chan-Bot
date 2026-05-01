# scripts/batch_train_stickers.py
"""
Yuki 表情包批量训练脚本
功能：扫描 data/stickers 文件夹中的所有图片，一次性进行打标 + 向量入库
"""

import asyncio
import os
from pathlib import Path

from modules.stickers.manager import StickerManager
from config import cfg


async def batch_train_stickers():
    print("=== Yuki 表情包批量训练开始 ===\n")

    # 1. 初始化 StickerManager（内部自动从 ProviderRegistry 获取 provider）
    sticker_manager = StickerManager()

    # 2. 指定表情包文件夹（你当前存放的位置）
    sticker_folder = Path("../data/stickers")

    if not sticker_folder.exists():
        print(f"❌ 文件夹不存在: {sticker_folder.absolute()}")
        print("请确保表情包已放到 data/stickers/ 目录下")
        return

    # 支持的图片格式
    supported_ext = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

    # 获取所有图片文件
    image_files = []
    for ext in supported_ext:
        image_files.extend(sticker_folder.glob(f"*{ext}"))
        image_files.extend(sticker_folder.glob(f"*{ext.upper()}"))

    image_files = sorted(set(image_files))  # 去重并排序

    if not image_files:
        print("❌ 在 data/stickers/ 中没有找到图片文件")
        return

    print(f"找到 {len(image_files)} 个表情包，开始批量训练...\n")

    success_count = 0
    fail_count = 0

    for i, image_path in enumerate(image_files, 1):
        print(f"[{i:3d}/{len(image_files)}] 正在处理: {image_path.name}")

        try:
            # 调用 ingest_sticker 进行完整训练（VL理解 + 结构化分析 + 向量入库）
            doc_id = await sticker_manager.ingest_sticker(
                image_ref=str(image_path),  # 传入本地路径
                chat_id="global",
                owner="admin"
            )
            success_count += 1
            print(f"    ✅ 训练成功 | doc_id: {doc_id}\n")

        except Exception as e:
            fail_count += 1
            print(f"    ❌ 处理失败: {e}\n")

        # 每处理5张休息一下，避免API限流或过热
        if i % 5 == 0:
            await asyncio.sleep(1.5)

    # 最终统计
    print("=" * 50)
    print("批量训练完成！")
    print(f"成功入库: {success_count} 张")
    print(f"失败: {fail_count} 张")
    print(f"当前表情包总数: {sticker_manager.collection.count()}")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(batch_train_stickers())