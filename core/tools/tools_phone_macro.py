# core/tools/tools_phone_macro.py
"""手机组合技工具：历史回看 / 存成宏 / 回放。

宏回放复用 tools_phone 的同一个单步执行器，规则与亲手操作完全一致：
    每步先按语义定位器找控件，执行后轮询 expect（package + 新增文案），
    不满足就停在那一颗，把当前界面回传给模型，绝不闭眼往下点。
"""
import asyncio

from config import cfg
from core import phone_macro as pm
from core.toolchain import ToolResult
from utils.logger import get_logger

from .tools_phone import (
    PhoneStepError,
    _annotate_screenshot,
    _dump_tree,
    _ensure_device,
    _exec_step,
    _format_tree,
    _register_screenshot,
    _screencap,
    _wait_expect,
)

logger = get_logger("tools")

MAX_MACRO_STEPS = 40
_VALID_OPS = {"tap", "long_press", "input", "swipe", "key", "launch", "wait"}


def _tools_cfg():
    return getattr(cfg, "tools", None)


def _format_entry(entry: dict) -> str:
    step = entry.get("step") or {}
    expect = entry.get("expect") or {}
    label = step.get("label") or (step.get("text") or "")
    detail = f'「{label}」' if label else ""
    if step.get("op") == "launch":
        detail = step.get("package") or ""
    if step.get("op") == "swipe":
        detail = "滑动"
    if step.get("op") == "key":
        detail = step.get("key") or ""
    package = (entry.get("after") or {}).get("package") or ""
    wants = "、".join(expect.get("labels") or [])
    tail = f" → 期望出现: {wants}" if wants else ""
    return f"#{entry.get('n')} {step.get('op')} {detail}{tail}  [{package}]"


def _format_step(index: int, step: dict) -> str:
    op = step.get("op")
    label = step.get("label") or ""
    if op == "launch":
        head = f"launch {step.get('package') or label}"
    elif op == "key":
        head = f"key {step.get('key')}"
    elif op == "swipe":
        head = "swipe"
    elif op == "input":
        head = f'input 「{step.get("text") or ""}」'
        if label:
            head = f"tap 「{label}」 + " + head
    else:
        head = f"{op} 「{label}」" if label else f"{op}"
    expect = step.get("expect") or {}
    wants = "、".join((expect.get("labels") or [])[:2])
    return f"  {index}. {head}" + (f" → 期望: {wants}" if wants else "")


def _format_macro(macro: dict, detail: bool = False) -> str:
    params = macro.get("params") or []
    param_text = "、".join(
        f"{p['name']}" + (f"={p['default']}" if p.get("default") not in (None, "") else "")
        for p in params
    )
    raw_steps = macro.get("steps")
    steps = raw_steps if isinstance(raw_steps, list) else []
    step_count = len(steps) if steps else (raw_steps if isinstance(raw_steps, int) else 0)
    head = (
        f"「{macro.get('name')}」v{macro.get('version')} "
        f"({step_count} 步, 用了 {macro.get('used') or 0} 次"
        f" 成功 {macro.get('ok') or 0}/失败 {macro.get('fail') or 0})"
    )
    if macro.get("desc"):
        head += f"\n  说明: {macro['desc']}"
    if param_text:
        head += f"\n  参数: {param_text}"
    if detail:
        for index, step in enumerate(steps, 1):
            head += "\n" + _format_step(index, step)
    return head


def _result_summary(macro: dict, report: dict | None = None) -> str:
    lines = [f"已保存组合技 {_format_macro(macro, detail=True)}"]
    if report:
        folded = report.get("round_trip", 0) + report.get("duplicate", 0) + report.get("noop", 0)
        if folded:
            lines.append(
                f"（从 {report.get('input', 0)} 步里折叠掉 {folded} 步冗余："
                f"往返 {report.get('round_trip', 0)} / 重复 {report.get('duplicate', 0)}"
                f" / 空转 {report.get('noop', 0)}）"
            )
    params = [p["name"] for p in macro.get("params") or []]
    hint = f", params={{{', '.join(repr(p) + ': ...' for p in params)}}}" if params else ""
    lines.append(f'以后用 phone_macro(action="play", name="{macro["name"]}"{hint}) 直接跑。')
    return "\n".join(lines)


async def _screenshot_hint(context, tree: dict) -> str:
    try:
        jpeg = _annotate_screenshot(await _screencap(), tree)
        if not jpeg:
            return ""
        attachment, hint = _register_screenshot(context, jpeg)
        return f"\n已附当前界面截图 {hint}（红框编号与上面 [#编号] 对应）" if hint else ""
    except Exception as exc:
        logger.warning(f"[PhoneMacro] 截图失败: {exc}")
        return ""


