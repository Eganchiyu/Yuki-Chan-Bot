# core/config/schema.py
"""YukiV6 配置数据结构定义、多 Provider 队列与表驱动旧属性兼容映射。"""

import os
from dataclasses import dataclass, field, fields
from typing import Any, List, Optional

from utils import BASE_DIR


def config_field(
    default: Any = None,
    *,
    comment: str = "",
    section: str = "",
    **kwargs,
) -> Any:
    """配置项字段工厂函数（携带 comment 与 section 元数据供 YAML 同步使用）。"""
    metadata = kwargs.pop("metadata", {})
    metadata.update({"comment": comment, "section": section})
    return field(default=default, metadata=metadata, **kwargs)


def config_field_factory(
    default_factory,
    *,
    comment: str = "",
    section: str = "",
    **kwargs,
) -> Any:
    """配置项字段工厂函数（用于可变默认值）。"""
    metadata = kwargs.pop("metadata", {})
    metadata.update({"comment": comment, "section": section})
    return field(default_factory=default_factory, metadata=metadata, **kwargs)


# ==================== 子配置数据类 ====================

@dataclass
class LLMProviderConfig:
    """单个 LLM 请求渠道（Provider）配置节点，可在 providers 队列中按序排列多个。"""
    name: str = config_field(
        "default",
        comment="渠道名称（如 main / backup / grok，供 /切换 与 /查询 识别）",
        section="providers",
    )
    base_url: str = config_field(
        "https://api.deepseek.com/v1",
        comment="OpenAI 兼容 API 地址",
        section="providers",
    )
    api_key: str = config_field(
        "",
        comment="该渠道的 API Key（留空则回退使用 api.llm_api_key）",
        section="providers",
    )
    model: str = config_field(
        "deepseek-chat",
        comment="该渠道的模型名称",
        section="providers",
    )
    native_vision: bool = config_field(
        False,
        comment="该渠道模型是否支持原生多模态图片输入",
        section="providers",
    )
    thinking_effort: str = config_field(
        "",
        comment="该渠道模型思考等级（low/medium/high，留空则沿用 model.thinking_effort）",
        section="providers",
    )
    enabled: bool = config_field(
        True,
        comment="是否启用该渠道节点",
        section="providers",
    )


@dataclass
class APIConfig:
    """API 配置"""
    llm_base_url: str = config_field("https://api.deepseek.com/v1", comment="首选 LLM API 地址", section="api")
    backup_base_url: str = config_field("https://api.deepseek.com/v1", comment="备选 LLM API 地址", section="api")
    image_process_url: str = config_field(
        "https://dashscope.aliyuncs.com/compatible-mode/v1", comment="视觉模型 API 地址", section="api"
    )
    llm_api_key: str = config_field("", comment="首选 LLM API Key", section="api")
    backup_api_key: str = config_field("", comment="备选 API Key（留空则使用 llm_api_key）", section="api")
    image_process_api_key: str = config_field("", comment="图像处理 API Key", section="api")
    image_gen_url: str = config_field(
        "https://dashscope.aliyuncs.com/compatible-mode/v1", comment="图像生成 API 地址", section="api"
    )
    image_gen_api_key: str = config_field("", comment="图像生成 API Key", section="api")


@dataclass
class SearchConfig:
    """外部检索服务配置（高德地图 / Tavily 搜索）"""
    amap_api_key: str = config_field(
        "", comment="高德地图 Web服务 Key（https://console.amap.com/dev/key/app）", section="search"
    )
    tavily_api_key: str = config_field(
        "", comment="Tavily 搜索 API Key（https://app.tavily.com/home）", section="search"
    )


@dataclass
class ModelConfig:
    """模型配置"""
    llm: str = config_field("deepseek-chat", comment="主对话模型", section="model")
    backup: str = config_field("deepseek-chat", comment="备用对话模型", section="model")
    vision: str = config_field("qwen3-vl-flash", comment="视觉/多模态模型；如不需要可留空", section="model")
    image_process_url: str = config_field(
        "https://dashscope.aliyuncs.com/compatible-mode/v1", comment="视觉模型 API 地址", section="model"
    )
    image_process_api_key: str = config_field("", comment="视觉/图像处理 API Key", section="model")
    llm_native_vision_enabled: bool = config_field(
        False, comment="主模型原生接收普通图片；表情包仍转写", section="model"
    )
    backup_native_vision_enabled: bool = config_field(
        False, comment="备用模型是否支持原生图片输入", section="model"
    )
    native_vision_max_images: int = config_field(4, comment="单次请求最多附带的普通图片数量", section="model")
    native_vision_history_turns: int = config_field(
        3, comment="原生图片保留的用户消息轮数（含当前轮）", section="model"
    )
    native_vision_max_size: int = config_field(1600, comment="原生图片最长边像素", section="model")
    native_vision_quality: int = config_field(90, comment="原生图片 JPEG 质量（1-100）", section="model")
    vision_download_max_bytes: int = config_field(20971520, comment="单张入站图片最大下载字节数", section="model")
    vision_download_timeout: float = config_field(15.0, comment="入站图片下载超时秒数", section="model")
    image_prefetch_enabled: bool = config_field(
        True, comment="收到消息即后台预取图片（下载+理解），缩短回复延迟", section="model"
    )
    image_prefetch_ttl: float = config_field(
        60.0, comment="图片预取结果缓存秒数（超过则丢弃重取）", section="model"
    )
    image_prefetch_max_entries: int = config_field(64, comment="图片预取缓存条目上限", section="model")
    image_gen: str = config_field("wan2.7-image", comment="图像生成模型", section="model")
    image_gen_url: str = config_field(
        "https://dashscope.aliyuncs.com/compatible-mode/v1", comment="图像生成 API 地址", section="model"
    )
    image_gen_api_key: str = config_field("", comment="图像生成 API Key", section="model")
    thinking_effort: str = config_field(
        "", comment="主模型思考等级（low/medium/high，留空则不传 reasoning_effort）", section="model"
    )
    llm_max_retries: int = config_field(
        3, comment="LLM 请求失败或回复为空时的最大重试次数（不含首次请求）", section="model"
    )


