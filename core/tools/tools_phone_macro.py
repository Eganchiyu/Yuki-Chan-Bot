# core/tools/tools_phone_macro.py
"""手机组合技工具：历史回看 / 存成宏（含 Sub-LLM 自动提炼） / 回放（含弹窗守护与自愈进化）。

宏回放复用 tools_phone 的同一个单步执行器，规则与亲手操作完全一致：
    每步先按语义定位器找控件，执行后轮询 expect（package + 新增文案），
    遇到阻碍先尝试 SystemWatcher 消除系统/广告弹窗，再尝试 MacroHealer 语义自愈，
    仍不满足就停在那一颗，把当前界面回传给模型，绝不闭眼往下点。
"""
from __future__ import annotations

import asyncio
import copy

from config import cfg
from core import phone_agent
from core import phone_macro as pm
from core.phone_driver import driver
from core.phone_focus import phone_focus_manager
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
    detail = f"「{label}」" if label else ""
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


def _result_summary(macro: dict, report: dict | None = None, auto_params: list[dict] | None = None) -> str:
    lines = [f"已保存组合技 {_format_macro(macro, detail=True)}"]
    if report:
        folded = (
            report.get("round_trip", 0)
            + report.get("duplicate", 0)
            + report.get("noop", 0)
            + report.get("distilled_dropped", 0)
        )
        if folded:
            extra = (
                f" / AI剔除探索滑动 {report.get('distilled_dropped', 0)}"
                if report.get("distilled_dropped")
                else ""
            )
            lines.append(
                f"（从 {report.get('input', 0)} 步里折叠掉 {folded} 步冗余："
                f"往返 {report.get('round_trip', 0)} / 重复 {report.get('duplicate', 0)}"
                f" / 空转 {report.get('noop', 0)}{extra}）"
            )
    if auto_params:
        extracted = "、".join(
            f"{p['name']}(默认={p.get('default', '')})" for p in auto_params
        )
        lines.append(f"（Sub-LLM 已自动提取业务参数：{extracted}）")
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


async def _save(
    context,
    name,
    desc,
    app,
    from_history,
    exclude,
    steps,
    param_defs,
    replace,
    auto_distill: bool = True,
):
    if not name:
        return ToolResult(success=False, content="save 需要 name", error="missing_name")

    report = None
    auto_extracted_params: list[dict] = []
    if steps:
        candidate = []
        for step in steps:
            if not isinstance(step, dict) or step.get("op") not in _VALID_OPS:
                return ToolResult(
                    success=False,
                    content=f"steps 里有不支持的步骤: {step}",
                    error="invalid_steps",
                )
            candidate.append(step)
    elif from_history:
        limit = max(1, min(int(from_history), 60))
        entries = pm.phone_history.recent(limit)
        if not entries:
            return ToolResult(
                success=False,
                content="最近没有可用的操作历史，先用 phone_action 摸一遍流程。",
                error="empty_history",
            )
        if exclude:
            excluded = {int(n) for n in exclude if str(n).strip().lstrip("-").isdigit()}
            entries = [e for e in entries if int(e.get("n") or 0) not in excluded]

        if auto_distill and not param_defs and not replace:
            distilled = await phone_agent.distill_history_to_macro(entries, user_goal=desc or "")
            candidate = distilled.get("steps") or []
            report = distilled.get("report")
            if distilled.get("distilled"):
                if not desc and distilled.get("desc"):
                    desc = distilled["desc"]
                if distilled.get("param_defs"):
                    param_defs = distilled["param_defs"]
                    auto_extracted_params = list(param_defs)
                if distilled.get("replace"):
                    replace = distilled["replace"]
        else:
            candidate, report = pm.clean_steps(entries)

        if not candidate:
            return ToolResult(
                success=False,
                content="清洗后没有剩下可用的步骤，可以传 steps 手写，或扩大 from_history。",
                error="empty_steps",
            )
    else:
        return ToolResult(
            success=False,
            content="save 需要 from_history=N 或 steps=[...]",
            error="missing_steps",
        )

    if len(candidate) > MAX_MACRO_STEPS:
        return ToolResult(
            success=False,
            content=f"组合技最多 {MAX_MACRO_STEPS} 步，现在是 {len(candidate)} 步。",
            error="too_many_steps",
        )

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
    return ToolResult(
        success=True,
        content=_result_summary(macro, report, auto_extracted_params),
        data={
            "name": macro["name"],
            "steps": len(candidate),
            "version": macro["version"],
            "auto_params": [p["name"] for p in auto_extracted_params],
        },
    )


