# manage_memory.py
print("正在加载记忆管理模块...")
from memory_rag import MemoryRAG
import datetime

def manage_memory():
    try:
        rag = MemoryRAG()
        collection = rag.collection
    except Exception as e:
        print(f"初始化失败: {e}")
        return

    # 获取所有记忆
    results = collection.get(include=["documents", "metadatas"])
    ids = results['ids']
    docs = results['documents']
    metas = results['metadatas']

    if not ids:
        print("记忆库无记录")
        return

    # 1. 列表显示
    print(f"--- 记忆库列表 (共 {len(ids)} 条) ---")
    for i in range(len(ids)):
        print("-" * 20 + f"[ID: {ids[i]}]" + "-" * 20)
        ts = metas[i].get('timestamp', 0)
        time_str = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
        # 优化预览，直接显示正文
        content_preview = docs[i].replace('\n', ' ')
        # content_preview = docs[i]
        print(f"[{i}] {time_str} | {content_preview}...")

    # 2. 指令交互
    print("\n操作: [编号]删除 | [del:1,3]批量删除 | [q]退出")
    cmd = input("> ").strip().lower()

    if cmd in ['q', 'exit']:
        return
    
    try:
        if cmd.startswith('del:'):
            indices = [int(x.strip()) for x in cmd.split(':')[1].split(',')]
            target_ids = [ids[idx] for idx in indices]
            collection.delete(ids=target_ids)
            print(f"已批量删除 {len(target_ids)} 条记录")
        elif cmd.isdigit():
            idx = int(cmd)
            collection.delete(ids=[ids[idx]])
            print(f"已删除记录 [{idx}]")
    except Exception as e:
        print(f"操作失败: 索引越界或输入有误 ({e})")

if __name__ == "__main__":
    while True:
        manage_memory()
        cont = input("继续管理记忆吗？(y/n): ").strip().lower()
        if cont != 'y':
            break
    