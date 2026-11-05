# core/tools/tools_bash.py
"""通用 bash 工具：让 Yuki 亲手跑命令。

定位：轻量、短耗时的同步操作（查状态、跑 skills 脚本、调 adb 等），
多步探索或长时间任务仍然交给小女仆。

安全策略：不设命令白名单（Yuki 需要较大的操作权限），只做两件事：
    1. 拦截「把自己或宿主机搞没」的毁灭性命令（防呆，不是权限墙）；
    2. 禁止直接读取凭证文件、并对输出里的密钥形态做脱敏。
"""
import asyncio
import os
import re
import signal

from config import cfg
from core.toolchain import ToolResult
from utils import BASE_DIR
from utils.logger import get_logger

logger = get_logger("tools")

# 工作目录固定在项目根：skills/ 脚本、data/ 路径都以此为准
WORKDIR = os.path.abspath(BASE_DIR)

# 防呆黑名单：命中即拒绝执行（附原因）
_DENY_RULES = [
    (re.compile(r"\bmkfs(\.\w+)?\b"), "格式化文件系统"),
    (re.compile(r"\bdd\b[^\n]*\bof=/dev/(sd|nvme|mmcblk|vd)"), "直接写块设备"),
    (re.compile(r"\b(shutdown|reboot|halt|poweroff)\b"), "关机/重启系统"),
    (re.compile(r":\(\)\s*\{[^}]*\}\s*;\s*:"), "fork 炸弹"),
    (re.compile(r"\b(chmod|chown)\b[^\n]*\s-R\s+[0-7]{3,4}\s+/(\s|$)"), "递归修改根目录权限"),
    (re.compile(r"\brm\b[^\n]*\s-r[a-z]*f[a-z]*\s*(/|~|/\*|~/\*)(\s|$)"), "递归删除根目录/家目录"),
    (re.compile(r">\s*/dev/(sd|nvme|mmcblk)"), "覆写块设备"),
]

# 凭证文件：只拦“读取/输出”，不影响正常调试其他配置
_CREDENTIAL_RULES = [
    (re.compile(r"\.credentials"), "凭证文件"),
    (re.compile(r"credentials\.ya?ml"), "凭证文件"),
    (re.compile(r"(^|[\s/'\"])(\.env)([\s'\"]|$)"), "环境变量文件"),
    (re.compile(r"id_rsa|id_ed25519"), "私钥文件"),
]

# 输出脱敏：密钥形态一律打码
_REDACT_RULES = [
    (re.compile(r"sk-[A-Za-z0-9_\-]{12,}"), "sk-***"),
    (re.compile(r"tvly-[A-Za-z0-9_\-]{8,}"), "tvly-***"),
    (re.compile(r"(?i)((?:api[_-]?key|token|secret|password|cookie)\s*[:=]\s*)"
                r"[\"']?[A-Za-z0-9_\-/.+]{8,}"), r"\1***"),
]

# 不传给子进程的敏感环境变量
_SENSITIVE_ENV = re.compile(r"(?i)(api[_-]?key|token|secret|password|credential|deepseek)")


def _check_command(command: str) -> str:
    """返回拒绝原因；空字符串表示放行。"""
    for pattern, reason in _DENY_RULES:
        if pattern.search(command):
            return f"拒绝执行：疑似{reason}命令，容易把运行环境搞坏。"
    for pattern, reason in _CREDENTIAL_RULES:
        if pattern.search(command):
            return f"拒绝执行：不允许读取{reason}（防止密钥外泄）。"
    return ""


def _redact(text: str) -> str:
    for pattern, replacement in _REDACT_RULES:
        text = pattern.sub(replacement, text)
    return text


def _child_env() -> dict:
    return {k: v for k, v in os.environ.items() if not _SENSITIVE_ENV.search(k)}


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = int(limit * 0.65)
    tail = max(0, limit - head - 40)
    return f"{text[:head]}\n...(中间省略 {len(text) - head - tail} 字)...\n{text[-tail:]}"


async def _run(command: str, timeout: float) -> tuple[int, str]:
    """执行命令，返回 (退出码, 合并输出)；超时按进程组整棵杀掉。"""
    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=WORKDIR,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=_child_env(),
        start_new_session=True,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode or 0, (stdout or b"").decode("utf-8", "replace")
    except asyncio.TimeoutError:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        await proc.wait()
        raise


async def bash_tool(context, command, timeout=20, note="", remember=True):
    """在当前环境执行一条 shell 命令。"""
    command = (command or "").strip()
    if not command:
        return ToolResult(success=False, content="缺少要执行的命令", error="missing_command")

    rejected = _check_command(command)
    if rejected:
        logger.warning(f"[Bash] 已拦截命令 chat={context.chat_id}: {command[:120]}")
        return ToolResult(success=False, content=rejected, error="command_rejected")

    cfg_tools = getattr(cfg, "tools", None)
    max_timeout = float(getattr(cfg_tools, "bash_max_timeout_seconds", 60))
    max_chars = int(getattr(cfg_tools, "bash_max_output_chars", 4000))
    try:
        timeout = float(timeout or getattr(cfg_tools, "bash_timeout_seconds", 20))
    except (TypeError, ValueError):
        timeout = 20.0
    timeout = max(1.0, min(timeout, max_timeout))

    try:
        exit_code, output = await _run(command, timeout)
    except asyncio.TimeoutError:
        return ToolResult(
            success=False,
            content=f"命令执行超时（{timeout:.0f}s），已终止。长任务请交给小女仆。",
            data={"command": command, "note": note},
            error="timeout",
        )
    except Exception as exc:
        logger.error(f"[Bash] 执行失败: {exc}")
        return ToolResult(
            success=False, content=f"命令执行失败: {exc}", data={"command": command}, error="exec_failed"
        )

    output = _truncate(_redact(output).strip(), max_chars)
    logger.info(f"[Bash] chat={context.chat_id} exit={exit_code} cmd={command[:100]}")
    content = output or "(命令没有输出)"
    if exit_code != 0:
        content = f"退出码 {exit_code}\n{content}"
    return ToolResult(
        success=exit_code == 0,
        content=content,
        data={
            "command": command,
            "exit_code": exit_code,
            "note": note or "",
            # remember=False：原始输出只在本轮可见，不写回长期历史
            "no_persist": not remember,
        },
        error="" if exit_code == 0 else "non_zero_exit",
    )
