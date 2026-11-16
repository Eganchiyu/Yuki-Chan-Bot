# core/art_gacha.py
"""二次元提示词抽卡：随机给一句英文提示词灵感（外部语料库 + 内置词条池）。

无参数设计：调用方只要一句“随机提示词”，不关心卡池、槽位、锁定、资产绑定。
来源有两类，随机混合：
  - 外部语料库 ``data/zako``（Zako-Prompt-Tools 的 Danbooru 标签，命中率见
    ``tools.art_gacha_zako_share``；语料缺失时自动跳过）
  - 内置词条池 ``data/art_gacha_pools.json``（槽位混搭 / SSR 蓝图模板）
"""
from __future__ import annotations

import json
import os
import random
import re
from typing import Any

from core.art_gacha_defaults import BUILTIN_GACHA_POOLS
from core.zako_prompt_pool import zako_prompt_pool
from utils import BASE_DIR
from utils.logger import get_logger

logger = get_logger("tools")

DEFAULT_GACHA_POOLS_PATH = os.path.join(BASE_DIR, "data", "art_gacha_pools.json")
SLOT_ORDER = ("composition", "style", "outfit", "action", "setting", "lighting")
_ARG_PATTERN = re.compile(r'\{argument\s+name="([^"]+)"\s+default="([^"]*)"\}')


class ArtGachaStore:
    """加载卡池并抽一句随机提示词。"""

    def __init__(self, json_path: str = DEFAULT_GACHA_POOLS_PATH):
        self.json_path = json_path

    def load(self) -> dict[str, Any]:
        if os.path.isfile(self.json_path):
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    slots = data.get("slots") if isinstance(data.get("slots"), dict) else {}
                    bps = data.get("blueprints") if isinstance(data.get("blueprints"), list) else []
                    if slots or bps:
                        return {"slots": slots, "blueprints": bps}
            except Exception as exc:
                logger.warning(f"[ArtGacha] 读取卡池失败 {self.json_path}: {exc}")
        return {
            "slots": dict(BUILTIN_GACHA_POOLS.get("slots") or {}),
            "blueprints": list(BUILTIN_GACHA_POOLS.get("blueprints") or []),
        }

    # ---------- 外部语料库配置 ----------

    @staticmethod
    def _zako_settings() -> dict[str, Any] | None:
        """外部语料库抽卡配置；未启用或语料缺失时返回 None。"""
        try:
            from config import cfg

            tools = cfg.tools
            enabled = bool(getattr(tools, "art_gacha_zako_enabled", True))
            share = float(getattr(tools, "art_gacha_zako_share", 0.9) or 0.0)
            ratings = getattr(tools, "art_gacha_zako_ratings", "G,S,Q")
            topic = getattr(tools, "art_gacha_zako_topic", "")
            exclude = getattr(tools, "art_gacha_zako_exclude_topics", "")
        except Exception:
            enabled, share, ratings, topic, exclude = True, 0.9, "G,S,Q", "", ""
        if not enabled or share <= 0:
            return None
        if not zako_prompt_pool.available():
            return None
        return {
            "share": max(0.0, min(1.0, share)),
            "ratings": ratings,
            "topic": topic,
            "exclude_topics": exclude,
        }

    # ---------- 内置词条池 ----------

    @staticmethod
    def _slot_prompt(slots_data: dict[str, Any], rng: random.Random) -> str:
        parts: list[str] = [
            "An original cute anime character with expressive luminous eyes and detailed hair strands"
        ]
        for key in ("outfit", "action", "setting", "lighting", "composition", "style"):
            items = slots_data.get(key) if isinstance(slots_data.get(key), list) else []
            valid = [i for i in items if isinstance(i, dict) and str(i.get("text") or "").strip()]
            if not valid:
                continue
            parts.append(str(rng.choice(valid).get("text")).strip())
        parts.append("no unintended transparent background")
        return ", ".join(parts) + "."

    @staticmethod
    def _blueprint_prompt(bp: dict[str, Any], rng: random.Random) -> str:
        template = str(bp.get("template") or "")
        arg_pools = bp.get("arguments") if isinstance(bp.get("arguments"), dict) else {}

        def _replace(match: re.Match) -> str:
            name = match.group(1)
            default_val = match.group(2)
            candidates = arg_pools.get(name)
            if isinstance(candidates, list) and candidates:
                return str(rng.choice(candidates))
            return default_val

        return _ARG_PATTERN.sub(_replace, template).strip()

    # ---------- 抽卡 ----------

    def draw(self, rng: random.Random | None = None) -> dict[str, str]:
        """抽一句随机提示词灵感，返回 ``{"source": ..., "prompt": ...}``。"""
        r = rng or random.Random()
        zako_cfg = self._zako_settings()

        if zako_cfg and r.random() < zako_cfg["share"]:
            picked = zako_prompt_pool.sample(
                rng=r,
                ratings=zako_cfg["ratings"],
                topic=zako_cfg["topic"],
                exclude_topics=zako_cfg["exclude_topics"],
            )
            if picked and picked.get("tag_text"):
                return {"source": "zako", "prompt": str(picked["tag_text"]).strip()}

        data = self.load()
        slots_data = data.get("slots") or {}
        blueprints = [b for b in (data.get("blueprints") or []) if isinstance(b, dict)]
        use_blueprint = bool(blueprints) and (not slots_data or r.random() < 0.5)
        if use_blueprint:
            bp = r.choice(blueprints)
            prompt = self._blueprint_prompt(bp, r)
            if prompt:
                return {"source": "blueprint", "prompt": prompt}
        prompt = self._slot_prompt(slots_data, r)
        return {"source": "slot", "prompt": prompt}


art_gacha_store = ArtGachaStore()
