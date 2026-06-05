import json
import os
import sys
import shutil

# 1. 路径修复（确保能找到 modules）
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.memory.rag import MemoryRAG
from config import cfg


def migrate_database():
    backup_file = "memory_backup_temp.json"

    # 检查备份
    if not os.path.exists(backup_file):
        print(f"[Error] 未找到备份文件: {backup_file}")
        return

    # --- 核心修复步骤：强制清理旧维度限制 ---
    if os.path.exists(cfg.VECTOR_DB_PATH):
        print(f"[Action] 正在物理删除旧数据库目录: {cfg.VECTOR_DB_PATH}")
        # 必须删除整个文件夹，Chroma 才会重新创建 768 维的索引
        shutil.rmtree(cfg.VECTOR_DB_PATH)

    print("[RAG] 初始化全新 768 维记忆库...")
    rag = MemoryRAG()

    with open(backup_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    documents = data.get('documents', [])
    metadatas = data.get('metadatas', [])

    print(f"[Restore] 开始迁移 {len(documents)} 条数据...")

    # --- 使用 Class 自身的保存逻辑 ---
    for doc, meta in zip(documents, metadatas):
        try:
            # 解析原有的 metadata 以还原上下文
            chat_id = meta.get('chat_id')
            # 还原 people 和 emotion (如果原本是 JSON 字符串，save_diary 会重新处理)
            people = json.loads(meta.get('people', '[]')) if 'people' in meta else None
            emotion = meta.get('emotion')

            # 调用你 class 里的原生保存方法
            # 这会自动触发模型计算 768 维向量
            rag.save_diary(
                content=doc,
                chat_id=chat_id,
                people=people,
                emotion=emotion
            )
        except Exception as e:
            print(f"[Skip] 某条记录保存失败: {e}")

    print("-" * 30)
    print(f"[Success] 数据库升级完成！")
    print(f"[Success] 现已支持 768 维语义检索。")
    print("-" * 30)

    # 测试检索
    print("[Test] 正在进行最终连通性测试...")
    test_result = rag.search_diaries("测试检索", n_results=1)
    print(f"[Test] 检索成功，返回结果数: {len(test_result)}")


if __name__ == "__main__":
    migrate_database()