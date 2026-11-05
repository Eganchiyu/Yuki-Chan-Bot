# core/phone_agent.py
"""智能提炼与守护层：系统弹窗守护 (SystemWatcher)、第二 LLM 历史提炼器 (MacroDistiller) 与宏回放自愈器 (MacroHealer)。"""
from __future__ import annotations

import copy
import json
import re

from config import cfg
from core import phone_macro as pm
from utils import llm_client
from utils.logger import get_logger

logger = get_logger("tools")

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)

# 系统权限/安全中心包名特征
PERMISSION_PACKAGES = {
    "com.android.permissioncontroller",
    "com.google.android.permissioncontroller",
    "com.android.packageinstaller",
    "com.google.android.packageinstaller",
    "com.huawei.systemmanager",
    "com.miui.securitycenter",
    "com.coloros.safecenter",
    "com.vivo.permissionmanager",
}

# 明确属于弹窗/遮罩的按钮文案（按匹配优先级排列）
OVERLAY_DIRECT_BUTTONS = (
    "仅在使用中允许",
    "本次运行允许",
    "始终允许",
    "允许",
    "跳过广告",
    "关闭广告",
    "跳过",
    "以后再说",
    "暂不更新",
    "稍后提醒",
    "暂不开启",
    "我知道了",
    "知道了",
    "残忍拒绝",
    "放弃优惠",
)

# 弹窗上下文特征词 + 通用关闭按钮（仅在存在上下文特征时才点，避免误触正常页面）
OVERLAY_CONTEXT_KEYWORDS = (
    "权限",
    "广告",
    "新版本",
    "更新",
    "升级",
    "青少年模式",
    "开启通知",
    "推送通知",
    "给个好评",
    "温馨提示",
)
OVERLAY_GENERIC_CLOSE_BUTTONS = ("取消", "关闭", "暂不", "稍后", "×", "✕")


def _extract_json_dict(raw_text: str) -> dict | None:
    """从 LLM 输出中提取 JSON 对象，兼容代码块包裹与前后杂文。"""
    text = (raw_text or "").strip()
    if not text:
        return None
    match = _JSON_BLOCK_RE.search(text)
    if match:
        text = match.group(1).strip()
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _format_tree_for_agent(tree: dict) -> str:
    width, height = tree.get("size") or (0, 0)
    lines = [f"[手机屏幕] 应用: {tree.get('package') or '未知'} | 尺寸: {width}x{height}"]
    for item in tree.get("nodes") or []:
        label = item.get("label") or "(无文字)"
        res_id = f" id={item['id']}" if item.get("id") else ""
        lines.append(
            f"[#{item.get('index')}] [{item.get('kind', '可点')}] {label}{res_id} @({item.get('cx')},{item.get('cy')})"
        )
    return "\n".join(lines)


async def call_sub_llm(system_prompt: str, user_prompt: str) -> str:
    """调用第二 LLM（Sub-LLM）适配器。未配置或网络失败时抛出异常交由上层无感降级。"""
    primary_key = (getattr(cfg, "LLM_API_KEY", "") or "").strip()
    backup_key = (getattr(cfg, "BACKUP_API_KEY", "") or primary_key).strip()
    primary_url = (getattr(cfg, "LLM_BASE_URL", "") or "").strip()
    backup_url = (getattr(cfg, "BACKUP_BASE_URL", "") or "").strip()

    if not primary_key and not backup_key:
        raise RuntimeError("Sub-LLM 未配置 API Key")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    last_err: Exception | None = None
    if primary_url and primary_key:
        try:
            msg = await llm_client.chat_completion_raw(
                base_url=primary_url,
                api_key=primary_key,
                messages=messages,
                model=getattr(cfg, "LLM_MODEL", "deepseek-chat") or "deepseek-chat",
                timeout=20.0,
                temperature=0.1,
            )
            content = (msg or {}).get("content") or ""
            if isinstance(content, str) and content.strip():
                return content.strip()
        except Exception as exc:
            last_err = exc
            logger.debug(f"[PhoneAgent] Sub-LLM 主线路请求失败: {exc}")

    if backup_url and backup_key:
        try:
            msg = await llm_client.chat_completion_raw(
                base_url=backup_url,
                api_key=backup_key,
                messages=messages,
                model=getattr(cfg, "BACKUP_MODEL", "deepseek-chat") or "deepseek-chat",
                timeout=20.0,
                temperature=0.1,
            )
            content = (msg or {}).get("content") or ""
            if isinstance(content, str) and content.strip():
                return content.strip()
        except Exception as exc:
            last_err = exc
            logger.debug(f"[PhoneAgent] Sub-LLM 备用线路请求失败: {exc}")

    raise RuntimeError(f"Sub-LLM 调用失败: {last_err or '空响应'}")


