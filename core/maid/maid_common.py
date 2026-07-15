import json
import os
import re

from utils.logger import get_logger

logger = get_logger("maid")

# --- 目录初始化 ---
SKILLS_DIR = "skills"      # 存放长期通用技能 (.py 和 .md)
WORKSPACE_DIR = "workspace" # 存放当前任务的临时草稿 (.py)
TASKS_DIR = "tasks"
LOGS_DIR = "logs"
MAID_VENV_DIR = "maid_venv" # 存放小女仆独立运行环境的目录

for d in [SKILLS_DIR, WORKSPACE_DIR, TASKS_DIR, LOGS_DIR, MAID_VENV_DIR]:
    os.makedirs(d, exist_ok=True)

MAX_TOOL_OUTPUT_CHARS = 12000
TERMINAL_DEFAULT_TIMEOUT = 30
TERMINAL_MAX_TIMEOUT = 120
MAX_MAID_ROUNDS = 20


def clean_json_output(text):
    """提取第一个 { 到最后一个 } 之间的内容，防止模型输出废话"""
    if not text: return ""
    match = re.search(r'\{.*\}', text, re.DOTALL)
    return match.group(0) if match else text.strip()


# --- 代码清洗函数 ---
def clean_code_block(raw_code):
    """
    清洗模型输出的代码，移除首尾的 Markdown 标记和多余空白。
    """
    if not raw_code:
        return ""

    code = raw_code.strip()
    # 增强过滤：处理 ```python 或 ```py
    if code.startswith("```"):
        lines = code.splitlines()
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        code = "\n".join(lines).strip()
    return code


def _truncate_text(text: str, limit: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    """限制工具返回长度，避免一次终端输出撑爆小女仆上下文。"""
    if text is None:
        return ""
    text = str(text)
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-limit // 2:]
    return f"{head}\n\n... [中间输出过长，已截断 {len(text) - limit} 字符] ...\n\n{tail}"


def _decode_process_output(output_bytes: bytes) -> str:
    """兼容 Windows 中文控制台输出。"""
    if not output_bytes:
        return ""
    for enc in ("utf-8", "gbk", "cp936"):
        try:
            return output_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return output_bytes.decode("utf-8", errors="replace")


def _extract_json_from_mixed(text: str):
    """从带 tip/日志的 CLI 输出里提取第一个合法 JSON 对象。"""
    if not text:
        return None
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[i:])
            return obj
        except json.JSONDecodeError:
            continue
    return None