@dataclass
class ConnectionConfig:
    """连接配置"""
    napcat_ws_url: str = config_field("ws://localhost:3001", comment="NapCat WebSocket 地址", section="connection")
    napcat_ws_token: str = config_field("", comment="NapCat WebSocket 认证 Token（留空则不认证）", section="connection")
    max_retries: int = config_field(3, comment="最大重试次数", section="connection")
    qq: int = config_field(0, comment="机器人 QQ 号", section="connection")


@dataclass
class TargetConfig:
    """目标配置"""
    qq: int = config_field(0, comment="私聊目标 QQ 号（主号，同时是默认收件人）", section="target")
    masters: List[int] = config_field_factory(
        list, comment="额外主人 QQ 号列表（与 qq 一并视为主人，如小号）", section="target"
    )
    groups: List[int] = config_field_factory(list, comment="目标群聊 QQ 号列表", section="target")
    whitelist: List[int] = config_field_factory(
        list, comment="白名单 QQ 号列表（可绕过机器人过滤）", section="target"
    )


@dataclass
class DiaryConfig:
    """日记触发配置"""
    idle_seconds: int = config_field(120, comment="空闲多久后触发日记（秒）", section="diary")
    min_turns: int = config_field(15, comment="最小对话轮数阈值", section="diary")
    max_length: int = config_field(50, comment="历史记录超过此条数强制写日记", section="diary")


@dataclass
class RAGConfig:
    """RAG 记忆配置"""
    enabled: bool = config_field(
        True, comment="RAG 日记检索开关（关闭后跳过日记检索，直接使用上下文对话）", section="rag"
    )
    retrieval_top_k: int = config_field(20, comment="检索返回的最大日记条数", section="rag")
    inject_top_k: int = config_field(5, comment="注入聊天上下文的日记条数（RAG 回忆条数）", section="rag")
    keep_last_dialogue: int = config_field(10, comment="保留的近期对话条数（短期记忆）", section="rag")


@dataclass
class EnergyConfig:
    """精力值系统配置"""
    initial: int = config_field(100, comment="初始精力值", section="energy")
    max: float = config_field(100.0, comment="最大精力值上限", section="energy")
    recovery_per_min: float = config_field(0.8, comment="每分钟恢复精力值", section="energy")
    cost_per_reply: int = config_field(6, comment="每次回复消耗精力值", section="energy")
    min_active: int = config_field(25, comment="低于此值进入低活跃状态", section="energy")


@dataclass
class AttentionConfig:
    """注意力/响应配置"""
    sensitivity: float = config_field(0.12, comment="注意力敏感度", section="attention")
    decay_level: float = config_field(0.65, comment="注意力衰减系数", section="attention")
    sigmoid_centre: float = config_field(50.0, comment="Sigmoid 中心点", section="attention")
    sigmoid_alpha: float = config_field(0.08, comment="Sigmoid 陡峭度", section="attention")
    keywords: List[str] = config_field_factory(
        lambda: ["主人", "哥哥"], comment="注意力关键词列表", section="attention"
    )


@dataclass
class PathsConfig:
    """本地文件路径配置"""
    vector_db: str = config_field("./yuki_memory", comment="向量数据库路径", section="paths")
    embed_model: str = config_field("./models/text2vec-base-chinese", comment="嵌入模型路径", section="paths")
    history_file: str = config_field("./data/chat_history.json", comment="历史记录文件路径", section="paths")
    log_file: str = config_field("./data/yuki_log.txt", comment="日志文件路径", section="paths")
    cache_dir: str = config_field("./data", comment="缓存目录路径", section="paths")
    cache_file: str = config_field("./data/meme_cache.json", comment="缓存文件路径", section="paths")
    ncm_cookie_file: str = config_field(
        "~/.cache/ncm_cookie.txt", comment="网易云音乐登录 Cookie 文件路径（浏览器 F12 复制，抓歌用）", section="paths"
    )
    ncm_download_dir: str = config_field("./output/ncm", comment="网易云音乐下载目录", section="paths")


@dataclass
class RequestTimeoutConfig:
    """请求超时配置"""
    total: int = config_field(60, comment="总超时时间（秒）", section="timing")
    connect: int = config_field(10, comment="连接超时时间（秒）", section="timing")
    sock_read: int = config_field(30, comment="读取超时时间（秒）", section="timing")


@dataclass
class TimingConfig:
    """时间/超时配置"""
    debounce_time: int = config_field(32, comment="防抖时间（秒）", section="timing")
    tool_call_delay_seconds: float = config_field(
        1.2, comment="工具调用前等待时间（秒），用于降低连续工具调用的机械感", section="timing"
    )
    request_timeout: RequestTimeoutConfig = config_field_factory(
        RequestTimeoutConfig, comment="请求超时配置", section="timing"
    )


