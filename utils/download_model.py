# export_model.py
from sentence_transformers import SentenceTransformer
import os


def download_model():
# 从你 config 里的配置读取
    model_name = "shibing624/text2vec-base-chinese"
    # 使用基于当前文件位置的绝对路径，确保无论从哪运行都保存到项目目录
    save_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "models", "text2vec-base-chinese"))

    print(f"正在准备导出语义嵌入式模型（用于辅助RAG向量检索）: {model_name}")
    print("这一步会访问huggingface官网下载模型，大小约400MB，需连接外网。")

    # 加载模型（它会先去缓存找，找不到才下载）
    model = SentenceTransformer(model_name)

    # 创建本地目录
    if not os.path.exists(save_path):
        os.makedirs(save_path, exist_ok=True)

    # 核心：直接保存到本地
    model.save(save_path)

    print(f"模型已成功保存到本地: {os.path.abspath(save_path)}，程序结束")