import asyncio
import json
import os
import time
from datetime import datetime

from config import cfg
from utils.llm_client import llm_chat

from core.maid import maid_common, maid_memory
from core.maid.maid_worklog import list_previous_work, read_work_trace
from core.maid.maid_common import (
    LOGS_DIR,
    MAX_MAID_ERRORS,
    MAX_MAID_ROUNDS,
    TERMINAL_DEFAULT_TIMEOUT,
    clean_code_block,
    clean_json_output,
    logger,
    _truncate_text,
)
from core.maid.maid_prompt import MAID_SYSTEM_PROMPT
from core.maid.maid_selfevolve import (
    propose_patch,
    read_last_result,
    request_restart,
    request_self_reload,
    verify_patch,
)
from core.maid.maid_runtime import (
    _clean_workspace,
    prepare_image_message,
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


def _degrade_image_message(message, note="[图片内容已过期，本轮不再附上]"):
    """把带图消息压成纯文本，避免同一张图在多轮里反复占用上下文。"""
    content = message.get("content")
    if not isinstance(content, list):
        return
    texts = [
        str(block.get("text") or "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    message["content"] = (" ".join(t for t in texts if t) or "[图片]") + " " + note


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


async def maid_evolution_loop(user_goal: str, chat_id: str = None, approver=None):
    task_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    today_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file = f"{LOGS_DIR}/trace_{task_id}.md"

    # [新改动] 追踪本次任务生成的临时技能文件
    created_skill_files = []

    current_skills = list_skills()
    startup_context = await maid_memory.build_startup_context()
    initial_user = (
        f"\n[系统环境]：当前真实时间是 {today_str}。如果任务涉及时间推算（如'今天'、'昨天'），请以此为准。\n"
        f"特别说明：（如果涉及发送图片到群聊的任务，只需要保存文件，并最终返回该文件的绝对路径，说明这个图片可以被发送即可，不用执行发送）\n"
        f"当前目标：{user_goal}\n当前技能列表：{current_skills}"
    )
    if startup_context:
        initial_user += f"\n\n[历史上下文]\n{startup_context}"
    messages = [
        {"role": "system", "content": MAID_SYSTEM_PROMPT},
        {"role": "user", "content": initial_user},
    ]

    logger.info(f"[Maid] 任务启动: {user_goal}")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"# 小女仆任务追踪: {task_id}\n\n**任务目标**: {user_goal}（如果涉及发送图片到群聊的任务，只需要保存文件，并最终返回该文件的绝对路径，说明这个图片可以被发送即可，不用执行发送）\n\n---\n")

    last_step = {"round": 0, "thought": "尚未开始", "tool": None, "result": "还没有执行任何工具。"}
    started_at = today_str

    start_time = time.monotonic()
    wall_budget = maid_common.MAID_MAX_WALL_SECONDS
    rounds_done = 0
    error_rounds = 0
    resume_used = False
    stopped_reason = ""
    image_messages = []
    image_rounds = {}

    while True:
        if rounds_done >= MAX_MAID_ROUNDS:
            stopped_reason = f"已用完 {MAX_MAID_ROUNDS} 个有效轮"
            break
        if error_rounds >= MAX_MAID_ERRORS:
            stopped_reason = f"网络/解析错误达到 {MAX_MAID_ERRORS} 次"
            break
        elapsed = time.monotonic() - start_time
        if elapsed >= wall_budget:
            stopped_reason = f"墙钟超时（已耗时 {int(elapsed)}s，上限 {int(wall_budget)}s）"
            break

        for image_message in list(image_messages):
            if image_rounds.get(id(image_message), 0) < rounds_done:
                _degrade_image_message(image_message)
                image_messages.remove(image_message)
                image_rounds.pop(id(image_message), None)

        pending_image = None
        round_no = rounds_done + 1
        logger.info(
            f"[Maid] 有效轮 {round_no}/{MAX_MAID_ROUNDS}，错误 {error_rounds}/{MAX_MAID_ERRORS}，"
            f"已耗时 {elapsed:.0f}s"
        )

        # 调用稳健 API。进度只作为本轮即时状态，不永久堆入上下文。
        progress_msg = {
            "role": "user",
            "content": f"[系统进度] 当前是第 {round_no}/{MAX_MAID_ROUNDS} 个有效轮，网络/解析错误已发生 {error_rounds}/{MAX_MAID_ERRORS} 次。请据此控制步骤；如果剩余轮次不足，优先返回当前状态和已获得的结果，不要无声耗尽轮次。"
        }
        messages.append(progress_msg)
        content = await call_cloud_maid_robust(messages)
        messages.pop()

        if f"{cfg.ROBOT_NAME.title()} 好像有点不舒服" in content:
            error_rounds += 1
            logger.warning(
                f"[Maid] LLM 调用失败（{error_rounds}/{MAX_MAID_ERRORS}），本轮不计入有效轮"
            )
            messages.append({
                "role": "user",
                "content": "[系统] 上一条请求没有返回有效内容（线路/网络问题）。本轮不计入任务轮次，请直接重新输出 JSON。",
            })
            await asyncio.sleep(min(3 * error_rounds, 15))
            continue

        try:
            call = json.loads(content)
        except json.JSONDecodeError:
            error_rounds += 1
            logger.warning(
                f"[Maid] JSON 解析失败（{error_rounds}/{MAX_MAID_ERRORS}），本轮不计入有效轮"
            )
            messages.append({"role": "user", "content": "错误：请务必输出纯净的 JSON 格式。"})
            continue

        thought = call.get("thought", "思考中...")
        tool = call.get("tool")
        args = call.get("args", {})
        rounds_done += 1

        logger.info(f"[Maid] 思考: {thought}")
        logger.info(f"[Maid] 动作: {tool}")

        try:
            if tool == "list_skills":
                res = list_skills()
            elif tool == "write_temp_skill":  # 改为 temp
                skill_name = args.get('name')
                res = write_temp_skill(skill_name, clean_code_block(args.get('code', '')))
            elif tool == "write_and_run_temp_skill":
                skill_name = args.get('name')
                res = await write_and_run_temp_skill(
                    skill_name,
                    clean_code_block(args.get('code', '')),
                    timeout=args.get('timeout'),
                    interpreter=args.get('interpreter'),
                )
            elif tool == "write_skill":
                # 兼容旧提示词/旧模型输出：现在统一写入临时技能，避免任务中随手污染固化 skills。
                skill_name = args.get('name')
                res = write_temp_skill(skill_name, clean_code_block(args.get('code', '')))
            elif tool == "run_skill":
                res = await run_skill(
                    args.get('name'),
                    timeout=args.get('timeout'),
                    interpreter=args.get('interpreter'),
                )
            elif tool == "install_package":
                pkg_name = args.get('pkg') or args.get('pkg_name')
                logger.info(f"[Maid] 正在安装依赖: {pkg_name}")
                res = await install_package(pkg_name.strip()) if pkg_name else "错误：未提供包名"
            elif tool == "terminal":
                command = args.get("command", "")
                cwd = args.get("cwd")
                timeout = args.get("timeout", TERMINAL_DEFAULT_TIMEOUT)
                allow_write = bool(args.get("allow_write", True))
                logger.info(f"[Maid] 终端执行: {command} (cwd={cwd or os.getcwd()}, allow_write={allow_write})")
                res = await terminal_command_maid(
                    command=command,
                    cwd=cwd,
                    timeout=timeout,
                    allow_write=allow_write,
                    approver=approver,
                    thought=thought,
                )
            elif tool == "read_skill":
                skill_name = args.get('name')
                logger.info(f"[Maid] 正在查阅技能源码: {skill_name}")
                res = read_skill(skill_name)
            elif tool == "read_image":
                image_path = args.get("path") or args.get("file_path")
                question = args.get("question")
                logger.info(f"[Maid] 正在读取图片: {image_path}")
                res, image_message = await prepare_image_message(image_path, question)
                if image_message is not None:
                    pending_image = image_message
                    image_messages.append(image_message)
                    image_rounds[id(image_message)] = rounds_done
            elif tool == "resume_task":
                target_id = args.get("task_id") or None
                state = {} if resume_used else await maid_memory.resume_state(target_id)
                if resume_used:
                    res = "本次任务已经恢复过一次快照，不能重复恢复。请基于当前上下文继续。"
                elif not state:
                    res = "没有可恢复的任务快照。"
                else:
                    restored_from = state.get("task_id")
                    messages = maid_memory.build_resumed_messages(state, MAID_SYSTEM_PROMPT, user_goal)
                    rounds_done = max(rounds_done, int(state.get("round") or 0))
                    last_step = state.get("last_step") or last_step
                    resume_used = True
                    logger.info(f"[Maid] 从快照恢复任务: {restored_from}（第 {rounds_done} 轮）")
                    res = f"已从任务 {restored_from} 的快照恢复上下文，有效轮从 {rounds_done} 继续。"
            elif tool == "read_file":
                file_path = args.get('path') or args.get('file_path')
                max_lines = args.get('max_lines', 500)
                offset = args.get('offset', 0)
                logger.info(f"[Maid] 正在读取文件: {file_path} (offset={offset})")
                res = read_file_content(file_path, max_lines, offset)
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
            elif tool == "propose_patch":
                logger.info("[Maid] 自改：写入候选补丁")
                res = propose_patch(
                    task_id,
                    args.get("files"),
                    summary=args.get("summary", ""),
                )
            elif tool == "verify_patch":
                logger.info("[Maid] 自改：快速自检")
                res = verify_patch(task_id)
            elif tool == "request_self_reload":
                logger.info("[Maid] 自改：请求生效（等待审查/校验结果）")
                res = await request_self_reload(
                    task_id,
                    summary=args.get("summary", ""),
                    reason=args.get("reason", ""),
                    wait_seconds=args.get("wait_seconds") or 180,
                )
            elif tool == "restart_yuki":
                logger.info("[Maid] 请求重启 Yuki 容器")
                res = request_restart(
                    task_id,
                    reason=args.get("reason", ""),
                )
            elif tool == "list_previous_work":
                logger.info("[Maid] 查询历史工作记录")
                res = list_previous_work(
                    keyword=args.get("keyword"),
                    limit=args.get("limit", 8),
                )
            elif tool == "read_work_trace":
                logger.info(f"[Maid] 读取历史轨迹: {args.get('task_id')}")
                res = read_work_trace(
                    args.get("task_id"),
                    max_chars=args.get("max_chars", 4000),
                )
            elif tool == "read_evolution_result":
                res = read_last_result(args.get("task_id"))
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

                elapsed_used = time.monotonic() - start_time
                await maid_memory.append_task_index(
                    task_id=task_id,
                    goal=user_goal,
                    status="finished",
                    result=reason,
                    rounds=rounds_done,
                    elapsed=elapsed_used,
                    chat_id=chat_id,
                )
                await maid_memory.delete_task_state(task_id)
                return {
                    "status": "finished",
                    "result": reason,
                    "goal": user_goal,
                    "task_id": task_id,
                    "rounds": rounds_done,
                    "elapsed": round(elapsed_used, 1),
                    "trace": log_file,
                    "state": "",
                }
            else:
                res = f"错误：未知工具 {tool}"

            last_step = {"round": rounds_done, "thought": thought, "tool": tool, "result": _truncate_text(res, 3000)}

            # 写入日志文件
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"### 步骤 {rounds_done}\n**思考**: {thought}\n\n**动作**: `{tool}`({args})\n\n**结果**: \n{res}\n\n")

            messages.append({"role": "assistant", "content": content})
            feedback = f"执行结果：\n{res}"
            if "NameError" in str(res):
                feedback += "\n[系统提示]: 你似乎忘记在代码中 'import' 必要的库了。"

            messages.append({"role": "user", "content": feedback})
            if pending_image is not None:
                messages.append(pending_image)

            await maid_memory.save_task_state(
                task_id=task_id,
                goal=user_goal,
                messages=messages,
                round_no=rounds_done,
                last_step=last_step,
                chat_id=chat_id,
                created_at=started_at,
            )

        except Exception as e:
            logger.error(f"[Maid] 运行异常: {str(e)}")
            messages.append({"role": "user", "content": f"运行中发生异常：{str(e)}（如果任务涉及发送图片任务，只需要保存文件，并在finish中返回该文件的绝对路径，说明这个图片可以被发送即可）"})

    # 超时清理
    try:
        _clean_workspace()
    except Exception as e:
        logger.error(f"[Maid] 清理草稿区失败: {e}")

    elapsed_total = time.monotonic() - start_time
    state_path = await maid_memory.save_task_state(
        task_id=task_id,
        goal=user_goal,
        messages=messages,
        round_no=rounds_done,
        last_step=last_step,
        chat_id=chat_id,
        status="interrupted",
        created_at=started_at,
    )
    timeout_result = (
        f"任务中止（{stopped_reason}）。有效轮 {rounds_done}/{MAX_MAID_ROUNDS}，"
        f"错误 {error_rounds}/{MAX_MAID_ERRORS}，耗时 {int(elapsed_total)}s。"
        f"最后进度：第 {last_step['round']} 轮，动作={last_step['tool']}，"
        f"思考={last_step['thought']}，结果={last_step['result']}"
        f"（快照已保留，可用 resume_task 继续）"
    )
    await maid_memory.append_task_index(
        task_id=task_id,
        goal=user_goal,
        status="timeout",
        result=timeout_result,
        rounds=rounds_done,
        elapsed=elapsed_total,
        chat_id=chat_id,
        state_path=state_path,
    )
    return {
        "status": "timeout",
        "result": timeout_result,
        "goal": user_goal,
        "task_id": task_id,
        "rounds": rounds_done,
        "elapsed": round(elapsed_total, 1),
        "trace": log_file,
        "state": state_path,
    }