@dataclass
class ToolsConfig:
    """主模型亲手操作类工具配置（手机 ADB / 艺术创作 / 浏览器）"""
    max_rounds: int = config_field(8, comment="单轮对话最多工具调用轮次（手机连招需要多步）", section="tools")
    prune_idle_turns: int = config_field(
        2, comment="连续多少轮不调用工具后，自动折叠历史里的工具原始输出", section="tools"
    )
    adb_path: str = config_field("adb", comment="adb 可执行文件路径（不在 PATH 里时填绝对路径）", section="tools")
    adb_serial: str = config_field("", comment="adb 设备序列号；留空使用唯一的已连接设备", section="tools")
    phone_wait_seconds: float = config_field(1.0, comment="手机操作后等待界面刷新的时间（秒）", section="tools")
    phone_max_nodes: int = config_field(60, comment="控件树最多返回的节点数", section="tools")
    phone_screenshot_max_width: int = config_field(
        720, comment="手机截图回传模型时缩放到的最大宽度（像素）", section="tools"
    )
    phone_screenshot_quality: int = config_field(70, comment="手机截图 JPEG 质量（1-100）", section="tools")
    phone_expect_timeout: float = config_field(
        3.0, comment="组合技回放时每步等待界面达到预期的秒数", section="tools"
    )
    phone_focus_idle_turns: int = config_field(
        5, comment="手机聚焦模式连续未操作手机的轮数上限（大于该轮数自动退出并注入总结）", section="tools"
    )
    phone_focus_max_rounds: int = config_field(
        100, comment="手机聚焦模式下单轮对话允许的最大工具调用轮次", section="tools"
    )
    art_focus_idle_turns: int = config_field(
        5, comment="艺术创作聚焦模式连续未操作的轮数上限（大于该轮数自动退出并注入总结）", section="tools"
    )
    art_focus_max_rounds: int = config_field(
        30, comment="艺术创作聚焦模式下单轮对话允许的最大工具调用轮次", section="tools"
    )
    browser_cdp_url: str = config_field(
        "http://127.0.0.1:9222", comment="宿主机 Chrome CDP 调试地址（--remote-debugging-port=9222）", section="tools"
    )
    browser_max_nodes: int = config_field(24, comment="浏览器交互树最多返回的控件数量", section="tools")
    browser_bar_quota: int = config_field(
        5, comment="Top 控件中按比例预留给顶栏/侧栏/底栏重要控件的配额", section="tools"
    )
    browser_wait_timeout: float = config_field(
        5.0, comment="浏览器每次操作后等待页面加载与元素稳定的最大秒数", section="tools"
    )
    browser_settle_ms: int = config_field(280, comment="页面 DOM 与网络静默判定窗口（毫秒）", section="tools")
    browser_screenshot_max_width: int = config_field(
        1280, comment="浏览器默认轻量截图宽度（像素，约 720p，不做高斯模糊）", section="tools"
    )
    browser_screenshot_quality: int = config_field(
        55, comment="浏览器默认轻量截图 JPEG 质量（1-100）", section="tools"
    )
    browser_screenshot_high_width: int = config_field(
        1600, comment="AI 主动调用高清截图时的最大宽度（像素）", section="tools"
    )
    browser_screenshot_high_quality: int = config_field(
        88, comment="AI 主动调用高清截图的 JPEG 质量（1-100）", section="tools"
    )
    browser_focus_idle_turns: int = config_field(
        5, comment="浏览器聚焦模式连续未操作浏览器的轮数上限（大于该轮数自动退出并注入总结）", section="tools"
    )
    browser_focus_max_rounds: int = config_field(
        60, comment="浏览器聚焦模式下单轮对话允许的最大工具调用轮次", section="tools"
    )
    art_gacha_zako_enabled: bool = config_field(
        True,
        comment="提示词抽卡是否启用外部语料库 data/zako（Zako-Prompt-Tools，缺失时自动回落原有抽卡）",
        section="tools",
    )
    art_gacha_zako_share: float = config_field(
        0.9, comment="auto 抽卡时命中外部语料库的概率（0~1，语料缺失或关闭时忽略）", section="tools"
    )
    art_gacha_zako_ratings: str = config_field(
        "G,S,Q", comment="外部语料库抽样允许的分级（逗号分隔，可选 G/S/Q/E）", section="tools"
    )
    art_gacha_zako_topic: str = config_field(
        "", comment="外部语料库抽样限定的主题名（留空=全部主题）", section="tools"
    )
    art_gacha_zako_exclude_topics: str = config_field(
        "高点赞TAG",
        comment="外部语料库抽样要排除的主题（逗号分隔；高点赞TAG 是整帖标签堆，几乎全是他人角色名）",
        section="tools",
    )


