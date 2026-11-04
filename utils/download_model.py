# utils/download_model.py
"""
RAG 与表情包系统共用的向量模型下载器与内存单例管理器。

解决两个核心痛点：
1. 磁盘与网络：
   - 直接按最小文件集流式下载到 `./models/text2vec-base-chinese/`，不经过 `~/.cache/huggingface` 二次拷贝（省去额外 391MB 磁盘占用）。
   - 自动按「ModelScope 阿里云国内源 → HF-Mirror 镜像 → HuggingFace 官方源」顺序故障切换，国内无代理也可满速下载，并带实时进度显示。
2. 内存单实例：
   - 提供 `get_embed_model()` 与 `get_chroma_client()` 进程级单例缓存，让 `MemoryRAG` 与 `StickerManager` 共享同一个 391MB `SentenceTransformer` 实例，节省 ~400MB 内存并使启动提速一倍。
"""

from __future__ import annotations

import glob
import os
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_MODEL_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "models", "text2vec-base-chinese")
)

# 最小必需的元数据与分词器文件（约 125KB）
COMMON_FILES: List[str] = [
    "config.json",
    "modules.json",
    "sentence_bert_config.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "vocab.txt",
    "1_Pooling/config.json",
]

# 下载源定义：(源名称, URL构造模板, 权重文件名)
def _build_sources(preferred: str = "auto") -> List[Tuple[str, str, str]]:
    hf_endpoint = os.environ.get("HF_ENDPOINT", "").strip().rstrip("/")
    sources: List[Tuple[str, str, str]] = [
        (
            "modelscope",
            "https://www.modelscope.cn/api/v1/models/Jerry0/text2vec-base-chinese/repo?Revision=master&FilePath={file}",
            "pytorch_model.bin",
        ),
        (
            "hf-mirror",
            "https://hf-mirror.com/shibing624/text2vec-base-chinese/resolve/main/{file}",
            "model.safetensors",
        ),
        (
            "huggingface",
            "https://huggingface.co/shibing624/text2vec-base-chinese/resolve/main/{file}",
            "model.safetensors",
        ),
    ]
    if hf_endpoint and hf_endpoint not in ("https://huggingface.co", "https://hf-mirror.com"):
        sources.insert(
            0,
            (
                "custom-hf-endpoint",
                f"{hf_endpoint}/shibing624/text2vec-base-chinese/resolve/main/{{file}}",
                "model.safetensors",
            ),
        )

    preferred = (preferred or os.environ.get("YUKI_MODEL_SOURCE", "auto")).strip().lower()
    if preferred and preferred != "auto":
        sources.sort(key=lambda item: 0 if item[0] == preferred else 1)
    return sources


def is_model_complete(save_path: str = DEFAULT_MODEL_DIR) -> bool:
    """检查目标目录是否已包含完整的嵌入模型。"""
    if not os.path.isdir(save_path):
        return False
    for rel in ("config.json", "modules.json", "1_Pooling/config.json"):
        if not os.path.exists(os.path.join(save_path, rel)):
            return False
    has_weight = (
        os.path.exists(os.path.join(save_path, "model.safetensors"))
        or os.path.exists(os.path.join(save_path, "pytorch_model.bin"))
    )
    return has_weight


def _migrate_from_hf_cache_if_available(save_path: str, remove_cache: bool = True) -> bool:
    """如果本机 ~/.cache/huggingface 已有缓存快照，直接迁移过来并清理冗余缓存。"""
    hf_cache_dir = os.path.expanduser(
        "~/.cache/huggingface/hub/models--shibing624--text2vec-base-chinese"
    )
    snapshots = sorted(glob.glob(os.path.join(hf_cache_dir, "snapshots", "*")))
    for snap in reversed(snapshots):
        if is_model_complete(snap):
            print(f"📦 检测到本机 HuggingFace 缓存已有该模型，正在直接迁移至 {save_path} ...")
            os.makedirs(os.path.join(save_path, "1_Pooling"), exist_ok=True)
            for root, _dirs, files in os.walk(snap):
                rel_dir = os.path.relpath(root, snap)
                target_dir = save_path if rel_dir == "." else os.path.join(save_path, rel_dir)
                os.makedirs(target_dir, exist_ok=True)
                for fname in files:
                    src_file = os.path.join(root, fname)
                    dst_file = os.path.join(target_dir, fname)
                    shutil.copy2(src_file, dst_file)
            if is_model_complete(save_path):
                if remove_cache:
                    try:
                        shutil.rmtree(hf_cache_dir)
                        print("🧹 已清理冗余的 ~/.cache/huggingface 副本（释放 ~391MB 磁盘空间）")
                    except OSError:
                        pass
                return True
    return False


