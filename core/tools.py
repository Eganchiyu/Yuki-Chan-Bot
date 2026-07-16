# core/tools.py
import asyncio
import datetime
import os
import re
from urllib.parse import quote_plus

import aiohttp

from config import cfg
from core.maid.maid import MaidCapabilityBoundary, build_maid_task, maid_evolution_loop, search_diary_fast
from core.toolchain import ToolResult, ToolSpec
from modules.shot_memory import ShotMemoryStore, render_snapshot, shot_live_buffer
from modules.system_state import monitor as system_state_monitor
from utils.logger import get_logger

logger = get_logger("tools")
shot_memory_store = ShotMemoryStore()


async def get_master_status_tool(context):
    data = system_state_monitor.master_status()
    return ToolResult(
        success=True,
        content=(
            f"主人在线：{data['online']}，活跃：{data['active']}，"
            f"当前窗口：{data['foreground_window'] or '未知'}"
        ),
        data=data,
    )

_TIMER_TASKS_KEY = "__timer_tasks__"
_TIMER_HANDLES_KEY = "__timer_handles__"
_TAVILY_SEARCH_URL = "https://api.tavily.com/search"
_AMAP_AROUND_URL = "https://restapi.amap.com/v5/place/around"
_AMAP_TEXT_URL = "https://restapi.amap.com/v5/place/text"
_AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"


def _timer_store(context):
    return context.yuki.maid_current_tasks.setdefault(_TIMER_TASKS_KEY, {})


def _timer_handles(context):
    return context.yuki.maid_current_tasks.setdefault(_TIMER_HANDLES_KEY, {})


def _parse_due_time(due_time=None, delay_seconds=None):
    """解析绝对或相对时间，返回触发时间与等待秒数。"""
    now = datetime.datetime.now()
    if delay_seconds is not None:
        delay = max(0.0, float(delay_seconds))
        return now + datetime.timedelta(seconds=delay), delay

    if not due_time:
        raise ValueError("missing_due_time")

    text = str(due_time).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            due_at = datetime.datetime.strptime(text, fmt)
            return due_at, max(0.0, (due_at - now).total_seconds())
        except ValueError:
            pass

    due_at = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    if due_at.tzinfo is not None:
        due_at = due_at.astimezone().replace(tzinfo=None)
    return due_at, max(0.0, (due_at - now).total_seconds())


