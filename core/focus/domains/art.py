# core/focus/domains/art.py
"""艺术创作聚焦域声明与入口/生图/资产管理/退出工具实现。"""
from __future__ import annotations

import os
import re
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
)

register_domain(ART)


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
    "4. 异步出图与自检：`art_draw` 只是提交任务、立刻返回，**不要空等**——这期间可以继续聊天或准备下一张；"
    "画好后成品会自动发到会话里，并在下一轮把成品预览交给你，那时先看一眼构图/文字/手指；"
    "若局部瑕疵可用 `art_draw(image_paths=[该file_path], prompt=\"Keep everything else identical, only fix...\", input_fidelity=\"high\")` 精修；"
    "成品不要自己再用 `send_qq_file` 重复发一遍。\n"
    "需要注意的是，上述的括号内内容仅是示例，实际使用时不要直接照搬括号内的文字，而是根据你想要的画面和风格来写 prompt。"
)


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
    content = f"{header}\n\n{overview}"
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
    for item in matched_assets:
        ref = item.get("reference")
        if ref and ref not in combined_refs:
            combined_refs.append(ref)
    for ref in extra_from_assets:
        if ref not in combined_refs:
            combined_refs.append(ref)

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

    from core.tools.tools_media import resolve_image_size

    target_size = resolve_image_size(size=size, aspect_ratio=aspect_ratio)
    bg_mode = "transparent" if str(background or "").strip().lower() == "transparent" else "opaque"
    qual_mode = str(quality or "high").strip().lower()
    if qual_mode not in ("low", "medium", "high"):
        qual_mode = "high"
    fid_mode = str(input_fidelity or "high").strip().lower()
    if fid_mode not in ("low", "high"):
        fid_mode = "high"

    gen_kwargs: dict[str, Any] = {
        "prompt": prompt,
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


async def art_gacha_tool(
    context,
    pool: str = "auto",
    assets: list[str] | str | None = None,
    blueprint_id: str = "",
    lock: dict[str, str] | str | None = None,
    note: str = "",
) -> ToolResult:
    """提示词抽卡：抽一发二次元 Prompt 灵感草稿返回给模型审阅与修改，不直接生图。"""
    matched_assets: list[dict[str, Any]] = []
    if assets:
        matched_assets, missing = art_asset_store.resolve_many(assets)
        if missing:
            available = "、".join(
                f"{a['key']}({a['owner']})" for a in art_asset_store.list()
            ) or "暂无已登记资产"
            return ToolResult(
                success=False,
                content=(
                    f"未找到已登记的艺术资产: {', '.join(missing)}。\n"
                    f"当前可用资产: {available}。"
                ),
                error="asset_not_found",
                name="art_gacha",
            )

    lock_dict: dict[str, str] | None = None
    if isinstance(lock, dict):
        lock_dict = {str(k): str(v) for k, v in lock.items()}
    elif isinstance(lock, str) and lock.strip():
        try:
            import json
            parsed = json.loads(lock)
            if isinstance(parsed, dict):
                lock_dict = {str(k): str(v) for k, v in parsed.items()}
        except Exception:
            lock_dict = None

    try:
        drawn = art_gacha_store.draw(
            pool=pool,
            blueprint_id=blueprint_id,
            lock=lock_dict,
            matched_assets=matched_assets,
        )
    except ValueError as exc:
        return ToolResult(
            success=False,
            content=str(exc),
            error="invalid_gacha_param",
            name="art_gacha",
        )

    focus_manager.record_step(
        context.chat_id,
        f"提示词抽卡 [{drawn.get('rarity')}] {drawn.get('card_name')}",
        note or drawn.get("card_id", ""),
        domain=ART.name,
    )

    content = art_gacha_store.format_result(drawn)
    return ToolResult(
        success=True,
        content=content,
        data={
            "gacha_card": drawn.get("card_name", ""),
            "card_id": drawn.get("card_id", ""),
            "rarity": drawn.get("rarity", ""),
            "mode": drawn.get("mode", ""),
            "aspect_ratio": drawn.get("aspect_ratio", "2:3"),
            "assets": drawn.get("assets", []),
            "prompt": drawn.get("prompt", ""),
            "note": note or "",
            "no_persist": False,
        },
        name="art_gacha",
    )


art_finish_tool = make_focus_finish_handler(ART)
