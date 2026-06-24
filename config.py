# config.py
"""
YukiV6 配置系统

设计原则：
1. 使用 dataclass 定义配置结构 - 类型安全、IDE 友好
2. 分层配置 - 默认值 → YAML 文件
3. 简化路径解析 - 统一处理相对路径
4. 启动时一次性加载 - 无热重载
5. 向后兼容 - cfg.xxx 访问方式不变

增强特性：
- 单一数据源：只在 dataclass 中定义，yaml 自动同步
- 配置项注释：通过 field metadata 添加注释
- 自动同步：运行 python config.py sync 自动生成/更新 yaml
"""

import os
from dataclasses import dataclass, field, fields
from typing import List, Optional, Any

import yaml

from utils import BASE_DIR


def config_field(
    default: Any = None,
    *,
    comment: str = "",
    section: str = "",
    **kwargs
) -> Any:
    """
    配置项字段工厂函数

    Args:
        default: 默认值
        comment: 配置项注释
        section: 所属分组（用于 yaml 生成）
        **kwargs: 其他 dataclass field 参数

    Returns:
        dataclass field

    示例：
        @dataclass
        class MyConfig:
            name: str = config_field("default", comment="名称配置")
    """
    metadata = kwargs.pop("metadata", {})
    metadata.update({
        "comment": comment,
        "section": section,
    })
    return field(default=default, metadata=metadata, **kwargs)


def config_field_factory(
    default_factory,
    *,
    comment: str = "",
    section: str = "",
    **kwargs
) -> Any:
    """
    配置项字段工厂函数（用于可变默认值）

    Args:
        default_factory: 默认值工厂函数
        comment: 配置项注释
        section: 所属分组
        **kwargs: 其他 dataclass field 参数

    Returns:
        dataclass field
    """
    metadata = kwargs.pop("metadata", {})
    metadata.update({
        "comment": comment,
        "section": section,
    })
    return field(default_factory=default_factory, metadata=metadata, **kwargs)


# ==================== 配置数据类 ====================

@dataclass
class APIConfig:
    """API 配置"""
    llm_base_url: str = config_field(
        "https://api.deepseek.com/v1",
        comment="首选 LLM API 地址",
        section="api"
    )
    backup_base_url: str = config_field(
        "https://api.deepseek.com/v1",
        comment="备选 LLM API 地址",
        section="api"
    )
    image_process_url: str = config_field(
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        comment="视觉模型 API 地址",
        section="api"
    )
    llm_api_key: str = config_field(
        "",
        comment="首选 LLM API Key",
        section="api"
    )
    backup_api_key: str = config_field(
        "",
        comment="备选 API Key（留空则使用 llm_api_key）",
        section="api"
    )
    image_process_api_key: str = config_field(
        "",
        comment="图像处理 API Key",
        section="api"
    )


@dataclass
class ModelConfig:
    """模型配置"""
    llm: str = config_field(
        "deepseek-chat",
        comment="主对话模型",
        section="model"
    )
    backup: str = config_field(
        "deepseek-chat",
        comment="备用对话模型",
        section="model"
    )
    vision: str = config_field(
        "qwen3-vl-flash",
        comment="视觉/多模态模型；如不需要可留空",
        section="model"
    )
    disable_thinking: bool = config_field(
        True,
        comment="默认关闭模型的 thinking/reasoning 输出",
        section="model"
    )


@dataclass
class ConnectionConfig:
    """连接配置"""
    napcat_ws_url: str = config_field(
        "ws://localhost:3001",
        comment="NapCat WebSocket 地址",
        section="connection"
    )
    napcat_ws_token: str = config_field(
        "",
        comment="NapCat WebSocket 认证 Token（留空则不认证）",
        section="connection"
    )
    max_retries: int = config_field(
        3,
        comment="最大重试次数",
        section="connection"
    )


@dataclass
class TargetConfig:
    """目标配置"""
    qq: int = config_field(
        0,
        comment="私聊目标 QQ 号",
        section="target"
    )
    groups: List[int] = config_field_factory(
        list,
        comment="目标群聊 QQ 号列表",
        section="target"
    )
    whitelist: List[int] = config_field_factory(
        list,
        comment="白名单 QQ 号列表（可绕过机器人过滤）",
        section="target"
    )


