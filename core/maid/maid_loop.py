import json
import os
from datetime import datetime

from config import cfg
from utils.llm_client import llm_chat

from core.maid.maid_common import (
    LOGS_DIR,
    MAX_MAID_ROUNDS,
    TERMINAL_DEFAULT_TIMEOUT,
    clean_code_block,
    clean_json_output,
    logger,
    _truncate_text,
)
from core.maid.maid_prompt import MAID_SYSTEM_PROMPT
from core.maid.maid_runtime import (
    _clean_workspace,
    install_package,
    list_skills,
    read_skill,
    run_skill,
    terminal_command_maid,
    write_and_run_temp_skill,
    write_temp_skill,
)
from core.maid.maid_tools import (
    amap_search_maid,
    browser_search_maid,
    list_directory_content,
    manage_timer_task_maid,
    read_file_content,
    search_diary_fast,
)


async def call_cloud_maid_robust(messages):
    """调用 LLM 完成小女仆任务。"""
    # 强制要求 JSON 格式输出
    payload_kwargs = {
        "response_format": {"type": "json_object"},
        "temperature": 0.3
    }

    result = await llm_chat(
        messages=messages,
        model=cfg.LLM_MODEL,
        **payload_kwargs
    )

    # 清洗可能存在的 Markdown 标签
    return clean_json_output(result)