async def _save(context, name, desc, app, from_history, exclude, steps, param_defs, replace):
    if not name:
        return ToolResult(success=False, content="save 需要 name", error="missing_name")

    report = None
    if steps:
        candidate = []
        for step in steps:
            if not isinstance(step, dict) or step.get("op") not in _VALID_OPS:
                return ToolResult(success=False, content=f"steps 里有不支持的步骤: {step}",
                                  error="invalid_steps")
            candidate.append(step)
    elif from_history:
        limit = max(1, min(int(from_history), 60))
        entries = pm.phone_history.recent(limit)
        if not entries:
            return ToolResult(success=False, content="最近没有可用的操作历史，先用 phone_action 摸一遍流程。",
                              error="empty_history")
        if exclude:
            excluded = {int(n) for n in exclude if str(n).strip().lstrip("-").isdigit()}
            entries = [e for e in entries if int(e.get("n") or 0) not in excluded]
        candidate, report = pm.clean_steps(entries)
        if not candidate:
            return ToolResult(success=False, content="清洗后没有剩下可用的步骤，可以传 steps 手写，或扩大 from_history。",
                              error="empty_steps")
    else:
        return ToolResult(success=False, content="save 需要 from_history=N 或 steps=[...]",
                          error="missing_steps")

    if len(candidate) > MAX_MACRO_STEPS:
        return ToolResult(success=False, content=f"组合技最多 {MAX_MACRO_STEPS} 步，现在是 {len(candidate)} 步。",
                          error="too_many_steps")

    if replace:
        candidate = pm.apply_replacements(candidate, replace)

    params_decl = pm.declared_params(param_defs)
    declared = {p["name"] for p in params_decl}
    used = pm.used_placeholders(candidate)
    unknown = sorted(used - declared)
    if unknown:
        return ToolResult(
            success=False,
            content=f"步骤里用了未声明的参数 {unknown}，请在 param_defs 里声明（或检查 replace 写错了）。",
            error="undefined_params",
        )

    package = app or next((s.get("package") for s in candidate if s.get("op") == "launch"), "")
    macro = pm.macro_store.save(name, desc, package, params_decl, candidate)
    return ToolResult(success=True, content=_result_summary(macro, report),
                      data={"name": macro["name"], "steps": len(candidate), "version": macro["version"]})


async def _play(context, name, values, dry_run, max_nodes, wait_seconds, expect_timeout):
    macro = pm.macro_store.get(name)
    if not macro:
        return ToolResult(success=False, content=f"没有叫「{name}」的组合技，先 phone_macro(action=\"list\") 看看。",
                          error="macro_not_found")

    params = dict(values or {})
    for item in macro.get("params") or []:
        if item["name"] not in params and item.get("default") not in (None, ""):
            params[item["name"]] = item["default"]

    steps, missing = pm.render_steps(macro.get("steps") or [], params)
    if missing:
        return ToolResult(
            success=False,
            content=(
                f"组合技「{name}」缺少参数 {missing}；"
                f"需要传全: {[p['name'] for p in macro.get('params') or []]}"
            ),
            error="missing_params",
        )

    if len(steps) > MAX_MACRO_STEPS:
        return ToolResult(success=False, content=f"组合技超过 {MAX_MACRO_STEPS} 步，拒绝执行。",
                          error="too_many_steps")

    if dry_run:
        lines = [f"「{name}」共 {len(steps)} 步（dry_run，未执行）"]
        lines += [_format_step(i, s) for i, s in enumerate(steps, 1)]
        return ToolResult(success=True, content="\n".join(lines), data={"steps": len(steps)})

    try:
        await _ensure_device()
    except RuntimeError as exc:
        return ToolResult(success=False, content=str(exc), error="device_unavailable")

    trace: list[str] = []
    tree = await _dump_tree(max_nodes)
    for index, step in enumerate(steps, 1):
        expect = step.get("expect") or {}
        try:
            display = await _exec_step(step, tree)
        except PhoneStepError as exc:
            pm.macro_store.record_result(name, False)
            lines = [f"组合技「{name}」停在第 {index} 步：{exc}"]
            lines += [f"  已完成: {t}" for t in trace]
            lines.append(_format_tree(tree))
            hint = await _screenshot_hint(context, tree)
            if hint:
                lines.append(hint)
            return ToolResult(success=False, content="\n".join(lines), error="macro_failed",
                              data={"name": name, "failed_step": index})

        await asyncio.sleep(wait_seconds)
        # launch 只校验是不是切到了目标 App：App 会恢复上次停留的页面，文案不可靠
        check = expect
        if step.get("op") == "launch":
            check = {"package": expect.get("package") or step.get("package") or "", "labels": []}
        timeout = expect_timeout * 2 if step.get("op") == "launch" else expect_timeout
        ok, tree = await _wait_expect(check, max_nodes, timeout)
        trace.append(f"{index}. {display}")
        if not ok:
            pm.macro_store.record_result(name, False)
            lines = [f"组合技「{name}」停在第 {index} 步：执行了 {display}，但界面没变成预期的样子"]
            wants = "、".join(expect.get("labels") or [])
            if wants:
                lines.append(f"  期望出现: {wants}")
            lines.append(f"  实际界面: {(tree.get('package') or '未知')}")
            lines += [f"  已完成: {t}" for t in trace[:-1]]
            lines.append(_format_tree(tree))
            hint = await _screenshot_hint(context, tree)
            if hint:
                lines.append(hint)
            return ToolResult(success=False, content="\n".join(lines), error="macro_failed",
                              data={"name": name, "failed_step": index})

    pm.macro_store.record_result(name, True)
    lines = [f"组合技「{name}」跑完了 {len(steps)} 步", "步骤: " + " / ".join(trace), _format_tree(tree)]
    return ToolResult(success=True, content="\n".join(lines),
                      data={"name": name, "steps": len(steps), "package": tree.get("package")})


