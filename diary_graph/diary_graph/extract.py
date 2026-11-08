"""本地关键词抽取：jieba 分词 + 词性过滤 + TF-IDF Top-K。"""

from __future__ import annotations

import re
from pathlib import Path

import jieba
import jieba.analyse
import jieba.posseg as pseg  # noqa: F401  (加载 posseg 资源)

# 只保留有概念价值的词性
ALLOW_POS = ("n", "nr", "ns", "nt", "nz", "vn", "v", "eng")

_PURE_DIGIT = re.compile(r"^[\d.\-_%]+$")
_URLISH = re.compile(r"(https?://|www\.)")
# 日记正文的时间前缀不属于内容
_DIARY_PREFIX = re.compile(r"^\s*【日记\([^)）]*\)】[：:]?\s*")


class KeywordExtractor:
    def __init__(self, base_dir: str | Path, min_len: int = 2,
                 allow_pos: tuple[str, ...] = ALLOW_POS,
                 extra_stop: str | Path | None = None):
        base = Path(base_dir)
        self.min_len = min_len
        self.allow_pos = allow_pos
        self.aliases = self._load_aliases(base / "aliases.txt")
        self.stopwords = self._load_stopwords(base / "stopwords.txt")
        if extra_stop:
            self.stopwords |= self._load_stopwords(Path(extra_stop))

        custom = base / "custom_dict.txt"
        if custom.exists():
            jieba.load_userdict(str(custom))
        if self.stopwords:
            jieba.analyse.set_stop_words(str(base / "stopwords.txt"))
        jieba.initialize()

        # 别名替换按长度降序，避免短别名先命中
        self._alias_patterns = [
            (re.compile(re.escape(alias), re.IGNORECASE), canon)
            for canon, alias in sorted(
                ((c, a) for c, al in self.aliases.items() for a in al),
                key=lambda x: len(x[1]), reverse=True)
        ]

    @staticmethod
    def _load_aliases(path: Path) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        if not path.exists():
            return out
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            canon, al = line.split("=", 1)
            out[canon.strip()] = [a.strip() for a in al.split("|") if a.strip()]
        return out

    @staticmethod
    def _load_stopwords(path: Path) -> set[str]:
        if not path.exists():
            return set()
        return {
            line.strip().lower()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }

    def normalize(self, text: str) -> str:
        text = _DIARY_PREFIX.sub("", text)
        for pat, canon in self._alias_patterns:
            text = pat.sub(canon, text)
        return text

    def _keep(self, word: str) -> bool:
        w = word.strip()
        if len(w) < self.min_len or _PURE_DIGIT.match(w) or _URLISH.search(w):
            return False
        return w.lower() not in self.stopwords

    def extract(self, text: str, top_k: int = 8) -> list[str]:
        text = self.normalize(text)
        if not text:
            return []
        tags = jieba.analyse.extract_tags(
            text, topK=max(top_k * 3, top_k + 4), allowPOS=self.allow_pos,
        )
        picked: list[str] = []
        for w in tags:
            if self._keep(w) and w not in picked:
                picked.append(w)
            if len(picked) >= top_k:
                break
        return picked
