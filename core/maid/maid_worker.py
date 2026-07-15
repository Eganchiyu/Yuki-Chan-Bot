import asyncio

from core.maid.maid_boundary import build_maid_report
from core.maid.maid_common import logger
from core.maid.maid_loop import maid_evolution_loop


async def maid_worker(engine, yuki_state, sender, history_manager):
    """消费小女仆任务，并将结果重新交给会话管线。"""
    while True:
        task = await yuki_state.maid_task_queue.get()
        goal = task["goal"]
        chat_id = str(task["chat_id"])
        mode = task.get("mode", "group")
        yuki_state.maid_current_tasks[chat_id] = goal
        try:
            result_dict = await maid_evolution_loop(user_goal=goal, chat_id=chat_id)
            report = build_maid_report(goal, result_dict)
            history_manager.append_session_message(chat_id, "user", report, is_maid_report=True)
            while not getattr(engine, "napcat_online", True):
                await asyncio.sleep(20)
            if engine.process_callback is not None:
                asyncio.create_task(
                    engine.process_callback(chat_id, mode, debounce_flag=False, force_reply=True)
                )
        except Exception as e:
            logger.error(f"[Maid] 处理任务失败: {e}")
        finally:
            yuki_state.maid_current_tasks.pop(chat_id, None)
            yuki_state.maid_task_queue.task_done()
