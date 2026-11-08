"""程序组路径与默认参数。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
ROOT = PKG_DIR.parent          # diary_graph/
PROJECT_DIR = ROOT.parent      # Yuki/

DEFAULT_DB = PROJECT_DIR / "yuki_memory" / "chroma.sqlite3"
DEFAULT_OUT = ROOT / "output"
# 复用主项目的记忆屏蔽词（Yuki、主人、机主等称谓）
DEFAULT_EXTRA_STOP = PROJECT_DIR / "blacklist.txt"


@dataclass
class BuildOptions:
    db: Path = DEFAULT_DB
    out_dir: Path = DEFAULT_OUT
    collection: str = "diaries"
    limit: int = 0            # 0 = 全部（取最新 N 篇）
    top_k: int = 8            # 每篇日记取多少关键词
    halflife_days: float = 365.0   # 时间衰减半衰期（<=0 关闭衰减）
    min_weight: float = 1.0   # 剪枝：边权重下限
    max_nodes: int = 900      # 保留加权度最高的 N 个节点（0 = 不限）
    max_docs_per_node: int = 8
    snippet_len: int = 260
    use_cache: bool = True
    dynamic_k: bool = True    # 按文本长度自适应每篇关键词数
    mix_rank: bool = True     # TF-IDF ∩ TextRank