def _download_file(url: str, dst_path: str, timeout: float = 30.0, show_progress: bool = False) -> None:
    """流式下载单个文件到临时路径并原子替换。"""
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    tmp_path = f"{dst_path}.part.{os.getpid()}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Yuki-Model-Downloader/2.0)"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp_path, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            downloaded = 0
            last_print = 0.0
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                downloaded += len(chunk)
                now = time.time()
                if show_progress and (now - last_print >= 0.4 or downloaded == total):
                    last_print = now
                    elapsed = max(now - t0, 0.001)
                    speed = (downloaded / (1024 * 1024)) / elapsed
                    if total > 0:
                        pct = downloaded * 100.0 / total
                        print(
                            f"\r   ⬇️  {downloaded / (1024 * 1024):.1f} / {total / (1024 * 1024):.1f} MB "
                            f"({pct:5.1f}%) | {speed:.2f} MB/s",
                            end="",
                            flush=True,
                        )
                    else:
                        print(
                            f"\r   ⬇️  {downloaded / (1024 * 1024):.1f} MB | {speed:.2f} MB/s",
                            end="",
                            flush=True,
                        )
            if show_progress:
                print()
        os.replace(tmp_path, dst_path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise


def download_model(force: bool = False, source: str = "auto", save_path: Optional[str] = None) -> str:
    """下载或校验 text2vec-base-chinese 嵌入模型。

    Args:
        force: 是否强制重新下载
        source: 下载源 ("auto" | "modelscope" | "hf-mirror" | "huggingface")
        save_path: 保存路径，默认 ./models/text2vec-base-chinese
    """
    target_dir = os.path.abspath(save_path or DEFAULT_MODEL_DIR)

    if is_model_complete(target_dir) and not force:
        if sys.stdin and sys.stdin.isatty():
            print(f"检测到本地已存在模型: {target_dir}")
            choice = input("是否重新下载并覆盖？(y/N): ").strip().lower()
            if choice != "y":
                print("跳过下载，使用本地已有模型。")
                return target_dir
        else:
            print(f"✅ 本地已存在完整向量模型: {target_dir}")
            return target_dir

    # 若未强制重下且本机 ~/.cache/huggingface 已有缓存，直接迁移并删除冗余副本
    if not force and _migrate_from_hf_cache_if_available(target_dir, remove_cache=True):
        print(f"✅ 模型已成功就绪: {target_dir}")
        return target_dir

    sources = _build_sources(source)
    last_err: Optional[Exception] = None

    for src_name, url_tpl, weight_file in sources:
        print(f"\n🌐 尝试从 [{src_name}] 下载向量模型 (text2vec-base-chinese, 约 391MB)...")
        try:
            os.makedirs(os.path.join(target_dir, "1_Pooling"), exist_ok=True)
            for rel_file in COMMON_FILES:
                url = url_tpl.format(file=rel_file)
                dst = os.path.join(target_dir, rel_file)
                _download_file(url, dst, timeout=20.0, show_progress=False)

            weight_url = url_tpl.format(file=weight_file)
            weight_dst = os.path.join(target_dir, weight_file)
            print(f"   正在下载权重文件 {weight_file} ...")
            _download_file(weight_url, weight_dst, timeout=60.0, show_progress=True)

            if is_model_complete(target_dir):
                print(f"✅ 向量模型已成功下载至: {target_dir} (来源: {src_name})")
                return target_dir
        except Exception as e:
            last_err = e
            print(f"⚠️ 从 [{src_name}] 下载失败: {e}，尝试下一个源...")

    raise RuntimeError(f"所有模型下载源均失败，最后错误: {last_err}")


# ==================== 进程内全局共享单例（消除双倍内存占用） ====================

_MODEL_LOCK = threading.Lock()
_EMBED_MODELS: Dict[str, Any] = {}
_CHROMA_CLIENTS: Dict[str, Any] = {}


def get_embed_model(model_path: Optional[str] = None):
    """获取共享的 SentenceTransformer 实例（同一路径在进程内只加载一次）。"""
    if not model_path:
        from config import cfg
        model_path = cfg.EMBED_MODEL
    abs_path = os.path.abspath(model_path)

    with _MODEL_LOCK:
        if abs_path not in _EMBED_MODELS:
            from sentence_transformers import SentenceTransformer
            _EMBED_MODELS[abs_path] = SentenceTransformer(abs_path)
        return _EMBED_MODELS[abs_path]


def get_chroma_client(db_path: Optional[str] = None):
    """获取共享的 ChromaDB PersistentClient 实例（同一路径在进程内只创建一次）。"""
    if not db_path:
        from config import cfg
        db_path = cfg.VECTOR_DB_PATH
    abs_path = os.path.abspath(db_path)

    with _MODEL_LOCK:
        if abs_path not in _CHROMA_CLIENTS:
            import chromadb
            _CHROMA_CLIENTS[abs_path] = chromadb.PersistentClient(path=abs_path)
        return _CHROMA_CLIENTS[abs_path]


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="下载 text2vec-base-chinese 向量模型")
    p.add_argument("--force", action="store_true", help="强制重新下载")
    p.add_argument(
        "--source",
        default="auto",
        choices=["auto", "modelscope", "hf-mirror", "huggingface"],
        help="指定下载源（默认 auto：优先国内 ModelScope 源）",
    )
    args = p.parse_args()
    download_model(force=args.force, source=args.source)