class SystemWatcher:
    """系统弹窗守护：识别权限请求、开屏广告、版本更新等阻断弹窗并自动消除。"""

    @classmethod
    def find_overlay_button(cls, tree: dict) -> dict | None:
        nodes = tree.get("nodes") or []
        if not nodes:
            return None
        package = (tree.get("package") or "").strip()
        is_perm_pkg = package in PERMISSION_PACKAGES or "permission" in package.lower()

        # 1) 精确匹配典型弹窗按钮文案
        for target_text in OVERLAY_DIRECT_BUTTONS:
            for node in nodes:
                label = (node.get("label") or "").strip()
                if label == target_text:
                    return node

        # 2) 前缀/包含匹配（如 "跳过 3s"、"跳过广告 5"、"仅在使用中允许"）
        for node in nodes:
            label = (node.get("label") or "").strip()
            if not label or len(label) > 12:
                continue
            if label.startswith("跳过") or label in ("关闭广告", "仅在使用中允许", "始终允许"):
                return node
            if is_perm_pkg and ("允许" in label and "不允许" not in label and "拒绝" not in label):
                return node

        # 3) 当界面带有明确弹窗上下文特征词（或处于权限包）时，匹配通用关闭/取消按钮
        all_labels_blob = " ".join((n.get("label") or "") for n in nodes)
        has_overlay_context = is_perm_pkg or any(kw in all_labels_blob for kw in OVERLAY_CONTEXT_KEYWORDS)
        if has_overlay_context:
            for btn_text in OVERLAY_GENERIC_CLOSE_BUTTONS:
                for node in nodes:
                    if (node.get("label") or "").strip() == btn_text:
                        return node

        return None

    @classmethod
    async def try_dismiss_overlay(cls, driver, tree: dict) -> bool:
        """若当前界面存在阻断弹窗/遮罩，自动点击消除并返回 True。"""
        try:
            target = cls.find_overlay_button(tree)
            if not target:
                return False
            cx, cy = int(target["cx"]), int(target["cy"])
            label = target.get("label") or "弹窗按钮"
            logger.info(f"[SystemWatcher] 检测到疑似弹窗遮罩，自动点击「{label}」@({cx},{cy})")
            if hasattr(driver, "tap"):
                await driver.tap(cx, cy)
            elif hasattr(driver, "adb"):
                await driver.adb(["shell", "input", "tap", str(cx), str(cy)], timeout=15)
            else:
                return False
            return True
        except Exception as exc:
            logger.warning(f"[SystemWatcher] 清理弹窗异常: {exc}")
            return False