@dataclass
class DiaryConfig:
    """日记触发配置"""
    idle_seconds: int = config_field(
        120,
        comment="空闲多久后触发日记（秒）",
        section="diary"
    )
    min_turns: int = config_field(
        15,
        comment="最小对话轮数阈值",
        section="diary"
    )
    max_length: int = config_field(
        50,
        comment="历史记录超过此条数强制写日记",
        section="diary"
    )


@dataclass
class RAGConfig:
    """RAG 记忆配置"""
    enabled: bool = config_field(
        True,
        comment="RAG 日记检索开关（关闭后跳过日记检索，直接使用上下文对话）",
        section="rag"
    )
    retrieval_top_k: int = config_field(
        20,
        comment="检索返回的最大日记条数",
        section="rag"
    )
    keep_last_dialogue: int = config_field(
        10,
        comment="保留的近期对话条数（短期记忆）",
        section="rag"
    )


@dataclass
class EnergyConfig:
    """精力值系统配置"""
    initial: int = config_field(
        100,
        comment="初始精力值",
        section="energy"
    )
    max: float = config_field(
        100.0,
        comment="最大精力值上限",
        section="energy"
    )
    recovery_per_min: float = config_field(
        0.8,
        comment="每分钟恢复精力值",
        section="energy"
    )
    cost_per_reply: int = config_field(
        6,
        comment="每次回复消耗精力值",
        section="energy"
    )
    min_active: int = config_field(
        25,
        comment="低于此值进入低活跃状态",
        section="energy"
    )


@dataclass
class AttentionConfig:
    """注意力/响应配置"""
    sensitivity: float = config_field(
        0.12,
        comment="注意力敏感度",
        section="attention"
    )
    decay_level: float = config_field(
        0.65,
        comment="注意力衰减系数",
        section="attention"
    )
    sigmoid_centre: float = config_field(
        50.0,
        comment="Sigmoid 中心点",
        section="attention"
    )
    sigmoid_alpha: float = config_field(
        0.08,
        comment="Sigmoid 陡峭度",
        section="attention"
    )
    keywords: List[str] = config_field_factory(
        lambda: ["主人", "哥哥"],
        comment="注意力关键词列表",
        section="attention"
    )


@dataclass
class PathsConfig:
    """本地文件路径配置"""
    vector_db: str = config_field(
        "./yuki_memory",
        comment="向量数据库路径",
        section="paths"
    )
    embed_model: str = config_field(
        "./models/text2vec-base-chinese",
        comment="嵌入模型路径",
        section="paths"
    )
    history_file: str = config_field(
        "./data/chat_history.json",
        comment="历史记录文件路径",
        section="paths"
    )
    log_file: str = config_field(
        "./data/yuki_log.txt",
        comment="日志文件路径",
        section="paths"
    )
    cache_dir: str = config_field(
        "./data",
        comment="缓存目录路径",
        section="paths"
    )
    cache_file: str = config_field(
        "./data/meme_cache.json",
        comment="缓存文件路径",
        section="paths"
    )


@dataclass
class RequestTimeoutConfig:
    """请求超时配置"""
    total: int = config_field(
        60,
        comment="总超时时间（秒）",
        section="timing"
    )
    connect: int = config_field(
        10,
        comment="连接超时时间（秒）",
        section="timing"
    )
    sock_read: int = config_field(
        30,
        comment="读取超时时间（秒）",
        section="timing"
    )


@dataclass
class TimingConfig:
    """时间/超时配置"""
    debounce_time: int = config_field(
        32,
        comment="防抖时间（秒）",
        section="timing"
    )
    tool_call_delay_seconds: float = config_field(
        1.2,
        comment="工具调用前等待时间（秒），用于降低连续工具调用的机械感",
        section="timing"
    )
    request_timeout: RequestTimeoutConfig = config_field_factory(
        RequestTimeoutConfig,
        comment="请求超时配置",
        section="timing"
    )