@dataclass
class AutonomousConfig:
    """自主沙盒（自主轮次 / 多主循环模式）配置"""
    enabled: bool = config_field(
        False, comment="自主轮次总开关，默认关；关时 /深思 直接拒绝", section="autonomous"
    )
    enabled_groups: List[str] = config_field_factory(
        list, comment="允许自主轮的群白名单，默认空 = 一个都不开", section="autonomous"
    )
    auto_trigger_enabled: bool = config_field(
        False, comment="冷场自动触发自主轮（只对白名单群生效）", section="autonomous"
    )
    min_group_idle_minutes: int = config_field(
        45, comment="群聊静默多少分钟后才允许自动触发", section="autonomous"
    )
    min_energy: float = config_field(0.60, comment="触发自主轮所需的最低精力值", section="autonomous")
    quiet_hours: List[int] = config_field_factory(
        lambda: [1, 7], comment="深夜禁触发区间 [起始小时, 结束小时)，跨零点写 [22, 6]", section="autonomous"
    )
    cooldown_minutes: int = config_field(
        120, comment="两次自动自主轮之间的最小间隔（分钟）", section="autonomous"
    )
    daily_max_runs: int = config_field(
        3, comment="每日自动触发上限（持久化，重启不清零）", section="autonomous"
    )
    max_wall_seconds: int = config_field(
        900, comment="非聊天模式单次最长占用秒数，超时强制暂停并全面放行", section="autonomous"
    )
    debate_max_rounds: int = config_field(32, comment="debate 模式（双念头交锋）最大轮数", section="autonomous")
    debate_max_tokens: int = config_field(4096, comment="debate 每步输出上限 token", section="autonomous")
    debate_retrieval_steps: int = config_field(
        5, comment="交锋前多少步可用检索工具（日记/群聊截屏/工作档案），之后收起只留投票", section="autonomous"
    )
    debate_compress_every: int = config_field(
        8, comment="debate 每多少步把旧交锋压成锚点卡", section="autonomous"
    )
    workshop_max_tool_calls: int = config_field(
        60, comment="workshop 模式单次最大工具调用次数", section="autonomous"
    )
    workshop_max_tokens: int = config_field(4096, comment="workshop 每步输出上限 token", section="autonomous")
    reflection_max_tokens: int = config_field(
        4096, comment="复盘（conclude_reflection）每步输出上限 token", section="autonomous"
    )
    zero_tool_max_retries: int = config_field(
        2, comment="零工具返回自动追问的最大容忍次数（防死循环）", section="autonomous"
    )
    step_timeout_seconds: int = config_field(
        180, comment="单步（一次 LLM + 该批工具）超时熔断秒数", section="autonomous"
    )
    catchup_enabled: bool = config_field(
        True, comment="回到群聊时是否注入「独处期间群里发生了什么」补台摘要", section="autonomous"
    )
    catchup_max_messages: int = config_field(80, comment="补台摘要最多纳入的消息条数", section="autonomous")
    catchup_summarize_threshold: int = config_field(
        12, comment="缺席消息超过该条数时改用 sub-LLM 摘要", section="autonomous"
    )
    digest_model: str = config_field("", comment="补台/压缩摘要模型，留空用主模型", section="autonomous")
    diary_local_ratio: float = config_field(0.7, comment="日记检索本群占比（软比例）", section="autonomous")
    daily_memory_ttl_hours: int = config_field(18, comment="今日工作记忆有效期（小时）", section="autonomous")
    high_spirits_turns: int = config_field(
        1, comment="回到群聊后「心情高涨」额外补发条数（1 = 回群第一句 + 补 1 句，共 2 连发）", section="autonomous"
    )
    high_spirits_minutes: int = config_field(
        25, comment="心情高涨状态持续分钟数（回复欲望加成有效期）", section="autonomous"
    )
    high_spirits_desire_bonus: float = config_field(
        0.45, comment="心情高涨时的回复欲望加成", section="autonomous"
    )
    high_spirits_followup_window: int = config_field(
        30, comment="两次连发之间的最小空隙秒数（30~60 为宜；到期无人接话才补第二句）", section="autonomous"
    )


@dataclass
class GitHubMonitorRepoConfig:
    """GitHub 监控仓库配置"""
    owner: str = config_field("", comment="仓库所有者", section="github_monitor")
    repo: str = config_field("", comment="仓库名", section="github_monitor")
    token: str = config_field(
        "", comment="该仓库专用的 GitHub PAT（留空则使用 github_token）", section="github_monitor"
    )
    poll_interval: int = config_field(300, comment="轮询间隔（秒）", section="github_monitor")
    chat_ids: List[str] = config_field_factory(
        list, comment="推送到的群号/QQ号列表（留空则使用 default_chat_ids）", section="github_monitor"
    )
    modes: List[str] = config_field_factory(
        lambda: ["group"], comment="推送模式（group / private）", section="github_monitor"
    )


@dataclass
class GitHubMonitorConfig:
    """GitHub 仓库监控配置"""
    enabled: bool = config_field(False, comment="是否启用 GitHub 仓库监控", section="github_monitor")
    github_token: str = config_field(
        "", comment="GitHub PAT（用于 Events API 认证，提高速率限制）", section="github_monitor"
    )
    default_chat_ids: List[str] = config_field_factory(
        list, comment="默认推送群号列表（仓库未单独配置 chat_id 时使用）", section="github_monitor"
    )
    poll_interval: int = config_field(300, comment="默认轮询间隔（秒）", section="github_monitor")
    repos: List[GitHubMonitorRepoConfig] = config_field_factory(
        list, comment="监控仓库列表", section="github_monitor"
    )


@dataclass
class QZoneMonitorConfig:
    """QQ 空间社交监控配置"""
    enabled: bool = config_field(False, comment="是否启用 QQ 空间社交监控", section="qzone_monitor")


# ==================== 表驱动旧属性兼容映射 ====================

