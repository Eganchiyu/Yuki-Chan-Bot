# core/art_gen_jobs.py
"""异步生图任务表：art_draw 只负责提交，后台画完后自动发图并唤起她回一句。

设计（与机主确认）：
    - 生成在独立 asyncio 任务里跑，工具调用立刻返回，整轮对话不再被几十秒~几分钟的
      生图请求卡住；
    - 同一个会话允许多张并行；
    - 画完自动把图片发到当前会话，并往历史里注入一条 ``is_art_report`` 的系统消息
      （带成品预览附件，方便她在下一轮视觉自检），再用 ``process_callback`` 触发
      一次强制回复——风格与小女仆汇报一致；
    - 失败同样注入一条汇报，让她知道该重试。
"""
from __future__ import annotations

import asyncio
import itertools
import os
import time
from dataclasses import dataclass, field

from config import cfg
from core.toolchain import ToolResult
from utils.logger import get_logger

logger = get_logger("tools")

DONE_PREFIX = "【画图完成】"
FAIL_PREFIX = "【画图失败】"
_MAX_KEPT_JOBS = 50


@dataclass
class ArtGenJob:
    """一张后台生成中的图。"""
    job_id: str
    chat_id: str
    mode: str
    prompt: str
    meta: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    finished_at: float = 0.0
    status: str = "queued"          # queued / running / done / failed / cancelled
    result: dict | None = None
    error: str = ""
    task: asyncio.Task | None = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "chat_id": self.chat_id,
            "mode": self.mode,
            "prompt": self.prompt,
            "meta": self.meta,
            "status": self.status,
            "error": self.error,
            "file_path": (self.result or {}).get("file_path", ""),
        }


def _register_preview(context, filepath: str) -> tuple[dict | None, str]:
    """把成品注册进会话 image_store，返回 (attachment, [img:XXX] 标记)。"""
    store = getattr(context, "image_store", None)
    if store is None or not filepath or not os.path.isfile(filepath):
        return None, ""
    try:
        with open(filepath, "rb") as f:
            raw = f.read()
        if not raw:
            return None, ""
        ext = os.path.splitext(filepath)[1].lower() or ".png"
        index = store.register(raw, url="art_draw", ext=ext)
        attachment = store.attachment(index)
        if attachment:
            return attachment, f"[img:{index}]"
    except Exception as exc:
        logger.warning(f"[ArtGen] 注册成品预览失败: {exc}")
    return None, ""


