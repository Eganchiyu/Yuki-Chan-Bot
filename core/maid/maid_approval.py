"""终端命令的授权判定。

原来的关键词黑名单会把 `rm -rf /tmp/x` 这类正常命令一起误杀。现在拆成两层：
- 硬拦截：只保留真正不可逆的少数命令（sudo / 关机 / mkfs / dd 写块设备 / 删根目录）。
- 静默判定：其余可疑命令交给「继承了当前 session 上下文与人格的 Yuki」做一次
  是否执行的判断，结果写进 trace，不打扰群聊。
没有 approver 的调用路径（CLI 直跑、toolchain inline）直接放行，避免卡住调试。
"""
import asyncio
import json
import os
import re

from config import cfg
from utils.llm_client import llm_chat

from core.maid.maid_common import _extract_json_from_mixed, logger

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

JUDGE_TIMEOUT = 30
JUDGE_RETRIES = 1
RECENT_CHAT_LIMIT = 10
RECENT_MSG_CHARS = 500

HARD_BLOCK_RULES = [
    (re.compile(r"\bsudo\b"), "sudo"),
    (re.compile(r"\b(shutdown|reboot|poweroff|halt|init\s+0)\b"), "关机/重启"),
    (re.compile(r"\bmkfs(\.\w+)?\b|\bformat\s+[a-z]:"), "格式化文件系统"),
    (re.compile(r"\bdd\b[^;&|]*\bof=/dev/"), "直接写块设备"),
    (re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"), "fork 炸弹"),
]

# 命中这些模式时不直接执行，先让 Yuki 判定；判定通过照常执行。
APPROVAL_RULES = [
    (re.compile(r"\brm\s+(-[^\s]+\s+)*"), "删除文件"),
    (re.compile(r"\bmv\s+"), "移动/改名文件"),
    (re.compile(r"\b(trash|shred)\b"), "删除文件"),
    (re.compile(r"\b(pip3?|python3?\s+-m\s+pip)\s+install\b"), "安装 Python 依赖"),
    (re.compile(r"\b(npm|pnpm|yarn)\s+(install|add|i)\b"), "安装前端依赖"),
    (re.compile(r"\b(kill|pkill|killall)\b"), "结束进程"),
    (re.compile(r"\bgit\s+(push|reset|clean|rebase|checkout)\b"), "改动 git 历史/远端"),
    (re.compile(r"\b(systemctl|service)\s+"), "操作系统服务"),
    (re.compile(r"\b(chmod|chown)\s+-R\b"), "递归改权限"),
    (re.compile(r"\bcurl\b[^;&|]*\|\s*(sudo\s+)?(bash|sh)\b|\bwget\b[^;&|]*\|\s*(bash|sh)\b"), "下载即执行"),
    (re.compile(r">\s*/(?!home/asumi/Yuki)"), "写入项目外路径"),
]


def _rm_targets_root(command: str) -> bool:
    """只拦真正删根目录的 rm，不再用字符串包含判断误杀 /tmp 之类。"""
    tokens = re.split(r"[\s;&|]+", command)
    if not any(token == "rm" or token.endswith("/rm") for token in tokens):
        return False
    has_recursive = any(
        token.startswith("-") and not token.startswith("--") and ("r" in token or "R" in token)
        for token in tokens
    )
    targets = [token for token in tokens if token in {"/", "/*", "/.", "/.."}]
    return has_recursive and bool(targets)


def classify_command(command: str) -> tuple:
    """返回 (verdict, reason)，verdict ∈ {"block", "ask", "allow"}。"""
    cmd = (command or "").strip()
    if not cmd:
        return "block", "命令为空"

    if _rm_targets_root(cmd):
        return "block", "删除根目录"

    for pattern, label in HARD_BLOCK_RULES:
        if pattern.search(cmd):
            return "block", label

    for pattern, label in APPROVAL_RULES:
        if pattern.search(cmd):
            return "ask", label
    return "allow", ""


def recent_chat_text(history_manager, chat_id, limit: int = RECENT_CHAT_LIMIT) -> str:
    """取该会话最近几条对话，压成一段文本给判定用。"""
    if history_manager is None or chat_id is None:
        return ""
    try:
        history = history_manager.load()
        session = history.get(str(chat_id)) or []
    except Exception as e:
        logger.warning(f"[Maid] 读取会话历史失败: {e}")
        return ""

    lines = []
    for message in session[-limit:]:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role not in {"user", "assistant"}:
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        content = content.replace("\n", " ").strip()
        if not content:
            continue
        if len(content) > RECENT_MSG_CHARS:
            content = content[:RECENT_MSG_CHARS] + "…"
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _judge_messages(persona: str, goal: str, command: str, cwd: str, thought: str, chat_text: str) -> list:
    system = (
        f"{persona or ''}\n\n"
        "[内部判定模式] 你现在不是在对用户说话，而是在替后台小女仆做一次「这条终端命令是否该执行」的判断。\n"
        "判断依据：是否服务于当前任务目标、是否可能破坏机主的系统或数据。\n"
        "只输出 JSON：{\"approve\": true 或 false, \"reason\": \"一句话理由\"}"
    )
    payload = [f"当前任务目标：{goal}"]
    if chat_text:
        payload.append(f"当前会话最近对话：\n{chat_text}")
    payload.append(f"小女仆当前思考：{thought or '（无）'}")
    payload.append(f"待执行命令：{command}\n工作目录：{cwd}")
    payload.append("请给出判定 JSON。")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(payload)},
    ]


