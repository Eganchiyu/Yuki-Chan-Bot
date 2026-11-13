# core/art_gacha.py
"""二次元提示词抽卡（Prompt Gacha）：槽位盲盒混搭与 SSR 导演大片蓝图。"""
from __future__ import annotations

import json
import os
import random
import re
from typing import Any

from core.art_gacha_defaults import BUILTIN_GACHA_POOLS
from utils import BASE_DIR
from utils.logger import get_logger

logger = get_logger("tools")

DEFAULT_GACHA_POOLS_PATH = os.path.join(BASE_DIR, "data", "art_gacha_pools.json")
SLOT_ORDER = ("composition", "style", "outfit", "action", "setting", "lighting")
SLOT_LABELS = {
    "composition": "镜头构图",
    "style": "时代/媒介画风",
    "outfit": "服饰穿搭",
    "action": "动作神态",
    "setting": "场景环境",
    "lighting": "光影色板",
}
_ARG_PATTERN = re.compile(r'\{argument\s+name="([^"]+)"\s+default="([^"]*)"\}')


class ArtGachaStore:
    """加载并抽取二次元提示词盲盒卡池。"""

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

    def list_blueprints(self) -> list[dict[str, Any]]:
        return list(self.load().get("blueprints") or [])

    @staticmethod
    def _pick_slot_entry(
        items: list[dict[str, Any]],
        lock_val: str | None,
        rng: random.Random,
    ) -> dict[str, str]:
        if lock_val and str(lock_val).strip():
            text = str(lock_val).strip()
            for item in items:
                if isinstance(item, dict) and item.get("label") == text:
                    return {
                        "label": str(item.get("label") or text),
                        "text": str(item.get("text") or ""),
                        "aspect_ratio": str(item.get("aspect_ratio") or ""),
                        "locked": "true",
                    }
            return {"label": f"自定义({text[:18]})", "text": text, "aspect_ratio": "", "locked": "true"}

        valid = [i for i in items if isinstance(i, dict) and str(i.get("text") or "").strip()]
        if not valid:
            return {"label": "", "text": "", "aspect_ratio": "", "locked": "false"}
        picked = rng.choice(valid)
        return {
            "label": str(picked.get("label") or ""),
            "text": str(picked.get("text") or "").strip(),
            "aspect_ratio": str(picked.get("aspect_ratio") or ""),
            "locked": "false",
        }

    @staticmethod
    def _render_blueprint(
        bp: dict[str, Any],
        overrides: dict[str, str] | None,
        rng: random.Random,
    ) -> tuple[str, dict[str, str]]:
        template = str(bp.get("template") or "")
        arg_pools = bp.get("arguments") if isinstance(bp.get("arguments"), dict) else {}
        ov = overrides or {}
        chosen_args: dict[str, str] = {}

        def _replace(match: re.Match) -> str:
            name = match.group(1)
            default_val = match.group(2)
            if name in ov and str(ov[name]).strip():
                val = str(ov[name]).strip()
            else:
                candidates = arg_pools.get(name)
                if isinstance(candidates, list) and candidates:
                    val = str(rng.choice(candidates))
                else:
                    val = default_val
            chosen_args[name] = val
            return val

        rendered = _ARG_PATTERN.sub(_replace, template).strip()
        return rendered, chosen_args

    @staticmethod
    def _build_asset_prefix(matched_assets: list[dict[str, Any]]) -> str:
        if not matched_assets:
            return ""
        if len(matched_assets) == 1:
            a = matched_assets[0]
            name = a.get("owner") or a.get("key")
            desc = str(a.get("description") or "").strip()
            desc_hint = f" ({desc})" if desc else ""
            return (
                f"Keep the exact face, hairstyle, hair color, eye color, and signature accessories of {name}{desc_hint} "
                "from the reference image."
            )
        names = ", ".join(str(a.get("owner") or a.get("key")) for a in matched_assets)
        return (
            f"Include the characters ({names}) from the reference images together, "
            "strictly preserving each character's exact face, hair color, eye color, hairstyle, and signature accessories."
        )

    def draw(
        self,
        *,
        pool: str = "auto",
        blueprint_id: str = "",
        lock: dict[str, str] | None = None,
        matched_assets: list[dict[str, Any]] | None = None,
        rng: random.Random | None = None,
    ) -> dict[str, Any]:
        """抽一发二次元提示词盲盒，返回结构化草稿（绝不直接生成图片）。"""
        r = rng or random.Random()
        data = self.load()
        slots_data = data.get("slots") or {}
        blueprints = data.get("blueprints") or []
        lock_map = {str(k).strip().lower(): str(v) for k, v in (lock or {}).items() if v is not None}
        assets_list = list(matched_assets or [])

        pool_mode = str(pool or "auto").strip().lower()
        if pool_mode not in ("auto", "slot", "blueprint"):
            pool_mode = "auto"

        if blueprint_id:
            pool_mode = "blueprint"
        elif lock_map and pool_mode == "auto":
            pool_mode = "slot"
        elif pool_mode == "auto":
            if blueprints and r.random() < 0.35:
                pool_mode = "blueprint"
            else:
                pool_mode = "slot"

        asset_prefix = self._build_asset_prefix(assets_list)
        asset_keys = [str(a.get("key")) for a in assets_list if a.get("key")]

        if pool_mode == "blueprint" and blueprints:
            target_bp = None
            if blueprint_id:
                bp_norm = str(blueprint_id).strip().lower()
                for bp in blueprints:
                    if str(bp.get("id") or "").lower() == bp_norm or str(bp.get("name") or "").lower() == bp_norm:
                        target_bp = bp
                        break
                if target_bp is None:
                    avail = ", ".join(str(b.get("id")) for b in blueprints)
                    raise ValueError(f"未找到蓝图模板: {blueprint_id}（可选: {avail}）")
            else:
                multi = len(assets_list) >= 2
                preferred = [b for b in blueprints if bool(b.get("multi_character")) == multi]
                candidates = preferred or blueprints
                target_bp = r.choice(candidates)

            rendered_prompt, chosen_args = self._render_blueprint(target_bp, lock_map, r)
            if asset_prefix:
                final_prompt = f"{asset_prefix} {rendered_prompt}"
            else:
                final_prompt = rendered_prompt

            return {
                "mode": "blueprint",
                "rarity": str(target_bp.get("rarity") or "SSR"),
                "card_id": str(target_bp.get("id") or ""),
                "card_name": str(target_bp.get("name") or "导演大片蓝图"),
                "aspect_ratio": str(target_bp.get("aspect_ratio") or "2:3"),
                "chosen_args": chosen_args,
                "slots": {},
                "assets": asset_keys,
                "prompt": final_prompt,
            }

        # 槽位混搭池（SR / R）
        picked_slots: dict[str, dict[str, str]] = {}
        aspect_ratio = "2:3"
        for slot_name in SLOT_ORDER:
            items = slots_data.get(slot_name) if isinstance(slots_data.get(slot_name), list) else []
            picked = self._pick_slot_entry(items, lock_map.get(slot_name), r)
            picked_slots[slot_name] = picked
            if slot_name == "composition" and picked.get("aspect_ratio"):
                aspect_ratio = picked["aspect_ratio"]

        subject_part = (
            asset_prefix
            if asset_prefix
            else "An original cute anime character with expressive luminous eyes and detailed hair strands"
        )
        parts = [subject_part]
        for key in ("outfit", "action", "setting", "lighting", "composition", "style"):
            txt = picked_slots.get(key, {}).get("text", "").strip()
            if txt:
                parts.append(txt)
        parts.append("no unintended transparent background")
        final_prompt = ", ".join(parts) + "."

        rarity = "SR" if len(lock_map) >= 1 else "R"
        return {
            "mode": "slot",
            "rarity": rarity,
            "card_id": "slot-mix",
            "card_name": "二次元灵感槽位盲盒",
            "aspect_ratio": aspect_ratio,
            "chosen_args": {},
            "slots": picked_slots,
            "assets": asset_keys,
            "prompt": final_prompt,
        }

    @staticmethod
    def format_result(result: dict[str, Any]) -> str:
        rarity = result.get("rarity", "SR")
        card_name = result.get("card_name", "提示词盲盒")
        card_id = result.get("card_id", "")
        aspect_ratio = result.get("aspect_ratio", "2:3")
        assets = result.get("assets") or []

        lines = [
            f"【抽卡结果 [{rarity}] {card_name}】"
            + (f" (模板ID: `{card_id}`)" if card_id and card_id != "slot-mix" else ""),
            f"- 推荐画幅 `aspect_ratio`: `{aspect_ratio}`",
        ]
        if assets:
            lines.append(f"- 绑定参考资产 `assets`: {assets}（建议 `input_fidelity=\"high\"`）")

        if result.get("mode") == "slot":
            lines.append("- 抽中词条拆解：")
            slots = result.get("slots") or {}
            for key in SLOT_ORDER:
                item = slots.get(key) or {}
                label = item.get("label") or "-"
                lock_tag = " [已锁定]" if item.get("locked") == "true" else ""
                lines.append(f"  · {SLOT_LABELS.get(key, key)}: {label}{lock_tag}")
        else:
            args = result.get("chosen_args") or {}
            if args:
                arg_str = "；".join(f"{k}={v}" for k, v in args.items())
                lines.append(f"- 抽中蓝图变量：{arg_str}")

        lines.extend([
            "",
            "【抽卡 Prompt 草稿（仅供参考，尚未生图）】",
            result.get("prompt", ""),
            "",
            "提示：这只是抽卡生成的灵感草稿，还没有生成图片。你可以自由修改角色、动作、服装、画面文字或氛围后，再调用 `art_draw` 出图（默认 `background=\"opaque\"` 勿用透明底）。",
        ])
        return "\n".join(lines)


art_gacha_store = ArtGachaStore()