async def _timer_wake_worker(context, task_id, delay_seconds):
    """到点后把定时事件写入群聊缓冲，并触发主 LLM 回复流程。"""
    try:
        await asyncio.sleep(delay_seconds)
        tasks = _timer_store(context)
        task = tasks.get(task_id)
        if not task or task.get("status") == "cancelled":
            return

        task["status"] = "triggered"
        task["triggered_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        chat_id = task["chat_id"]
        reminder = task.get("message") or task["title"]
        message_obj = {
            "content": f"【定时任务到点】{reminder}",
            "time": task["triggered_at"],
            "is_timer_event": True,
        }

        callback = context.metadata.get("process_callback") or getattr(context.yuki, "process_callback", None)
        if callback is None:
            logger.warning(f"[Timer] process_callback 未设置，无法触发回复: {task_id}")
            return
        asyncio.create_task(
            callback(
                chat_id,
                task.get("mode", "group"),
                message_obj=message_obj,
                debounce_flag=False,
                force_reply=True,
            )
        )
        logger.info(f"[Timer] 已经通过主管道触发定时任务: {task_id} chat_id={chat_id}")
    finally:
        _timer_handles(context).pop(task_id, None)


async def search_diary_tool(context, date_str=None, keyword=None):
    """查询 Yuki 日记。"""
    logger.info(
        f"[ToolCall][search_diary] chat_id={context.chat_id} date_str={date_str} keyword={keyword}"
    )
    if not date_str and not keyword:
        return ToolResult(success=False, content="请至少提供日期或关键词。", error="missing_date_or_keyword")
    result = await asyncio.to_thread(search_diary_fast, date_str, keyword)
    return ToolResult(success=True, content=result)


async def manage_timer_task_tool(
    context,
    title=None,
    due_time=None,
    delay_seconds=None,
    action="create",
    task_id=None,
    message=None,
):
    """为当前群聊/私聊创建、取消或列出精确定时任务。"""
    tasks = _timer_store(context)
    handles = _timer_handles(context)
    chat_id = str(context.chat_id)

    if action == "list":
        current_tasks = [task for task in tasks.values() if task.get("chat_id") == chat_id]
        return ToolResult(success=True, content="当前会话定时任务列表", data=current_tasks)

    if action == "cancel":
        key = task_id
        if not key and title:
            key = next((tid for tid, task in tasks.items() if task.get("title") == title), None)
        if not key or key not in tasks:
            return ToolResult(success=False, content="未找到对应定时任务", error="timer_not_found")
        task = tasks[key]
        task["status"] = "cancelled"
        handle = handles.pop(key, None)
        if handle:
            handle.cancel()
        return ToolResult(success=True, content="定时任务已取消", data=task)

    if not title:
        return ToolResult(success=False, content="缺少定时任务标题", error="missing_title")

    try:
        due_at, delay = _parse_due_time(due_time, delay_seconds)
    except (TypeError, ValueError) as e:
        return ToolResult(success=False, content="定时任务时间格式无效", error=str(e))

    new_task_id = f"timer_{chat_id}_{int(datetime.datetime.now().timestamp() * 1000)}"
    task = {
        "id": new_task_id,
        "title": title,
        "message": message or title,
        "chat_id": chat_id,
        "mode": context.mode,
        "due_time": due_at.strftime("%Y-%m-%d %H:%M:%S"),
        "delay_seconds": round(delay, 3),
        "status": "scheduled",
    }
    tasks[new_task_id] = task
    handles[new_task_id] = asyncio.create_task(_timer_wake_worker(context, new_task_id, delay))
    return ToolResult(success=True, content="定时任务已创建，到点后会触发 Yuki 回复。", data=task)


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

    if run_inline:
        result = await maid_evolution_loop(user_goal=goal, chat_id=context.chat_id)
        return ToolResult(
            success=result.get("status") == "finished",
            content=result.get("result", "小女仆未返回结果"),
            data=result,
        )

    task = build_maid_task(goal, context.chat_id, context.mode, source="toolchain")
    await context.yuki.maid_task_queue.put(task)
    context.yuki.maid_current_tasks[context.chat_id] = task
    return ToolResult(success=True, content="已交给小女仆后台处理。")


async def send_master_private_tool(context, message, reason="重要信息"):
    """向主人私聊发送私密信息，同时保存群聊上下文快照供后续召回。"""
    if not message:
        return ToolResult(success=False, content="缺少消息内容", error="missing_message")

    # 保存上下文快照
    try:
        from core.private_context import save_context_snapshot
        cid = str(context.chat_id)
        recent_msgs = context.session[-10:]
        slim_msgs = []
        for msg in recent_msgs:
            if msg.get("role") in ("user", "assistant"):
                slim_msgs.append({
                    "role": msg["role"],
                    "content": msg.get("content", "")[:200],
                    "time": msg.get("time", ""),
                })
        save_context_snapshot(
            source_chat_id=cid,
            message=message,
            reason=reason,
            recent_messages=slim_msgs,
        )
        logger.info(f"[Tool] 已保存私聊上下文快照，来源群聊 {cid}")
    except Exception as e:
        logger.warning(f"[Tool] 保存上下文快照失败（不影响发送）: {e}")

    # 发送私信（使用私聊 API）
    await context.sender.send(cfg.TARGET_QQ, message, mode="private")

    # 把这条消息同步写入主人私聊的 chat_history
    try:
        history_manager = context.metadata.get("history_manager")
        if history_manager:
            master_cid = str(cfg.TARGET_QQ)
            history_manager.append_session_message(
                master_cid,
                "assistant",
                f"[群聊通知] {message}",
                source_chat_id=str(context.chat_id),
                reason=reason,
            )
            logger.info(f"[Tool] 已同步消息到主人私聊历史 ({master_cid})")
    except Exception as e:
        logger.warning(f"[Tool] 同步私聊历史失败（不影响发送）: {e}")

    return ToolResult(success=True, content="已私聊发送给主人，并保存了上下文快照。")


async def recall_private_context_tool(context, limit=5, source_chat_id=None):
    """召回最近发给主人的群聊上下文快照，了解群里发生了什么重要事情。"""
    try:
        from core.private_context import recall_context, format_context_for_prompt
        snapshots = recall_context(limit=limit, source_chat_id=source_chat_id)
        if not snapshots:
            return ToolResult(success=True, content="暂无群聊上下文快照，还没有从群里发过私信通知。")

        formatted = format_context_for_prompt(snapshots)
        return ToolResult(success=True, content=formatted, data={"count": len(snapshots)})
    except Exception as e:
        logger.error(f"[Tool] 召回上下文失败: {e}")
        return ToolResult(success=False, content=f"召回上下文失败: {str(e)}", error=str(e))


async def amap_search_tool(context, keywords, search_type="text", location=None, address=None, city=None, radius=3000, page_size=10):
    """高德地图统一搜索：text=关键词搜索, around=周边搜索(需坐标), geocode=地名转坐标。"""
    api_key = os.getenv("AMAP_API_KEY")
    if not api_key:
        return ToolResult(success=False, content="未配置 AMAP_API_KEY，无法调用高德地图服务。", error="missing_amap_api_key")

    timeout = aiohttp.ClientTimeout(total=15)

    if search_type == "geocode":
        if not address:
            return ToolResult(success=False, content="缺少地址信息", error="missing_address")
        params = {"key": api_key, "address": address}
        if city:
            params["city"] = city
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(_AMAP_GEOCODE_URL, params=params) as response:
                data = await response.json(content_type=None)
        if data.get("status") != "1":
            return ToolResult(success=False, content=f"高德地图返回错误：{data.get('info', '未知错误')}", data=data, error=data.get("infocode", "amap_error"))
        geocodes = data.get("geocodes") or []
        if not geocodes:
            return ToolResult(success=False, content="未找到该地址的坐标信息。", error="no_geocode_result")
        results = [{"name": g.get("formatted_address"), "location": g.get("location"), "city": g.get("city"), "district": g.get("district")} for g in geocodes[:5]]
        return ToolResult(success=True, content=f"已定位到 {len(results)} 个地址", data={"results": results})

    if not keywords:
        return ToolResult(success=False, content="缺少搜索关键词", error="missing_keywords")

    if search_type == "around":
        if not location:
            return ToolResult(success=False, content="周边搜索需要中心点坐标（经度,纬度）", error="missing_location")
        params = {
            "key": api_key, "keywords": keywords, "location": location,
            "radius": max(100, min(int(radius), 50000)),
            "page_size": max(1, min(int(page_size), 25)),
            "page_num": 1, "show_fields": "business",
        }
        url = _AMAP_AROUND_URL
    else:
        params = {
            "key": api_key, "keywords": keywords,
            "page_size": max(1, min(int(page_size), 25)),
            "page_num": 1, "show_fields": "business",
        }
        if city:
            params["region"] = city
        url = _AMAP_TEXT_URL

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params=params) as response:
            data = await response.json(content_type=None)
            if response.status >= 400:
                return ToolResult(success=False, content="高德地图请求失败。", data=data, error=f"http_{response.status}")

    if data.get("status") != "1":
        return ToolResult(success=False, content=f"高德地图返回错误：{data.get('info', '未知错误')}", data=data, error=data.get("infocode", "amap_error"))

    pois = []
    for poi in (data.get("pois") or []):
        biz = poi.get("business") or {}
        pois.append({
            "name": poi.get("name"), "address": poi.get("address"),
            "location": poi.get("location"), "type": poi.get("type"),
            "distance": poi.get("distance"), "city": poi.get("cityname"),
            "tel": biz.get("tel"), "rating": biz.get("rating"), "cost": biz.get("cost"),
        })
    count = data.get("count", len(pois))
    summary = f"共找到 {count} 个地点" if count else "未找到相关地点"
    return ToolResult(success=True, content=summary, data={"count": count, "pois": pois})