_LEGACY_ALIASES: dict[str, tuple[str, ...]] = {
    "LLM_BASE_URL": ("api", "llm_base_url"),
    "BACKUP_BASE_URL": ("api", "backup_base_url"),
    "IMAGE_PROCESS_API_URL": ("api", "image_process_url"),
    "LLM_API_KEY": ("api", "llm_api_key"),
    "BACKUP_API_KEY": ("api", "backup_api_key"),
    "IMAGE_PROCESS_API_KEY": ("api", "image_process_api_key"),
    "IMAGE_GEN_URL": ("api", "image_gen_url"),
    "IMAGE_GEN_API_KEY": ("api", "image_gen_api_key"),
    "AMAP_API_KEY": ("search", "amap_api_key"),
    "TAVILY_API_KEY": ("search", "tavily_api_key"),
    "LLM_MODEL": ("model", "llm"),
    "BACKUP_MODEL": ("model", "backup"),
    "LLM_NATIVE_VISION_ENABLED": ("model", "llm_native_vision_enabled"),
    "BACKUP_NATIVE_VISION_ENABLED": ("model", "backup_native_vision_enabled"),
    "IMAGE_PREFETCH_ENABLED": ("model", "image_prefetch_enabled"),
    "IMAGE_PREFETCH_TTL": ("model", "image_prefetch_ttl"),
    "IMAGE_PREFETCH_MAX_ENTRIES": ("model", "image_prefetch_max_entries"),
    "VISION_MODEL": ("model", "vision"),
    "IMAGE_GEN_MODEL": ("model", "image_gen"),
    "NAPCAT_WS_URL": ("connection", "napcat_ws_url"),
    "NAPCAT_WS_TOKEN": ("connection", "napcat_ws_token"),
    "MAX_RETRIES": ("connection", "max_retries"),
    "INITIAL_ENERGY": ("energy", "initial"),
    "MAX_ENERGY": ("energy", "max"),
    "RECOVERY_PER_MIN": ("energy", "recovery_per_min"),
    "COST_PER_REPLY": ("energy", "cost_per_reply"),
    "MIN_ACTIVE_ENERGY": ("energy", "min_active"),
    "SENSITIVITY": ("attention", "sensitivity"),
    "DECAY_LEVEL": ("attention", "decay_level"),
    "SIGMOID_CENTRE": ("attention", "sigmoid_centre"),
    "SIGMOID_ALPHA": ("attention", "sigmoid_alpha"),
    "DIARY_IDLE_SECONDS": ("diary", "idle_seconds"),
    "DIARY_MIN_TURNS": ("diary", "min_turns"),
    "DIARY_MAX_LENGTH": ("diary", "max_length"),
    "KEEP_LAST_DIALOGUE": ("rag", "keep_last_dialogue"),
    "RAG_ENABLED": ("rag", "enabled"),
    "RETRIEVAL_TOP_K": ("rag", "retrieval_top_k"),
    "INJECT_TOP_K": ("rag", "inject_top_k"),
    "DEBOUNCE_TIME": ("timing", "debounce_time"),
    "MAX_MESSAGE_LENGTH": ("max_message_length",),
    "MAX_CONCURRENT_MEME": ("max_concurrent_meme",),
    "DEBUG": ("debug",),
}

_PATH_DEFAULTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "VECTOR_DB_PATH": ("vector_db", ("yuki_memory",)),
    "EMBED_MODEL": ("embed_model", ("models", "text2vec-base-chinese")),
    "HISTORY_FILE": ("history_file", ("data", "chat_history.json")),
    "LOG_FILE": ("log_file", ("data", "yuki_log.txt")),
    "CACHE_DIR": ("cache_dir", ("data",)),
}


def _coerce_provider(item: Any, fallback_key: str = "", fallback_thinking: str = "") -> LLMProviderConfig:
    if isinstance(item, LLMProviderConfig):
        return LLMProviderConfig(
            name=item.name or "provider",
            base_url=item.base_url or "https://api.deepseek.com/v1",
            api_key=item.api_key or fallback_key,
            model=item.model or "deepseek-chat",
            native_vision=bool(item.native_vision),
            thinking_effort=str(item.thinking_effort or fallback_thinking or "").strip(),
            enabled=bool(item.enabled),
        )
    if isinstance(item, dict):
        return LLMProviderConfig(
            name=str(item.get("name") or item.get("model") or "provider"),
            base_url=str(item.get("base_url") or "https://api.deepseek.com/v1"),
            api_key=str(item.get("api_key") or fallback_key or ""),
            model=str(item.get("model") or "deepseek-chat"),
            native_vision=bool(item.get("native_vision", False)),
            thinking_effort=str(item.get("thinking_effort") or fallback_thinking or "").strip(),
            enabled=bool(item.get("enabled", True)),
        )
    raise TypeError(f"Unsupported provider item: {type(item)!r}")


# ==================== 主配置类 ====================