class ArtGenJobStore:
    """进程内的后台生图任务表（重启即清空，图片文件已落盘不受影响）。"""

    def __init__(self):
        self._jobs: dict[str, ArtGenJob] = {}
        self._seq = itertools.count(1)

    # ------------------------------------------------------------------ 提交
    def submit(self, context, gen_kwargs: dict, meta: dict | None = None, prompt: str = "") -> ArtGenJob:
        """提交一次后台生图，立即返回 job（不等待模型出图）。"""
        job = ArtGenJob(
            job_id=f"art-{int(time.time())}-{next(self._seq)}",
            chat_id=str(context.chat_id),
            mode=getattr(context, "mode", "group") or "group",
            prompt=str(prompt or gen_kwargs.get("prompt") or ""),
            meta=dict(meta or {}),
        )
        self._jobs[job.job_id] = job
        job.task = asyncio.create_task(
            self._run(job, context, dict(gen_kwargs)), name=f"artgen:{job.job_id}"
        )
        job.status = "running"
        logger.info(f"[ArtGen] {job.job_id} 已提交后台生成 chat_id={job.chat_id}")
        self._trim()
        return job

    async def wait(self, job_id: str) -> ArtGenJob | None:
        """等待某个任务收尾（测试与排障用；工具链本身不调用）。"""
        job = self._jobs.get(job_id)
        if job is None:
            return None
        if job.task is not None:
            try:
                await job.task
            except Exception:
                pass
        return job

    def get(self, job_id: str) -> ArtGenJob | None:
        return self._jobs.get(job_id)

    def active(self, chat_id: str | None = None) -> list[ArtGenJob]:
        return [
            job for job in self._jobs.values()
            if job.status in ("queued", "running")
            and (chat_id is None or job.chat_id == str(chat_id))
        ]

    def _trim(self) -> None:
        if len(self._jobs) <= _MAX_KEPT_JOBS:
            return
        finished = [j for j in self._jobs.values() if j.status not in ("queued", "running")]
        finished.sort(key=lambda j: j.created_at)
        for job in finished[: max(0, len(self._jobs) - _MAX_KEPT_JOBS)]:
            self._jobs.pop(job.job_id, None)

    # ------------------------------------------------------------------ 执行
    async def _run(self, job: ArtGenJob, context, gen_kwargs: dict) -> None:
        try:
            from core.tools.tools_media import generate_image_tool

            res = await generate_image_tool(context, **gen_kwargs)
            if not isinstance(res, ToolResult) or not res.success:
                raise RuntimeError(getattr(res, "content", "") or "图像生成失败")
            job.result = dict(res.data or {})
            job.status = "done"
            logger.info(f"[ArtGen] {job.job_id} 生成完成: {job.result.get('file_path')}")
            await self._deliver_success(job, context)
        except asyncio.CancelledError:
            job.status = "cancelled"
            raise
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            logger.error(f"[ArtGen] {job.job_id} 生成失败: {exc}")
            await self._deliver_failure(job, context)
        finally:
            job.finished_at = time.time()

    # ------------------------------------------------------------------ 交付
    async def _deliver_success(self, job: ArtGenJob, context) -> None:
        from core.tools.tools_message import send_qq_file_tool

        filepath = str((job.result or {}).get("file_path") or "")
        sent = False
        if filepath and os.path.isfile(filepath):
            try:
                send_res = await send_qq_file_tool(context, filepath, file_type="image")
                sent = bool(send_res.success)
                if not sent:
                    logger.warning(f"[ArtGen] {job.job_id} 自动发图失败: {send_res.content}")
            except Exception as exc:
                logger.warning(f"[ArtGen] {job.job_id} 自动发图异常: {exc}")
        attachment, preview_tag = _register_preview(context, filepath)
        if attachment:
            job.result["screenshot"] = attachment

        meta = job.meta or {}
        lines = [f"{DONE_PREFIX} 后台那张图已经画完了（任务 {job.job_id}）。"]
        if filepath:
            lines.append(f"- 文件: {filepath}")
        size = (job.result or {}).get("size") or meta.get("size") or ""
        if size:
            lines.append(f"- 画幅: {size}；背景: {meta.get('background', 'opaque')}")
        if meta.get("note"):
            lines.append(f"- 创作意图: {meta['note']}")
        if meta.get("used_assets"):
            lines.append(f"- 参考资产: {', '.join(meta['used_assets'])}")
        if preview_tag:
            lines.append(f"- 成品预览 {preview_tag}（可直接看画面，必要时再精修）")
        if sent:
            lines.append("- 这张图已经自动发到会话里了，不要重复再发一遍。")
        else:
            lines.append("- 自动发送没成功，请用 send_qq_file 把上面的文件发出去。")
        lines.append("结合这个结果，自然地跟大家说一两句吧。")

        self._inject_report(context, "\n".join(lines), attachment)

    async def _deliver_failure(self, job: ArtGenJob, context) -> None:
        meta = job.meta or {}
        lines = [f"{FAIL_PREFIX} 刚才那张图没画成（任务 {job.job_id}）。", f"- 原因: {job.error or '未知错误'}"]
        if job.prompt:
            lines.append(f"- 当时的 prompt: {job.prompt[:120]}")
        if meta.get("used_assets"):
            lines.append(f"- 参考资产: {', '.join(meta['used_assets'])}")
        lines.append("可以换个说法重试一次，或者先跟群友说一声。")
        self._inject_report(context, "\n".join(lines), None)

    def _inject_report(self, context, report: str, attachment) -> None:
        """把汇报写进历史，并触发一次强制回复。"""
        chat_id = str(getattr(context, "chat_id", "") or "")
        mode = getattr(context, "mode", "group") or "group"
        history_manager = (context.metadata or {}).get("history_manager")
        if history_manager is not None:
            try:
                history_manager.append_session_message(
                    chat_id,
                    "user",
                    report,
                    is_art_report=True,
                    image_attachments=[attachment] if attachment else None,
                )
            except TypeError:
                history_manager.append_session_message(chat_id, "user", report, is_art_report=True)
            except Exception as exc:
                logger.warning(f"[ArtGen] 写入画图汇报失败: {exc}")

        callback = (context.metadata or {}).get("process_callback")
        if callback is None:
            logger.warning("[ArtGen] process_callback 未设置，无法唤起回复")
            return
        try:
            coro = callback(chat_id, mode, debounce_flag=False, force_reply=True)
            if asyncio.iscoroutine(coro):
                asyncio.create_task(coro)
        except Exception as exc:
            logger.warning(f"[ArtGen] 触发回复失败: {exc}")


art_gen_store = ArtGenJobStore()


def format_job_line(job: ArtGenJob) -> str:
    """给工具返回用的简短描述。"""
    return f"{job.job_id}（{cfg.ROBOT_NAME.title()}正在后台画）"