# ==================== 主配置类 ====================

@dataclass
class Config:
    """
    配置中心 - 启动时从 config.yaml 一次性加载

    使用方式：
        from config import cfg
        print(cfg.robot_name)
        print(cfg.api.llm_api_key)

    添加新配置项：
        1. 在对应的 dataclass 中使用 config_field() 定义
        2. 运行 python config.py sync 自动生成/更新 yaml
    """
    # 基础身份
    robot_name: str = config_field(
        "yuki",
        comment="机器人名称",
        section="identity"
    )
    master_name: str = config_field(
        "主人",
        comment="主人称呼",
        section="identity"
    )

    # 安全配置
    max_message_length: int = config_field(
        150,
        comment="单条消息最大长度，防止 token 炸弹",
        section="security"
    )

    # 子配置组
    api: APIConfig = config_field_factory(
        APIConfig,
        comment="API 配置",
        section="api"
    )
    model: ModelConfig = config_field_factory(
        ModelConfig,
        comment="模型配置",
        section="model"
    )
    connection: ConnectionConfig = config_field_factory(
        ConnectionConfig,
        comment="连接配置",
        section="connection"
    )
    target: TargetConfig = config_field_factory(
        TargetConfig,
        comment="目标配置",
        section="target"
    )
    diary: DiaryConfig = config_field_factory(
        DiaryConfig,
        comment="日记触发配置",
        section="diary"
    )
    rag: RAGConfig = config_field_factory(
        RAGConfig,
        comment="RAG 记忆配置",
        section="rag"
    )
    energy: EnergyConfig = config_field_factory(
        EnergyConfig,
        comment="精力值系统配置",
        section="energy"
    )
    attention: AttentionConfig = config_field_factory(
        AttentionConfig,
        comment="注意力/响应配置",
        section="attention"
    )
    paths: PathsConfig = config_field_factory(
        PathsConfig,
        comment="本地文件路径配置",
        section="paths"
    )
    timing: TimingConfig = config_field_factory(
        TimingConfig,
        comment="时间/超时配置",
        section="timing"
    )

    # 并发/调试
    max_concurrent_meme: int = config_field(
        3,
        comment="最大并发处理表情包数量",
        section="debug"
    )
    debug: bool = config_field(
        True,
        comment="调试模式开关",
        section="debug"
    )

    # ==================== 计算属性 ====================

    @property
    def ROBOT_NAME(self) -> str:
        """机器人名称（小写）"""
        return (self.robot_name or "yuki").lower()

    @property
    def MASTER_NAME(self) -> str:
        """主人称呼"""
        return self.master_name or "主人"

    @property
    def LLM_BASE_URL(self) -> str:
        """首选 LLM API 地址"""
        return self.api.llm_base_url

    @property
    def BACKUP_BASE_URL(self) -> str:
        """备选 LLM API 地址"""
        return self.api.backup_base_url

    @property
    def IMAGE_PROCESS_API_URL(self) -> str:
        """视觉模型 API 地址"""
        return self.api.image_process_url

    @property
    def LLM_API_KEY(self) -> str:
        """首选 LLM API Key"""
        return self.api.llm_api_key

    @property
    def BACKUP_API_KEY(self) -> str:
        """备选 LLM API Key"""
        return self.api.backup_api_key

    @property
    def IMAGE_PROCESS_API_KEY(self) -> str:
        """视觉模型 API Key"""
        return self.api.image_process_api_key

    @property
    def LLM_MODEL(self) -> str:
        """主对话模型"""
        return self.model.llm

    @property
    def BACKUP_MODEL(self) -> str:
        """备用对话模型"""
        return self.model.backup

    @property
    def VISION_MODEL(self) -> str:
        """视觉模型"""
        return self.model.vision

    @property
    def DISABLE_THINKING(self) -> bool:
        """是否关闭模型 thinking/reasoning 输出"""
        raw_value = getattr(self, "_raw", {}).get("model", {}).get("disable_thinking")
        return self.model.disable_thinking if raw_value is None else bool(raw_value)

    @property
    def NAPCAT_WS_URL(self) -> str:
        """NapCat WebSocket 地址"""
        return self.connection.napcat_ws_url

    @property
    def NAPCAT_WS_TOKEN(self) -> str:
        """NapCat WebSocket Token"""
        return self.connection.napcat_ws_token

    @property
    def MAX_RETRIES(self) -> int:
        """最大重试次数"""
        return self.connection.max_retries

    @property
    def TARGET_QQ(self) -> int:
        """主人 QQ 号"""
        return int(self.target.qq)

    @property
    def DEBUG(self) -> bool:
        """调试模式"""
        return self.debug

    @property
    def INITIAL_ENERGY(self) -> int:
        """初始精力值"""
        return self.energy.initial

    @property
    def MAX_ENERGY(self) -> float:
        """最大精力值"""
        return self.energy.max

    @property
    def RECOVERY_PER_MIN(self) -> float:
        """每分钟恢复精力值"""
        return self.energy.recovery_per_min

    @property
    def COST_PER_REPLY(self) -> int:
        """每次回复消耗精力值"""
        return self.energy.cost_per_reply

    @property
    def MIN_ACTIVE_ENERGY(self) -> int:
        """低活跃精力阈值"""
        return self.energy.min_active

    @property
    def SENSITIVITY(self) -> float:
        """注意力敏感度"""
        return self.attention.sensitivity

    @property
    def DECAY_LEVEL(self) -> float:
        """注意力衰减系数"""
        return self.attention.decay_level

    @property
    def SIGMOID_CENTRE(self) -> float:
        """Sigmoid 中心点"""
        return self.attention.sigmoid_centre

    @property
    def SIGMOID_ALPHA(self) -> float:
        """Sigmoid 陡峭度"""
        return self.attention.sigmoid_alpha

    @property
    def DIARY_IDLE_SECONDS(self) -> int:
        """空闲日记触发时间"""
        return self.diary.idle_seconds

    @property
    def DIARY_MIN_TURNS(self) -> int:
        """日记最小轮数"""
        return self.diary.min_turns

    @property
    def DIARY_MAX_LENGTH(self) -> int:
        """历史强制总结长度"""
        return self.diary.max_length

    @property
    def KEEP_LAST_DIALOGUE(self) -> int:
        """保留近期对话条数"""
        return self.rag.keep_last_dialogue

    @property
    def RAG_ENABLED(self) -> bool:
        """RAG 日记检索开关"""
        return self.rag.enabled

    @property
    def RETRIEVAL_TOP_K(self) -> int:
        """RAG 默认检索条数"""
        return self.rag.retrieval_top_k

    @property
    def DEBOUNCE_TIME(self) -> int:
        """消息防抖时间"""
        return self.timing.debounce_time

    @property
    def MAX_MESSAGE_LENGTH(self) -> int:
        """单条消息最大长度"""
        return self.max_message_length

    @property
    def MAX_CONCURRENT_MEME(self) -> int:
        """最大并发表情包处理数"""
        return self.max_concurrent_meme

    @property
    def REQUEST_TIMEOUT(self):
        """请求超时配置（aiohttp.ClientTimeout）"""
        import aiohttp
        tc = self.timing.request_timeout
        return aiohttp.ClientTimeout(
            total=tc.total,
            connect=tc.connect,
            sock_read=tc.sock_read
        )

    @property
    def TARGET_GROUPS(self) -> List[int]:
        """目标群组列表"""
        return [int(g) for g in self.target.groups]

    @property
    def TARGET_WHITELIST(self) -> List[int]:
        """白名单 QQ 号列表"""
        return [int(q) for q in self.target.whitelist]

    @property
    def keywords(self) -> List[str]:
        """注意力关键词列表（包含机器人名称）"""
        base = list(self.attention.keywords)
        robot = self.ROBOT_NAME
        if robot and robot not in base:
            base.append(robot)
        return base

    # ==================== 路径属性（自动解析相对路径）====================

    @staticmethod
    def _resolve_path(p: str) -> str:
        """解析路径：相对路径转绝对路径"""
        if p and isinstance(p, str) and p.startswith("./"):
            return os.path.join(BASE_DIR, p[2:])
        return p

    @property
    def VECTOR_DB_PATH(self) -> str:
        """向量数据库路径"""
        return self._resolve_path(self.paths.vector_db) or os.path.join(BASE_DIR, "yuki_memory")

    @property
    def EMBED_MODEL(self) -> str:
        """嵌入模型路径"""
        return self._resolve_path(self.paths.embed_model) or os.path.join(BASE_DIR, "models", "text2vec-base-chinese")

    @property
    def HISTORY_FILE(self) -> str:
        """历史记录文件路径"""
        return self._resolve_path(self.paths.history_file) or os.path.join(BASE_DIR, "data", "chat_history.json")

    @property
    def LOG_FILE(self) -> str:
        """日志文件路径"""
        return self._resolve_path(self.paths.log_file) or os.path.join(BASE_DIR, "data", "yuki_log.txt")

    @property
    def CACHE_DIR(self) -> str:
        """缓存目录路径"""
        return self._resolve_path(self.paths.cache_dir) or os.path.join(BASE_DIR, "data")

    @property
    def CACHE_FILE(self) -> str:
        """缓存文件路径"""
        return self._resolve_path(self.paths.cache_file) or os.path.join(self.CACHE_DIR, "meme_cache.json")

    # ==================== 兼容旧版 API ====================

    def get(self, *keys, default=None):
        """
        显式读取嵌套配置（兼容旧版 API）

        用法：cfg.get("api", "llm_api_key", default="")
        """
        d = self.__dict__
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
        global cfg
        cfg = load_config()


