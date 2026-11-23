"""小女仆后台消费队列：并行执行 + 可被 Yuki 强制叫停。

和旧版的区别：
    - 旧版是一条串行 while 循环，一个任务从头跑到尾才接下一个，也没有办法中断；
    - 现在每取到一个任务就开一个独立协程，最多 MAID_MAX_CONCURRENT 个同时跑，
      任务元数据登记在 MaidRuntime 里，stop_maid 能按编号/关键词直接叫停。
"""
import asyncio

from core.maid.maid_backend import maid_evolution_loop
from core.maid.maid_boundary import build_maid_report
from core.maid.maid_common import MAID_MAX_CONCURRENT, logger
from core.maid.maid_resume import mark_reported
from core.maid.maid_runtime import runtime_of


async def maid_worker(engine, yuki_state, sender, history_manager):
    """消费小女仆任务队列，每个任务一个协程并行跑。"""
    del sender
    runtime = runtime_of(yuki_state)
    semaphore = asyncio.Semaphore(MAID_MAX_CONCURRENT)
    running: set = set()
    logger.info(f"[Maid] 队列已启动（最多 {MAID_MAX_CONCURRENT} 个并行）")
    while True:
        task = await yuki_state.maid_task_queue.get()
        record = runtime.get(task.get("uid")) if isinstance(task, dict) else None
        if record is not None and record.cancel_requested:
            # 还没开跑就被叫停：直接丢掉，不占用并发位
            runtime.mark(record.uid, "cancelled")
            runtime.remove(record.uid)
            yuki_state.maid_task_queue.task_done()
            logger.info(f"[Maid] {record.chat_id} {record.label()} 排队阶段被叫停，跳过")
            continue
        worker = asyncio.create_task(
            _run_maid_task(engine, yuki_state, history_manager, task, runtime, semaphore)
        )
        running.add(worker)
        worker.add_done_callback(running.discard)


async def _run_maid_task(engine, yuki_state, history_manager, task, runtime, semaphore):
    """跑一个小女仆任务：拿并发位 → 跑 harness → 汇报（被叫停则不汇报）。"""
    goal = task["goal"]
    chat_id = str(task["chat_id"])
    mode = task.get("mode", "group")
    uid = str(task.get("uid") or "")
    record = runtime.get(uid)
    if record is not None:
        runtime.attach_handler(uid, asyncio.current_task())
    acquired = False
    try:
        await semaphore.acquire()
        acquired = True
        if record is not None and record.cancel_requested:
            return
        if record is not None:
            runtime.mark(uid, "running")
        _remember_chat_state(yuki_state, chat_id, goal, mode)
        result_dict = await maid_evolution_loop(
            user_goal=goal, chat_id=chat_id, mode=mode, task_handle=record
        )
        if record is not None and (record.cancel_requested
                                   or str(result_dict.get("status")) == "cancelled"):
            logger.info(f"[Maid] {chat_id} 任务已叫停，不做汇报: {goal[:40]}")
            return
        report = build_maid_report(goal, result_dict)
        history_manager.append_session_message(chat_id, "user", report, is_maid_report=True)
        # 打上「已汇报」标记，重启后的补报巡检不会重复说一遍
        mark_reported(result_dict.get("task_id"))
        while not getattr(engine, "napcat_online", True):
            await asyncio.sleep(20)
        if engine.process_callback is not None:
            asyncio.create_task(
                engine.process_callback(chat_id, mode, debounce_flag=False, force_reply=True)
            )
    except asyncio.CancelledError:
        logger.info(f"[Maid] {chat_id} 任务被强制叫停（协程已取消）: {goal[:40]}")
        if record is not None and record.cancel_requested and record.dsh_task_id:
            # 兜底：harness 没来得及落标记时也要让宿主杀掉 dsh，并标记「不用汇报」
            from core.maid.maid_runtime import _mark_host_cancel
            _mark_host_cancel(record.dsh_task_id)
        raise
    except Exception as e:
        logger.error(f"[Maid] 处理任务失败: {e}")
    finally:
        if acquired:
            semaphore.release()
        if record is not None:
            runtime.remove(uid)
        _forget_chat_state(yuki_state, runtime, chat_id)
        yuki_state.maid_task_queue.task_done()


def _remember_chat_state(yuki_state, chat_id, goal, mode):
    """兼容旧字段：/查询、上下文快照仍读 maid_current_tasks。"""
    del mode
    yuki_state.maid_current_tasks[chat_id] = goal


def _forget_chat_state(yuki_state, runtime, chat_id):
    """本会话还有别的任务在跑就留着，否则清掉兼容字段。"""
    if runtime.active_for_chat(chat_id):
        return
    try:
        yuki_state.maid_current_tasks.pop(chat_id, None)
    except AttributeError:
        pass
