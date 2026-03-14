# manual_memory.py
import datetime
import sys
from memory_rag import MemoryRAG

def save_manual_diary(cid = "manual_record"):
    # 初始化 RAG 实例
    try:
        rag = MemoryRAG()
    except Exception as e:
        print(f"初始化 RAG 失败: {e}")
        return

    print("Yuki 记忆手动录入模式 (输入 'quit' 退出)")

    while True:
        try:
            # 使用更简洁的提示符
            content = input("> ").strip()
            
            if not content:
                continue
            if content.lower() in ['quit', 'exit', 'q']:
                break
                
            # 使用统一的标识符
            # manual_chat_id = "manual_record" 
            
            # 执行存入
            rag.save_diary(
                content=content,
                chat_id=cid
            )
            
            curr_time = datetime.datetime.now().strftime('%H:%M:%S')
            print(f"[{curr_time}] 已存入记忆库")

        except KeyboardInterrupt:
            print("\n已退出")
            break
        except Exception as e:
            print(f"存入失败: {e}")

if __name__ == "__main__":
    cid = input("请输入聊天 ID（默认为 'manual_record'，直接回车即可）: ").strip()
    if not cid:
        cid = "manual_record"
    save_manual_diary(cid)