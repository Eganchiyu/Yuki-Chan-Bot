# core/tools/tools.py
"""工具规格装配：汇总各职责子服务导出的 ToolSpec，并保持旧引用兼容。"""
from core.focus.domains.art import (
    art_asset_tool,
    art_draw_tool,
    art_finish_tool,
    art_gacha_tool,
    art_start_tool,
)
from core.focus.domains.browser import browser_finish_tool, browser_start_tool
from core.phone_focus import phone_finish_tool, phone_start_tool
from core.toolchain import MAID_GOAL_BREVITY_HINT, ToolSpec

from .tools_browser import browser_action_tool

from .tools_diary import search_diary_tool
from .tools_maid import delegate_to_maid_tool, stop_maid_tool
from .tools_media import download_file_tool, generate_image_tool
from .tools_message import poke_tool, send_master_private_tool, send_qq_file_tool
from .tools_notebook import update_notebook_tool
from .tools_phone import phone_action_tool
from .tools_phone_macro import phone_macro_tool
from .tools_rich import parse_rich_message_tool
from .tools_skip import skip_reply_tool
from .tools_snapshot import capture_group_snapshot_tool, search_group_snapshots_tool

TOOL_SPECS = [
    ToolSpec(
        name="phone_start",
        description=(
            "拿起手机开始操作（点外卖、查App、跑组合技等）。"
            "调用后进入手机聚焦模式，解锁触控与组合技工具并立即返回当前屏幕控件树与已有组合技。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "这次拿起手机要做什么（可选，如“点美团外卖”）",
                },
            },
        },
        handler=phone_start_tool,
    ),
    ToolSpec(
        name="phone_action",
        description=(
            "亲手操作插在电脑上的安卓手机（adb）。先 action=inspect 看清当前界面，"
            "返回仅含可交互元素（输入/可点/滚动）的带编号 [#1][#2] 控件树与红框标注截图（静态文字直接看截图）；"
            "之后用 target=编号 精确点按，不用猜坐标。"
            "action 可选：inspect / tap / long_press / input / swipe / key / back / home / launch / wait。"
            "input 的 text 支持中文（需要手机装 ADBKeyboard，否则会提示）；"
            "每次操作后会自动等界面刷新并返回最新可交互控件树与带红框编号的屏幕截图。"
            "每一步都会自动记进操作历史，摸熟后可用 phone_macro 的 save(from_history=N) 存成组合技。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "inspect", "tap", "long_press", "input", "swipe",
                        "scroll_to_find", "key", "back", "home", "launch", "wait",
                    ],
                    "description": "要做的动作，默认 inspect（只看不动）；scroll_to_find 可自动循环滑动查找含 text 的控件",
                    "default": "inspect",
                },
                "target": {
                    "type": "string",
                    "description": "控件编号（如 3 或 #3）或坐标 \"x,y\"；key 动作时填按键名（back/home/enter）",
                },
                "text": {"type": "string", "description": "input 时要输入的文字"},
                "direction": {"type": "string", "description": "swipe 方向：up/down/left/right，默认 up"},
                "duration": {"type": "integer", "description": "swipe 时长毫秒，默认300"},
                "app": {"type": "string", "description": "launch 时的 App 名称（如 美团）或包名"},
                "seconds": {"type": "number", "description": "wait 的秒数"},
                "include_screenshot": {
                    "type": "boolean",
                    "description": "是否附带当前屏幕红框标注截图（默认 true）",
                    "default": True,
                },
                "note": {
                    "type": "string",
                    "description": "顺手记一句这步在做什么/看到什么，之后上下文折叠时只保留它",
                },
                "remember": {
                    "type": "boolean",
                    "description": "是否写进长期记忆与手机操作历史，默认true；纯试探可传false",
                    "default": True,
                },
            },
        },
        handler=phone_action_tool,
    ),
    ToolSpec(
        name="phone_macro",
        description=(
            "手机组合技：把摸熟的操作流程存成可复用的宏，以后一句话跑完。"
            "phone_action 的每一步都会自动记进操作历史（remember=false 不记）；"
            "流程走通后 save(name=..., from_history=10) 取最近 10 步存成宏，"
            "会自动折叠「点进页面又返回」这类白跑步骤，也能用 exclude=[历史编号] 手动剔。"
            "之后 play(name=..., params={...}) 回放：每步先按控件文案重新定位，"
            "执行后校验界面是否按预期变化，不对就停在那一颗并回传现场控件树与截图。"
            "固定文字想复用可以 param_defs 声明参数 + replace={\"炸鸡\":\"{{food}}\"} 参数化。"
            "历史用 history 回看；宏跑挂了就修好后 save 同名覆盖（version 自增）。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "history", "show", "save", "play", "delete"],
                    "description": "list=列出宏；history=看操作历史；show=看某个宏的步骤；save=存宏；play=回放；delete=删宏",
                    "default": "list",
                },
                "name": {"type": "string", "description": "宏的名字（save/show/play/delete 用）"},
                "desc": {"type": "string", "description": "save 时的一句话说明"},
                "app": {"type": "string", "description": "save 时的主 App 包名，留空自动从 launch 步骤取"},
                "from_history": {
                    "type": "integer",
                    "description": "save 时取最近多少条成功操作作为步骤，如 10",
                },
                "exclude": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "save 时要剔掉的历史编号（history 里显示的 #n）",
                },
                "steps": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "save 时直接手写步骤（会覆盖 from_history），一般不用",
                },
                "param_defs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "save 时声明的参数名，如 [\"food\"]",
                },
                "replace": {
                    "type": "object",
                    "description": "save 时把录下来的固定文字换成占位符，如 {\"炸鸡\": \"{{food}}\"}",
                },
                "params": {
                    "type": "object",
                    "description": "play 时传给宏的参数值，如 {\"food\": \"炸鸡\"}",
                },
                "dry_run": {"type": "boolean", "description": "play 时只列步骤不执行", "default": False},
                "auto_distill": {
                    "type": "boolean",
                    "description": "save 时是否启用 Sub-LLM 自动剔除冗余探索滑动并提取业务参数，默认 true",
                    "default": True,
                },
                "limit": {"type": "integer", "description": "history 最多返回多少条，默认15"},
                "note": {"type": "string", "description": "顺手记一句这步在做什么"},
            },
        },
        handler=phone_macro_tool,
    ),
    ToolSpec(
        name="phone_finish",
        description=(
            "结束操作手机并退出聚焦模式，恢复常规工具空间。"
            "请传入一句简短的 summary 总结刚才在手机上做了什么及结果，"
            "它会覆盖工作模式中的繁琐操作记录保留在上下文里。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "简短总结刚才在手机上做了什么与结果（会以 USER 总结的形式写入上下文）",
                },
            },
            "required": ["summary"],
        },
        handler=phone_finish_tool,
    ),
    ToolSpec(
        name="delegate_to_maid",
        description=(
            "将工作任务委托给电脑上的小女仆处理。使用小女仆完成你自己不能完成的任务。"
            "委托后立即返回，她在后台干活，完成后会主动把结果汇报给你——"
            "不要等待结果，也不需要反复询问进度。"
            "可以连续下发多个任务，她们会各自并行跑（返回里带编号，如 #2），互不等待。"
            f"{MAID_GOAL_BREVITY_HINT}"
        ),
        parameters={
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "要完成的任务描述，写清目标和验收标准",
                },
            },
            "required": ["goal"],
        },
        handler=delegate_to_maid_tool,
    ),
    ToolSpec(
        name="stop_maid",
        description=(
            "强制叫停正在干活的小女仆：直接从后台取消，进程会被杀掉，"
            "任务不会再跑，也不会再给你汇报结果。"
            "不填参数就停掉本会话全部小女仆任务；只想停某一个时，"
            "填 task_id（编号如 2 / #2）或 keyword（任务内容关键词）。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "要叫停的小女仆编号（如 2 或 #2），留空表示不按编号筛选",
                },
                "keyword": {
                    "type": "string",
                    "description": "按任务内容关键词匹配（如「天气」），留空表示不按关键词筛选",
                },
            },
        },
        handler=stop_maid_tool,
    ),
    ToolSpec(
        name="search_diary",
        description=(
            "（随机）查询日记/记忆。可按日期、关键词检索。"
            "两个参数都不填时随机翻看日记本里的若干条，适合想随意回忆/找话题时使用。"
            "结果会标注每条日记的归属（[本群]/[本对话] 或 [群:xxx]），以本群记录为主、别的群记录少量出现；"
            "如果本群没有相关记录会明确告诉你，只有别的群的记录。"
        ),
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
        name="update_notebook",
        description=(
            "用来更新小本本。你会在情绪高涨、想更新信念、记录重要的人或事，或者想写下长期目标时使用。你可以使用符合自己风格的第一人称口吻来书写。"
            "小本本分两个区：日常随记区（zone=daily，最多350字）与长期规划路标区（zone=plans，最多160字，只放最活跃的1~2条任务指针）。"
            "每次调用只覆盖所写分区，**该区要保留的内容请一起写进去。**"
        ),
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "该分区的完整内容（日常随记区最多350字符，长期规划区最多160字符）",
                },
                "zone": {
                    "type": "string",
                    "enum": ["daily", "plans"],
                    "description": "daily=日常随记区（默认）；plans=长期规划路标区（只放最活跃的 1~2 条任务指针）",
                    "default": "daily",
                },
            },
            "required": ["content"],
        },
        handler=update_notebook_tool,
        persist_result=False,
    ),
    ToolSpec(
        name="skip",
        description=(
            "跳过本轮回复，保持安静。当这段对话并没有涉及你、群友们在互相聊自己的事、"
            "或者此刻不适合你发言（话题很沉重、插话会唐突、别人刚说完正事）时调用它，"
            "本轮就不会发出任何消息。想说话的时候正常回复即可，不需要调用。"
            "私聊里必须回复，不要使用。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "一句话说明这轮为什么不说话（只记进日志，不会发出去）"},
            },
        },
        handler=skip_reply_tool,
        persist_result=False,
    ),
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
        name="art_start",
        description=(
            "打开画板进入艺术创作模式（画图、参考图生图、登记/管理群友立绘参考图资产）。请在需要画图或管理群友立绘资产时调用它。"
            "调用后立即返回当前已登记的角色参考图资产列表，并解锁 art_draw / art_asset / art_finish 工具。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "这次进入艺术创作模式要画什么或管理什么资产（可选）",
                },
            },
        },
        handler=art_start_tool,
    ),
    ToolSpec(
        name="art_draw",
        description=(
            "在艺术创作模式下生成图片。"
            "可通过 assets 选择一张或多张已登记的角色/群友立绘资产（如 [\"yuki\"]、[\"yuki\", \"master\"]、[\"池宇健\"]）作为参考图，"
            "以保持人物长相、发色瞳色、发饰和服装一致；也可同时用 image_paths 传入会话临时图片（如 [\"[img:001]\"]）或上一张成图路径做局部精修。"
            "prompt 推荐用结构化英文画面导演指令（含景别角度、二次元时代/媒介画风锚点、动作神态与饰品数量词、物理光影方向与色板脚本），画面内要渲染的中文/日文台词与招牌文字用引号保留原文；换装时需明写保留参考图的脸型、发色瞳色与发饰。"
            "默认 background=\"opaque\" 生成非透明实底背景，仅在用户明确要求透明背景/免抠贴纸时传 \"transparent\"。"
            "**本工具是异步的**：调用后立刻返回任务号，图片在后台生成，画完会自动发到会话里并把成品预览交给你（下一轮可见），"
            "所以不要在调用后空等或反复轮询，也不要用 send_qq_file 重发成品；这期间可以继续聊天或提交下一张。\n"
            "如果用户说明需要“把图片里的xxx换为某人”，要使用发送的图片和任务资产联合生图。以此类推。需要提前想好这张图里会有那些指定人，然后使用全部的这些assets资产参考图。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "结构化画面导演描述（优先英文描述景别、画风锚点、精确数量词、光影与色板；画面中需渲染的中文/日文文字用引号保留原文）",
                },
                "assets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "选用的已登记艺术资产 key 或人物名称列表（如 [\"yuki\", \"master\"]），支持单张或多张同框",
                },
                "image_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "额外临时参考图列表（可选，元素为 [img:XXX] 索引或本地图片路径，与 assets 合计最多4张）",
                },
                "aspect_ratio": {
                    "type": "string",
                    "enum": ["1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"],
                    "description": "画幅比例预设：1:1(1024*1024方图)、2:3(1024*1536竖版立绘)、3:2(1536*1024横版插画)、3:4、4:3、9:16、16:9",
                    "default": "1:1",
                },
                "background": {
                    "type": "string",
                    "enum": ["opaque", "transparent"],
                    "description": "背景模式：默认 opaque（非透明实底/完整背景）。仅在用户明确要求透明背景、免抠图或透明贴纸时才设为 transparent",
                    "default": "opaque",
                },
                "quality": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "成图精细度：默认 high（强烈建议保持 high 以确保线稿、瞳孔细节与文字准确率）",
                    "default": "high",
                },
                "input_fidelity": {
                    "type": "string",
                    "enum": ["high", "low"],
                    "description": "参考图保真度（仅传参考图时生效）：默认 high 强保五官/发饰一致；若需跨画风重绘（如精绘转极简Q版）可设 low",
                    "default": "high",
                },
                "size": {
                    "type": "string",
                    "description": "自定义尺寸（如 1024*1024、1024*1536），不填则按 aspect_ratio 自动匹配",
                },
                "seed": {
                    "type": "integer",
                    "description": "可选随机种子，用于固定构图微调（若当前模型不支持会自动忽略回退）",
                },
                "note": {
                    "type": "string",
                    "description": "顺手记一句这步画了什么",
                },
            },
            "required": ["prompt"],
        },
        handler=art_draw_tool,
    ),
    ToolSpec(
        name="art_asset",
        description=(
            "艺术资产管理：登记、修改、删除或查看某位群友/角色的立绘或三视图参考图。"
            "当群友发来立绘/设定图（如 [img:001]）或刚画好满意的人设图时，可用 action=\"register\" 登记到资产库（会自动持久化保存图片），"
            "并写上简短的语言描述（几个字即可：发色瞳色、长发/短发、发饰、衣着等）。"
            "后续画该人物时即可在 art_draw 的 assets 中直接选用。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "register", "update", "delete"],
                    "description": "list=查看全部资产；register=登记新资产(同名覆盖)；update=修改已有资产；delete=删除资产",
                    "default": "list",
                },
                "key": {
                    "type": "string",
                    "description": "资产唯一标识（如 \"yuki\"、\"master\"、\"池宇健\"、\"池宇健_三视图\"）",
                },
                "owner": {
                    "type": "string",
                    "description": "对应群友昵称或角色名称（如 \"池宇健\"、\"Yuki\"）",
                },
                "reference": {
                    "type": "string",
                    "description": "参考图来源（如会话图片索引 \"[img:001]\" 或本地路径 \"output/...\"），登记时会自动复制到资产目录永久保存",
                },
                "description": {
                    "type": "string",
                    "description": "简短外貌特征描述（几个字即可：发色瞳色、发型、发饰、衣着等）",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "资产标签列表，如 [\"三视图\", \"立绘\"]",
                },
                "aliases": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "人物别名列表（可选，方便用不同称呼检索）",
                },
                "note": {
                    "type": "string",
                    "description": "顺手记一句这步做了什么",
                },
            },
        },
        handler=art_asset_tool,
    ),
    ToolSpec(
        name="art_gacha",
        description=(
            "随机抽一句二次元提示词灵感（来自 Danbooru 标签语料库或内置词条池）。"
            "无参数调用即可。它只给素材、不生成图片：把它改写成完整的场景描述"
            "（角色、动作、服装、场景、光影、构图，别人物的名字一律丢掉），"
            "再传给 art_draw 出图。"
        ),
        parameters={
            "type": "object",
            "properties": {},
        },
        handler=art_gacha_tool,
    ),
    ToolSpec(
        name="art_finish",
        description=(
            "结束艺术创作并退出聚焦模式，收起画板并恢复常规工具空间。"
            "请传入一句简短的 summary 总结刚才画了什么或登记/修改了什么资产，"
            "它会覆盖创作模式中的操作过程记录保留在上下文里。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "简短总结刚才在艺术创作模式下做了什么与结果（会以 USER 总结的形式写入上下文）",
                },
            },
            "required": ["summary"],
        },
        handler=art_finish_tool,
    ),
    ToolSpec(
        name="browser_start",
        description=(
            "打开或接管宿主机 Chrome 浏览器进入浏览器聚焦模式（保留现有登录态）。"
            "进入后返回首屏 720p 标注截图、页面文本和 Top 24 降序交互控件树，并展开 browser_action / browser_finish。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "这次逛网页或操作浏览器想做什么（可选）",
                },
                "url": {
                    "type": "string",
                    "description": "可选，直接要打开的网页 URL；留空则直接查看当前活动标签页",
                },
            },
        },
        handler=browser_start_tool,
    ),
    ToolSpec(
        name="browser_action",
        description=(
            "在浏览器聚焦模式下查看或操控网页（自动等待页面加载与元素稳定后再抽取控件树）。"
            "返回去重后的 [页面文本] 与按重要程度降序编好号的 Top 24 主视觉控件（大控件优先，含按比例保留的 [Bar] 控件）。"
            "控件明确时默认跳过截图以省流提速；控件不明确时自动附 720p 大号红框图，你也可随时传 screenshot=\"high\" 或 action=\"screenshot\" 自己看图。"
            "全程保持 Yuki 可爱灵巧的语气与自主判断，不要写成机械的流水账汇报。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "inspect", "open", "click", "double_click", "hover",
                        "input", "press", "scroll", "back", "forward", "reload",
                        "wait", "tabs", "switch_tab", "new_tab", "close_tab", "screenshot",
                    ],
                    "description": "动作类型，默认 inspect；screenshot 会强制拉取一张高清标注图",
                    "default": "inspect",
                },
                "target": {
                    "type": "string",
                    "description": "控件编号（如 1 或 #1）或视口坐标 \"x,y\"；switch_tab 时填标签页编号或标题关键词",
                },
                "text": {"type": "string", "description": "input 时要输入的文字（支持中文）"},
                "url": {"type": "string", "description": "open / new_tab 时要打开的 URL"},
                "key": {"type": "string", "description": "press 时要按的键名，如 Enter / Escape / Tab / Space / ArrowDown"},
                "direction": {"type": "string", "description": "scroll 方向：up / down / left / right，默认 down"},
                "screenshot": {
                    "type": "string",
                    "enum": ["auto", "blur", "high", "none"],
                    "description": "auto=控件明确不截/不明确附720p图；high=主动看高清图；blur=720p轻量图；none=不截图",
                    "default": "auto",
                },
                "clear": {"type": "boolean", "description": "input 前是否先全选清空输入框，默认 false", "default": False},
                "seconds": {"type": "number", "description": "wait 的秒数"},
                "note": {"type": "string", "description": "顺手记一句这步在看什么或发现了什么"},
                "remember": {"type": "boolean", "description": "是否记入操作过程，默认 true", "default": True},
            },
        },
        handler=browser_action_tool,
    ),
    ToolSpec(
        name="browser_finish",
        description=(
            "结束本轮浏览并退出浏览器聚焦模式，恢复常规工具空间。"
            "请传入一句简短的 summary 总结刚才在浏览器里逛了什么/结果怎样，"
            "然后用 Yuki 平常的可爱灵巧口吻自然回复大家，不要机械复述操作步骤。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "简短总结刚才在浏览器里做了什么与结果（会以 USER 总结写入上下文）",
                },
            },
            "required": ["summary"],
        },
        handler=browser_finish_tool,
    ),
]

# 兼容旧引用，后续新增工具优先维护 TOOL_SPECS。
TOOL_SCHEMAS = [spec.to_schema() for spec in TOOL_SPECS]
TOOL_HANDLERS = {spec.name: spec.handler for spec in TOOL_SPECS}