async def browser_search_tool(context, query, max_results=5, search_depth="basic"):
    """调用 Tavily 搜索服务，返回可供 LLM 总结的网页结果。"""
    if not query:
        return ToolResult(success=False, content="缺少搜索关键词", error="missing_query")

    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        url = f"https://www.bing.com/search?q={quote_plus(query)}"
        return ToolResult(
            success=False,
            content="未配置 TAVILY_API_KEY，暂时只能返回浏览器搜索地址。",
            data={"url": url},
            error="missing_tavily_api_key",
        )

    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": search_depth,
        "max_results": max(1, min(int(max_results), 10)),
        "include_answer": True,
    }
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(_TAVILY_SEARCH_URL, json=payload) as response:
            data = await response.json(content_type=None)
            if response.status >= 400:
                return ToolResult(
                    success=False,
                    content="Tavily 搜索请求失败。",
                    data=data,
                    error=f"http_{response.status}",
                )

    results = []
    for item in data.get("results", []):
        results.append({
            "title": item.get("title"),
            "url": item.get("url"),
            "content": item.get("content"),
            "score": item.get("score"),
        })
    return ToolResult(
        success=True,
        content=data.get("answer") or f"已搜索到 {len(results)} 条结果。",
        data={"query": query, "answer": data.get("answer"), "results": results},
    )


