import sys
from modules.memory.rag import MemoryRAG
import plotly.express as px
import pandas as pd
from sklearn.manifold import TSNE
import numpy as np
import datetime
from sklearn.metrics.pairwise import cosine_similarity
import aiohttp
import asyncio
import os


class MemoryAuditor:
    def __init__(self):
        self.api_key = os.getenv("TEATOP_API_KEY", "").strip()
        self.api_url = "https://api.ytea.top/v1/chat/completions"
        self.model = "deepseek-chat"  # 沿用你测试效果最好的模型

    async def ask_yuki_to_choose(self, doc_a, doc_b, retries=3):
        """让 AI 决定保留哪条记录，带重试逻辑"""
        prompt = f"""你是一个记忆管理助手。下面有两条相似的电子妹妹 Yuki 的日记，请帮我决定保留哪一条。
准则：保留包含更多【具体事实、技术细节、特定日期、人物名称】的一条。如果两条信息量差不多，保留较短的一条。

日记 A: {doc_a}
日记 B: {doc_b}

请直接输出你选择的字母（A 或 B）以及简短理由。格式：[选择] - [理由]"""

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3  # 降低随机性，保证审计客观
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}

        for attempt in range(retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(self.api_url, json=payload, headers=headers, timeout=20) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            return data["choices"][0]["message"]["content"]
                        else:
                            print(f"  ⚠️ AI 服务响应异常 (HTTP {resp.status})，正在重试 {attempt + 1}/{retries}...")
            except Exception as e:
                print(f"  ⚠️ 连接失败 ({e})，正在重试 {attempt + 1}/{retries}...")

            await asyncio.sleep(2)  # 失败后等 2 秒再试

        return "ERROR - 无法连接 AI"


async def smart_semantic_deduplication(rag, chat_id, threshold=0.92):
    auditor = MemoryAuditor()
    print(f"🔍 正在对群聊 {chat_id} 进行【AI 智能审计】...")

    res = rag.collection.get(where={"chat_id": chat_id}, include=["embeddings", "documents"])
    vectors, docs, ids = np.array(res.get('embeddings')), res.get('documents'), res.get('ids')

    if vectors is None or len(vectors) < 2: return

    sim_matrix = cosine_similarity(vectors)
    to_delete_ids = []

    for i in range(len(docs)):
        if ids[i] in to_delete_ids: continue
        for j in range(i + 1, len(docs)):
            if ids[j] in to_delete_ids: continue

            if sim_matrix[i][j] > threshold:
                print(f"\n🤖 发现疑似冗余 (相似度: {sim_matrix[i][j]:.4f})")
                # 调用 AI 决策
                decision = await auditor.ask_yuki_to_choose(docs[i], docs[j])
                print(f"   AI 决策: {decision}")

                if "选择: A" in decision or "选择 A" in decision:
                    to_delete_ids.append(ids[j])  # 保留 A，删 B
                elif "选择: B" in decision or "选择 B" in decision:
                    to_delete_ids.append(ids[i])  # 保留 B，删 A
                else:
                    # 如果 AI 没给明确结论，默认保留老的（索引小的）
                    to_delete_ids.append(ids[j])

    if to_delete_ids:
        confirm = input(f"\n📊 AI 建议清理 {len(to_delete_ids)} 条记录。执行？(y/n): ")
        if confirm.lower() == 'y':
            rag.collection.delete(ids=to_delete_ids)
            print(f"✨ 已根据 AI 建议完成精炼。")

def semantic_deduplication(rag, chat_id, threshold=0.92):
    print(f"🔍 正在对群聊 {chat_id} 进行语义审计...")

    # 1. 获取数据
    res = rag.collection.get(
        where={"chat_id": chat_id},
        include=["embeddings", "documents"]
    )

    vectors = np.array(res.get('embeddings'))
    docs = res.get('documents')
    ids = res.get('ids')

    if vectors is None or len(vectors) < 2:
        print("❌ 记录太少，无法比对。")
        return

    # 2. 计算余弦相似度矩阵
    # 结果是一个 [N x N] 的矩阵，每个元素表示 i 和 j 的相似度
    sim_matrix = cosine_similarity(vectors)

    to_delete_indices = set()
    redundant_pairs = []

    # 3. 扫描冗余（只看上三角矩阵，避免重复比对）
    for i in range(len(docs)):
        if i in to_delete_indices: continue
        for j in range(i + 1, len(docs)):
            if sim_matrix[i][j] > threshold:
                redundant_pairs.append((i, j, sim_matrix[i][j]))
                to_delete_indices.add(j)  # 标记 j 为冗余

    # 4. 展示结果
    if not redundant_pairs:
        print(f"✅ 审计完成！未发现相似度高于 {threshold} 的冗余记录。")
        return

    print(f"\n{" 发现冗余建议 ":!^40}")
    for i, j, score in redundant_pairs[:10]:  # 最多显示10组预览
        print(f"\n[相似度: {score:.4f}]")
        print(f"保留项: {docs[i]}...")
        print(f"冗余项: {docs[j]}...")

    print(f"\n📊 统计：共 {len(docs)} 条，发现 {len(to_delete_indices)} 条语义重复。")
    confirm = input(f"❓ 是否一键清理这 {len(to_delete_indices)} 条冗余记录？(y/n): ")

    if confirm.lower() == 'y':
        target_ids = [ids[idx] for idx in to_delete_indices]
        # ChromaDB 批量删除有上限，建议分批或直接删
        rag.collection.delete(ids=target_ids)
        print(f"✨ 清理完成！删除了 {len(target_ids)} 条复读机记忆。")

def visualize_interactive_memory(rag, chat_id):
    print(f"正在从 ChromaDB 提取 {chat_id} 的 3D 向量数据...")

    # 1. 获取该群聊的所有向量、文本和元数据
    res = rag.collection.get(
        where={"chat_id": chat_id},
        include=["embeddings", "documents", "metadatas"]
    )

    vectors = res.get('embeddings')
    documents = res.get('documents')
    metadatas = res.get('metadatas')

    if vectors is None or len(vectors) < 5:
        print("❌ 数据太少（至少需要5条），无法生成有意义的可视化。")
        return

    # 2. 准备数据，加入时间戳和内容预览
    print(f"正在准备 {len(vectors)} 条记忆的数据集...")
    df = pd.DataFrame({
        'content': [d.replace('\n', ' ') for d in documents],  # 清理换行
        'timestamp': [m.get('timestamp', 0) for m in metadatas],
        'chat_id': [m.get('chat_id', 'unknown') for m in metadatas]
    })

    # 转换时间戳为可读格式
    df['time_str'] = df['timestamp'].apply(
        lambda ts: datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
    )
    # 截取前60字作为鼠标悬停预览
    df['preview'] = df['content'].apply(lambda c: c[:60] + '...' if len(c) > 60 else c)

    # 3. 降维处理 (768D -> 3D，更立体)
    print(f"正在通过 t-SNE 计算 {len(vectors)} 条记忆的 3D 相对位置...")
    data_np = np.array(vectors)
    tsne = TSNE(n_components=3, perplexity=min(30, len(vectors) - 1), init='pca', random_state=42)
    embedded_3d = tsne.fit_transform(data_np)

    # 将 3D 坐标加入 DataFrame
    df['x'] = embedded_3d[:, 0]
    df['y'] = embedded_3d[:, 1]
    df['z'] = embedded_3d[:, 2]

    # 4. 创建交互式 3D 散点图
    print("正在生成交互式 3D 记忆球...")
    fig = px.scatter_3d(
        df, x='x', y='y', z='z',
        color='timestamp',  # 用时间作为颜色渐变
        color_continuous_scale='Turbo',  # 炫酷的赛博色调
        opacity=0.7,
        hover_data={
            'x': False, 'y': False, 'z': False,  # 隐藏坐标
            'time_str': True,  # 显示时间
            'preview': True,  # 显示内容预览
            'chat_id': True  # 显示群聊ID
        },
        labels={'timestamp': '时间分布'},
        title=f"Yuki Interactive Memory Space: {chat_id}"
    )

    # 5. 美化布
    fig.update_traces(marker=dict(size=5, line=dict(width=0)))  # 调整点的大小
    fig.update_layout(
        template='plotly_dark',  # 使用暗色主题
        scene=dict(
            xaxis=dict(showgrid=False, showticklabels=False, title=''),
            yaxis=dict(showgrid=False, showticklabels=False, title=''),
            zaxis=dict(showgrid=False, showticklabels=False, title=''),
            bgcolor='black'  # 纯黑背景
        )
    )

    # 6. 保存为 HTML 并自动打开
    output_file = f"memory_map_{chat_id}.html"
    fig.write_html(output_file, auto_open=True)
    print(f"✨ 交互式记忆球已生成，已在浏览器中打开：{output_file}")

# ================= 逻辑模块 1: 手动录入 (原 manual_memory.py) =================
def save_manual_diary(rag, cid="manual_record"):
    print(f"\n>>> 进入手动录入模式 (当前 ID: {cid})")
    print("输入内容后回车存入，输入 'q' 返回主菜单")

    while True:
        try:
            content = input("> ").strip()
            if not content:
                continue
            if content.lower() in ['quit', 'exit', 'q']:
                break
                
            # 执行存入
            rag.save_diary(content=content, chat_id=cid)
            
            curr_time = datetime.datetime.now().strftime('%H:%M:%S')
            print(f"[{curr_time}] ✅ 已存入记忆库")
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ 存入失败: {e}")

# ================= 逻辑模块 2: 记忆管理 (原 manage_memory.py) =================
def manage_memory(rag):
    try:
        collection = rag.collection
    except Exception as e:
        print(f"❌ 读取集合失败: {e}")
        return

    while True:
        # 获取所有记忆
        results = collection.get(include=["documents", "metadatas"])
        ids = results['ids']
        docs = results['documents']
        metas = results['metadatas']

        if not ids:
            print("\n此时记忆库无记录。")
            break

        # 列表显示
        print(f"\n--- 记忆库列表 (共 {len(ids)} 条) ---")
        for i in range(len(ids)):
            print("-" * 15 + f" [索引 {i} | ID: {ids[i]}] " + "-" * 15)
            ts = metas[i].get('timestamp', 0)
            time_str = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
            content_preview = docs[i].replace('\n', ' ')
            print(f"{time_str} | {content_preview}")

        print("\n操作提示: [输入数字]删除单条 | [del:1,3]批量删除 | [q]返回主菜单")
        cmd = input("管理指令 > ").strip().lower()

        if cmd in ['q', 'exit']:
            break
        
        try:
            if cmd.startswith('del:'):
                indices = [int(x.strip()) for x in cmd.split(':')[1].split(',')]
                target_ids = [ids[idx] for idx in indices]
                collection.delete(ids=target_ids)
                print(f"✨ 已成功批量删除 {len(target_ids)} 条记录")
            elif cmd.isdigit():
                idx = int(cmd)
                collection.delete(ids=[ids[idx]])
                print(f"✨ 已成功删除记录 [{idx}]")
            else:
                print("无效指令")
        except Exception as e:
            print(f"❌ 操作失败: 索引越界或输入有误 ({e})")

# ================= 主入口 =================
# def main():
#     print("正在加载 Yuki 记忆系统...")
#     try:
#         # 统一初始化 RAG，避免重复加载模型
#         rag = MemoryRAG()
#     except Exception as e:
#         print(f"❌ 初始化失败，请检查 memory_rag.py 是否正确: {e}")
#         return
#
#     while True:
#         print("\n" + "Selection".center(40, "="))
#         print("1. 📝 手动录入记忆")
#         print("2. 🔍 浏览/删除记忆")
#         print("q. 🚪 退出程序")
#         print("=" * 40)
#
#         choice = input("请选择功能: ").strip().lower()
#
#         if choice == '1':
#             cid = input("请输入 Chat ID (默认 manual_record): ").strip()
#             save_manual_diary(rag, cid if cid else "manual_record")
#         elif choice == '2':
#             manage_memory(rag)
#         elif choice in ['q', 'exit', 'quit']:
#             print("程序已退出。")
#             break
#         else:
#             print("⚠️ 无效选择，请重新输入")


# ================= 逻辑模块 3: 群聊分组管理 (新增) =================
def chat_group_manager(rag):
    collection = rag.collection

    while True:
        # 1. 扫描所有唯一的 chat_id
        results = collection.get(include=["metadatas"])
        metas = results.get('metadatas', [])
        chat_ids = sorted(list(set(m.get('chat_id', 'unknown') for m in metas)))

        if not chat_ids:
            print("\n目前没有任何群聊记录。")
            break

        print(f"\n{' 群聊列表 ':*^30}")
        for i, cid in enumerate(chat_ids):
            count = sum(1 for m in metas if m.get('chat_id') == cid)
            print(f"[{i}] {cid} ({count} 条记录)")
        print("-" * 30)
        print("操作提示: [数字]进入 | [viz:数字]可视化 | [dedup:数字]语义去重 | [clear:数字]清空 | [q]返回")

        cmd = input("群组指令 > ").strip().lower()
        if cmd == 'q': break

        try:


            if ":" in cmd:
                action, idx_str = cmd.split(':')
                idx = int(idx_str)
                target_cid = chat_ids[idx]

                if action == 'viz':
                    visualize_interactive_memory(rag, target_cid)
                elif action == 'dedup':
                    # --- 调用新功能 ---
                    semantic_deduplication(rag, target_cid)
                elif action == 'clear':
                    confirm = input(f"⚠️ 确定要清空群聊 '{target_cid}'？(y/n): ")
                    if confirm.lower() == 'y':
                        collection.delete(where={"chat_id": target_cid})
                        print(f"🔥 已清空: {target_cid}")
                continue  # 处理完冒号指令，跳回循环开头

            # 2. 匹配纯数字指令
            if cmd.isdigit():
                idx = int(cmd)
                target_cid = chat_ids[idx]
                _view_single_chat(collection, target_cid)
                continue

            print("⚠️ 无效指令")

        except (ValueError, IndexError) as e:
            print(f"❌ 操作失败: 请输入正确的索引数字 (错误原因: {e})")


def _view_single_chat(collection, chat_id):
    """内部函数：查看并管理特定群聊的内容"""
    while True:
        # 仅获取该 chat_id 的数据
        res = collection.get(where={"chat_id": chat_id}, include=["documents", "metadatas"])
        ids, docs, metas = res['ids'], res['documents'], res['metadatas']

        if not ids:
            print(f"\n群聊 {chat_id} 已无内容。")
            break

        print(f"\n--- 正在浏览群聊: {chat_id} (共 {len(ids)} 条) ---")
        for i in range(len(ids)):
            ts = metas[i].get('timestamp', 0)
            time_str = datetime.datetime.fromtimestamp(ts).strftime('%m-%d %H:%M')
            print(f"[{i}] {time_str} | {docs[i][:50]}...")  # 预览前50字

        print(f"\n[{chat_id}] 操作: [数字]删除单条 | [q]返回群列表")
        sub_cmd = input(f"{chat_id} > ").strip().lower()

        if sub_cmd == 'q': break

        if sub_cmd.isdigit():
            idx = int(sub_cmd)
            try:
                collection.delete(ids=[ids[idx]])
                print(f"✨ 已从 {chat_id} 中删除记录")
            except:
                print("❌ 删除失败")


# ================= 修改后的主入口 =================
def main():
    print("正在加载 Yuki 记忆系统...")
    try:
        rag = MemoryRAG()
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        return

    while True:
        print("\n" + " Yuki Memory Terminal ".center(40, "="))
        print("1. 📝 手动录入记忆")
        print("2. 🔍 浏览/删除全部记录")
        print("3. 💬 按群聊(ChatID)分类管理")  # 新增
        print("q. 🚪 退出程序")
        print("=" * 40)

        choice = input("请选择功能: ").strip().lower()

        if choice == '1':
            cid = input("请输入 Chat ID (默认 manual_record): ").strip()
            save_manual_diary(rag, cid if cid else "manual_record")
        elif choice == '2':
            manage_memory(rag)
        elif choice == '3':
            chat_group_manager(rag)  # 新增
        elif choice in ['q', 'exit', 'quit']:
            break
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n程序已强制停止")
        sys.exit(0)