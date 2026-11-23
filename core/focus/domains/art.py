# core/focus/domains/art.py
"""艺术创作聚焦域声明与入口/生图/资产管理/退出工具实现。"""
from __future__ import annotations

import os
import re
import time
from typing import Any

from core.art_assets import _clean_ref, art_asset_store
from core.art_gen_jobs import art_gen_store
from core.art_gacha import art_gacha_store
from core.focus.domain import BASE_KEEP_TOOLS, FocusDomain
from core.focus.manager import focus_manager, register_domain
from core.focus.tools import make_focus_finish_handler
from core.toolchain import ToolResult
from utils import BASE_DIR
from utils.logger import get_logger

logger = get_logger("tools")


def _art_stub(payload: dict) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if data.get("art_job"):
        assets = data.get("used_assets") or []
        asset_str = f" assets={','.join(assets)}" if assets else ""
        return f"art_draw{asset_str} -> 后台任务 {data.get('job_id', '')}".strip()
    if "file_path" in data and "prompt" in data:
        assets = data.get("used_assets") or []
        asset_str = f" assets={','.join(assets)}" if assets else ""
        return f"art_draw{asset_str} -> {data.get('file_path')}"
    if "asset_action" in data:
        return f"art_asset {data.get('asset_action')} {data.get('key', '')}".strip()
    if "gacha_card" in data:
        return f"art_gacha [{data.get('rarity', '')}] {data.get('gacha_card', '')}".strip()
    return str(payload.get("content") or "").replace("\n", " ")


def _handle_art_gacha_jump(chat_id: str, history: Any, matched_messages: list[dict]) -> str:
    custom_notes: list[str] = []
    for m in matched_messages:
        raw = str(m.get("raw_text") or "").strip()
        if raw.startswith("/抽图") and len(raw) > 3 and raw[3].isspace():
            note_part = raw[3:].strip()
            if note_part:
                custom_notes.append(note_part)
    custom_note = " ".join(custom_notes).strip()

    jump_res = prepare_art_gacha_jump(
        chat_id,
        history=history,
        goal=custom_note or "抽图创作",
    )
    gacha_prompt = jump_res.get("prompt") or ""
    gacha_source = jump_res.get("source") or ""
    custom_hint = (
        f"用户附带自定义要求：「{custom_note}」（请务必优先满足该要求，例如选用指定的个人资产图、人物、动作或构图，并将下方抽卡 Prompt 作为画面风格与场景灵感融入）。\n"
        if custom_note
        else "请直接根据以上抽卡 Prompt 结合合适的个人资产图（如有需要）改写为完整画面描述，"
    )
    return (
        f"【系统直达抽图指令】已为你直接进入艺术创作模式并自动完成一次抽卡（来源: {gacha_source}）。"
        f"本次抽到的灵感 Prompt 如下：\n{gacha_prompt}\n"
        f"{custom_hint}"
        "立即调用 `art_draw` 进行绘画。注意：提交绘画后不要调用 `art_finish`，保持创作模式开启以便后续继续抽图。"
    )


ART = FocusDomain(
    name="art",
    title="艺术创作",
    entry_tool="art_start",
    exit_tool="art_finish",
    domain_tools=frozenset({"art_draw", "art_asset", "art_gacha"}),
    keep_tools=BASE_KEEP_TOOLS,
    summary_prefix="【艺术创作总结】",
    exit_hint="（你已结束本轮艺术创作并收起画板，请直接根据上述创作结果回复用户。）",
    idle_turns_key="art_focus_idle_turns",
    max_rounds_key="art_focus_max_rounds",
    default_fallback="已完成艺术创作。",
    empty_trace_fallback="已打开画板查看资产并完成创作。",
    stub=_art_stub,
    jump_tag="art_gacha_jump",
    on_jump=_handle_art_gacha_jump,
)

register_domain(ART)


_TEMP_REF_LABEL = "临时参考图（对话里的图片或本地路径，未登记资产）"


def _asset_label(item: dict) -> str:
    """把已登记资产压成一句「角色名（主人）：外观描述」，供多图绑定说明使用。"""
    key = item.get("key") or ""
    owner = item.get("owner") or key
    desc = (item.get("description") or "").strip()
    head = f"{key}（{owner}）" if owner and owner != key else f"{key}"
    return f"{head}：{desc}" if desc else head