def _resolve_image_path(context, path: str) -> str:
    """解析 [img:XXX]/[shot:N] 索引为真实文件路径，普通路径原样返回。"""
    import re
    m = re.match(r'^\[img:(\d{3})\]$', path)
    if m:
        idx = m.group(1)
        image_store = getattr(context, "image_store", None)
        if image_store:
            resolved = image_store.resolve(idx)
            if resolved:
                return resolved

    shot = re.match(r'^\[shot:(\d+)\]$', path)
    if shot:
        resolved = shot_memory_store.resolve(context.chat_id, shot.group(1))
        if resolved:
            return resolved
    return path


async def capture_group_snapshot_tool(context, note, limit=12):
    """把当前群聊最近上下文渲染成永久保存的伪截屏。"""
    if not note:
        return ToolResult(success=False, content="缺少截屏备注", error="missing_note")
    if context.mode not in ("group", "master_private"):
        return ToolResult(success=False, content="截屏留念目前只适合群聊上下文。", error="unsupported_mode")

    chat_id = str(context.chat_id)
    limit = max(4, min(int(limit or 12), 20))
    history = context.session[-limit:]
    message_objs = context.metadata.get("message_objs") or []
    live_messages = shot_live_buffer.snapshot(chat_id, limit=limit)
    connector = getattr(context.sender, "connector", None)

    try:
        image_bytes, meta = await render_snapshot(
            chat_id,
            note,
            history,
            message_objs,
            connector=connector,
            live_messages=live_messages,
        )
        record = shot_memory_store.save_record(chat_id, note, image_bytes, metadata=meta)
    except Exception as e:
        logger.error(f"[ShotMemory] 截屏失败: {e}")
        return ToolResult(success=False, content=f"截屏失败: {str(e)}", error=str(e))

    return ToolResult(
        success=True,
        content=f"截屏已保存: {record['note']}",
        data={
            "file_path": record["file_path"],
            "note": record["note"],
            "created_at": record["created_at"],
            "group_name": record.get("group_name", ""),
        },
    )


async def search_group_snapshots_tool(context, keyword=None, limit=5):
    """搜索当前群聊的永久截屏记录，并预热 [shot:N] 索引。"""
    chat_id = str(context.chat_id)
    records = shot_memory_store.search(chat_id, keyword=keyword, limit=limit)
    prepared = shot_memory_store.preload(chat_id, records)
    if not prepared:
        return ToolResult(success=True, content="没有找到本群相关截屏记录。", data={"records": []})

    lines = [f"找到 {len(prepared)} 条本群截屏记录，已预热为 [shot:编号]："]
    for item in prepared:
        lines.append(
            f"{item['shot_tag']} {item.get('created_at', '')} | {item.get('note', '')}\n"
            f"路径: {item['absolute_path']}"
        )
    return ToolResult(success=True, content="\n".join(lines), data={"records": prepared})


