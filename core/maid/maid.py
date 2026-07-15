import asyncio

from utils.llm_client import close_global_session

from core.maid.maid_boundary import MaidCapabilityBoundary, build_maid_report, build_maid_task
from core.maid.maid_common import (
    LOGS_DIR,
    MAID_VENV_DIR,
    MAX_MAID_ROUNDS,
    MAX_TOOL_OUTPUT_CHARS,
    SKILLS_DIR,
    TASKS_DIR,
    TERMINAL_DEFAULT_TIMEOUT,
    TERMINAL_MAX_TIMEOUT,
    WORKSPACE_DIR,
    _decode_process_output,
    _extract_json_from_mixed,
    _truncate_text,
    clean_code_block,
    clean_json_output,
    logger,
)
from core.maid.maid_loop import call_cloud_maid_robust, maid_evolution_loop
from core.maid.maid_prompt import MAID_SYSTEM_PROMPT
from core.maid.maid_runtime import (
    _clean_workspace,
    _ensure_maid_env,
    _ensure_skill_deps,
    _is_terminal_command_allowed,
    _kill_process_tree,
    install_package,
    list_skills,
    read_skill,
    run_skill,
    terminal_command_maid,
    write_and_run_temp_skill,
    write_temp_skill,
)
from core.maid.maid_tools import (
    _format_file_size,
    amap_search_maid,
    browser_search_maid,
    list_directory_content,
    manage_timer_task_maid,
    read_file_content,
    search_diary_fast,
)
from core.maid.maid_worker import maid_worker

__all__ = [
    "MaidCapabilityBoundary",
    "build_maid_task",
    "build_maid_report",
    "clean_json_output",
    "call_cloud_maid_robust",
    "maid_worker",
    "SKILLS_DIR",
    "WORKSPACE_DIR",
    "TASKS_DIR",
    "LOGS_DIR",
    "MAID_VENV_DIR",
    "MAX_TOOL_OUTPUT_CHARS",
    "TERMINAL_DEFAULT_TIMEOUT",
    "TERMINAL_MAX_TIMEOUT",
    "MAX_MAID_ROUNDS",
    "_ensure_maid_env",
    "_ensure_skill_deps",
    "_truncate_text",
    "_decode_process_output",
    "_extract_json_from_mixed",
    "_kill_process_tree",
    "_is_terminal_command_allowed",
    "terminal_command_maid",
    "_clean_workspace",
    "MAID_SYSTEM_PROMPT",
    "clean_code_block",
    "write_temp_skill",
    "write_and_run_temp_skill",
    "run_skill",
    "install_package",
    "list_skills",
    "search_diary_fast",
    "read_skill",
    "read_file_content",
    "list_directory_content",
    "_format_file_size",
    "manage_timer_task_maid",
    "browser_search_maid",
    "amap_search_maid",
    "maid_evolution_loop",
]


if __name__ == "__main__":
    async def main():
        try:
            # 2. 使用 await 调用异步的进化循环
            target_task = "请写一个明显阻塞程序运行的代码并运行，比如打开任务管理器，我要测试agent的阻塞保护功能。"
            result = await maid_evolution_loop(target_task)

            # 3. 此时 result 才是真正的字典结果
            if result:
                logger.info(f"\n任务完成! 结果: {result.get('result', '无返回信息')}")
        finally:
            # 4. 无论成功失败，关闭全局 Session 释放资源
            await close_global_session()

    # 5. 启动 asyncio 事件循环
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n[Maid] 用户手动停止了小女仆")