def _build_reference_legend(refs: list[str], labels: dict[str, str]) -> str:
    """多张参考图时生成「第几张图是谁」的绑定说明；单图无需说明，返回空串。"""
    if len(refs) < 2:
        return ""
    parts = [
        f"image {idx} = {labels.get(ref) or _TEMP_REF_LABEL}"
        for idx, ref in enumerate(refs, start=1)
    ]
    return (
        "【参考图对应关系（务必遵守）】本次共传入 "
        f"{len(refs)} 张输入参考图，顺序如下：\n"
        + "\n".join(f"- {p}" for p in parts)
        + "\n"
        "画图时每个角色必须严格保持「自己那一张」参考图的脸型、发色瞳色、发饰与服饰，"
        "禁止把不同参考图里的人物特征互换或融合；prompt 里描述角色时也按上面的 image 序号对应写。"
        "若 prompt 的文字描写与某张参考图实际外观冲突，一律以参考图为准。"
    )


def _looks_like_path_or_img_tag(val: str) -> bool:
    text = _clean_ref(val)
    if not text:
        return False
    if re.match(r"^\[img:\d{1,3}\]$", text):
        return True
    if "/" in text or "\\" in text or text.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        cand = text if os.path.isabs(text) else os.path.join(BASE_DIR, text)
        return os.path.isfile(cand)
    return False


_ART_DIRECTOR_GUIDE = (
    "【二次元艺术总监生图指南（发挥模型全实力）】\n"
    "1. Prompt 写法（四段式导演指令，画面描述优先用英文，画面内需渲染的中文/日文台词与标题用引号保留原文）：\n"
    "   - 景别与时代画风锚点：先定机位与细分流派，勿只写 anime style。\n"
    "   - 主体与精确计数：写清动作、神态、服饰、发饰并尽量给数量词（如 2 cat ears, 1 black choker, exactly 1 floating question mark），显著压低多饰品/崩坏。\n"
    "   - 光影与色板脚本：指定光源方向、边缘光与色彩基调（如 golden-hour backlighting, warm rim light along hair and shoulders, pastel mauve & pearl white palette）。\n"
    "   - 版面文字与减法约束：有字时写明字色/排向/气泡位置；极简图结尾加 no extra objects, no detailed background。\n"
    "2. 背景铁律（极其重要）：默认必须使用 `background=\"opaque\"` 生成完整实底/纯色背景；仅在用户明确要求“透明背景/免抠/透明贴纸”时才传 `background=\"transparent\"`。\n"
    "3. 角色一致性与换装：用 `assets` 时默认 `input_fidelity=\"high\"` 锁定五官与发饰；换装时在 prompt 明写保留参考图的脸型、发色瞳色与标志性发饰并替换服装；若要跨画风重绘（如精绘转极简 Q 版表情包）可设 `input_fidelity=\"low\"`。\n"
    "    - 多参考图：一次传 2 张以上 `assets` 时，prompt 里必须写明哪张图对应哪个角色"
    "（如 image 1 = yuki、image 2 = master），并按各自参考图写发色瞳色与服饰；"
    "系统会自动在 prompt 前附上「参考图对应关系」，你按它来写即可，别把两人的特征写串。\n"
    "4. 异步出图与自检：`art_draw` 只是提交任务、立刻返回，**不要空等**——这期间可以继续聊天或准备下一张；"
    "画好后成品会自动发到会话里，并在下一轮把成品预览交给你，那时先看一眼构图/文字/手指；"
    "若局部瑕疵可用 `art_draw(image_paths=[该file_path], prompt=\"Keep everything else identical, only fix...\", input_fidelity=\"high\")` 精修；"
    "成品不要自己再用 `send_qq_file` 重复发一遍。\n"
    "需要注意的是，上述的括号内内容仅是示例，实际使用时不要直接照搬括号内的文字，而是根据你想要的画面和风格来写 prompt。"
)


