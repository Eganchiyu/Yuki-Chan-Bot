"""重启补报：小女仆在宿主跑，容器重启不会打断她，但会打断「回报」这一环。

场景（自改时必然发生）：
    小女仆提交补丁 → 宿主 supervisor 应用 → 重启容器（15~30s）
    → 容器里等待 result.json 的协程随进程消失
    → 而宿主的 dsh 进程还活着，稍后把结论写进 staging/ 与 tasks/dsh/<id>/result.json
    → 没人读，Yuki 永远不知道该任务已经完成

本模块在容器内常驻轮询，把「已有 result.json 但没汇报过」的任务捡回来，
走和 maid_worker 一样的回报通道（写进会话历史 + 触发一次主动回复），
然后打上 `reported.ok`，保证每条结果只汇报一次。
"""
import asyncio
import json
import os
import time
from datetime import datetime

from core.maid.maid_boundary import build_maid_report
from core.maid.maid_common import logger

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DSH_TASKS_DIR = os.path.join(PROJECT_ROOT, "tasks", "dsh")
REPORTED_MARK = "reported.ok"
SCAN_INTERVAL = float(os.environ.get("YUKI_MAID_REPORT_SCAN", "30"))
# 单次启动最多补报几条：积压太多时不要一口气刷屏
MAX_PER_SCAN = int(os.environ.get("YUKI_MAID_REPORT_MAX", "3"))
# 等 NapCat 上线的最长时间；超时就留到下轮（不丢，只是晚一点说）
NAPCAT_WAIT_SECONDS = 300


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _reported_mark(task_dir):
    return os.path.join(task_dir, REPORTED_MARK)


def mark_reported(task_id) -> bool:
    """标记某任务的结果已经交给 Yuki（由正常路径与补报路径共同调用）。"""
    if not task_id:
        return False
    task_dir = os.path.join(DSH_TASKS_DIR, str(task_id))
    if not os.path.isdir(task_dir):
        return False
    try:
        with open(_reported_mark(task_dir), "w", encoding="utf-8") as f:
            f.write(datetime.now().isoformat(timespec="seconds") + "\n")
        return True
    except OSError as e:
        logger.warning(f"[Maid/Resume] 写汇报标记失败 {task_id}: {e}")
        return False


def _pending_results():
    """列出「已完成但未汇报」的任务，按完成时间从旧到新。"""
    if not os.path.isdir(DSH_TASKS_DIR):
        return []
    out = []
    for name in os.listdir(DSH_TASKS_DIR):
        task_dir = os.path.join(DSH_TASKS_DIR, name)
        if not os.path.isdir(task_dir):
            continue
        result_path = os.path.join(task_dir, "result.json")
        if not os.path.exists(result_path) or os.path.exists(_reported_mark(task_dir)):
            continue
        result = _read_json(result_path)
        if not isinstance(result, dict):
            continue
        request = _read_json(os.path.join(task_dir, "request.json")) or {}
        try:
            mtime = os.path.getmtime(result_path)
        except OSError:
            mtime = 0
        out.append({"task_dir": task_dir, "task_id": name, "result": result,
                    "request": request, "mtime": mtime})
    out.sort(key=lambda x: x["mtime"])
    return out


async def report_orphaned_results(engine, yuki_state, history_manager):
    """常驻任务：把重启期间/之后完成的小女仆结果补报给 Yuki。"""
    logger.info("[Maid/Resume] 补报巡检已启动（每 %ss 扫一次 tasks/dsh）", int(SCAN_INTERVAL))
    while True:
        try:
            pending = _pending_results()
            if pending:
                handled = 0
                for item in pending:
                    if handled >= MAX_PER_SCAN:
                        break
                    await _report_one(item, engine, yuki_state, history_manager)
                    handled += 1
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[Maid/Resume] 巡检异常: {e}")
        await asyncio.sleep(SCAN_INTERVAL)


async def _report_one(item, engine, yuki_state, history_manager):
    task_id = item["task_id"]
    result = item["result"]
    request = item["request"]
    chat_id = str(request.get("chat_id") or "")
    goal = str(request.get("goal") or result.get("goal") or "")

    if not chat_id:
        # 没有会话来源（手动调试任务）：标记掉，不打扰任何人
        mark_reported(task_id)
        logger.info(f"[Maid/Resume] {task_id} 无 chat_id，跳过汇报")
        return

    # 这条结果是在容器重启前还是之后完成的？决定措辞
    restarted = False
    try:
        if item["mtime"] and time.time() - item["mtime"] > 120:
            restarted = True
    except OSError:
        pass

    report = build_maid_report(goal, {
        "status": result.get("status"),
        "result": result.get("result"),
        "rounds": result.get("steps"),
        "elapsed": result.get("elapsed"),
        "trace": os.path.join("logs", f"trace_{task_id}.md"),
        "state": "",
    })
    if restarted:
        report = report.replace(
            "【小女仆完成! 小女仆汇报】",
            "【小女仆完成! 小女仆汇报】（Yuki 刚重启过，这条是重启前就做完的）",
        )

    # 等 NapCat 上线再投递：离线时投进去也发不出去
    waited = 0
    while not getattr(engine, "napcat_online", True):
        if waited >= NAPCAT_WAIT_SECONDS:
            logger.warning(f"[Maid/Resume] {task_id} 等待 NapCat 上线超时，下轮再试")
            return
        await asyncio.sleep(10)
        waited += 10

    try:
        history_manager.append_session_message(chat_id, "user", report, is_maid_report=True)
    except Exception as e:
        logger.error(f"[Maid/Resume] {task_id} 写入会话历史失败: {e}")
        return
    mark_reported(task_id)

    if engine.process_callback is not None:
        try:
            asyncio.create_task(
                engine.process_callback(chat_id, "group", debounce_flag=False, force_reply=True)
            )
        except Exception as e:
            logger.error(f"[Maid/Resume] {task_id} 触发回复失败: {e}")
    logger.info(f"[Maid/Resume] {task_id} 补报完成（{result.get('status')}）")
