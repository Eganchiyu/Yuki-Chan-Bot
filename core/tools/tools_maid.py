# core/tools/tools_maid.py
"""小女仆委托工具。"""
from core.maid.maid import MaidCapabilityBoundary, build_maid_task
from core.toolchain import ToolResult


async def delegate_to_maid_tool(context, goal):
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

    # 一律入队后台执行：工具链单次调用超时（默认 120 秒）远小于小女仆任务上限
    # （900 秒），同步等待只会把「已经做完了」变成「工具执行超时」。
    # 完成后由 maid_worker / 补报巡检把结果交回会话。
    task = build_maid_task(goal, context.chat_id, context.mode, source="toolchain")
    await context.yuki.maid_task_queue.put(task)
    context.yuki.maid_current_tasks[context.chat_id] = task
    return ToolResult(success=True, content="已交给小女仆后台处理。")
