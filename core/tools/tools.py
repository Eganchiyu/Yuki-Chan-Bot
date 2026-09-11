# core/tools/tools.py
"""工具规格装配：汇总各职责子服务导出的 ToolSpec，并保持旧引用兼容。"""
from core.toolchain import ToolSpec

from .tools_browser import enter_browser_interaction_tool
from .tools_diary import search_diary_tool
from .tools_maid import delegate_to_maid_tool
from .tools_media import download_file_tool, generate_image_tool
from .tools_message import poke_tool, send_master_private_tool, send_qq_file_tool
from .tools_ncm import ncm_download_tool, ncm_search_tool
from .tools_qzone import publish_qzone_mood_tool
from .tools_rich import parse_rich_message_tool
from .tools_search import amap_search_tool, browser_search_tool
from .tools_snapshot import capture_group_snapshot_tool, search_group_snapshots_tool
from .tools_status import get_master_status_tool
from .tools_timer import manage_timer_task_tool

TOOL_SPECS = [
    ToolSpec(
        name="delegate_to_maid",
        description="将工作任务委托给电脑上的小女仆处理。使用小女仆完成你自己不能完成的任务。",
        parameters={
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "要完成的任务描述"},
                "run_inline": {"type": "boolean"},
            },
            "required": ["goal"],
        },
        handler=delegate_to_maid_tool,
    ),
    ToolSpec(
        name="search_diary",
        description="查询日记/记忆，支持按日期和关键词检索。",
        parameters={
            "type": "object",
            "properties": {
                "date_str": {"type": "string", "description": "日期，如 2026-05-20 或 2026-05"},
                "keyword": {"type": "string", "description": "需要匹配的关键词"},
            },
        },
        handler=search_diary_tool,
    ),
    ToolSpec(
        name="get_master_status",
        description="判断主人是否在线、是否活跃，并返回当前聚焦的窗口标题。",
        parameters={"type": "object", "properties": {}},
        handler=get_master_status_tool,
    ),
    # ToolSpec(
    #     name="enter_browser_interaction",
    #     description="进入浏览器交互聚焦模式。用于需要观察或操作浏览器时调用；如果已有聚焦模式运行则会拒绝重复进入。",
    #     parameters={
    #         "type": "object",
    #         "properties": {
    #             "goal": {"type": "string", "description": "进入浏览器模式后要完成的任务目标"},
    #         },
    #     },
    #     handler=enter_browser_interaction_tool,
    # ),
    ToolSpec(
        name="send_master_private",
        description="向主人私聊发送私密信息。用于信息通知、有人提到主人或者想要找主人等场景。",
        parameters={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "要发送给主人的消息内容"},
            },
            "required": ["message"],
        },
        handler=send_master_private_tool,
    ),
    ToolSpec(
        name="poke",
        description="戳一戳指定用户。可以传入昵称（自动解析）或直接传入 QQ 号。",
        parameters={
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "用户昵称或群名片"},
                "user_id": {"type": "integer", "description": "用户 QQ 号（如果已知）"},
            },
        },
        handler=poke_tool,
    ),
    ToolSpec(
        name="send_qq_file",
        description="发送本地图片、语音或普通文件；优先用此工具，不要在回复中手写 CQ 文件码。",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "本地文件路径"},
                "file_type": {"type": "string", "enum": ["auto", "image", "voice", "file"]},
                "caption": {"type": "string", "description": "发送文件前附带的一句说明，可省略"},
            },
            "required": ["file_path"],
        },
        handler=send_qq_file_tool,
    ),
    ToolSpec(
        name="ncm_search",
        description="搜索网易云音乐歌曲，返回歌曲列表（含歌曲 id、歌手、专辑、时长）。用户想找歌/点歌/要歌曲链接时使用，搜索到后如需下载用 ncm_download。若返回 ncm_cookie_expired 错误并带 qr_image_path，需用 send_qq_file 把该二维码图片发给用户扫码，用户扫码后再次调用即可。",
        parameters={
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "搜索关键词，如歌名或歌手名"},
                "limit": {"type": "integer", "description": "返回数量，默认5，最多5", "default": 5},
            },
            "required": ["keyword"],
        },
        handler=ncm_search_tool,
    ),
    ToolSpec(
        name="ncm_download",
        description="把网易云音乐歌曲下载到本地，返回文件路径。之后可用 send_qq_file 把文件发送到群里或私聊。VIP/版权受限歌曲可能下载失败。若返回 ncm_cookie_expired 错误并带 qr_image_path，需用 send_qq_file 把该二维码图片发给用户扫码，用户扫码后再次调用即可。",
        parameters={
            "type": "object",
            "properties": {
                "song_id": {"type": "integer", "description": "歌曲 ID（来自 ncm_search 结果）"},
                "quality": {"type": "string", "description": "码率，默认320000（320kbps）；失败可降为128000", "default": "320000"},
                "filename": {"type": "string", "description": "保存的文件名，可省略"},
            },
            "required": ["song_id"],
        },
        handler=ncm_download_tool,
    ),
    ToolSpec(
        name="capture_group_snapshot",
        description="截屏留念当前群聊最近上下文：把最近聊天渲染成一张本地永久保存的截图并标记。想记录热闹、名场面、群里发生了什么时直接调用。",
        parameters={
            "type": "object",
            "properties": {
                "note": {"type": "string", "description": "备注/事件描述，记录发生的事情和你的评论"},
                "limit": {"type": "integer", "description": "截取最近多少条上下文，默认12", "default": 12},
            },
            "required": ["note"],
        },
        handler=capture_group_snapshot_tool,
    ),
    ToolSpec(
        name="search_group_snapshots",
        description="翻看本群以前截屏过的记录。按关键词搜索或随机返回当前群聊永久保存过的截屏，最多返回5条，并预热为 [shot:1]、[shot:2] 等索引；要发送时用 send_qq_file 发送对应 [shot:编号]。",
        parameters={
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "搜索关键词；可省略，省略时随机返回本群截屏"},
                "limit": {"type": "integer", "description": "返回数量，默认5，最多5", "default": 5},
            },
        },
        handler=search_group_snapshots_tool,
    ),
    ToolSpec(
        name="publish_qzone_mood",
        description="发布 QQ 空间说说，支持文本和图片。不要频繁调用。",
        parameters={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "说说文本内容"},
                "visible": {"type": "integer", "description": "可见范围: 1=公开(默认) 4=仅自己", "default": 1},
                "image_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "图片本地路径列表（可选），如 [\"D:/photo/a.jpg\"]",
                },
            },
            "required": ["content"],
        },
        handler=publish_qzone_mood_tool,
    ),
    ToolSpec(
        name="parse_rich_message",
        description=(
            "主动解析最近收到的富文本消息，包括合并转发、小程序、JSON、XML、Markdown。"
            "遇到 [合并转发:id=xxx]、[小程序] 或看不清的富文本时使用。"
            "合并转发很长时用 start/count 分页阅读，嵌套合并转发会自动展开到 max_depth。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "rich_id": {"type": "string", "description": "富文本 ID，主要用于合并转发 ID；不填则解析最近一条富文本"},
                "rich_type": {
                    "type": "string",
                    "enum": ["auto", "forward", "miniapp", "json", "xml", "markdown"],
                    "description": "富文本类型，默认自动识别",
                    "default": "auto",
                },
                "start": {"type": "integer", "description": "合并转发从第几条开始读，默认1", "default": 1},
                "count": {"type": "integer", "description": "本次读取多少条，默认20，最多80", "default": 20},
                "max_depth": {"type": "integer", "description": "嵌套合并转发自动展开深度，默认3", "default": 3},
            },
        },
        handler=parse_rich_message_tool,
    ),
    ToolSpec(
        name="download_file",
        description="下载群聊/私聊中的文件到本地。当想要下载文件消息（显示为 [文件:file_id=xxx]）时，使用此工具下载文件。下载后可以委托小女仆分析文件内容。",
        parameters={
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "文件 ID，从消息中的 [文件:file_id=xxx] 获取"},
                "filename": {"type": "string", "description": "保存的文件名（可选，默认使用原文件名）"},
            },
        },
        handler=download_file_tool,
    ),
    ToolSpec(
        name="generate_image",
        description=(
            "根据文字描述生成图片。生成后保存到本地 output 目录，返回文件路径。"
            "生成完后必须用 send_qq_file 工具把图片发出来。"
            "重要：prompt 必须完整详细，包含主体、场景、风格、光影、构图等细节，"
            "融入 Yuki 的二次元少女特色（白色长发蓝瞳少女，雪花发饰）"
        ),
        parameters={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "图像描述（使用中文描述）"},
                "size": {"type": "string", "description": "图片尺寸，如 1024*1024、512*512", "default": "1024*1024"},
            },
            "required": ["prompt"],
        },
        handler=generate_image_tool,
    ),
]

