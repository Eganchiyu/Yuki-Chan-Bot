"""小女仆后端入口：统一使用宿主侧 DeepSeek Harness（core/maid/maid_harness.py）。

旧版内置 LLM 循环（legacy）已归档至 `_archive/maid_legacy/`。
"""
from core.maid.maid_harness import harness_evolution_loop as maid_evolution_loop

BACKEND = "harness"

__all__ = ["BACKEND", "maid_evolution_loop"]