async def send_qq_file_tool(context, file_path, file_type="auto", caption=None):
    """发送本地图片、语音或普通文件。支持 [img:XXX] 索引。"""
    if not file_path:
        return ToolResult(success=False, content="缺少文件路径", error="missing_file_path")

    file_path = _resolve_image_path(context, file_path)
    abs_path = os.path.abspath(os.path.expanduser(file_path))
    if not os.path.isfile(abs_path):
        return ToolResult(success=False, content="文件不存在，无法发送。", error="file_not_found")

    suffix = os.path.splitext(abs_path)[1].lower()
    if file_type == "auto":
        if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
            file_type = "image"
        elif suffix in {".wav", ".mp3", ".amr", ".silk", ".m4a", ".ogg"}:
            file_type = "voice"
        else:
            file_type = "file"

    if caption:
        await context.sender.send(context.chat_id, caption, mode=context.mode)
    if file_type == "voice":
        await context.sender.send_local_voice(context.chat_id, abs_path, mode=context.mode)
    elif file_type == "image":
        await context.sender.send_local_image(context.chat_id, abs_path, mode=context.mode)
        if context.mode == "group":
            shot_live_buffer.append(
                context.chat_id,
                name=cfg.ROBOT_NAME.title(),
                raw_text="[图片]",
                content="[图片]",
                segments=[{"type": "image", "data": {"file": abs_path}}],
                user_id=cfg.SELF_QQ,
                is_bot=True,
            )
    elif file_type == "file":
        if hasattr(context.sender, "send_local_file"):
            await context.sender.send_local_file(context.chat_id, abs_path, mode=context.mode)
        else:
            await context.sender.send(context.chat_id, f"[CQ:file,file=file:///{abs_path}]", mode=context.mode)
    else:
        return ToolResult(success=False, content="不支持的文件类型", error="unsupported_file_type")
    return ToolResult(success=True, content="文件已发送。", data={"file_path": abs_path, "file_type": file_type})


async def resolve_user_tool(context, name=None):
    """根据昵称解析用户 QQ 号。用于需要指定目标用户的场景（如戳一戳、发送文件等）。"""
    if not name:
        return ToolResult(success=False, content="缺少用户昵称", error="missing_name")

    user_id = context.yuki.user_mapping.resolve(context.chat_id, name)
    if user_id:
        return ToolResult(success=True, content=str(user_id), data={"name": name, "user_id": user_id})

    # 返回当前群聊中已知的所有映射，帮助调试
    all_mappings = context.yuki.user_mapping.get_all(context.chat_id)
    return ToolResult(
        success=False,
        content=f"未找到用户 '{name}' 的 QQ 号。",
        data={"searched": name, "known_users": all_mappings},
        error="user_not_found",
    )


async def poke_tool(context, target=None, user_id=None):
    """
    戳一戳指定用户。

    调用链路：
    1. 如果提供了昵称，从 user_mapping 解析 QQ 号
    2. 调用 sender.send_poke() 发送 WebSocket 请求
    3. 返回结果给 LLM
    """
    # 如果提供了昵称但没有 user_id，尝试解析
    if target and not user_id:
        resolved = context.yuki.user_mapping.resolve(context.chat_id, target)
        if resolved:
            user_id = resolved
            logger.info(f"[Poke] 昵称 '{target}' 解析为 QQ: {user_id}")
        else:
            return ToolResult(
                success=False,
                content=f"未找到用户 '{target}'，可能他还没在群里说过话。",
                error="user_not_found",
            )

    if not user_id:
        return ToolResult(success=False, content="请指定戳一戳的目标用户（昵称或 QQ 号）。", error="missing_target")

    # 调用 sender 的 send_poke 方法（通过 WebSocket 发送）
    try:
        result = await context.sender.send_poke(user_id, context.chat_id)

        if result and result.get("status") == "ok":
            return ToolResult(
                success=True,
                content=f"已戳一戳 {target or user_id}~",
                data={"user_id": user_id, "target": target}
            )
        else:
            error_msg = result.get("message", "未知错误") if result else "请求超时"
            return ToolResult(
                success=False,
                content=f"戳一戳失败: {error_msg}",
                data=result,
                error="api_error",
            )
    except Exception as e:
        logger.error(f"[Poke] 戳一戳异常: {e}")
        return ToolResult(success=False, content=f"戳一戳失败: {str(e)}", error=str(e))