def _step_expect_check(step: dict, expect: dict) -> tuple[dict, float]:
    """launch 步骤只校验包名，且给予双倍超时。"""
    if step.get("op") == "launch":
        return {"package": expect.get("package") or step.get("package") or "", "labels": []}, 2.0
    return expect, 1.0


async def _play(context, name, values, dry_run, max_nodes, wait_seconds, expect_timeout):
    macro = pm.macro_store.get(name)
    if not macro:
        return ToolResult(
            success=False,
            content=f"没有叫「{name}」的组合技，先 phone_macro(action=\"list\") 看看。",
            error="macro_not_found",
        )

    params = dict(values or {})
    for item in macro.get("params") or []:
        if item["name"] not in params and item.get("default") not in (None, ""):
            params[item["name"]] = item["default"]

    raw_template_steps = macro.get("steps") or []
    steps, missing = pm.render_steps(raw_template_steps, params)
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
        return ToolResult(
            success=False,
            content=f"组合技超过 {MAX_MACRO_STEPS} 步，拒绝执行。",
            error="too_many_steps",
        )

    if dry_run:
        lines = [f"「{name}」共 {len(steps)} 步（dry_run，未执行）"]
        lines += [_format_step(i, s) for i, s in enumerate(steps, 1)]
        return ToolResult(success=True, content="\n".join(lines), data={"steps": len(steps)})

    try:
        await _ensure_device()
    except RuntimeError as exc:
        return ToolResult(success=False, content=str(exc), error="device_unavailable")

    trace: list[str] = []
    healed_records: dict[int, dict] = {}
    tree = await _dump_tree(max_nodes)

    for index, step in enumerate(steps, 1):
        expect = step.get("expect") or {}
        active_step = step
        exec_error: PhoneStepError | None = None
        display = ""

        try:
            display = await _exec_step(active_step, tree)
        except PhoneStepError as exc:
            exec_error = exc
            # 第一步（弹窗清理）：检查是否被系统权限/广告弹窗遮挡
            if await phone_agent.try_dismiss_overlay(driver, tree):
                await asyncio.sleep(wait_seconds)
                tree = await _dump_tree(max_nodes)
                try:
                    display = await _exec_step(active_step, tree)
                    exec_error = None
                except PhoneStepError as retry_exc:
                    exec_error = retry_exc

            # 第二步（LLM 自愈）：若非弹窗或清理后仍找不到控件，尝试 Sub-LLM 语义自愈
            if exec_error is not None:
                healed = await phone_agent.heal_step(active_step, tree)
                if healed is not None:
                    try:
                        display = await _exec_step(healed, tree)
                        active_step = healed
                        healed_records[index - 1] = healed
                        exec_error = None
                    except PhoneStepError as heal_exc:
                        exec_error = heal_exc

        # 第三步（优雅降级）：自愈仍无法执行
        if exec_error is not None:
            pm.macro_store.record_result(name, False)
            lines = [f"组合技「{name}」停在第 {index} 步：{exec_error}"]
            lines += [f"  已完成: {t}" for t in trace]
            lines.append(_format_tree(tree))
            hint = await _screenshot_hint(context, tree)
            if hint:
                lines.append(hint)
            return ToolResult(
                success=False,
                content="\n".join(lines),
                error="macro_failed",
                data={"name": name, "failed_step": index},
            )

        await asyncio.sleep(wait_seconds)
        check, mult = _step_expect_check(active_step, expect)
        timeout = expect_timeout * mult
        ok, tree = await _wait_expect(check, max_nodes, timeout)

        if not ok:
            # 第一步（弹窗清理）：执行后可能弹出了权限框或广告遮住了预期界面
            if await phone_agent.try_dismiss_overlay(driver, tree):
                await asyncio.sleep(wait_seconds)
                ok, tree = await _wait_expect(check, max_nodes, timeout)
                if not ok:
                    # 若弹窗清理后仍在原界面，重试一次当前步骤
                    try:
                        display = await _exec_step(active_step, tree)
                        await asyncio.sleep(wait_seconds)
                        ok, tree = await _wait_expect(check, max_nodes, timeout)
                    except PhoneStepError:
                        pass

        if not ok and (index - 1) not in healed_records:
            # 第二步（LLM 自愈）：尝试在当前树用 Sub-LLM 寻找替代控件
            healed = await phone_agent.heal_step(active_step, tree)
            if healed is not None:
                try:
                    display = await _exec_step(healed, tree)
                    await asyncio.sleep(wait_seconds)
                    ok, tree = await _wait_expect(check, max_nodes, timeout)
                    if ok:
                        active_step = healed
                        healed_records[index - 1] = healed
                except PhoneStepError:
                    pass

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
            return ToolResult(
                success=False,
                content="\n".join(lines),
                error="macro_failed",
                data={"name": name, "failed_step": index},
            )

    # 整个宏顺利跑通：若有步骤经历了 LLM 自愈，自动更新持久化定位器（自我进化）
    evolved_Version = None
    if healed_records:
        try:
            updated_steps = copy.deepcopy(raw_template_steps)
            for idx, healed_step in healed_records.items():
                if 0 <= idx < len(updated_steps):
                    orig_step = updated_steps[idx]
                    orig_loc_text = ((orig_step.get("loc") or {}).get("text") or "")
                    new_loc = copy.deepcopy(healed_step.get("loc") or {})
                    # 若原步骤定位器含有 {{参数}} 占位符，保留占位符文本，只更新 id/cls/rel
                    if "{{" in orig_loc_text and "}}" in orig_loc_text:
                        new_loc["text"] = orig_loc_text
                    else:
                        orig_step["label"] = healed_step.get("label") or orig_step.get("label") or ""
                    orig_step["loc"] = new_loc
            saved_macro = pm.macro_store.save(
                name,
                macro.get("desc") or "",
                macro.get("app") or "",
                macro.get("params") or [],
                updated_steps,
            )
            evolved_Version = saved_macro.get("version")
            logger.info(f"[PhoneMacro] 组合技「{name}」已完成自愈进化 -> v{evolved_Version}")
        except Exception as exc:
            logger.warning(f"[PhoneMacro] 保存自愈定位器失败: {exc}")

    pm.macro_store.record_result(name, True)
    lines = [f"组合技「{name}」跑完了 {len(steps)} 步", "步骤: " + " / ".join(trace)]
    if healed_records:
        healed_nums = ", ".join(f"第{i + 1}步" for i in sorted(healed_records))
        lines.append(f"（自愈进化：{healed_nums}已由 Sub-LLM 自动适配新控件并更新宏定位器）")
    lines.append(_format_tree(tree))
    return ToolResult(
        success=True,
        content="\n".join(lines),
        data={
            "name": name,
            "steps": len(steps),
            "package": tree.get("package"),
            "healed_steps": [i + 1 for i in sorted(healed_records)],
        },
    )


