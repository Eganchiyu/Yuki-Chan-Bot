# core/tools/tools_maid.py
"""小女仆委托 / 叫停工具。"""
from core.maid.maid import MaidCapabilityBoundary, build_maid_task
from core.maid.maid_runtime import runtime_of
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
    # （480 秒），同步等待只会把「已经做完了」变成「工具执行超时」。
    # 完成后由 maid_worker / 补报巡检把结果交回会话。
    task = build_maid_task(goal, context.chat_id, context.mode, source="toolchain")
    runtime = runtime_of(context.yuki)
    record = runtime.register(
        goal=goal, chat_id=str(context.chat_id), mode=context.mode, source="toolchain"
    )
    task["uid"] = record.uid
    await context.yuki.maid_task_queue.put(task)
    context.yuki.maid_current_tasks[context.chat_id] = task

    active = runtime.active_for_chat(context.chat_id)
    return ToolResult(
        success=True,
        content=(
            f"已把 {record.label()} 交给小女仆后台处理（本会话同时在做 {len(active)} 个，"
            "可以继续派新的并行任务）。完成后她会自己汇报；想临时叫停就用 stop_maid。"
        ),
        data={"task_id": record.short_id, "uid": record.uid, "active": len(active)},
    )


async def stop_maid_tool(context, task_id="", keyword=""):
    """强制叫停正在跑的小女仆任务（默认停本会话全部）。"""
    runtime = runtime_of(context.yuki)
    matched, active = runtime.find(context.chat_id, task_id=task_id, keyword=keyword)

    if not active:
        return ToolResult(success=True, content="现在没有在跑的小女仆任务，没什么可叫停的。")
    if not matched:
        listing = "、".join(record.label() for record in sorted(active, key=lambda r: r.seq))
        return ToolResult(
            success=False,
            content=f"没找到匹配的小女仆任务。现在在跑的是：{listing}",
            error="maid_task_not_found",
            data={"active": [record.short_id for record in active]},
        )

    labels = runtime.request_cancel(matched)
    remaining = len(runtime.live_for_chat(context.chat_id))
    tail = f"还有 {remaining} 个在跑。" if remaining else "本会话的小女仆已经全部停下了。"
    return ToolResult(
        success=True,
        content=f"已经从后台强制叫停：{'、'.join(labels)}，进程直接取消，她不会再汇报这件事。{tail}",
        data={"cancelled": labels, "remaining": remaining},
    )
