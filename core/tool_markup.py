# core/tool_markup.py
"""文本形式的工具调用解析与清洗。

模型在个别情况下（工具轮次用尽后走了不带 tools 的收尾请求、上游把
tool_calls 折叠进 content、模型自己模仿标记格式）会把工具调用写成**正文
文本**，例如：

    <｜｜DSML｜｜ calls>
    <｜｜DSML｜｜ invoke name="delegate_to_maid">
    <｜｜DSML｜｜ parameter name="arguments" string="true">{"goal": "xxx"}</｜｜DSML｜｜ parameter>
    </｜｜DSML｜｜ invoke>
    </｜｜DSML｜｜ calls>

或 ``<tool_call>{"name": ..., "arguments": {...}}</tool_call>``。

这类文本既不能执行，又会被当成回复原文发出去。本模块提供两个入口：

- ``extract_text_tool_calls()``：把文本里的调用还原成标准 tool_calls，交给
  工具链照常执行（自我纠正），同时返回剔除了标记的正文；
- ``strip_tool_call_markup()``：只剔除标记，用于发送前的兜底清洗。
"""
import json
import re
import uuid

from utils.logger import get_logger

logger = get_logger("tool_markup")

# 标记片段：`<｜｜DSML｜｜`、`</｜｜DSML｜｜`，兼容 `<||DSML||`、`<|DSML|`、全半角竖线混用
_DSML_OPEN = r"<[|｜]{1,3}\s*DSML\s*[|｜]{1,3}\s*"
_DSML_END = r"</?[|｜]{1,3}\s*DSML\s*[|｜]{1,3}\s*/?\s*"

_DSML_INVOKE_BLOCK_RE = re.compile(_DSML_OPEN + r"invoke\b([^>]*)>(.*?)" + _DSML_END + r"invoke\s*>", re.S)
_DSML_PARAM_RE = re.compile(_DSML_OPEN + r"parameter\b([^>]*)>(.*?)" + _DSML_END + r"parameter\s*>", re.S)
_DSML_TAG_RE = re.compile(
    r"</?[|｜]{1,3}\s*DSML\s*[|｜]{1,3}\s*/?\s*(?:calls|invoke|parameter)\b[^>]*>", re.S
)
_NAME_ATTR_RE = re.compile(r"""name\s*=\s*["']?([\w\-]+)["']?""")

# <tool_call>...</tool_call> / <function_call>...</function_call>
_JSON_BLOCK_RE = re.compile(r"<tool_call>(.*?)</tool_call>", re.S | re.I)
# <function=name>{"args"}</function>
_FUNCTION_BLOCK_RE = re.compile(r"<function\s*=\s*([\w\-]+)\s*>(.*?)</function\s*>", re.S | re.I)
# 裸 JSON 代码块：```json {"name": ..., "arguments": {...}} ```
_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S | re.I)


def _parse_args(value):
    """把参数值解析成 dict：优先当 JSON 对象，失败则原样返回字符串。"""
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text
    return parsed


def _build_call(name, args, index):
    """构造标准 tool_call；单个 arguments 键且为 JSON 对象时展开成参数。"""
    if isinstance(args, dict) and set(args) == {"arguments"}:
        inner = _parse_args(args["arguments"])
        if isinstance(inner, dict):
            args = inner
    arguments = args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)
    return {
        "id": f"call_text_{uuid.uuid4().hex[:12]}_{index}",
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def _parse_dsml_invokes(text):
    """解析 DSML 的 invoke/parameter 标记。"""
    calls = []
    for attrs, body in _DSML_INVOKE_BLOCK_RE.findall(text):
        name_match = _NAME_ATTR_RE.search(attrs or "")
        if not name_match:
            continue
        params = {}
        for param_attrs, param_body in _DSML_PARAM_RE.findall(body or ""):
            param_name = _NAME_ATTR_RE.search(param_attrs or "")
            if param_name:
                params[param_name.group(1)] = _parse_args(param_body)
        if not params:
            # invoke 里直接写 JSON 的变体
            direct = _parse_args(body)
            if isinstance(direct, dict):
                params = direct
        calls.append(_build_call(name_match.group(1), params, len(calls)))
    return calls


def _parse_json_blocks(text):
    """解析 <tool_call>{...}</tool_call> 与裸 JSON 代码块。"""
    calls = []
    candidates = list(_JSON_BLOCK_RE.findall(text)) + list(_FENCED_JSON_RE.findall(text))
    for raw in candidates:
        payload = _parse_args(raw)
        if not isinstance(payload, dict):
            continue
        name = payload.get("name") or payload.get("tool") or payload.get("function")
        if isinstance(name, dict):  # {"function": {"name": ..., "arguments": ...}}
            args = name.get("arguments") or name.get("parameters") or {}
            name = name.get("name")
        else:
            args = payload.get("arguments") or payload.get("parameters") or {}
        if isinstance(name, str) and name:
            calls.append(_build_call(name, _parse_args(args), len(calls)))
    return calls


def _parse_function_blocks(text):
    """解析 <function=name>json</function> 风格。"""
    calls = []
    for name, raw in _FUNCTION_BLOCK_RE.findall(text):
        args = _parse_args(raw)
        if not isinstance(args, dict):
            args = {"arguments": raw}
        calls.append(_build_call(name, args, len(calls)))
    return calls


def strip_tool_call_markup(text: str) -> str:
    """剔除正文中的工具调用标记，只留可读文字。

    未闭合的开标记按「从标记起到结尾都是内部结构」处理，直接截断，
    宁可少发一句，也不把这些标记外泄。
    """
    if not text:
        return ""
    cleaned = _JSON_BLOCK_RE.sub("", text)
    cleaned = _FUNCTION_BLOCK_RE.sub("", cleaned)
    cleaned = _DSML_INVOKE_BLOCK_RE.sub("", cleaned)
    # 未闭合的标记（被截断）：从第一个残留标记起全部丢弃
    leftover = re.search(r"</?[|｜]{1,3}\s*DSML\s*[|｜]{1,3}\s*/?\s*(?:calls|invoke|parameter)\b", cleaned, re.S)
    if leftover:
        cleaned = cleaned[: leftover.start()]
    cleaned = _DSML_TAG_RE.sub("", cleaned)
    if not cleaned.strip():
        # 整段都是标记时，可能只剩裸 JSON 体，一并丢弃
        return ""
    return cleaned.strip()


def extract_text_tool_calls(content: str, valid_names=None):
    """从正文中还原工具调用。

    Returns:
        (calls, cleaned_text)：calls 是标准 tool_call 列表（可能为空），
        cleaned_text 是剔除了标记后的正文。
    """
    if not content or not isinstance(content, str):
        return [], content or ""

    calls = _parse_dsml_invokes(content)
    if not calls:
        calls = _parse_function_blocks(content)
    if not calls:
        calls = _parse_json_blocks(content)

    allowed = set(valid_names) if valid_names else None
    if allowed is not None:
        calls = [c for c in calls if c["function"]["name"] in allowed]
    if not calls:
        return [], content

    cleaned = strip_tool_call_markup(content)
    # 只写了 JSON 体的变体：正文只剩裸 JSON 时视为纯标记
    if cleaned and cleaned.lstrip().lower().startswith("{"):
        try:
            json.loads(cleaned)
            cleaned = ""
        except json.JSONDecodeError:
            pass
    return calls, cleaned