def build_art_start_content() -> tuple[str, list[dict]]:
    """构造进入艺术创作模式时的完整指南文本与已登记资产列表。"""
    overview = art_asset_store.format_overview()
    assets_data = art_asset_store.list()
    header = (
        "【已进入艺术创作聚焦模式】已展开 art_draw / art_gacha / art_asset / art_finish 工具，并收起其他无关日常工具。\n"
        "- 画图用 `art_draw`：可通过 `assets=[\"yuki\", \"master\"]` 直接选用下方已登记的角色参考图（支持单张或多张同框），"
        "也可同时传 `image_paths=[\"[img:001]\"]` 混用群聊临时参考图。"
        "**art_draw 是异步的**：提交后立刻返回，后台画完会自动把图发到会话里并提醒你；你不用等，也不要再用 `send_qq_file` 重发成品。\n"
        "- 提示词抽卡用 `art_gacha`：想抽风格盲盒或找创作灵感时，抽一发二次元 Prompt 草稿给你参考与微调（不会直接生图），满意后再调用 `art_draw`。\n"
        "- 资产管理用 `art_asset`：支持登记群友/角色立绘或三视图（`register`）、修改（`update`）、删除（`delete`）或查看列表（`list`）。\n"
        "- 创作与发图全部完成后，请调用 `art_finish(summary=\"...\")` 收起画板并写一句简短这段工作的总结。\n\n"
        f"{_ART_DIRECTOR_GUIDE}"
    )
    return f"{header}\n\n{overview}", assets_data


def prepare_art_gacha_jump(
    chat_id: Any,
    history: Any = None,
    goal: str = "抽图创作",
) -> dict[str, Any]:
    """硬编码状态跳跃：直接进入创作模式（若未进入则注入完整指南与个人资产）并自动抽卡。"""
    cid = str(chat_id)
    already_focused = focus_manager.is_focused(cid, ART.name)
    focus_manager.enter(cid, ART.name, goal=goal, history=history)

    if not already_focused:
        art_start_content, _ = build_art_start_content()
        focus_manager.record_step(cid, f"开始艺术创作: {goal}", domain=ART.name)
        if history is not None:
            history.append_session_message(
                cid,
                "tool",
                art_start_content,
                name="art_start",
                tool_call_id=f"jump_art_start_{int(time.time() * 1000)}",
                focus_work=ART.name,
                save_immediately=False,
                return_snapshot=False,
            )

    drawn = art_gacha_store.draw()
    gacha_prompt = str(drawn.get("prompt") or "").strip()
    gacha_source = str(drawn.get("source") or "")
    if not gacha_prompt:
        pools = art_gacha_store.load()
        gacha_prompt = art_gacha_store._slot_prompt(pools.get("slots") or {}, __import__("random").Random())
        gacha_source = "slot"

    focus_manager.record_step(cid, "提示词抽卡", gacha_source, domain=ART.name)
    if history is not None:
        history.append_session_message(
            cid,
            "tool",
            gacha_prompt,
            name="art_gacha",
            tool_call_id=f"jump_art_gacha_{int(time.time() * 1000)}",
            focus_work=ART.name,
            save_immediately=False,
            return_snapshot=False,
        )

    return {
        "entered_art": not already_focused,
        "source": gacha_source,
        "prompt": gacha_prompt,
    }


async def art_start_tool(context, goal: str = "") -> ToolResult:
    """进入艺术创作聚焦模式，立即返回当前已登记的艺术资产列表与创作工具说明。"""
    history = (
        (context.metadata or {}).get("history_manager")
        if isinstance(context.metadata, dict)
        else None
    )
    focus_manager.enter(context.chat_id, ART.name, goal=goal, history=history)
    if goal:
        focus_manager.record_step(context.chat_id, f"开始艺术创作: {goal}", domain=ART.name)

    content, assets_data = build_art_start_content()
    return ToolResult(
        success=True,
        content=content,
        data={
            "focus": "entered",
            "art_focus": "entered",
            "goal": goal or "",
            "assets": assets_data,
            "no_persist": False,
        },
        name="art_start",
    )


