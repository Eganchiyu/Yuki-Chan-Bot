#!/usr/bin/env python3
"""自改补丁的独立审查（宿主侧）。

为什么放在宿主而不是容器内：
    容器内的 `core/maid/maid_selfevolve.py` 是可被小女仆自己修改的代码，
    把审查逻辑放在那里等于让被审查者保管审查规则。本文件在宿主 `deploy/` 下，
    容器只读挂载 + agent 禁区，改不到自己。

它只做一件事：给「补丁 + 任务目标」打一次模型分，把问题分成两级——
blocking（必修，会导致出真事）阻断生效；advisory（建议）只记录，不阻断。
早先是二值判定，一条「表述不一致」也能卡死整个修复，这是主要改动原因。
**它不是安全边界**——禁区路径判定、5 道校验门、快照回滚一个都不能少，
它只负责把粗暴的行数阈值换成一次语义判断。

已知局限：写代码与审查代码是同一个模型，存在自我批准偏差。缓解手段是
独立审查员提示、低温度、强制要求指出具体问题与修改建议。
"""
import difflib
import importlib.util
import json
import os
import py_compile
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import fields

ROOT = os.environ.get("YUKI_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAX_DIFF_CHARS = 40000
MAX_FILE_DIFF_CHARS = 15000

REVIEW_SYSTEM = """你是代码审查员，负责审查一次「AI 自我修改自身代码」的补丁。

你的输出分两级，只有一级会阻断：

## blocking（必修，写进 blocking 数组）
出现以下任一情况才算 blocking——它们会导致补丁生效后**出真事**：
1. 语法/导入/未定义符号问题，或明显会在运行时抛异常的路径（属性不存在、索引/键缺失未处理、
   异常类型没覆盖住）。
2. 删除或削弱既有功能与防护：异常处理、超时、限流、鉴权、输入校验、日志留痕。
3. 数据面扩大：读写数据目录/记忆库/向量库/密钥/配置，或让数据外发面变大（把本地文件、
   历史会话内容送给第三方 API）。
4. 资源失控：无界读取（响应体/文件不设上限）、无界循环、在协程里做阻塞调用（同步 DNS、
   同步 sleep、CPU 重活）。
5. 与声明目标无关的改动，或整模块重写导致 git 回滚不可用。
6. 补丁依赖一个**未被证明存在**的外部符号/字段（例如 import 了某模块里的函数，但没有依据
   说明它存在）。这类问题必须写进 blocking，并明确要求补丁方给出 `grep` 证据。

## advisory（建议，写进 advisory 数组，**不阻断**）
- 命名/描述文字不一致、注释缺失、可读性、可选优化、测试覆盖不足、与现有风格不一致、
  「如果……可能……」式的推测性风险。
- 只要不满足 blocking 的六条，一律放 advisory。**advisory 再多也不能作为驳回理由。**

## 判断倾向
- 如果 reason 里给出了验证命令与输出（例如 `python3 -m py_compile ...`、`pytest -k ...` 的结果），
  且改动范围与该证据一致，就采信它，不要因为「可能有问题」驳回。
- 真正拿不准且风险确实高的，写进 blocking 并说明**需要哪一条具体证据**才能放行；
  不要写「建议再确认一下」这种无法执行的意见。
- 不评判代码风格好不好、注释够不够。

只输出 JSON，不要任何解释文字：
{"risk": "low|medium|high",
 "blocking": ["必修问题，每条含 文件 + 行为 + 可执行的改法"],
 "advisory": ["不阻断的建议"]}

空数组表示没有。blocking 为空即视为通过。
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


def _read_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _providers(text):
    """把 config.yaml 的 providers 列表切成原始字典（只做 YAML 分词，不选路）。

    选哪一条、key 怎么回退、enabled 怎么过滤，全部交给 core/config/schema.py 的
    provider 层（Config.providers + get_llm_routes），这里不重复实现一套 Key 读取。
    """
    items, item, inside = [], None, False
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith((" ", "\t")):
            inside = line.split(":", 1)[0].strip() == "providers"
            continue
        if not inside:
            continue
        s = line.strip()
        if s.startswith("- "):
            item = {}
            items.append(item)
            s = s[2:].strip()
            if not s:
                continue
        if item is None or ":" not in s:
            continue
        k, v = s.split(":", 1)
        item[k.strip()] = v.strip().strip("'\"")
    return items


def _section_scalars(text, section):
    """最小解析 `section:` 下的一级 key（宿主 python3 没装 PyYAML）。"""
    out, current = {}, None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith((" ", "\t")):
            current = line.split(":", 1)[0].strip()
            continue
        if current != section:
            continue
        stripped = line.strip()
        if stripped.startswith("- ") or ":" not in stripped:
            continue
        k, v = stripped.split(":", 1)
        out[k.strip()] = v.strip().strip("'\"")
    return out


def _provider_layer():
    """按文件加载 core/config/schema.py（避开 core/__init__ 与 yaml 依赖）。"""
    path = os.path.join(ROOT, "core", "config", "schema.py")
    if not os.path.isfile(path):
        return None
    try:
        spec = importlib.util.spec_from_file_location("yuki_config_schema", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


def _pick_fields(cls, data):
    """只保留 dataclass 认识的非空字段，避免未知键把构造打挂。"""
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in data.items() if k in names and v != ""}


def _build_routes(schema, text):
    """把一份 config.yaml 文本交给 provider 层，返回其 get_llm_routes() 的有序队列。"""
    providers = [p for p in _providers(text) if p]
    api = schema.APIConfig(**_pick_fields(schema.APIConfig, _section_scalars(text, "api")))
    model = schema.ModelConfig(**_pick_fields(schema.ModelConfig, _section_scalars(text, "model")))
    cfg = schema.Config(
        providers=[schema.LLMProviderConfig(**_pick_fields(schema.LLMProviderConfig, p)) for p in providers],
        api=api,
        model=model,
    )
    if cfg.providers:
        cfg._sync_api_model_from_providers()  # 与 core/config/loader.load_config 同一套归一化
    return cfg.get_llm_routes()


def _legacy_route(text):
    """provider 层加载不了时的最后手段：仍按旧 api/model 字段取一条，保证审查员能起。"""
    return {
        "name": "legacy",
        "base_url": _simple_yaml_get(text, "api", "llm_base_url"),
        "api_key": _simple_yaml_get(text, "api", "llm_api_key"),
        "model": _simple_yaml_get(text, "model", "llm"),
    }


def _env_routes(env_get):
    """配置里没有可用 Key 时的宿主兜底：环境变量 → .env 类文件。"""
    key, source = env_get(
        "YUKI_LLM_API_KEY", "LLM_API_KEY", "REVIEWER_API_KEY",
        "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "API_KEY",
    )
    if not key:
        return []
    base_url = env_get("YUKI_LLM_BASE_URL", "LLM_BASE_URL", "OPENAI_BASE_URL")[0] or "https://api.deepseek.com/v1"
    model = env_get("YUKI_LLM_MODEL", "LLM_MODEL")[0] or "deepseek-chat"
    return [({"name": "env", "base_url": base_url, "model": model, "api_key": key}, source)]


def _resolve_routes():
    """经 provider 层解析出可用线路队列，返回 [(conf, source)]，conf 含 base_url/model/api_key。"""
    labels = ("configs/config.yaml", "configs/config.yaml.backup")
    texts = [(label, _read_text(os.path.join(ROOT, label))) for label in labels]
    schema = _provider_layer()

    env_files = {}
    for rel in (".env", "configs/.env", "configs/config.env", ".env.local"):
        path = os.path.join(ROOT, rel)
        if os.path.isfile(path):
            env_files[rel] = _read_text(path)

    def env_get(*names):
        for name in names:
            val = os.environ.get(name, "").strip()
            if val:
                return val, f"env:{name}"
        for rel, text in env_files.items():
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip().strip("'\"")
                if k.strip() in names and v:
                    return v, f"{rel}:{k.strip()}"
        return "", ""

    routes = []
    for label, text in texts:
        if not text:
            continue
        if schema is not None:
            try:
                found = _build_routes(schema, text)
            except Exception:
                found = []
            prefix = label
        else:
            found = [_legacy_route(text)]
            prefix = f"{label}:legacy"
        for item in found:
            conf = {
                "name": str(getattr(item, "name", "") or ""),
                "base_url": str(getattr(item, "base_url", "") or ""),
                "model": str(getattr(item, "model", "") or ""),
                "api_key": str(getattr(item, "api_key", "") or ""),
            }
            if conf["api_key"]:
                routes.append((conf, f"{prefix}:providers[{conf['name'] or '?'}]"))
        if routes:
            break

    if not routes:
        routes = _env_routes(env_get)

    base_url = env_get("YUKI_LLM_BASE_URL", "LLM_BASE_URL", "OPENAI_BASE_URL")[0]
    model = env_get("YUKI_LLM_MODEL", "LLM_MODEL")[0]
    normalized = []
    for conf, source in routes:
        conf["base_url"] = (conf["base_url"] or base_url or "https://api.deepseek.com/v1").rstrip("/")
        conf["model"] = conf["model"] or model or "deepseek-chat"
        normalized.append((conf, source))
    return normalized


def _load_llm_config():
    """返回 (conf, source)：conf 为 provider 层选出的首选可用线路（无 Key 时 api_key 为空）。

    线路选择（enabled 过滤、key 回退、主备合成、顺序切换）全部委托 core/config/schema.py，
    本文件只负责 YAML 分词与宿主兜底；全都没有 Key 时由 review_patch 走静态降级。
    """
    routes = _resolve_routes()
    if routes:
        return routes[0]
    return {"name": "", "base_url": "", "model": "", "api_key": ""}, ""


def _audit(event):
    """审查审计日志（logs/review_audit.jsonl）；写失败不影响主流程。"""
    try:
        path = os.path.join(ROOT, "logs", "review_audit.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        event = dict(event)
        event["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass


# 静态降级审查的白名单：与 supervisor 的路径分级一致（禁区另行显式拒绝）
ALLOW_PREFIXES = ("core/", "utils/", "modules/", "network/", "skills/", "workspace/", "temp/")
ALLOW_FILES = ("main.py", "config.py", "init.py")
BLOCK_PREFIXES = (
    ".git/", "deploy/", "configs/", "data/", "yuki_memory/", "memory/", "logs/",
    "models/", "maid_venv/", "core/prompts.py", "core/maid/maid_charter.py",
)
# 新增行里出现即提示（只记录，不阻断——降级模式只做「语法 + 路径」硬门）
RISKY_PATTERNS = (
    "os.system(", "subprocess.", "eval(", "exec(", "__import__", "ctypes.",
    "rm -rf", "shutil.rmtree", "socket.socket(", "pickle.loads",
)


def _static_check(request_dir, files):
    """无模型可用时的降级审查：py_compile + 路径白名单。

    返回 (approved, blocking, advisory)。通过即放行（配合 supervisor 的 5 道校验门、
    快照与自动回滚，静态门只拦「编译不过 / 越界路径」这两类硬错误）。
    """
    blocking, advisory = [], []
    if not files:
        return False, ["补丁文件列表为空"], advisory

    for item in files:
        rel = str(item.get("path") or "").replace("\\", "/").lstrip("./")
        if not rel:
            blocking.append("补丁里有空路径条目")
            continue
        if rel.startswith(BLOCK_PREFIXES):
            blocking.append(f"{rel} 落在禁区路径，不允许改动")
            continue
        if not (rel.startswith(ALLOW_PREFIXES) or rel in ALLOW_FILES):
            blocking.append(f"{rel} 不在可改白名单（core/ utils/ modules/ network/ skills/ workspace/ temp/ main.py config.py init.py）")
            continue

        cand = os.path.join(request_dir, "files", rel)
        if not os.path.isfile(cand):
            blocking.append(f"{rel} 候选文件不存在：{cand}")
            continue
        if not rel.endswith(".py"):
            continue
        try:
            with tempfile.TemporaryDirectory() as td:
                py_compile.compile(cand, cfile=os.path.join(td, "cand.pyc"), doraise=True)
        except py_compile.PyCompileError as e:
            blocking.append(f"{rel} 语法编译失败：{str(e).splitlines()[0][:200]}")
            continue
        except Exception as e:
            blocking.append(f"{rel} 编译异常：{e}")
            continue

        try:
            with open(cand, encoding="utf-8", errors="replace") as f:
                new_lines = f.read().splitlines()
        except Exception:
            new_lines = []
        old_path = os.path.join(ROOT, rel)
        old_text = _read_text(old_path) if os.path.exists(old_path) else ""
        old_set = set(old_text.splitlines())
        for ln in new_lines:
            if ln in old_set:
                continue
            for pat in RISKY_PATTERNS:
                if pat in ln:
                    advisory.append(f"{rel} 新增行涉及 {pat}：{ln.strip()[:120]}")
                    break

    return (not blocking), blocking, advisory


def _static_review(request_dir, req, files, why):
    """模型审查不可用时的降级入口：静态检查通过即放行，并写审计日志。"""
    approved, blocking, advisory = _static_check(request_dir, files)
    task_id = os.path.basename(str(request_dir).rstrip("/"))
    if approved:
        detail = f"静态降级审查通过（模型审查不可用：{why}）；py_compile + 路径白名单检查通过，已放行"
        if advisory:
            detail += "\n提示（不阻断）：\n" + "\n".join(f"  - {a}" for a in advisory[:10])
        _audit({"task_id": task_id, "mode": "static-fallback", "reason": why,
                "approved": True, "files": [f.get("path") for f in files],
                "advisory": advisory[:20]})
        return True, detail, "static"

    detail = f"静态降级审查驳回（模型审查不可用：{why}）：{len(blocking)} 条硬错误"
    detail += "\n" + "\n".join(f"  - {b}" for b in blocking)
    _audit({"task_id": task_id, "mode": "static-fallback", "reason": why,
            "approved": False, "files": [f.get("path") for f in files],
            "blocking": blocking[:20]})
    return False, detail, "unknown"


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
        "请给出审查 JSON（blocking / advisory 两级，blocking 为空即通过）。"
    )
    return [
        {"role": "system", "content": REVIEW_SYSTEM},
        {"role": "user", "content": user},
    ]


def _request_once(conf, messages, timeout=90):
    """按一条线路打一次请求，返回 (content, err)。"""
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


def _call_llm(messages, timeout=90):
    """按 provider 层给出的队列顺序依次尝试，返回 (content, err, source)。"""
    routes = _resolve_routes()
    if not routes:
        return None, "未找到可用 LLM 线路（provider 队列为空，环境变量与 .env 也无 Key）", ""
    errors = []
    for conf, source in routes[:5]:
        content, err = _request_once(conf, messages, timeout)
        if not err:
            return content, "", source
        errors.append(f"{source or conf.get('base_url')} → {err}")
    return None, "；".join(errors[:3]), ""


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


def _as_list(value):
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if str(v).strip()]
    return []


def _normalize_verdict(verdict):
    """把新旧两种输出格式统一成 (blocking, advisory, risk)。

    兼容旧格式：只有 approve/problems/suggestions 时，approve=false 视作 blocking。
    """
    risk = str(verdict.get("risk") or "unknown")
    if "blocking" in verdict or "advisory" in verdict:
        return _as_list(verdict.get("blocking")), _as_list(verdict.get("advisory")), risk

    problems = _as_list(verdict.get("problems"))
    suggestions = _as_list(verdict.get("suggestions"))
    approve = verdict.get("approve")
    if isinstance(approve, str):
        approve = approve.strip().lower() in {"true", "yes", "1"}
    if approve:
        return [], [f"{p}｜建议：{s}" if s else p
                    for p, s in zip(problems or [""], suggestions or [""]) if p or s], risk
    merged = [f"{p}｜建议：{s}" if s else p for p, s in zip(problems, suggestions)]
    merged += problems[len(merged):] + suggestions[len(problems):]
    return merged or ["（旧格式驳回但未给出具体理由，请缩小改动范围后重试）"], [], risk


def review_patch(request_dir, req, files):
    """返回 (approve, detail, risk)。

    只有 blocking 非空才驳回；advisory 会一并写进 detail，供模型下一轮参考，
    但不会阻止补丁生效——避免「一条文字不一致」把整个修复卡死。

    approve=False 且 detail 里含「审查不可用」时，表示是审查环节本身失败（网络/配置），
    调用方可以据此决定是按拒绝处理还是重试。
    """
    messages = build_review_messages(request_dir, req, files)
    raw, err, source = _call_llm(messages)
    if err:
        return _static_review(request_dir, req, files, err)

    verdict = _parse(raw)
    if not isinstance(verdict, dict):
        return _static_review(request_dir, req, files, f"审查结果无法解析：{str(raw)[:200]}")

    blocking, advisory, risk = _normalize_verdict(verdict)
    if not blocking and "blocking" not in verdict and "approve" not in verdict:
        return _static_review(request_dir, req, files, f"审查结果缺少 blocking/approve 字段：{str(raw)[:200]}")

    if advisory:
        adv_text = "\n".join(f"  - {a}" for a in advisory)
    else:
        adv_text = ""

    task_id = os.path.basename(str(request_dir).rstrip("/"))
    if not blocking:
        detail = f"审查通过（风险 {risk}）"
        if adv_text:
            detail += f"；不阻断的建议：\n{adv_text}"
        _audit({"task_id": task_id, "mode": "llm", "approved": True, "source": source,
                "risk": risk, "files": [f.get("path") for f in files]})
        return True, detail, risk

    lines = [f"审查驳回（风险 {risk}）：有 {len(blocking)} 条必修问题"]
    lines.append("必修（必须解决才能生效）：")
    lines += [f"  - {b}" for b in blocking]
    if adv_text:
        lines.append("不阻断的建议（不影响本次生效，有余力再改）：")
        lines.append(adv_text)
    _audit({"task_id": task_id, "mode": "llm", "approved": False, "source": source,
            "risk": risk, "files": [f.get("path") for f in files], "blocking": blocking[:20]})
    return False, "\n".join(lines), risk