async def download_file_tool(context, file_id=None, filename=None):
    """
    下载群聊/私聊中的文件到本地。

    当收到文件消息时，消息中会包含 [文件:file_id=xxx] 标记。
    使用此工具可以通过 file_id 下载文件到本地，然后可以委托小女仆分析文件内容。

    Args:
        file_id: 文件 ID（从消息中的 [文件:file_id=xxx] 获取）
        filename: 保存的文件名（可选，默认使用原文件名）
    """
    if not file_id:
        # 尝试从最近的消息中提取 file_id
        recent_text = context.combined_text or ""
        file_ids = re.findall(r'\[文件:file_id=([^\]]+)\]', recent_text)
        if file_ids:
            file_id = file_ids[0]
            logger.info(f"[DownloadFile] 从消息中提取 file_id: {file_id}")
        else:
            return ToolResult(
                success=False,
                content="缺少文件 ID。请从消息中的 [文件:file_id=xxx] 获取。",
                error="missing_file_id"
            )

    try:
        result = await context.sender.download_file(file_id, filename)

        if result.get("success"):
            file_path = result.get("file_path")
            saved_filename = result.get("filename")

            if file_path:
                return ToolResult(
                    success=True,
                    content=f"文件已下载: {saved_filename}",
                    data={
                        "file_path": file_path,
                        "filename": saved_filename,
                        "file_id": file_id,
                    }
                )
            elif result.get("url"):
                # 文件是 URL，需要额外下载
                return ToolResult(
                    success=True,
                    content=f"文件 URL: {result['url']}",
                    data={
                        "url": result["url"],
                        "filename": saved_filename,
                        "file_id": file_id,
                    }
                )
        else:
            return ToolResult(
                success=False,
                content=f"下载文件失败: {result.get('error', '未知错误')}",
                error=result.get("error", "download_failed")
            )
    except Exception as e:
        logger.error(f"[DownloadFile] 下载文件异常: {e}")
        return ToolResult(success=False, content=f"下载文件失败: {str(e)}", error=str(e))


async def publish_qzone_mood_tool(context, content, visible=1, image_paths=None):
    """发布 QQ 空间说说。支持纯文本和带图。image_paths 支持 [img:XXX] 索引。"""
    if not content:
        return ToolResult(success=False, content="缺少说说内容", error="missing_content")

    # 解析图片索引
    if image_paths:
        image_paths = [_resolve_image_path(context, p) for p in image_paths]

    from modules.qzone import publish_mood
    connector = context.sender.connector
    result = await publish_mood(connector, content, visible, image_paths)

    if result.get("success"):
        suffix = "（带图）" if result.get("has_image") else ""

        # 通知监控器记录新说说
        try:
            from modules.qzone.monitor import notify_new_post
            chat_context = []
            # 从历史中提取最近的群聊消息作为上下文
            cid = str(context.chat_id)
            if hasattr(context.yuki, 'message_buffer'):
                buf = context.yuki.message_buffer.get(cid, [])
                chat_context = [m.get("content", "")[:80] for m in buf[-5:] if m.get("content")]
            notify_new_post(
                tid=result.get("tid", ""),
                content=content[:100],
                source_chat=cid,
                chat_context=chat_context,
            )
        except Exception as e:
            logger.warning(f"[QZone] 通知监控器失败: {e}")

        return ToolResult(
            success=True,
            content=f"说说已发布{suffix}: {content}",
            data={"tid": result.get("tid"), "time": result.get("time")},
        )
    return ToolResult(
        success=False,
        content=f"发布失败: {result.get('message', '未知错误')}",
        data=result,
        error=result.get("message", "publish_failed"),
    )