# ==================== 配置加载函数 ====================

def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个字典"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _dict_to_dataclass(cls, data: dict):
    """将字典转换为 dataclass 实例"""
    if not isinstance(data, dict):
        return data

    field_types = {f.name: f.type for f in cls.__dataclass_fields__.values()}
    kwargs = {}

    for key, value in data.items():
        if key in field_types:
            field_type = field_types[key]
            # 如果字段类型是 dataclass，递归转换
            if hasattr(field_type, '__dataclass_fields__') and isinstance(value, dict):
                kwargs[key] = _dict_to_dataclass(field_type, value)
            else:
                kwargs[key] = value

    return cls(**kwargs)


def load_config(config_path: Optional[str] = None) -> Config:
    """
    加载配置文件

    Args:
        config_path: 配置文件路径，默认为 configs/config.yaml

    Returns:
        Config 实例
    """
    if config_path is None:
        config_path = os.path.join(BASE_DIR, "configs", "config.yaml")

    # 默认配置
    default_config = Config()

    # 如果配置文件不存在，创建默认配置
    if not os.path.exists(config_path):
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        save_config(default_config, config_path)
        default_config._raw = {}
        default_config._content_hash = ""
        return default_config

    # 读取 YAML 配置
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        # 配置文件损坏，备份并使用默认配置
        bak_path = config_path + ".bak"
        import shutil
        shutil.copy2(config_path, bak_path)
        print(f"[Config] 配置文件解析失败，已备份到 {bak_path}: {e}")
        return default_config

    # 将 YAML 数据转换为 Config 实例
    config = _dict_to_dataclass(Config, yaml_data)
    config._raw = yaml_data
    config._content_hash = ""

    return config