async def art_draw_tool(
    context,
    prompt: str = "",
    assets: list[str] | str | None = None,
    image_paths: list[str] | str | None = None,
    aspect_ratio: str = "1:1",
    size: str | None = None,
    seed: int | None = None,
    quality: str = "high",
    background: str = "opaque",
    input_fidelity: str = "high",
    note: str = "",
) -> ToolResult:
    """在艺术创作模式下生成图片，支持选用已登记资产参考图、高阶画质/保真度控制与画幅比例预设。"""
    if not prompt or not str(prompt).strip():
        return ToolResult(
            success=False,
            content="缺少图像描述 prompt",
            error="missing_prompt",
            name="art_draw",
        )

    matched_assets, missing_queries = art_asset_store.resolve_many(assets)
    extra_from_assets: list[str] = []
    still_missing: list[str] = []
    for q in missing_queries:
        if _looks_like_path_or_img_tag(q):
            extra_from_assets.append(q)
        else:
            still_missing.append(q)

    if still_missing:
        available = "、".join(
            f"{a['key']}({a['owner']})" for a in art_asset_store.list()
        ) or "暂无已登记资产"
        return ToolResult(
            success=False,
            content=(
                f"未找到已登记的艺术资产: {', '.join(still_missing)}。\n"
                f"当前可用资产: {available}。\n"
                "如需使用未登记的群聊图片，请先用 art_asset(action=\"register\") 登记，或直接传进 image_paths。"
            ),
            error="asset_not_found",
            name="art_draw",
        )

    combined_refs: list[str] = []
    ref_labels: dict[str, str] = {}
    for item in matched_assets:
        ref = item.get("reference")
        if ref and ref not in combined_refs:
            combined_refs.append(ref)
            ref_labels[ref] = _asset_label(item)
    for ref in extra_from_assets:
        if ref not in combined_refs:
            combined_refs.append(ref)
            ref_labels[ref] = _TEMP_REF_LABEL

    if image_paths:
        raw_paths = [image_paths] if isinstance(image_paths, str) else list(image_paths)
        for p in raw_paths:
            p_clean = _clean_ref(p)
            if p_clean:
                # 若模型把资产名误传进了 image_paths，也顺手兼容解析
                asset_item = art_asset_store.get(p_clean)
                resolved_ref = asset_item["reference"] if asset_item else p_clean
                if resolved_ref not in combined_refs:
                    combined_refs.append(resolved_ref)
                    ref_labels[resolved_ref] = (
                        _asset_label(asset_item) if asset_item else _TEMP_REF_LABEL
                    )

    from core.tools.tools_media import resolve_image_size

    target_size = resolve_image_size(size=size, aspect_ratio=aspect_ratio)
    bg_mode = "transparent" if str(background or "").strip().lower() == "transparent" else "opaque"
    qual_mode = str(quality or "high").strip().lower()
    if qual_mode not in ("low", "medium", "high"):
        qual_mode = "high"
    fid_mode = str(input_fidelity or "high").strip().lower()
    if fid_mode not in ("low", "high"):
        fid_mode = "high"

    legend = _build_reference_legend(combined_refs, ref_labels)
    gen_prompt = f"{legend}\n\n{prompt}" if legend else prompt

    gen_kwargs: dict[str, Any] = {
        "prompt": gen_prompt,
        "size": target_size,
        "image_paths": combined_refs if combined_refs else None,
        "aspect_ratio": aspect_ratio,
        "seed": seed,
        "quality": qual_mode,
        "background": bg_mode,
    }
    if combined_refs:
        gen_kwargs["input_fidelity"] = fid_mode
    if bg_mode == "transparent":
        gen_kwargs["output_format"] = "png"

    used_keys = [a["key"] for a in matched_assets]
    used_owners = [f"{a['key']}({a['owner']})" for a in matched_assets]
    step_target = f"参考资产[{','.join(used_keys)}]" if used_keys else "无资产参考"
    focus_manager.record_step(
        context.chat_id,
        f"画图 {step_target}",
        note or str(prompt).strip()[:36],
        domain=ART.name,
    )

    # 异步：只提交任务，后台画完自动发图并唤起一次回复，工具链不再被生图卡住
    job = art_gen_store.submit(
        context,
        gen_kwargs,
        meta={
            "used_assets": used_keys,
            "note": note or "",
            "size": target_size,
            "aspect_ratio": aspect_ratio,
            "background": bg_mode,
            "quality": qual_mode,
            "prompt": prompt,
        },
        prompt=prompt,
    )

    asset_line = f"，参考资产: {', '.join(used_owners)}" if used_owners else ""
    content = (
        f"已提交后台生成（任务 {job.job_id}）：画幅 {target_size}，背景 {bg_mode}{asset_line}。\n"
        "这张图不用你等——画好后会自动发到会话里，并在下一轮把成品交给你看一眼。\n"
        "这期间你可以继续和群友聊天、准备下一张 prompt，或直接 art_finish 收工。"
    )
    data = {
        "art_job": "queued",
        "job_id": job.job_id,
        "prompt": prompt,
        "used_assets": used_keys,
        "reference_paths": combined_refs,
        "size": target_size,
        "aspect_ratio": aspect_ratio,
        "background": bg_mode,
        "quality": qual_mode,
        "note": note or "",
        "no_persist": False,
    }
    if combined_refs:
        data["input_fidelity"] = fid_mode
    return ToolResult(
        success=True,
        content=content,
        data=data,
        name="art_draw",
    )