async def phone_macro_tool(
    context,
    action="list",
    name="",
    desc="",
    app="",
    from_history=0,
    exclude=None,
    steps=None,
    param_defs=None,
    replace=None,
    params=None,
    dry_run=False,
    limit=15,
    note="",
    auto_distill: bool = True,
):
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
                return ToolResult(
                    success=True,
                    content=(
                        "还没有保存过组合技。先用 phone_action 把流程摸一遍，"
                        "再 phone_macro(action=\"save\", name=\"...\", from_history=10) 存下来。"
                    ),
                    data={"count": 0},
                )
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
            res = await _save(
                context, name, desc, app, from_history, exclude, steps, param_defs, replace,
                auto_distill=bool(auto_distill),
            )
            if res.success:
                phone_focus_manager.record_step(context.chat_id, f"保存组合技「{name}」", note)
            return res

        if action in ("play", "run", "执行", "回放"):
            res = await _play(context, name, params, dry_run, max_nodes, wait_seconds, expect_timeout)
            phone_focus_manager.record_step(
                context.chat_id,
                f"回放组合技「{name}」({'成功' if res.success else '受阻'})",
                note,
            )
            return res

        if action in ("delete", "删除"):
            if pm.macro_store.delete(name):
                return ToolResult(success=True, content=f"已删除组合技「{name}」")
            return ToolResult(success=False, content=f"没有叫「{name}」的组合技。", error="macro_not_found")

        return ToolResult(success=False, content=f"不支持的 action: {action}", error="invalid_action")
    except Exception as exc:
        logger.error(f"[PhoneMacro] {action} 失败: {exc}")
        return ToolResult(
            success=False,
            content=f"组合技操作失败: {exc}",
            error="macro_error",
            data={"action": action, "note": note},
        )