def save_config(config: Config, config_path: Optional[str] = None):
    """
    保存配置到文件

    Args:
        config: Config 实例
        config_path: 配置文件路径
    """
    if config_path is None:
        config_path = os.path.join(BASE_DIR, "configs", "config.yaml")

    os.makedirs(os.path.dirname(config_path), exist_ok=True)

    # 转换为字典
    from dataclasses import asdict
    data = asdict(config)

    # 生成 YAML
    yaml_content = yaml.dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False
    )

    # 添加文件头
    header = "# YukiV6 配置文件\n# 所有配置均在此文件管理，请勿提交到 Git\n# 本文件已在 .gitignore 中\n\n"

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(header + yaml_content)


# ==================== 兼容旧版接口 ====================

def _build_attr_map() -> dict:
    """
    从 dataclass 的 field metadata 自动构建 _ATTR_MAP

    这样只需要在 dataclass 中定义一次，_ATTR_MAP 自动生成
    """
    attr_map = {}

    def _collect_fields(cls, prefix=()):
        for f in fields(cls):
            field_path = prefix + (f.name,)
            metadata = f.metadata or {}
            comment = metadata.get("comment", "")

            # 如果是 dataclass 类型，递归收集
            field_type = f.type
            if hasattr(field_type, '__dataclass_fields__'):
                _collect_fields(field_type, field_path)
            else:
                # 构建大写名称
                attr_name = "_".join(field_path).upper()
                attr_map[attr_name] = (field_path, f.default if f.default is not f.default_factory else f.default_factory(), comment)

    _collect_fields(Config)
    return attr_map


