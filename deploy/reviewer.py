#!/usr/bin/env python3
"""自改补丁的独立审查（宿主侧）。

为什么放在宿主而不是容器内：
    容器内的 `core/maid/maid_selfevolve.py` 是可被小女仆自己修改的代码，
    把审查逻辑放在那里等于让被审查者保管审查规则。本文件在宿主 `deploy/` 下，
    容器只读挂载 + agent 禁区，改不到自己。

它只做一件事：给「补丁 + 任务目标」打一次模型分，输出通过/驳回与具体改法。
**它不是安全边界**——禁区路径判定、5 道校验门、快照回滚一个都不能少，
它只负责把粗暴的行数阈值换成一次语义判断。

已知局限：写代码与审查代码是同一个模型，存在自我批准偏差。缓解手段是
独立审查员提示、低温度、强制要求指出具体问题与修改建议。
"""
import difflib
import json
import os
import urllib.error
import urllib.request

ROOT = os.environ.get("YUKI_ROOT", "/home/asumi/Yuki")
MAX_DIFF_CHARS = 40000
MAX_FILE_DIFF_CHARS = 15000

REVIEW_SYSTEM = """你是代码审查员，负责审查一次「AI 自我修改自身代码」的补丁。

判断标准（按重要性排序）：
1. 相关性：改动是否只服务于声明的任务目标？有没有顺手改无关模块？
2. 不删功能：有没有删除或削弱既有功能、异常处理、日志、限流、安全防护？
3. 数据安全：有没有触碰数据目录、记忆库、向量库、配置文件、人格设定？
4. 正确性：逻辑是否自相矛盾、变量未定义、异常路径缺失、导入缺失？
5. 可回滚：改动是否小到能靠 git 回滚，而不是整模块重写？
6. 副作用：有没有引入外部依赖、阻塞主循环、无界循环、写死绝对路径？

你不负责判断风格好不好、注释够不够。只判断「这次改动该不该被允许生效」。

只输出 JSON，不要任何解释文字：
{"approve": true 或 false, "risk": "low|medium|high", "problems": ["具体问题"], "suggestions": ["具体改法"]}

要求：
- approve=false 时，problems 必须指出可定位的问题（文件/行为），suggestions 必须给出可执行的修改方向。
- 拿不准时宁可 approve=false 并说明需要补充什么信息。
"""


def _simple_yaml_get(text, section, key):
    """不依赖 PyYAML 的最小解析：只取 `section:` 下的一级 `key: value`。

    宿主 python3 通常没装 yaml（supervisor 刻意只用标准库），
    而 config.yaml 结构固定（一级两空格缩进），手写足够且无额外依赖。
    """
    current = None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith((" ", "\t")):
            current = line.split(":", 1)[0].strip()
            continue
        if current != section:
            continue
        stripped = line.strip()
        if stripped.startswith(f"{key}:"):
            return stripped.split(":", 1)[1].strip().strip("'\"")
    return ""


def _load_llm_config():
    """读 configs/config.yaml 的 LLM 配置；读不到就用环境变量兜底。"""
    try:
        with open(os.path.join(ROOT, "configs", "config.yaml"), encoding="utf-8") as f:
            text = f.read()
    except Exception:
        text = ""

    base_url = _simple_yaml_get(text, "api", "llm_base_url") or os.environ.get("YUKI_LLM_BASE_URL", "https://api.deepseek.com/v1")
    api_key = _simple_yaml_get(text, "api", "llm_api_key") or os.environ.get("YUKI_LLM_API_KEY", "")
    model = _simple_yaml_get(text, "model", "llm") or os.environ.get("YUKI_LLM_MODEL", "deepseek-chat")
    return {"base_url": base_url.rstrip("/"), "api_key": api_key, "model": model}