async def maid_evolution_loop(user_goal: str, chat_id: str = None):
    task_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    today_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file = f"{LOGS_DIR}/trace_{task_id}.md"

    # [新改动] 追踪本次任务生成的临时技能文件
    created_skill_files = []

    current_skills = list_skills()
    messages = [
        {"role": "system", "content": MAID_SYSTEM_PROMPT},
        {"role": "user", "content": f"\n[系统环境]：当前真实时间是 {today_str}。如果任务涉及时间推算（如'今天'、'昨天'），请以此为准。\n特别说明：（如果涉及发送图片到群聊的任务，只需要保存文件，并最终返回该文件的绝对路径，说明这个图片可以被发送即可，不用执行发送）\n当前目标：{user_goal}\n当前技能列表：{current_skills}"}
    ]

    logger.info(f"[Maid] 任务启动: {user_goal}")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"# 小女仆任务追踪: {task_id}\n\n**任务目标**: {user_goal}（如果涉及发送图片到群聊的任务，只需要保存文件，并最终返回该文件的绝对路径，说明这个图片可以被发送即可，不用执行发送）\n\n---\n")

    last_step = {"round": 0, "thought": "尚未开始", "tool": None, "result": "还没有执行任何工具。"}

    for i in range(1, MAX_MAID_ROUNDS + 1):
        remaining_rounds = MAX_MAID_ROUNDS - i
        logger.info(f"[Maid] 第 {i}/{MAX_MAID_ROUNDS} 轮决策，剩余 {remaining_rounds} 轮")

        # 调用稳健 API。进度只作为本轮即时状态，不永久堆入上下文。
        progress_msg = {
            "role": "user",
            "content": f"[系统进度] 当前是第 {i}/{MAX_MAID_ROUNDS} 轮决策，剩余 {remaining_rounds} 轮。请据此控制步骤；如果剩余轮次不足，优先返回当前状态和已获得的结果，不要无声耗尽轮次。"
        }
        messages.append(progress_msg)
        content = await call_cloud_maid_robust(messages)
        messages.pop()

        if f"{cfg.ROBOT_NAME.title()} 好像有点不舒服" in content:
            logger.error("[Maid] 线路全线崩溃，停止尝试")
            break

        try:
            call = json.loads(content)
            thought = call.get("thought", "思考中...")
            tool = call.get("tool")
            args = call.get("args", {})

            logger.info(f"[Maid] 思考: {thought}")
            logger.info(f"[Maid] 动作: {tool}")

            if tool == "list_skills":
                res = list_skills()
            elif tool == "write_temp_skill":  # 改为 temp
                skill_name = args.get('name')
                res = write_temp_skill(skill_name, clean_code_block(args.get('code', '')))
            elif tool == "write_and_run_temp_skill":
                skill_name = args.get('name')
                res = await write_and_run_temp_skill(skill_name, clean_code_block(args.get('code', '')))
            elif tool == "write_skill":
                # 兼容旧提示词/旧模型输出：现在统一写入临时技能，避免任务中随手污染固化 skills。
                skill_name = args.get('name')
                res = write_temp_skill(skill_name, clean_code_block(args.get('code', '')))
            elif tool == "run_skill":
                res = await run_skill(args.get('name'))
            elif tool == "install_package":
                pkg_name = args.get('pkg') or args.get('pkg_name')
                logger.info(f"[Maid] 正在安装依赖: {pkg_name}")
                res = await install_package(pkg_name.strip()) if pkg_name else "错误：未提供包名"
            elif tool == "terminal":
                command = args.get("command", "")
                cwd = args.get("cwd")
                timeout = args.get("timeout", TERMINAL_DEFAULT_TIMEOUT)
                allow_write = bool(args.get("allow_write", False))
                logger.info(f"[Maid] 终端执行: {command} (cwd={cwd or os.getcwd()}, allow_write={allow_write})")
                res = await terminal_command_maid(command=command, cwd=cwd, timeout=timeout, allow_write=allow_write)
            elif tool == "read_skill":
                skill_name = args.get('name')
                logger.info(f"[Maid] 正在查阅技能源码: {skill_name}")
                res = read_skill(skill_name)
            elif tool == "read_file":
                file_path = args.get('path') or args.get('file_path')
                max_lines = args.get('max_lines', 500)
                logger.info(f"[Maid] 正在读取文件: {file_path}")
                res = read_file_content(file_path, max_lines)
            elif tool == "list_directory":
                dir_path = args.get('path') or args.get('dir_path') or "."
                show_hidden = args.get('show_hidden', False)
                logger.info(f"[Maid] 列出目录: {dir_path}")
                res = list_directory_content(dir_path, show_hidden)
            elif tool == "search_diary":
                date_str = args.get('date_str')
                keyword = args.get('keyword')
                logger.info(f"[Maid] 搜索日记: 日期={date_str} 关键词={keyword}")
                res = search_diary_fast(date_str, keyword)
            elif tool == "browser_search":
                query = args.get('query')
                max_results = args.get('max_results', 5)
                search_depth = args.get('search_depth', 'basic')
                logger.info(f"[Maid] 网页搜索: {query}")
                res = await browser_search_maid(query, max_results, search_depth)
            elif tool == "amap_search":
                keywords = args.get('keywords')
                search_type = args.get('search_type', 'text')
                location = args.get('location')
                address = args.get('address')
                city = args.get('city')
                radius = args.get('radius', 3000)
                page_size = args.get('page_size', 10)
                logger.info(f"[Maid] 高德地图搜索: {keywords} ({search_type})")
                res = await amap_search_maid(keywords, search_type, location, address, city, radius, page_size)
            elif tool == "manage_timer_task":
                title = args.get('title')
                due_time = args.get('due_time')
                delay_seconds = args.get('delay_seconds')
                action = args.get('action', 'create')
                task_id = args.get('task_id')
                message = args.get('message')
                logger.info(f"[Maid] 定时任务: {action} - {title}")
                res = await manage_timer_task_maid(title, due_time, delay_seconds, action, task_id, message)
            elif tool == "agently_list_messages":
                limit = args.get("limit", 10)
                folder = args.get("folder", "inbox")
                logger.info(f"[Maid] 查看收件箱: limit={limit}, folder={folder}")
                res = await agently_list_messages(limit=limit, folder=folder)
            elif tool == "agently_read_message":
                message_id = args.get("message_id", "")
                logger.info(f"[Maid] 读取邮件: {message_id}")
                res = await agently_read_message(message_id)
            elif tool == "agently_send_email":
                to = args.get("to", "")
                subject = args.get("subject", "")
                body = args.get("body", "")
                logger.info(f"[Maid] 发送邮件: to={to}, subject={subject}")
                res = await agently_send_email(to=to, subject=subject, body=body)
            elif tool == "finish":
                reason = args.get('reason', '任务完成')
                logger.info(f"[Maid] 任务达成: {reason}")

                # === 任务结束：清理战场 ===
                try:
                    _clean_workspace()
                except Exception as e:
                    logger.error(f"[Maid] 清理草稿区失败: {e}")

                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(f"### 任务完成\n**结果**: {reason}\n")
                return {"status": "finished", "result": reason, "goal": user_goal}
            else:
                res = f"错误：未知工具 {tool}"

            last_step = {"round": i, "thought": thought, "tool": tool, "result": _truncate_text(res, 3000)}

            # 写入日志文件
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"### 步骤 {i}\n**思考**: {thought}\n\n**动作**: `{tool}`({args})\n\n**结果**: \n{res}\n\n")

            messages.append({"role": "assistant", "content": content})
            feedback = f"执行结果：\n{res}"
            if "NameError" in str(res):
                feedback += "\n[系统提示]: 你似乎忘记在代码中 'import' 必要的库了。"

            messages.append({"role": "user", "content": feedback})

        except json.JSONDecodeError:
            logger.warning("[Maid] JSON 解析失败，反馈给模型重试")
            messages.append({"role": "user", "content": "错误：请务必输出纯净的 JSON 格式。"})
        except Exception as e:
            logger.error(f"[Maid] 运行异常: {str(e)}")
            messages.append({"role": "user", "content": f"运行中发生异常：{str(e)}（如果任务涉及发送图片任务，只需要保存文件，并在finish中返回该文件的绝对路径，说明这个图片可以被发送即可）"})

    # 超时清理
    try:
        _clean_workspace()
    except Exception as e:
        logger.error(f"[Maid] 清理草稿区失败: {e}")

    timeout_result = (
        f"任务处理超时（已用完 {MAX_MAID_ROUNDS} 轮）。"
        f"最后进度：第 {last_step['round']} 轮，动作={last_step['tool']}，"
        f"思考={last_step['thought']}，结果={last_step['result']}"
    )
    return {"status": "timeout", "result": timeout_result, "goal": user_goal}