# 自动构建 _ATTR_MAP（向后兼容）
_ATTR_MAP = _build_attr_map()

# Section 注释头映射
_SECTION_HEADERS = {
    "identity": "# ================= 机器人身份 =================",
    "security": "# ================= 安全配置 =================",
    "api": "# ================= API 配置 =================",
    "model": "# ================= 模型配置 =================",
    "connection": "# ================= 连接配置 =================",
    "target": "# ================= 目标配置 =================",
    "diary": "# ================= 日记触发配置 =================",
    "rag": "# ================= RAG 记忆配置 =================",
    "paths": "# ================= 本地文件路径配置 =================\n# 均为相对项目根目录的路径",
    "timing": "# ================= 时间/超时配置 =================",
    "energy": "# ================= 精力值系统配置 =================",
    "attention": "# ================= 注意力/响应配置 =================",
    "debug": "# ================= 调试配置 =================",
}


def _get_section_for_field(field_path: tuple) -> str:
    """根据字段路径获取所属 section"""
    # 从 dataclass 的 metadata 中获取 section
    def _find_section(cls, prefix=(), target_path=()):
        for f in fields(cls):
            current_path = prefix + (f.name,)
            metadata = f.metadata or {}
            section = metadata.get("section", "")

            if current_path == target_path:
                return section

            field_type = f.type
            if hasattr(field_type, '__dataclass_fields__'):
                result = _find_section(field_type, current_path, target_path)
                if result:
                    return result
        return ""

    return _find_section(Config, (), field_path)


def generate_default_config() -> str:
    """生成默认配置 YAML 文本（用于 setup.py）"""
    from dataclasses import asdict
    default_config = Config()
    data = asdict(default_config)

    header = "# YukiV6 配置文件\n# 所有配置均在此文件管理，请勿提交到 Git\n# 本文件已在 .gitignore 中\n\n"
    yaml_content = yaml.dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False
    )

    return header + yaml_content


def _add_inline_comments(yaml_text: str) -> str:
    """给 YAML 文本添加行尾注释（用于 setup.py）"""
    comment_map = {}
    for name, (path, default, comment) in _ATTR_MAP.items():
        if comment:
            comment_map[path] = comment

    lines = yaml_text.split("\n")
    path_stack = []
    result = []

    for line in lines:
        stripped = line.lstrip()
        if not stripped:
            result.append(line)
            continue

        indent = len(line) - len(stripped)
        level = indent // 2
        path_stack = path_stack[:level]

        # Section 注释头
        if level == 0 and ":" in stripped and not stripped.startswith("#"):
            key = stripped.split(":")[0].strip()
            if key in _SECTION_HEADERS:
                result.append("")
                result.append(_SECTION_HEADERS[key])

        # 行尾注释
        if ":" in stripped and not stripped.startswith("#") and not stripped.startswith("-"):
            key = stripped.split(":")[0].strip()
            path_stack.append(key)
            path_tuple = tuple(path_stack)
            if path_tuple in comment_map:
                line = f"{line}  # {comment_map[path_tuple]}"

        result.append(line)

    return "\n".join(result)


# ==================== 同步功能 ====================