async def art_asset_tool(
    context,
    action: str = "list",
    key: str = "",
    owner: str = "",
    reference: str = "",
    description: str = "",
    tags: list[str] | str | None = None,
    aliases: list[str] | str | None = None,
    note: str = "",
) -> ToolResult:
    """艺术资产管理工具：查看、登记、修改或删除群友/角色的立绘参考图。"""
    act = str(action or "list").strip().lower()

    if act == "list":
        overview = art_asset_store.format_overview()
        focus_manager.record_step(context.chat_id, "查看艺术资产列表", note, domain=ART.name)
        return ToolResult(
            success=True,
            content=overview,
            data={
                "asset_action": "list",
                "assets": art_asset_store.list(),
                "note": note or "",
                "no_persist": False,
            },
            name="art_asset",
        )

    if act == "register":
        record, err = art_asset_store.register(
            key=key or owner,
            reference=reference,
            owner=owner,
            description=description,
            tags=tags,
            aliases=aliases,
            context=context,
        )
        if err or not record:
            return ToolResult(
                success=False,
                content=f"登记艺术资产失败: {err}",
                error="asset_register_failed",
                name="art_asset",
            )
        focus_manager.record_step(
            context.chat_id,
            f"登记资产 {record['key']}({record['owner']})",
            note or record.get("description", ""),
            domain=ART.name,
        )
        return ToolResult(
            success=True,
            content=(
                f"已成功登记艺术资产：\n{art_asset_store.format_asset_line(record)}\n\n"
                f"{art_asset_store.format_overview()}"
            ),
            data={
                "asset_action": "register",
                "key": record["key"],
                "asset": record,
                "note": note or "",
                "no_persist": False,
            },
            name="art_asset",
        )

    if act == "update":
        record, err = art_asset_store.update(
            key=key or owner,
            reference=reference or None,
            owner=owner or None,
            description=description or None,
            tags=tags,
            aliases=aliases,
            context=context,
        )
        if err or not record:
            return ToolResult(
                success=False,
                content=f"修改艺术资产失败: {err}",
                error="asset_update_failed",
                name="art_asset",
            )
        focus_manager.record_step(
            context.chat_id,
            f"修改资产 {record['key']}({record['owner']})",
            note or record.get("description", ""),
            domain=ART.name,
        )
        return ToolResult(
            success=True,
            content=(
                f"已更新艺术资产：\n{art_asset_store.format_asset_line(record)}\n\n"
                f"{art_asset_store.format_overview()}"
            ),
            data={
                "asset_action": "update",
                "key": record["key"],
                "asset": record,
                "note": note or "",
                "no_persist": False,
            },
            name="art_asset",
        )

    if act == "delete":
        removed, err = art_asset_store.delete(key or owner)
        if err or not removed:
            return ToolResult(
                success=False,
                content=f"删除艺术资产失败: {err}",
                error="asset_delete_failed",
                name="art_asset",
            )
        focus_manager.record_step(
            context.chat_id,
            f"删除资产 {removed['key']}({removed.get('owner', '')})",
            note,
            domain=ART.name,
        )
        return ToolResult(
            success=True,
            content=(
                f"已删除艺术资产: {removed['key']}（人物: {removed.get('owner') or removed['key']}）\n\n"
                f"{art_asset_store.format_overview()}"
            ),
            data={
                "asset_action": "delete",
                "key": removed["key"],
                "removed": removed,
                "note": note or "",
                "no_persist": False,
            },
            name="art_asset",
        )

    return ToolResult(
        success=False,
        content=f"不支持的 action: {action}（可选: list / register / update / delete）",
        error="invalid_action",
        name="art_asset",
    )


async def art_gacha_tool(context) -> ToolResult:
    """提示词抽卡：随机抽一句提示词灵感返回给模型润色，不直接生图（无参数）。"""
    drawn = art_gacha_store.draw()
    prompt = str(drawn.get("prompt") or "").strip()
    if not prompt:
        return ToolResult(
            success=False,
            content="这轮没抽到内容，再调用一次试试。",
            error="empty_draw",
            name="art_gacha",
        )

    focus_manager.record_step(
        context.chat_id,
        "提示词抽卡",
        drawn.get("source", ""),
        domain=ART.name,
    )

    return ToolResult(
        success=True,
        content=prompt,
        data={
            "source": drawn.get("source", ""),
            "prompt": prompt,
            "no_persist": False,
        },
        name="art_gacha",
    )


art_finish_tool = make_focus_finish_handler(ART)
