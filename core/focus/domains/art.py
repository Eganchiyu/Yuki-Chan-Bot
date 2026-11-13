# core/focus/domains/art.py
"""艺术创作聚焦域声明与入口/生图/资产管理/退出工具实现。"""
from __future__ import annotations

import os
import re
from typing import Any

from core.art_assets import _clean_ref, art_asset_store
from core.focus.domain import BASE_KEEP_TOOLS, FocusDomain
from core.focus.manager import focus_manager, register_domain
from core.focus.tools import make_focus_finish_handler
from core.toolchain import ToolResult
from utils import BASE_DIR
from utils.logger import get_logger

logger = get_logger("tools")


def _art_stub(payload: dict) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if "file_path" in data and "prompt" in data:
        assets = data.get("used_assets") or []
        asset_str = f" assets={','.join(assets)}" if assets else ""
        return f"art_draw{asset_str} -> {data.get('file_path')}"
    if "asset_action" in data:
        return f"art_asset {data.get('asset_action')} {data.get('key', '')}".strip()
    return str(payload.get("content") or "").replace("\n", " ")


ART = FocusDomain(
    name="art",
    title="艺术创作",
    entry_tool="art_start",
    exit_tool="art_finish",
    domain_tools=frozenset({"art_draw", "art_asset"}),
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
        "【已进入艺术创作聚焦模式】已展开 art_draw / art_asset / art_finish 工具，并收起其他无关日常工具。\n"
        "- 画图用 `art_draw`：可通过 `assets=[\"yuki\", \"master\"]` 直接选用下方已登记的角色参考图（支持单张或多张同框），"
        "也可同时传 `image_paths=[\"[img:001]\"]` 混用群聊临时参考图；生成完后请用 `send_qq_file` 把图片发到会话中。\n"
        "- 资产管理用 `art_asset`：支持登记群友/角色立绘或三视图（`register`）、修改（`update`）、删除（`delete`）或查看列表（`list`）。\n"
        "- 创作与发图全部完成后，请调用 `art_finish(summary=\"...\")` 收起画板并写一句简短总结。"
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
    note: str = "",
) -> ToolResult:
    """在艺术创作模式下生成图片，支持选用已登记资产参考图、临时参考图与画幅比例预设。"""
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

    from core.tools.tools_media import generate_image_tool, resolve_image_size

    target_size = resolve_image_size(size=size, aspect_ratio=aspect_ratio)
    gen_res = await generate_image_tool(
        context,
        prompt=prompt,
        size=target_size,
        image_paths=combined_refs if combined_refs else None,
        aspect_ratio=aspect_ratio,
        seed=seed,
    )
    if not gen_res.success:
        return ToolResult(
            success=False,
            content=gen_res.content,
            data=gen_res.data,
            error=gen_res.error,
            name="art_draw",
        )

    used_keys = [a["key"] for a in matched_assets]
    used_owners = [f"{a['key']}({a['owner']})" for a in matched_assets]
    step_target = f"参考资产[{','.join(used_keys)}]" if used_keys else "无资产参考"
    focus_manager.record_step(
        context.chat_id,
        f"画图 {step_target}",
        note or str(prompt).strip()[:36],
        domain=ART.name,
    )

    filepath = (gen_res.data or {}).get("file_path", "")
    final_size = (gen_res.data or {}).get("size", target_size)
    asset_line = f"\n已选用登记资产: {', '.join(used_owners)}" if used_owners else ""
    content = (
        f"图像已生成并保存: {filepath}（画幅: {final_size}）{asset_line}\n"
        "请调用 send_qq_file 将图片发送给用户；若这幅图是新的角色设定/立绘，也可用 art_asset 登记到资产库。"
    )
    data = dict(gen_res.data or {})
    data.update({
        "used_assets": used_keys,
        "reference_paths": combined_refs,
        "size": final_size,
        "aspect_ratio": aspect_ratio,
        "note": note or "",
        "no_persist": False,
    })
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


art_finish_tool = make_focus_finish_handler(ART)