class MacroDistiller:
    """第二 LLM 历史提炼器：在规则清洗基础上剔除冗余探索滑动，并自动提取业务参数。"""

    SYSTEM_PROMPT = (
        "你是 Android 自动化宏提炼助手。用户会给你一段手机操作步骤列表（JSON）和目标说明。\n"
        "请你完成两件事：\n"
        "1. 剔除无效的探索性滑动（例如为了找某个按钮而连续上下翻找多次的冗余 swipe，只保留必要的动作）；\n"
        "2. 自动识别用户输入（input 动作的 text 或紧随其后的搜索结果点击）中的业务变量（如搜索词“炸鸡”、收件人姓名等），"
        "将其提取为参数定义 param_defs 和文本替换映射 replace。\n"
        "严格只输出一个 JSON 对象，格式如下（不要输出任何额外解释）：\n"
        "{\n"
        '  "desc": "一句话描述该宏的功能",\n'
        '  "keep_indices": [0, 1, 2],\n'
        '  "param_defs": [{"name": "food", "desc": "要搜索的美食名称", "default": "炸鸡"}],\n'
        '  "replace": {"炸鸡": "{{food}}"}\n'
        "}\n"
        "注意：keep_indices 是要保留的原步骤在输入 steps 数组中的 0-based 索引列表（也可以直接返回 steps 数组）。"
    )

    @classmethod
    async def distill_history_to_macro(cls, entries: list[dict], user_goal: str = "") -> dict:
        cleaned_steps, report = pm.clean_steps(entries)
        fallback = {
            "desc": user_goal or "",
            "steps": cleaned_steps,
            "param_defs": [],
            "replace": {},
            "report": report,
            "distilled": False,
        }
        if not cleaned_steps:
            return fallback

        try:
            brief_steps = []
            for idx, step in enumerate(cleaned_steps):
                brief_steps.append({
                    "index": idx,
                    "op": step.get("op"),
                    "label": step.get("label") or "",
                    "text": step.get("text") or "",
                    "package": step.get("package") or "",
                    "expect": step.get("expect") or {},
                })
            user_prompt = json.dumps(
                {"user_goal": user_goal or "", "steps": brief_steps},
                ensure_ascii=False,
                indent=2,
            )
            raw = await call_sub_llm(cls.SYSTEM_PROMPT, user_prompt)
            data = _extract_json_dict(raw)
            if not data:
                logger.warning("[MacroDistiller] Sub-LLM 未返回有效 JSON，降级为规则清洗结果")
                return fallback

            # 解析保留的步骤：优先使用 keep_indices 映射回原始完整 step（保留完整 loc 和 expect）
            distilled_steps: list[dict] = []
            if isinstance(data.get("keep_indices"), list):
                for idx in data["keep_indices"]:
                    if isinstance(idx, int) and 0 <= idx < len(cleaned_steps):
                        distilled_steps.append(copy.deepcopy(cleaned_steps[idx]))
            elif isinstance(data.get("steps"), list):
                for item in data["steps"]:
                    if isinstance(item, int) and 0 <= item < len(cleaned_steps):
                        distilled_steps.append(copy.deepcopy(cleaned_steps[item]))
                    elif isinstance(item, dict):
                        idx = item.get("index")
                        if isinstance(idx, int) and 0 <= idx < len(cleaned_steps):
                            merged = copy.deepcopy(cleaned_steps[idx])
                            for k in ("op", "label", "text", "package", "key", "seconds"):
                                if k in item and item[k] not in (None, ""):
                                    merged[k] = item[k]
                            distilled_steps.append(merged)
                        elif item.get("op"):
                            distilled_steps.append(copy.deepcopy(item))

            if not distilled_steps:
                distilled_steps = copy.deepcopy(cleaned_steps)

            raw_replace = data.get("replace")
            replace_map = (
                {str(k): str(v) for k, v in raw_replace.items() if k and v}
                if isinstance(raw_replace, dict)
                else {}
            )
            param_defs = pm.declared_params(data.get("param_defs") or [])

            # 确保 replace 中引用的 {{placeholder}} 都在 param_defs 中有声明
            if replace_map:
                temp_steps = pm.apply_replacements(copy.deepcopy(distilled_steps), replace_map)
                used = pm.used_placeholders(temp_steps)
                declared_names = {p["name"] for p in param_defs}
                for missing_name in sorted(used - declared_names):
                    default_val = next(
                        (old for old, new in replace_map.items() if f"{{{{{missing_name}}}}}" in new),
                        "",
                    )
                    param_defs.append({"name": missing_name, "desc": "", "default": default_val})

            desc = str(data.get("desc") or user_goal or "").strip()
            report["distilled_dropped"] = max(0, len(cleaned_steps) - len(distilled_steps))
            report["steps"] = len(distilled_steps)
            return {
                "desc": desc,
                "steps": distilled_steps,
                "param_defs": param_defs,
                "replace": replace_map,
                "report": report,
                "distilled": True,
            }
        except Exception as exc:
            logger.warning(f"[MacroDistiller] Sub-LLM 提炼降级为规则清洗: {exc}")
            return fallback