@dataclass
class Config:
    """配置中心 - 启动时从 config.yaml 一次性加载。"""
    robot_name: str = config_field("yuki", comment="机器人名称", section="identity")
    master_name: str = config_field("主人", comment="主人称呼", section="identity")
    max_message_length: int = config_field(150, comment="单条消息最大长度，防止 token 炸弹", section="security")

    api: APIConfig = config_field_factory(APIConfig, comment="API 配置", section="api")
    model: ModelConfig = config_field_factory(ModelConfig, comment="模型配置", section="model")
    providers: List[LLMProviderConfig] = config_field_factory(
        list,
        comment="多 Provider 故障转移队列（按顺序依次尝试；留空时自动由 api+model 主备合成）",
        section="providers",
    )
    connection: ConnectionConfig = config_field_factory(ConnectionConfig, comment="连接配置", section="connection")
    target: TargetConfig = config_field_factory(TargetConfig, comment="目标配置", section="target")
    diary: DiaryConfig = config_field_factory(DiaryConfig, comment="日记触发配置", section="diary")
    search: SearchConfig = config_field_factory(SearchConfig, comment="外部检索服务配置", section="search")
    rag: RAGConfig = config_field_factory(RAGConfig, comment="RAG 记忆配置", section="rag")
    energy: EnergyConfig = config_field_factory(EnergyConfig, comment="精力值系统配置", section="energy")
    attention: AttentionConfig = config_field_factory(AttentionConfig, comment="注意力/响应配置", section="attention")
    paths: PathsConfig = config_field_factory(PathsConfig, comment="本地文件路径配置", section="paths")
    timing: TimingConfig = config_field_factory(TimingConfig, comment="时间/超时配置", section="timing")
    tools: ToolsConfig = config_field_factory(ToolsConfig, comment="主模型亲手操作类工具配置", section="tools")
    autonomous: AutonomousConfig = config_field_factory(
        AutonomousConfig, comment="自主沙盒（自主轮次 / 多主循环）配置", section="autonomous"
    )
    github_monitor: GitHubMonitorConfig = config_field_factory(
        GitHubMonitorConfig, comment="GitHub 仓库监控配置", section="github_monitor"
    )
    qzone_monitor: QZoneMonitorConfig = config_field_factory(
        QZoneMonitorConfig, comment="QQ 空间社交监控配置", section="qzone_monitor"
    )

    max_concurrent_meme: int = config_field(3, comment="最大并发处理表情包数量", section="debug")
    debug: bool = config_field(True, comment="调试模式开关", section="debug")

    def __post_init__(self) -> None:
        self._sync_media_api_between_api_and_model()
        if self.providers:
            self._sync_api_model_from_providers()
        self._initial_api_model_sig = self._api_model_sig()

    def _sync_media_api_between_api_and_model(self) -> None:
        """支持在 model 段直接配置视觉与生图 URL/Key（删除顶层 api 段时仍双向兼容 cfg.api.*）。"""
        default_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        if self.model.image_process_url != default_url or not self.api.image_process_url:
            self.api.image_process_url = self.model.image_process_url
        elif self.api.image_process_url:
            self.model.image_process_url = self.api.image_process_url

        if self.model.image_process_api_key:
            self.api.image_process_api_key = self.model.image_process_api_key
        elif self.api.image_process_api_key:
            self.model.image_process_api_key = self.api.image_process_api_key

        if self.model.image_gen_url != default_url or not self.api.image_gen_url:
            self.api.image_gen_url = self.model.image_gen_url
        elif self.api.image_gen_url:
            self.model.image_gen_url = self.api.image_gen_url

        if self.model.image_gen_api_key:
            self.api.image_gen_api_key = self.model.image_gen_api_key
        elif self.api.image_gen_api_key:
            self.model.image_gen_api_key = self.api.image_gen_api_key

    def _api_model_sig(self) -> tuple:
        return (
            self.api.llm_base_url,
            self.api.backup_base_url,
            self.api.llm_api_key,
            self.api.backup_api_key,
            self.model.llm,
            self.model.backup,
            self.model.llm_native_vision_enabled,
            self.model.backup_native_vision_enabled,
        )

    def _providers_api_model_sig(self) -> tuple | None:
        if not self.providers:
            return None
        fallback_key = self.api.llm_api_key
        fallback_thinking = str(self.model.thinking_effort or "").strip()
        normalized = [
            _coerce_provider(p, fallback_key=fallback_key, fallback_thinking=fallback_thinking)
            for p in self.providers
        ]
        routes = [p for p in normalized if p.enabled]
        if not routes:
            return None
        head = routes[0]
        second = routes[1] if len(routes) >= 2 else head
        return (
            head.base_url,
            second.base_url,
            head.api_key or self.api.llm_api_key,
            second.api_key,
            head.model,
            second.model,
            head.native_vision,
            second.native_vision,
        )

    def _use_providers_queue(self) -> bool:
        """无副作用判定是否启用 providers 队列；当旧单测直接 monkeypatch 了 api/model 字段时自动退回主备模式。"""
        if not self.providers:
            return False
        cur_sig = self._api_model_sig()
        if cur_sig == self._providers_api_model_sig():
            return True
        if cur_sig == getattr(self, "_initial_api_model_sig", None):
            return True
        return False

    # ==================== 多 Provider 故障转移队列 ====================

    def get_llm_routes(self) -> List[LLMProviderConfig]:
        """获取当前有序的 LLM Provider 故障转移队列。

        - 若 `providers` 配置了至少一个 enabled 节点（且未被旧单测直接覆写 api/model），按队列顺序返回；
        - 否则自动由 `api` + `model` 的主/备字段合成为 2 节点队列（100% 兼容现有配置与旧单测）。
        """
        fallback_key = self.api.llm_api_key
        fallback_thinking = str(self.model.thinking_effort or "").strip()
        if self._use_providers_queue():
            normalized = [
                _coerce_provider(p, fallback_key=fallback_key, fallback_thinking=fallback_thinking)
                for p in self.providers
            ]
            active = [p for p in normalized if p.enabled]
            if active:
                return active

        primary = LLMProviderConfig(
            name="主线",
            base_url=self.api.llm_base_url,
            api_key=self.api.llm_api_key,
            model=self.model.llm,
            native_vision=self.model.llm_native_vision_enabled,
            thinking_effort=fallback_thinking,
            enabled=True,
        )
        backup = LLMProviderConfig(
            name="备用",
            base_url=self.api.backup_base_url,
            api_key=self.api.backup_api_key or self.api.llm_api_key,
            model=self.model.backup,
            native_vision=self.model.backup_native_vision_enabled,
            thinking_effort=fallback_thinking,
            enabled=True,
        )
        return [primary, backup]

    def _sync_api_model_from_providers(self) -> None:
        """当使用显式 providers 队列时，把队首/次席同步回 api 与 model 字段，保持下游访问一致。"""
        fallback_key = self.api.llm_api_key
        fallback_thinking = str(self.model.thinking_effort or "").strip()
        normalized = [
            _coerce_provider(p, fallback_key=fallback_key, fallback_thinking=fallback_thinking)
            for p in (self.providers or [])
        ]
        routes = [p for p in normalized if p.enabled]
        if not routes:
            return
        head = routes[0]
        self.api.llm_base_url = head.base_url
        self.api.llm_api_key = head.api_key or self.api.llm_api_key
        self.model.llm = head.model
        self.model.llm_native_vision_enabled = head.native_vision
        if len(routes) >= 2:
            second = routes[1]
            self.api.backup_base_url = second.base_url
            self.api.backup_api_key = second.api_key
            self.model.backup = second.model
            self.model.backup_native_vision_enabled = second.native_vision
        self._synced_providers_id = id(self.providers)
        self._synced_api_model_sig = self._api_model_sig()

    def swap_llm_route(self, target: Optional[str] = None) -> bool:
        """主备/多渠道切换（QQ `/切换 [目标]`），返回切换后是否处于非初始首选线路。"""
        if self._use_providers_queue() and len(self.providers) >= 2:
            normalized = [
                _coerce_provider(p, fallback_key=self.api.llm_api_key, fallback_thinking=self.model.thinking_effort)
                for p in self.providers
            ]
            enabled_indices = [i for i, p in enumerate(normalized) if p.enabled]
            target_str = str(target or "").strip()
            if target_str:
                matched_idx = None
                if target_str.isdigit():
                    idx = int(target_str) - 1
                    if 0 <= idx < len(normalized):
                        matched_idx = idx
                if matched_idx is None:
                    tl = target_str.lower()
                    for i, p in enumerate(normalized):
                        if tl == p.name.lower() or tl in p.name.lower() or tl in p.model.lower():
                            matched_idx = i
                            break
                if matched_idx is None:
                    raise ValueError(f"未找到匹配的渠道: {target_str}")
                normalized[matched_idx].enabled = True
                normalized = [normalized[matched_idx]] + normalized[:matched_idx] + normalized[matched_idx + 1 :]
            elif len(enabled_indices) >= 2:
                first_en = enabled_indices[0]
                normalized = normalized[:first_en] + normalized[first_en + 1 :] + [normalized[first_en]]
            else:
                normalized = normalized[1:] + normalized[:1]
            self.providers = normalized
            self._sync_api_model_from_providers()
            swapped = bool(getattr(self, "_llm_route_swapped", False))
            self._llm_route_swapped = not swapped
            return self._llm_route_swapped

        api, model = self.api, self.model
        api.llm_base_url, api.backup_base_url = api.backup_base_url, api.llm_base_url
        api.llm_api_key, api.backup_api_key = api.backup_api_key, api.llm_api_key
        if not api.llm_api_key:
            api.llm_api_key = api.backup_api_key
        model.llm, model.backup = model.backup, model.llm
        model.llm_native_vision_enabled, model.backup_native_vision_enabled = (
            model.backup_native_vision_enabled,
            model.llm_native_vision_enabled,
        )
        swapped = bool(getattr(self, "_llm_route_swapped", False))
        self._llm_route_swapped = not swapped
        return self._llm_route_swapped

    # ==================== 真计算属性 ====================

    @property
    def ROBOT_NAME(self) -> str:
        return (self.robot_name or "yuki").lower()

    @property
    def MASTER_NAME(self) -> str:
        return self.master_name or "主人"

    @property
    def LLM_MAX_RETRIES(self) -> int:
        return int(self.model.llm_max_retries)

    @property
    def THINKING_EFFORT(self) -> str:
        if self.providers:
            routes = self.get_llm_routes()
            if routes and routes[0].thinking_effort:
                return str(routes[0].thinking_effort).strip()
        return str(self.model.thinking_effort or "").strip()

    @property
    def SELF_QQ(self) -> int:
        return int(self.connection.qq)

    @property
    def TARGET_QQ(self) -> int:
        return int(self.target.qq)

    @property
    def MASTER_QQS(self) -> List[int]:
        result: List[int] = []
        for raw in [self.target.qq, *(self.target.masters or [])]:
            try:
                qq = int(raw)
            except (TypeError, ValueError):
                continue
            if qq > 0 and qq not in result:
                result.append(qq)
        return result

    def is_master_qq(self, user_id) -> bool:
        try:
            return int(user_id) in self.MASTER_QQS
        except (TypeError, ValueError):
            return False

    @property
    def REQUEST_TIMEOUT(self):
        import aiohttp

        tc = self.timing.request_timeout
        return aiohttp.ClientTimeout(total=tc.total, connect=tc.connect, sock_read=tc.sock_read)

    @property
    def TARGET_GROUPS(self) -> List[int]:
        return [int(g) for g in self.target.groups]

    @property
    def TARGET_WHITELIST(self) -> List[int]:
        return [int(q) for q in self.target.whitelist]

    @property
    def keywords(self) -> List[str]:
        base = list(self.attention.keywords)
        robot = self.ROBOT_NAME
        if robot and robot not in base:
            base.append(robot)
        return base

    # ==================== 路径解析与表驱动 __getattr__ ====================

    @staticmethod
    def _resolve_path(p: str) -> str:
        if p and isinstance(p, str) and p.startswith("./"):
            return os.path.join(BASE_DIR, p[2:])
        return p

    @property
    def CACHE_FILE(self) -> str:
        return self._resolve_path(self.paths.cache_file) or os.path.join(self.CACHE_DIR, "meme_cache.json")

    def __getattr__(self, name: str) -> Any:
        # 1. 路径属性映射
        if name in _PATH_DEFAULTS:
            attr_name, fallback_parts = _PATH_DEFAULTS[name]
            paths_obj = object.__getattribute__(self, "paths")
            raw_val = getattr(paths_obj, attr_name, "")
            return self._resolve_path(raw_val) or os.path.join(BASE_DIR, *fallback_parts)

        # 2. 若显式配置了 providers 队列（且未被旧单测直接覆写 api/model），优先从队列第 1/2 项读取
        if name in {
            "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_NATIVE_VISION_ENABLED",
            "BACKUP_BASE_URL", "BACKUP_API_KEY", "BACKUP_MODEL", "BACKUP_NATIVE_VISION_ENABLED",
        }:
            if self._use_providers_queue():
                routes = self.get_llm_routes()
                if routes:
                    head = routes[0]
                    second = routes[1] if len(routes) >= 2 else head
                    mapping = {
                        "LLM_BASE_URL": head.base_url,
                        "LLM_API_KEY": head.api_key,
                        "LLM_MODEL": head.model,
                        "LLM_NATIVE_VISION_ENABLED": head.native_vision,
                        "BACKUP_BASE_URL": second.base_url,
                        "BACKUP_API_KEY": second.api_key,
                        "BACKUP_MODEL": second.model,
                        "BACKUP_NATIVE_VISION_ENABLED": second.native_vision,
                    }
                    return mapping[name]

        # 3. 声明式旧版大写属性别名表
        if name in _LEGACY_ALIASES:
            cur: Any = self
            for part in _LEGACY_ALIASES[name]:
                cur = object.__getattribute__(cur, part) if cur is self else getattr(cur, part)
            return cur

        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    # ==================== 兼容旧版 API ====================

    def get(self, *keys, default=None):
        """显式读取嵌套配置（兼容旧版 API）：cfg.get("api", "llm_api_key", default="")"""
        d: Any = self.__dict__
        for k in keys:
            if isinstance(d, dict) and k in d:
                d = d[k]
            elif hasattr(d, k):
                d = getattr(d, k)
            else:
                return default
        return d

    def reload(self):
        """兼容旧版 reload() - 重新加载配置文件"""
        import config as top_config
        from core.config.loader import load_config

        top_config.cfg = load_config()