def _file_diff(request_dir, rel_path):
    """生成单文件 unified diff；新文件则整份算新增。"""
    new_path = os.path.join(request_dir, "files", rel_path)
    old_path = os.path.join(ROOT, rel_path)
    try:
        with open(new_path, encoding="utf-8", errors="replace") as f:
            new_text = f.read()
    except Exception as e:
        return f"（无法读取候选文件 {rel_path}: {e}）"

    if os.path.exists(old_path):
        try:
            with open(old_path, encoding="utf-8", errors="replace") as f:
                old_text = f.read()
        except Exception:
            old_text = ""
        diff = list(difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"a/{rel_path}", tofile=f"b/{rel_path}", n=3,
        ))
        text = "".join(diff) or f"（{rel_path} 内容无变化）"
    else:
        text = f"（新文件 {rel_path}，{len(new_text.splitlines())} 行）\n" + new_text

    if len(text) > MAX_FILE_DIFF_CHARS:
        text = text[:MAX_FILE_DIFF_CHARS] + f"\n... [本文件 diff 过长，已截断，原长 {len(text)} 字符]"
    return text


def build_review_messages(request_dir, req, files):
    diffs = []
    for item in files:
        rel = str(item["path"]).replace("\\", "/")
        diffs.append(f"### {rel}\n```diff\n{_file_diff(request_dir, rel)}\n```")
    diff_text = "\n\n".join(diffs)
    if len(diff_text) > MAX_DIFF_CHARS:
        diff_text = diff_text[:MAX_DIFF_CHARS] + f"\n... [diff 总计过长已截断，原长 {len(diff_text)} 字符]"

    user = (
        f"任务目标：\n{req.get('reason') or '(未提供)'}\n\n"
        f"改动摘要：\n{req.get('summary') or '(未提供)'}\n\n"
        f"涉及 {len(files)} 个文件：\n{diff_text}\n\n"
        "请给出审查 JSON。"
    )
    return [
        {"role": "system", "content": REVIEW_SYSTEM},
        {"role": "user", "content": user},
    ]


def _call_llm(messages, timeout=90):
    conf = _load_llm_config()
    if not conf["api_key"]:
        return None, "未找到 LLM API Key（configs/config.yaml 的 api.llm_api_key 为空）"
    payload = {
        "model": conf["model"],
        "messages": messages,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        f"{conf['base_url']}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {conf['api_key']}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"], ""
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        return None, f"审查请求失败 HTTP {e.code}: {detail}"
    except Exception as e:
        return None, f"审查请求异常: {e}"


def _parse(text):
    """从模型输出里抠出 JSON。"""
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return None


def review_patch(request_dir, req, files):
    """返回 (approve, detail, risk)。

    approve=False 且 detail 里含「审查不可用」时，表示是审查环节本身失败（网络/配置），
    调用方可以据此决定是按拒绝处理还是重试。
    """
    messages = build_review_messages(request_dir, req, files)
    raw, err = _call_llm(messages)
    if err:
        return False, f"审查不可用：{err}（保守起见不放行，请稍后重试或人工确认）", "unknown"

    verdict = _parse(raw)
    if not isinstance(verdict, dict) or "approve" not in verdict:
        return False, f"审查结果无法解析，保守起见不放行。原始输出：{str(raw)[:300]}", "unknown"

    approve = verdict.get("approve")
    if isinstance(approve, str):
        approve = approve.strip().lower() in {"true", "yes", "1"}
    approve = bool(approve)
    risk = str(verdict.get("risk") or "unknown")
    problems = verdict.get("problems") or []
    suggestions = verdict.get("suggestions") or []

    if approve:
        detail = f"审查通过（风险 {risk}）" + (f"；提示：{'；'.join(map(str, problems))}" if problems else "")
        return True, detail, risk

    lines = [f"审查驳回（风险 {risk}）"]
    if problems:
        lines.append("问题：")
        lines += [f"  - {p}" for p in problems]
    if suggestions:
        lines.append("建议改法：")
        lines += [f"  - {s}" for s in suggestions]
    if not problems and not suggestions:
        lines.append("（审查未给出具体理由，请缩小改动范围后重试）")
    return False, "\n".join(lines), risk
