"""JM 下载器 — YukiV6 适配层

在 listen_main.py 中拦截 /jm 指令，不入上下文，
后台下载完成后通过 Yuki 的 ws_sender 发送文件。

用法（由 listen_main.py 调用）:
    from modules.jm_downloader import handle_jm_command
    if await handle_jm_command(chat_id, raw_msg, sender, mode):
        continue  # 已拦截，跳过后续处理
"""
import asyncio
import logging
import os
import re
from pathlib import Path

from .downloader import download_album
from .cache import init_cache

logger = logging.getLogger("jm_downloader")

# 缓存目录：YukiV6/data/jm_cache
_PROJECT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
_CACHE_DIR = os.path.join(_PROJECT_ROOT, "data", "jm_cache")

# 模块加载时初始化缓存目录（resolve 为绝对路径，避免 pyminizip 不支持 ..）
init_cache(os.path.abspath(_CACHE_DIR))

# 正则：/jm123456 或 /jm 123456 或 /jm 123456 1-30
_JM_PATTERN = re.compile(
    r"^/jm\s*(\d{4,8})(?:\s+(\d{1,3})-(\d{1,3}))?\s*$",
    re.IGNORECASE,
)

# 数字→中文映射（用于文件名混淆）
_DIGIT_MAP = str.maketrans("0123456789", "零一二三四五六七八九")


def _to_chinese_digits(num: str) -> str:
    """350234 → 三五零二三四"""
    return num.translate(_DIGIT_MAP)


def _parse_jm_command(text: str) -> tuple[str, int | None, int | None] | None:
    """解析 /jm 指令，返回 (album_id, range_start, range_end) 或 None"""
    m = _JM_PATTERN.match(text.strip())
    if not m:
        return None
    album_id = m.group(1)
    r_start = int(m.group(2)) if m.group(2) else None
    r_end = int(m.group(3)) if m.group(3) else None
    return album_id, r_start, r_end


async def handle_jm_command(chat_id, raw_msg: str, sender, mode: str = "group") -> bool:
    """拦截 /jm 指令。返回 True 表示已拦截（调用方应跳过后续处理）。
    
    不入上下文、不写历史，后台下载完成后直接发文件。
    """
    parsed = _parse_jm_command(raw_msg)
    if parsed is None:
        return False

    album_id, range_start, range_end = parsed
    logger.info(f"[JM] 拦截指令: album={album_id}, range={range_start}-{range_end}, chat={chat_id}")

    # 后台任务：下载 + 发送
    asyncio.create_task(
        _download_and_send(chat_id, album_id, range_start, range_end, sender, mode)
    )
    return True


async def _download_and_send(
    chat_id,
    album_id: str,
    range_start: int | None,
    range_end: int | None,
    sender,
    mode: str,
):
    """后台执行：下载 → 生成文件 → 发送"""
    try:
        # 提示开始
        await sender.send(chat_id, "📥 正在处理，请稍候...", mode=mode)

        result = await asyncio.to_thread(
            download_album,
            album_id=album_id,
            range_start=range_start,
            range_end=range_end,
            max_chapters=30,
            output_format="pdf",
            zip_password="",
            retention_days=3,
            max_cache_gb=3.0,
        )

        if not result["success"]:
            await sender.send(chat_id, "❌ 失败", mode=mode)
            return

        import shutil
        import tempfile
        import string
        import random as _random
        from PyPDF2 import PdfReader, PdfWriter

        pdf_path = result.get("pdf_path")
        file_sent = False
        temp_files = []

        if pdf_path and pdf_path.exists():
            # 随机密码
            pwd = "".join(_random.choices(string.ascii_letters + string.digits, k=8))

            # 加密 PDF
            fake_name = f"{_to_chinese_digits(album_id)}.pdf"
            temp_dir = tempfile.gettempdir()
            temp_enc = os.path.join(temp_dir, fake_name)

            reader = PdfReader(str(pdf_path))
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)
            writer.encrypt(pwd)
            with open(temp_enc, "wb") as f:
                writer.write(f)
            temp_files.append(temp_enc)

            # 发送密码 + 文件
            await sender.send(chat_id, f"🔑 {pwd}", mode=mode)
            await asyncio.sleep(0.5)
            await sender.send_local_file(chat_id, temp_enc, mode=mode)
            file_sent = True
            logger.info(f"[JM] 已发送(密码={pwd}, 文件={fake_name})")

        if not file_sent:
            await sender.send(chat_id, "❌ 文件生成失败", mode=mode)

        for f in temp_files:
            try:
                os.remove(f)
            except Exception:
                pass

    except Exception as exc:
        logger.error(f"[JM] 异常: {exc}", exc_info=True)
        try:
            await sender.send(chat_id, "❌ 出错了", mode=mode)
        except Exception:
            pass