def _build_attr_map() -> dict:
    """从 dataclass 的 field metadata 自动构建 _ATTR_MAP。"""
    attr_map = {}

    def _collect_fields(cls, prefix=()):
        for f in fields(cls):
            field_path = prefix + (f.name,)
            metadata = f.metadata or {}
            comment = metadata.get("comment", "")
            field_type = f.type
            if hasattr(field_type, "__dataclass_fields__"):
                _collect_fields(field_type, field_path)
            else:
                attr_name = "_".join(field_path).upper()
                default_val = f.default if f.default is not f.default_factory else f.default_factory()
                attr_map[attr_name] = (field_path, default_val, comment)

    _collect_fields(Config)
    return attr_map


_ATTR_MAP = _build_attr_map()

_SECTION_HEADERS = {
    "identity": "# ================= 机器人身份 =================",
    "security": "# ================= 安全配置 =================",
    "api": "# ================= API 配置 =================",
    "providers": "# ================= 多 Provider 故障转移队列 =================",
    "search": "# ================= 外部检索服务配置（高德地图 / Tavily） =================",
    "model": "# ================= 模型配置 =================",
    "connection": "# ================= 连接配置 =================",
    "target": "# ================= 目标配置 =================",
    "diary": "# ================= 日记触发配置 =================",
    "rag": "# ================= RAG 记忆配置 =================",
    "paths": "# ================= 本地文件路径配置 =================\n# 均为相对项目根目录的路径",
    "timing": "# ================= 时间/超时配置 =================",
    "tools": "# ================= 亲手操作类工具（手机 ADB） =================",
    "energy": "# ================= 精力值系统配置 =================",
    "attention": "# ================= 注意力/响应配置 =================",
    "debug": "# ================= 调试配置 =================",
    "autonomous": "# ================= 自主沙盒（自主轮次 / 多主循环） =================",
}
