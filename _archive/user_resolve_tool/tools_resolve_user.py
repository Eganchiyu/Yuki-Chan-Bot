# core/tools/tools_resolve_user.py
"""根据昵称解析用户 QQ 号工具。"""
from core.toolchain import ToolResult, ToolSpec


async def resolve_user_tool(context, name=None):
    """根据昵称解析用户 QQ 号。用于需要指定目标用户的场景（如戳一戳、发送文件等）。"""
    if not name:
        return ToolResult(success=False, content="缺少用户昵称", error="missing_name")

    user_id = context.yuki.user_mapping.resolve(context.chat_id, name)
    if user_id:
        return ToolResult(success=True, content=str(user_id), data={"name": name, "user_id": user_id})

    # 返回当前群聊中已知的所有映射，帮助调试
    all_mappings = context.yuki.user_mapping.get_all(context.chat_id)
    return ToolResult(
        success=False,
        content=f"未找到用户 '{name}' 的 QQ 号。",
        data={"searched": name, "known_users": all_mappings},
        error="user_not_found",
    )


RESOLVE_USER_SPEC = ToolSpec(
    name="resolve_user",
    description="根据用户昵称解析 QQ 号。想要获取QQ号的时候使用。",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "用户昵称"},
        },
        "required": ["name"],
    },
    handler=resolve_user_tool,
)