# 兼容旧引用，后续新增工具优先维护 TOOL_SPECS。
TOOL_SCHEMAS = [spec.to_schema() for spec in TOOL_SPECS]
TOOL_HANDLERS = {spec.name: spec.handler for spec in TOOL_SPECS}

# 这部分不要删除，保留以后可能需要
# async def resolve_user_tool(context, name=None):
#     """根据昵称解析用户 QQ 号。用于需要指定目标用户的场景（如戳一戳、发送文件等）。"""
#     if not name:
#         return ToolResult(success=False, content="缺少用户昵称", error="missing_name")

#     user_id = context.yuki.user_mapping.resolve(context.chat_id, name)
#     if user_id:
#         return ToolResult(success=True, content=str(user_id), data={"name": name, "user_id": user_id})

#     # 返回当前群聊中已知的所有映射，帮助调试
#     all_mappings = context.yuki.user_mapping.get_all(context.chat_id)
#     return ToolResult(
#         success=False,
#         content=f"未找到用户 '{name}' 的 QQ 号。",
#         data={"searched": name, "known_users": all_mappings},
#         error="user_not_found",
#     )
# 配套的 ToolSpec
# ToolSpec(
#     name="resolve_user",
#     description="根据用户昵称解析 QQ 号。想要获取QQ号的时候使用。",
#     parameters={
#         "type": "object",
#         "properties": {
#             "name": {"type": "string", "description": "用户昵称"},
#         },
#         "required": ["name"],
#     },
#     handler=resolve_user_tool,
# ),
