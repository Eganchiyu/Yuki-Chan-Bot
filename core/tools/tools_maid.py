# core/tools/tools_maid.py
"""小女仆委托工具。"""
from core.maid.maid import MaidCapabilityBoundary, build_maid_task
from core.maid.maid_common import logger
from core.toolchain import ToolResult


async def delegate_to_maid_tool(context, goal, run_inline=False):
    """调用小女仆处理重型任务。"""
    if not goal:
        return ToolResult(success=False, content="缺少任务目标", error="missing_goal")

    boundary = MaidCapabilityBoundary.judge(goal)
    if not boundary["allowed"]:
        return ToolResult(
            success=False,
            content=f"小女仆不建议执行：{boundary['reason']}。{boundary['suggestion']}",
            data=boundary,
            error="capability_boundary_rejected",
        )

    # 旧版允许 run_inline=True 同步等待，但工具链对单次调用只有
    # cfg.timing.tool_call_timeout_seconds（默认 120 秒），而小女仆的任务上限是 900 秒——
    # 同步等必然会超时，把「她已经做完了」变成「工具执行超时」。
    # 现在一律入队后台执行，完成后由 maid_worker / 补报巡检把结果交回会话。
    if run_inline:
        logger.warning("[Maid] delegate_to_maid 收到 run_inline=True，已忽略：改为后台执行")

    task = build_maid_task(goal, context.chat_id, context.mode, source="toolchain")
    await context.yuki.maid_task_queue.put(task)
    context.yuki.maid_current_tasks[context.chat_id] = task
    return ToolResult(success=True, content="已交给小女仆后台处理。")
