# core/focus/rewrite.py
"""聚焦模式上下文覆写纯函数：负责持久化历史清理、当轮内存消息清理与孤儿片段识别。"""
from __future__ import annotations

from typing import Callable

from core.focus.domain import FocusDomain


def message_focus_domain(
    msg: dict,
    domain_of_tool: Callable[[str], FocusDomain | None] | None = None,
) -> str | None:
    """识别一条历史消息所属的聚焦域名称（兼容旧 phone_focus_work 标记）。"""
    if not isinstance(msg, dict):
        return None
    role = msg.get("role")
    if role not in ("tool", "assistant"):
        return None
    if role == "assistant" and not msg.get("is_tool_thought"):
        return None

    fw = msg.get("focus_work")
    if isinstance(fw, str) and fw:
        return fw
    if fw is True or msg.get("phone_focus_work"):
        return "phone"

    if role == "tool" and domain_of_tool is not None:
        d = domain_of_tool(str(msg.get("name") or ""))
        if d is not None:
            return d.name
    return None


def is_domain_work_message(msg: dict, domain: FocusDomain) -> bool:
    """判断持久化 session 中的一条消息是否属于指定域需要被总结覆盖的工作记录。"""
    if not isinstance(msg, dict):
        return False
    role = msg.get("role")
    fw = msg.get("focus_work")
    matches_flag = (fw == domain.name) or (
        domain.name == "phone" and bool(msg.get("phone_focus_work") or fw is True)
    )
    if role == "tool":
        return matches_flag or (msg.get("name") in domain.work_tools)
    if role == "assistant":
        return bool(msg.get("is_tool_thought") and matches_flag)
    return False


def is_focus_summary_message(msg: dict, domain_name: str | None = None) -> bool:
    """判断一条消息是否为聚焦退出总结（兼容旧 is_phone_summary）。"""
    if not isinstance(msg, dict):
        return False
    if msg.get("is_focus_summary"):
        if domain_name is None:
            return True
        return msg.get("focus_domain") == domain_name
    if msg.get("is_phone_summary"):
        return domain_name in (None, "phone")
    return False


def build_summary_message(domain: FocusDomain, summary_text: str) -> dict:
    """构造写入持久化历史的 USER 聚焦总结消息（同时写新字段与手机域兼容字段）。"""
    msg = {
        "role": "user",
        "content": f"{domain.effective_summary_prefix}{summary_text}",
        "is_focus_summary": True,
        "focus_domain": domain.name,
    }
    if domain.name == "phone":
        msg["is_phone_summary"] = True
    return msg


def rewrite_persistent_session(
    session: list[dict],
    domain: FocusDomain,
    summary_text: str,
) -> list[dict]:
    """返回清理掉指定域工作记录并在末尾追加 USER 总结后的新会话列表。"""
    filtered = [msg for msg in session if not is_domain_work_message(msg, domain)]
    filtered.append(build_summary_message(domain, summary_text))
    return filtered


def rewrite_in_memory_messages(
    tool_messages: list[dict],
    domain: FocusDomain,
    summary_text: str,
) -> None:
    """原地清理当轮 tool_messages 中的指定域工具调用链，保留期间普通消息并追加 USER 总结。"""
    if not isinstance(tool_messages, list):
        return

    cleaned: list[dict] = []
    domain_call_ids: set[str] = set()
    work_tools = domain.work_tools

    for msg in tool_messages:
        if not isinstance(msg, dict):
            cleaned.append(msg)
            continue
        role = msg.get("role")

        # 1) assistant 发起的 tool_calls
        if role == "assistant" and msg.get("tool_calls"):
            calls = msg.get("tool_calls") or []
            remaining_calls = []
            for call in calls:
                fn_name = (call.get("function") or {}).get("name") or ""
                call_id = call.get("id") or ""
                if fn_name in work_tools:
                    if call_id:
                        domain_call_ids.add(call_id)
                else:
                    remaining_calls.append(call)
            if remaining_calls:
                new_msg = dict(msg)
                new_msg["tool_calls"] = remaining_calls
                cleaned.append(new_msg)
            continue

        # 2) tool 结果消息
        if role == "tool":
            if (
                msg.get("name") in work_tools
                or msg.get("tool_call_id") in domain_call_ids
                or is_domain_work_message(msg, domain)
            ):
                continue
            cleaned.append(msg)
            continue

        # 3) 工具截图临时 user 消息
        if role == "user":
            content = msg.get("content")
            if isinstance(content, str) and content.startswith("【工具截图】"):
                continue
            if isinstance(content, list) and any(
                isinstance(b, dict) and str(b.get("text") or "").startswith("【工具截图】")
                for b in content
            ):
                continue

        cleaned.append(msg)

    cleaned.append({
        "role": "user",
        "content": (
            f"{domain.effective_summary_prefix}{summary_text}\n"
            f"{domain.effective_exit_hint}"
        ),
    })
    tool_messages[:] = cleaned
