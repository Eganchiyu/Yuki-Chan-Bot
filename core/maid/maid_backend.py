"""小女仆后端选择。

- harness（默认）：执行交给宿主侧的 DeepSeek Harness（core/maid/maid_harness.py）
- legacy：原来的内置 LLM 循环（core/maid/maid_loop.py）

保留 legacy 是为了出问题时一条命令回退，不需要改代码：
    YUKI_MAID_BACKEND=legacy docker restart yuki
两个后端返回的任务结果结构一致，上层（报告、记忆、队列）不用区分。
"""
import os

BACKEND = (os.environ.get("YUKI_MAID_BACKEND") or "harness").strip().lower()

if BACKEND == "legacy":
    from core.maid.maid_loop import maid_evolution_loop as _legacy_loop

    async def maid_evolution_loop(user_goal, chat_id=None, approver=None, mode=None, **kwargs):
        """legacy 不需要 mode（它只靠 chat_id 决定回报对象），但签名要保持一致。"""
        return await _legacy_loop(user_goal, chat_id, approver)
else:
    from core.maid.maid_harness import harness_evolution_loop as maid_evolution_loop

__all__ = ["BACKEND", "maid_evolution_loop"]
