# core/focus/domains/__init__.py
"""已内置的聚焦模式域集合。"""
from core.focus.domains.art import (
    ART,
    art_asset_tool,
    art_draw_tool,
    art_finish_tool,
    art_gacha_tool,
    art_start_tool,
)
from core.focus.domains.phone import PHONE, phone_finish_tool, phone_start_tool

__all__ = [
    "PHONE",
    "phone_start_tool",
    "phone_finish_tool",
    "ART",
    "art_start_tool",
    "art_draw_tool",
    "art_gacha_tool",
    "art_asset_tool",
    "art_finish_tool",
]