def sync_config(config_path: Optional[str] = None, verbose: bool = True) -> bool:
    """
    同步配置文件到 dataclass 定义的最新结构

    功能：
    1. 保留用户已修改的值
    2. 添加新增的配置项（使用默认值）
    3. 删除已移除的配置项
    4. 更新注释和格式

    Args:
        config_path: 配置文件路径
        verbose: 是否打印详细信息

    Returns:
        是否有变更
    """
    if config_path is None:
        config_path = os.path.join(BASE_DIR, "configs", "config.yaml")

    # 1. 读取现有配置
    existing_data = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                existing_data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            if verbose:
                print(f"[Config Sync] 配置文件解析失败: {e}")
            return False

    # 2. 获取默认配置结构
    default_config = Config()
    from dataclasses import asdict
    default_data = asdict(default_config)

    # 3. 深度合并（保留用户值，添加新字段）
    merged_data = _deep_merge(default_data, existing_data)

    # 4. 检查是否有变更
    has_changes = merged_data != existing_data

    # 5. 保存更新后的配置
    if has_changes or not os.path.exists(config_path):
        # 备份原文件
        if os.path.exists(config_path):
            import shutil
            backup_path = config_path + ".backup"
            shutil.copy2(config_path, backup_path)
            if verbose:
                print(f"[Config Sync] 已备份原配置到: {backup_path}")

        # 生成带注释的 YAML
        yaml_content = yaml.dump(
            merged_data,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False
        )
        yaml_content = _add_inline_comments(yaml_content)

        # 添加文件头
        header = "# YukiV6 配置文件\n# 所有配置均在此文件管理，请勿提交到 Git\n# 本文件已在 .gitignore 中\n\n"

        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(header + yaml_content)

        if verbose:
            print(f"[Config Sync] 配置已同步到: {config_path}")
            if has_changes:
                # 显示变更的字段
                added = set(default_data.keys()) - set(existing_data.keys())
                removed = set(existing_data.keys()) - set(default_data.keys())
                if added:
                    print(f"[Config Sync] 新增字段: {added}")
                if removed:
                    print(f"[Config Sync] 移除字段: {removed}")
    else:
        if verbose:
            print("[Config Sync] 配置已是最新，无需同步")

    return has_changes


# ==================== CLI 入口 ====================

if __name__ == "__main__":
    import sys

    def print_help():
        """打印帮助信息"""
        print("""
YukiV6 配置管理工具

用法:
    python config.py <command> [options]

命令:
    sync        同配配置文件到最新结构
    generate    生成默认配置文件
    help        显示此帮助信息

示例:
    python config.py sync
    python config.py sync --path configs/config.yaml
    python config.py generate
    python config.py generate --output configs/config.yaml
        """)

    def cmd_sync(args):
        """同步配置"""
        path = None
        verbose = True

        i = 0
        while i < len(args):
            if args[i] == "--path" and i + 1 < len(args):
                path = args[i + 1]
                i += 2
            elif args[i] == "--quiet":
                verbose = False
                i += 1
            else:
                i += 1

        success = sync_config(path, verbose)
        sys.exit(0 if success else 1)

    def cmd_generate(args):
        """生成默认配置"""
        path = None

        i = 0
        while i < len(args):
            if args[i] == "--output" and i + 1 < len(args):
                path = args[i + 1]
                i += 2
            else:
                i += 1

        if path is None:
            path = os.path.join(BASE_DIR, "configs", "config.yaml")

        # 生成默认配置
        config = Config()
        save_config(config, path)
        print(f"[Config] 默认配置已生成到: {path}")

    # 解析命令
    if len(sys.argv) < 2:
        print_help()
        sys.exit(0)

    command = sys.argv[1]
    args = sys.argv[2:]

    if command == "sync":
        cmd_sync(args)
    elif command == "generate":
        cmd_generate(args)
    elif command in ("help", "--help", "-h"):
        print_help()
    else:
        print(f"未知命令: {command}")
        print_help()
        sys.exit(1)


# ==================== 全局单例 ====================

cfg = load_config()