class MacroHealer:
    """宏回放自愈器：当控件定位失败或页面改版时，调用 Sub-LLM 在当前控件树中寻找语义等价控件。"""

    SYSTEM_PROMPT = (
        "你是 Android 自动化回放自愈助手。宏回放在当前步骤受阻（控件未找到或位置/文案发生微调）。\n"
        "请根据失败步骤的原始意图（op, label, loc, expect）和当前屏幕的控件树列表，"
        "判断当前屏幕上是否存在语义等价的目标控件（例如 App 改版导致“去结算”变成“结算(1)”或位置偏移）。\n"
        "如果找到了对应的控件，返回它的编号 index（整数）；如果当前界面完全不对或找不到，index 填 null。\n"
        "严格只输出一个 JSON 对象，格式如下：\n"
        '{"index": 3, "reason": "文案从去结算微调为立即结算"}'
    )

    @classmethod
    async def heal_step(cls, failed_step: dict, current_tree: dict) -> dict | None:
        if not isinstance(failed_step, dict) or not isinstance(current_tree, dict):
            return None
        op = failed_step.get("op")
        if op not in ("tap", "long_press", "input"):
            return None
        nodes = current_tree.get("nodes") or []
        if not nodes:
            return None

        try:
            step_info = {
                "op": op,
                "label": failed_step.get("label") or "",
                "loc": failed_step.get("loc") or {},
                "expect": failed_step.get("expect") or {},
            }
            user_prompt = (
                f"失败步骤意图:\n{json.dumps(step_info, ensure_ascii=False)}\n\n"
                f"当前界面控件树:\n{_format_tree_for_agent(current_tree)}"
            )
            raw = await call_sub_llm(cls.SYSTEM_PROMPT, user_prompt)
            data = _extract_json_dict(raw)
            if not data:
                return None

            raw_index = data.get("index")
            if raw_index is None:
                return None
            if isinstance(raw_index, str):
                raw_index = raw_index.lstrip("#").strip()
                if not raw_index.isdigit():
                    return None
            target_index = int(raw_index)
            matched_node = next((n for n in nodes if n.get("index") == target_index), None)
            if not matched_node:
                return None

            healed = copy.deepcopy(failed_step)
            healed["loc"] = pm.build_locator(matched_node, current_tree)
            if matched_node.get("label"):
                healed["label"] = matched_node["label"][:40]
            healed["_healed_index"] = target_index
            healed["_healed_reason"] = str(data.get("reason") or "Sub-LLM 语义匹配自愈")
            logger.info(
                f"[MacroHealer] 步骤自愈成功: 原「{failed_step.get('label')}」-> "
                f"[#{target_index}]「{matched_node.get('label')}」 ({healed['_healed_reason']})"
            )
            return healed
        except Exception as exc:
            logger.warning(f"[MacroHealer] 自愈调用失败，优雅降级: {exc}")
            return None


async def try_dismiss_overlay(driver, tree: dict) -> bool:
    return await SystemWatcher.try_dismiss_overlay(driver, tree)


async def distill_history_to_macro(entries: list[dict], user_goal: str = "") -> dict:
    return await MacroDistiller.distill_history_to_macro(entries, user_goal=user_goal)


async def heal_step(failed_step: dict, current_tree: dict) -> dict | None:
    return await MacroHealer.heal_step(failed_step, current_tree)