async def phone_macro_tool(context, action="list", name="", desc="", app="", from_history=0,
                           exclude=None, steps=None, param_defs=None, replace=None,
                           params=None, dry_run=False, limit=15, note=""):
    """手机组合技：list / history / show / save / play / delete。"""
    action = (action or "list").strip().lower()
    tools_cfg = _tools_cfg()
    max_nodes = int(getattr(tools_cfg, "phone_max_nodes", 60) or 60)
    wait_seconds = float(getattr(tools_cfg, "phone_wait_seconds", 1.0) or 1.0)
    expect_timeout = float(getattr(tools_cfg, "phone_expect_timeout", 3.0) or 3.0)

    try:
        if action in ("list", "列表"):
            macros = pm.macro_store.list()
            if not macros:
                return ToolResult(success=True, content=(
                    "还没有保存过组合技。先用 phone_action 把流程摸一遍，"
                    "再 phone_macro(action=\"save\", name=\"...\", from_history=10) 存下来。"
                ), data={"count": 0})
            lines = [f"已保存 {len(macros)} 个组合技:"]
            lines += [_format_macro(m) for m in macros]
            return ToolResult(success=True, content="\n".join(lines), data={"count": len(macros)})

        if action in ("history", "历史"):
            entries = pm.phone_history.recent(max(1, min(int(limit or 15), 60)))
            if not entries:
                return ToolResult(success=True, content="还没有手机操作历史。", data={"count": 0})
            lines = [f"最近 {len(entries)} 条手机操作（从旧到新）:"]
            lines += [_format_entry(entry) for entry in entries]
            lines.append("要存成组合技: phone_macro(action=\"save\", name=\"...\", from_history=N)")
            return ToolResult(success=True, content="\n".join(lines), data={"count": len(entries)})

        if action in ("show", "查看"):
            macro = pm.macro_store.get(name)
            if not macro:
                return ToolResult(success=False, content=f"没有叫「{name}」的组合技。", error="macro_not_found")
            return ToolResult(success=True, content=_format_macro(macro, detail=True))

        if action in ("save", "保存"):
            return await _save(context, name, desc, app, from_history, exclude, steps, param_defs, replace)

        if action in ("play", "run", "执行", "回放"):
            return await _play(context, name, params, dry_run, max_nodes, wait_seconds, expect_timeout)

        if action in ("delete", "删除"):
            if pm.macro_store.delete(name):
                return ToolResult(success=True, content=f"已删除组合技「{name}」")
            return ToolResult(success=False, content=f"没有叫「{name}」的组合技。", error="macro_not_found")

        return ToolResult(success=False, content=f"不支持的 action: {action}", error="invalid_action")
    except Exception as exc:
        logger.error(f"[PhoneMacro] {action} 失败: {exc}")
        return ToolResult(success=False, content=f"组合技操作失败: {exc}", error="macro_error",
                          data={"action": action, "note": note})