async def generate_image_tool(context, prompt, size="1024*1024"):
    """调用图像生成模型生成图片，保存到 output 目录并返回路径。"""
    if not prompt:
        return ToolResult(success=False, content="缺少图像描述", error="missing_prompt")

    api_key = cfg.IMAGE_GEN_API_KEY
    if not api_key:
        return ToolResult(success=False, content="未配置 image_gen_api_key", error="missing_api_key")

    base_url = cfg.IMAGE_GEN_URL
    model = cfg.IMAGE_GEN_MODEL
    # 兼容 "1024x1024" → "1024*1024"
    size = size.replace("x", "*").replace("X", "*")

    # wan 系列走 DashScope 原生 API，其他走 OpenAI 兼容接口
    use_native = model.startswith("wan")

    if use_native:
        import re
        host_match = re.match(r'(https://[^/]+)/compatible-mode/v1', base_url)
        if host_match:
            api_endpoint = f"{host_match.group(1)}/api/v1/services/aigc/multimodal-generation/generation"
        else:
            api_endpoint = f"{base_url.rstrip('/')}/api/v1/services/aigc/multimodal-generation/generation"

        payload = {
            "model": model,
            "input": {
                "messages": [
                    {"role": "user", "content": [{"text": prompt}]}
                ]
            },
            "parameters": {"size": size, "n": 1},
        }

        async def _do_generate():
            timeout = aiohttp.ClientTimeout(total=120)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    api_endpoint,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                ) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status != 200:
                        raise Exception(f"API 返回 {resp.status}: {data}")
                    return data

        try:
            data = await _do_generate()
        except Exception as e:
            logger.error(f"[ImageGen] 生成失败: {e}")
            return ToolResult(success=False, content=f"图像生成失败: {str(e)}", error=str(e))

        try:
            image_url = data["output"]["choices"][0]["message"]["content"][0]["image"]
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"[ImageGen] 解析返回数据失败: {data}")
            return ToolResult(success=False, content="模型返回数据格式异常", error=str(e))

        # 下载图片到本地
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(output_dir, exist_ok=True)
        filename = datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '.png'
        filepath = os.path.join(output_dir, filename)

        try:
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(image_url) as resp:
                    if resp.status != 200:
                        raise Exception(f"下载图片失败: HTTP {resp.status}")
                    img_bytes = await resp.read()
                    with open(filepath, 'wb') as f:
                        f.write(img_bytes)
        except Exception as e:
            logger.error(f"[ImageGen] 下载图片失败: {e}")
            return ToolResult(success=False, content=f"图片下载失败: {str(e)}", error=str(e))

        logger.info(f"[ImageGen] 图片已保存: {filepath} ({len(img_bytes)} bytes)")

    else:
        # OpenAI 兼容接口（如 gpt-image 等）
        def _do_generate():
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url)
            return client.images.generate(
                model=model, prompt=prompt, n=1,
                size=size, response_format="b64_json",
            )

        try:
            response = await asyncio.to_thread(_do_generate)
        except Exception as e:
            logger.error(f"[ImageGen] 生成失败: {e}")
            return ToolResult(success=False, content=f"图像生成失败: {str(e)}", error=str(e))

        image_data = response.data[0]
        if not (hasattr(image_data, 'b64_json') and image_data.b64_json):
            return ToolResult(success=False, content="模型未返回图像数据", error="no_image_data")

        import base64
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
        os.makedirs(output_dir, exist_ok=True)
        filename = datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '.png'
        filepath = os.path.join(output_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(base64.b64decode(image_data.b64_json))

        logger.info(f"[ImageGen] 图片已保存: {filepath}")

    return ToolResult(
        success=True,
        content=f"图像已生成并保存: {filepath}",
        data={"file_path": filepath, "prompt": prompt},
    )


TOOL_SPECS = [
    ToolSpec(
        name="get_master_status",
        description="判断主人是否在线、是否活跃，并返回当前聚焦的窗口标题。",
        parameters={"type": "object", "properties": {}},
        handler=get_master_status_tool,
    ),
    ToolSpec(
        name="search_diary",
        description="查询日记/记忆，支持按日期和关键词检索。",
        parameters={
            "type": "object",
            "properties": {
                "date_str": {"type": "string", "description": "日期，如 2026-05-20 或 2026-05"},
                "keyword": {"type": "string", "description": "需要匹配的关键词"},
            },
        },
        handler=search_diary_tool,
    ),
    ToolSpec(
        name="delegate_to_maid",
        description="将工作任务委托给电脑上的小女仆处理。",
        parameters={
            "type": "object",
            "properties": {
                "goal": {"type": "string"},
                "run_inline": {"type": "boolean"},
            },
            "required": ["goal"],
        },
        handler=delegate_to_maid_tool,
    ),
    ToolSpec(
        name="send_master_private",
        description="向主人私聊发送私密信息。发送时会自动保存群聊上下文快照，方便主人后续了解群里发生了什么。用于重要信息通知、有人提到主人等场景。",
        parameters={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "要发送给主人的消息内容"},
                "reason": {"type": "string", "description": "触发原因，如'有人提到主人'、'重要通知'等", "default": "重要信息"},
            },
            "required": ["message"],
        },
        handler=send_master_private_tool,
    ),
    ToolSpec(
        name="recall_private_context",
        description="召回最近发给主人的群聊上下文快照。当主人在私聊中问起群里的事情、或者你想了解之前通知过主人什么时使用。",
        parameters={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "返回的快照数量上限，默认5", "default": 5},
                "source_chat_id": {"type": "string", "description": "可选，只召回指定群聊的快照"},
            },
        },
        handler=recall_private_context_tool,
    ),
    ToolSpec(
        name="capture_group_snapshot",
        description="截屏留念当前群聊最近上下文：把最近聊天渲染成一张本地永久保存的截图并标记。想记录热闹、名场面、群里发生了什么时直接调用。",
        parameters={
            "type": "object",
            "properties": {
                "note": {"type": "string", "description": "备注/事件描述，记录发生的事情和你的评论"},
                "limit": {"type": "integer", "description": "截取最近多少条上下文，默认12", "default": 12},
            },
            "required": ["note"],
        },
        handler=capture_group_snapshot_tool,
    ),
    ToolSpec(
        name="search_group_snapshots",
        description="翻看本群截屏记录。按关键词搜索当前群聊永久保存的截屏，最多返回5条，并预热为 [shot:1]、[shot:2] 等索引；要发送时用 send_qq_file 发送对应 [shot:编号]。",
        parameters={
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "搜索关键词，可省略以查看最近记录"},
                "limit": {"type": "integer", "description": "返回数量，默认5，最多5", "default": 5},
            },
        },
        handler=search_group_snapshots_tool,
    ),
    ToolSpec(
        name="send_qq_file",
        description="发送本地图片、语音或普通文件；优先用此工具，不要在回复中手写 CQ 文件码。",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "本地文件路径"},
                "file_type": {"type": "string", "enum": ["auto", "image", "voice", "file"]},
                "caption": {"type": "string", "description": "发送文件前附带的一句说明，可省略"},
            },
            "required": ["file_path"],
        },
        handler=send_qq_file_tool,
    ),
    ToolSpec(
        name="resolve_user",
        description="根据用户昵称解析 QQ 号。想要获取QQ号的时候使用。",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "用户昵称"},
            },
            "required": ["name"],
        },
        handler=resolve_user_tool,
    ),
    ToolSpec(
        name="poke",
        description="戳一戳指定用户。可以传入昵称（自动解析）或直接传入 QQ 号。",
        parameters={
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "用户昵称或群名片"},
                "user_id": {"type": "integer", "description": "用户 QQ 号（如果已知）"},
            },
        },
        handler=poke_tool,
    ),
    ToolSpec(
        name="download_file",
        description="下载群聊/私聊中的文件到本地。当想要下载文件消息（显示为 [文件:file_id=xxx]）时，使用此工具下载文件。下载后可以委托小女仆分析文件内容。",
        parameters={
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "文件 ID，从消息中的 [文件:file_id=xxx] 获取"},
                "filename": {"type": "string", "description": "保存的文件名（可选，默认使用原文件名）"},
            },
        },
        handler=download_file_tool,
    ),
    ToolSpec(
        name="publish_qzone_mood",
        description="发布 QQ 空间说说。支持纯文本和带图片。使用前确保内容合适，不要频繁调用。",
        parameters={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "说说文本内容"},
                "visible": {"type": "integer", "description": "可见范围: 1=公开(默认) 4=仅自己", "default": 1},
                "image_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "图片本地路径列表（可选），如 [\"D:/photo/a.jpg\"]",
                },
            },
            "required": ["content"],
        },
        handler=publish_qzone_mood_tool,
    ),
    ToolSpec(
        name="generate_image",
        description=(
            "根据文字描述生成图片。生成后保存到本地 output 目录，返回文件路径。"
            "生成完后必须用 send_qq_file 工具把图片发出来。"
            "重要：prompt 必须完整详细，包含主体、场景、风格、光影、构图等细节，"
            "融入 Yuki 的二次元少女特色（白色长发蓝瞳少女，雪花发饰）"
        ),
        parameters={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "图像描述（使用中文描述）"},
                "size": {"type": "string", "description": "图片尺寸，如 1024*1024、512*512", "default": "1024*1024"},
            },
            "required": ["prompt"],
        },
        handler=generate_image_tool,
    ),
]

# 兼容旧引用，后续新增工具优先维护 TOOL_SPECS。
TOOL_SCHEMAS = [spec.to_schema() for spec in TOOL_SPECS]
TOOL_HANDLERS = {spec.name: spec.handler for spec in TOOL_SPECS}
