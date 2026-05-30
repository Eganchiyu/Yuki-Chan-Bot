import sys
import os
import json

# 获取项目根目录 (假设脚本在 scripts/03_RAG_Tools/ 下，根目录是上一级的上一级)
# 如果根目录层级不同，请调整 os.path.dirname 的次数
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(project_root)

from modules.memory.rag import MemoryRAG

def export_yuki_dataset(output_file="yuki_diary_finetune.jsonl"):
    rag = MemoryRAG()
    # 提取全局所有记录
    all_data = rag.collection.get()
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for doc in all_data.get('documents', []):
            # 将每一篇明文日记包装成指令格式
            qa_pair = {
                "instruction": "基于今天的交互记忆和状态，以Yuki的第一人称视角撰写一篇日记。",
                "input": "",
                "output": doc
            }
            f.write(json.dumps(qa_pair, ensure_ascii=False) + '\n')
            
    print(f"成功导出 {len(all_data.get('documents', []))} 篇 Yuki 日记数据！")

if __name__ == "__main__":
    export_yuki_dataset()