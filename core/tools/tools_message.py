# core/tools/tools_message.py
"""消息发送类工具：私聊通知、戳一戳、发送本地文件。"""
import os
import shutil
import time

from config import cfg
from core.toolchain import ToolResult
from modules.shot_memory import shot_live_buffer

from .tools_common import _resolve_image_path, logger

# 项目根（容器内与宿主机同路径，其子目录为 rw 挂载）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 容器内可读可写的挂载目录：优先查 data/inbox（宿主机产物同步落点），再查其它 rw 目录
_MOUNTED_DIRS = ("data/inbox", "temp", "output", "workspace", "temp_images", "data")
_SKIP_DIRS = {"node_modules", "__pycache__", ".git", "maid_venv", "models"}
# 兜底复制的落点（data/ 是 rw 挂载，容器内外同路径可见）
_FALLBACK_DIR = os.path.join(_PROJECT_ROOT, "data", "sent_files")


def _path_candidates(raw_path):
    """把各种形态的路径映射成容器内可能的等价路径（按优先级排序）。"""
    p = str(raw_path or "").strip()
    if p.startswith("file://"):
        p = p[7:]
    if p.startswith("~"):
        p = os.path.expanduser(p)
    if not os.path.isabs(p):
        p = os.path.join(_PROJECT_ROOT, p)

    candidates = [p]
    # 宿主机前缀不同、但文件其实在项目里时：/某个前缀/output/a.png → <项目根>/output/a.png
    parts = [x for x in p.split("/") if x]
    for i in range(1, len(parts)):
        tail = os.path.join(_PROJECT_ROOT, *parts[i:])
        if tail not in candidates:
            candidates.append(tail)
    return candidates


def _find_same_name(name, max_entries=50000):
    """在可写挂载目录里按文件名找同源文件（有界遍历，取 mtime 最新的那个）。"""
    if not name:
        return ""
    best, best_mtime, seen = "", None, 0
    for d in _MOUNTED_DIRS:
        base = os.path.join(_PROJECT_ROOT, d)
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            if root[len(base):].count(os.sep) >= 3:
                dirs[:] = []
            dirs[:] = [x for x in dirs if x not in _SKIP_DIRS]
            for f in files:
                seen += 1
                if seen > max_entries:
                    return best
                if f != name:
                    continue
                fp = os.path.join(root, f)
                try:
                    mt = os.path.getmtime(fp)
                except OSError:
                    continue
                if best_mtime is None or mt > best_mtime:
                    best, best_mtime = fp, mt
    return best


def _ensure_sendable_path(raw_path):
    """返回 (容器内可发送的路径, 错误码)。

    容器内读不到给定路径时（典型：宿主机 /tmp、/home/asumi 下容器未挂载的路径，
    或者 cwd 不同导致的相对路径），先试项目内等价路径，再按同名文件兜底，
    找到源文件后复制进 data/sent_files/ 并校验，返回容器内路径。
    """
    for candidate in _path_candidates(raw_path):
        if os.path.isfile(candidate):
            return candidate, ""

    name = os.path.basename(str(raw_path or "").strip().rstrip("/"))
    src = _find_same_name(name)
    if not src:
        return "", "file_not_found"

    try:
        os.makedirs(_FALLBACK_DIR, exist_ok=True)
        dst = os.path.join(_FALLBACK_DIR, f"{time.strftime('%Y%m%d_%H%M%S')}_{name}")
        shutil.copy2(src, dst)
    except OSError as e:
        logger.warning(f"[Tool] 兜底复制文件失败 {src} -> {_FALLBACK_DIR}: {e}")
        return "", "file_copy_failed"

    if not os.path.isfile(dst) or os.path.getsize(dst) != os.path.getsize(src):
        logger.warning(f"[Tool] 兜底复制校验失败: {src} -> {dst}")
        return "", "file_copy_failed"
    logger.info(f"[Tool] 路径兜底：{raw_path} -> {src}，复制到 {dst}")
    return dst, ""


async def send_master_private_tool(context, message):
    """向主人私聊发送私密信息，同时保存群聊上下文快照供后续召回。"""
    if not message:
        return ToolResult(success=False, content="缺少消息内容", error="missing_message")

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
            )
            logger.info(f"[Tool] 已同步消息到主人私聊历史 ({master_cid})")
    except Exception as e:
        logger.warning(f"[Tool] 同步私聊历史失败（不影响发送）: {e}")
    return ToolResult(success=True, content="已私聊发送给主人。")


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
                content=f"未找到用户 '{target}'，可能他还没在群里说过话或者程序冷启动未记录到映射。",
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


async def send_qq_file_tool(context, file_path, file_type="auto", caption=None):
    """发送本地图片、语音或普通文件。支持 [img:XXX] 索引。

    容器内读不到给定路径时（宿主机 /tmp 等未挂载路径、cwd 不同的相对路径），
    会兜底把文件复制到 data/sent_files/ 再用容器内路径发送。
    """
    if not file_path:
        return ToolResult(success=False, content="缺少文件路径", error="missing_file_path")

    file_path = _resolve_image_path(context, file_path)
    abs_path, err = _ensure_sendable_path(file_path)
    if not abs_path:
        if err == "file_copy_failed":
            return ToolResult(
                success=False,
                content=f"文件读到了但复制到 data/sent_files/ 失败，无法发送：{file_path}",
                error="file_copy_failed",
            )
        return ToolResult(
            success=False,
            content=f"文件不存在，也无法在项目挂载目录里找到同名文件：{file_path}",
            error="file_not_found",
        )

    suffix = os.path.splitext(abs_path)[1].lower()
    if file_type == "auto":
        if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
            file_type = "image"
        elif suffix in {".amr", ".silk", ".ogg"}:
            file_type = "voice"
        else:
            # 音乐文件（mp3/m4a/wav/flac 等）按普通文件发送，避免走 QQ 语音转码（60s 限制）
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