def _parse_verdict(text: str) -> tuple:
    obj = _extract_json_from_mixed(text or "")
    if not isinstance(obj, dict) or "approve" not in obj:
        return None, ""
    approve = obj.get("approve")
    if isinstance(approve, str):
        approve = approve.strip().lower() in {"true", "yes", "1", "同意"}
    else:
        approve = bool(approve)
    reason = str(obj.get("reason") or "").strip()
    return approve, reason


async def judge_by_yuki(
    command: str,
    goal: str,
    cwd: str = None,
    thought: str = "",
    persona: str = "",
    history_manager=None,
    chat_id=None,
    timeout: float = JUDGE_TIMEOUT,
) -> tuple:
    """让继承当前 session 上下文的 Yuki 判断命令是否执行。失败/超时一律按拒绝处理。"""
    chat_text = await asyncio.to_thread(recent_chat_text, history_manager, chat_id)
    messages = _judge_messages(persona, goal, command, cwd or PROJECT_ROOT, thought, chat_text)

    last_error = ""
    for attempt in range(JUDGE_RETRIES + 1):
        try:
            raw = await asyncio.wait_for(
                llm_chat(
                    messages=messages,
                    model=cfg.LLM_MODEL,
                    response_format={"type": "json_object"},
                    temperature=0.2,
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            last_error = f"判定超时（{timeout}s）"
            logger.warning(f"[Maid] 命令判定超时: {command}")
            continue
        except Exception as e:
            last_error = f"判定调用异常：{e}"
            logger.warning(f"[Maid] 命令判定异常: {e}")
            continue

        approve, reason = _parse_verdict(raw)
        if approve is None:
            last_error = "判定结果无法解析"
            logger.warning(f"[Maid] 命令判定结果无法解析: {str(raw)[:120]}")
            messages.append({"role": "user", "content": "上一条不是合法 JSON，请只输出 {\"approve\": true/false, \"reason\": \"...\"}"})
            continue
        logger.info(f"[Maid] 命令判定：{'同意' if approve else '拒绝'}（{reason}）")
        return approve, reason or ("同意执行" if approve else "未给出理由")

    return False, last_error or "判定失败"


def build_approver(yuki_state, history_manager, chat_id, mode, goal, gateway=None):
    """构造传给 maid_evolution_loop 的 approver 回调（跑在 Yuki 的事件循环里）。"""
    escalate = os.getenv("MAID_ESCALATE_TO_MASTER", "").strip().lower() in {"1", "true", "yes"}

    async def _approver(command: str, cwd: str = None, thought: str = "") -> tuple:
        persona = ""
        try:
            persona = yuki_state.get_setting(mode)
        except Exception as e:
            logger.warning(f"[Maid] 获取 Yuki 人格失败: {e}")

        approve, reason = await judge_by_yuki(
            command=command,
            goal=goal,
            cwd=cwd,
            thought=thought,
            persona=persona,
            history_manager=history_manager,
            chat_id=chat_id,
        )
        if approve or not escalate or gateway is None:
            return approve, reason

        # 可选升级：Yuki 拒绝后在群里问机主一次（默认关闭，MAID_ESCALATE_TO_MASTER=1 打开）
        try:
            await gateway.send(
                str(chat_id),
                f"【小女仆请求授权】\n命令：{command}\nYuki 的判断：{reason}\n机主回复「同意」即可执行，其它视为拒绝。",
                mode=mode,
            )
            approved_by_master, master_reason = await wait_for_master_reply(history_manager, chat_id)
            if approved_by_master:
                return True, "机主同意"
            return False, f"机主未同意：{master_reason}"
        except Exception as e:
            logger.warning(f"[Maid] 升级询问机主失败: {e}")
            return False, reason

    return _approver


async def wait_for_master_reply(history_manager, chat_id, timeout: float = 300, interval: float = 2.0) -> tuple:
    """轮询会话历史等机主回一条新消息，用于可选的升级授权。"""
    try:
        baseline = len((history_manager.load().get(str(chat_id)) or []))
    except Exception:
        baseline = 0

    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(interval)
        try:
            session = history_manager.load().get(str(chat_id)) or []
        except Exception:
            continue
        for message in session[baseline:]:
            if not isinstance(message, dict) or message.get("role") != "user":
                continue
            content = str(message.get("content") or "").strip()
            if not content:
                continue
            agree = content in {"同意", "可以", "允许", "执行", "ok", "OK", "yes"} or "同意" in content
            return agree, content[:80]
    return False, "等待机主回复超时"
