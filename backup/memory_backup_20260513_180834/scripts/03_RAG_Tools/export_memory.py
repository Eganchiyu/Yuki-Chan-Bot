import json
import os
import sys

# 确保能找到你的 modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.memory.rag import MemoryRAG


def export_current_memory():
    """
    仅保留提取记忆的逻辑：从当前数据库读取所有数据并备份到本地文件。
    """
    backup_file = "memory_backup_temp.json"

    print("[Backup] 正在尝试连接记忆库...")
    try:
        # 初始化 RAG 类
        rag = MemoryRAG()

        # 1. 从 collection 中获取所有数据
        # 注意：这里只包含 documents, metadatas 和 ids，不包含旧的 embeddings
        all_data = rag.collection.get(include=['documents', 'metadatas'])

        count = len(all_data.get('ids', []))

        # 2. 检查并保存
        if count == 0:
            print("[Backup] 记忆库为空，无需提取。")
        else:
            with open(backup_file, "w", encoding="utf-8") as f:
                json.dump(all_data, f, ensure_ascii=False, indent=4)

            print("-" * 30)
            print(f"[Success] 成功提取 {count} 条记忆！")
            print(f"[Success] 备份文件已保存至: {os.path.abspath(backup_file)}")
            print("-" * 30)

    except Exception as e:
        print(f"[Error] 提取记忆失败: {e}")
        print("请确保 config.py 中的 VECTOR_DB_PATH 指向正确的数据库目录。")


if __name__ == "__main__":
    export_current_memory()