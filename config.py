# config.py
import copy
import hashlib
import logging
import os
import time
import yaml
import aiohttp

from utils import BASE_DIR

logger = logging.getLogger("config")

# 属性名 -> (yaml 路径元组, 默认值, 注释)
# 注释为 None 表示不添加行尾注释
_ATTR_MAP = {
    # 安全配置
    "MAX_MESSAGE_LENGTH": (("max_message_length",), 150, "单条消息最大长度，防止 token 炸弹"),

    # 日记触发
    "DIARY_IDLE_SECONDS": (("diary", "idle_seconds"), 120, "空闲多久后触发日记（秒）"),
    "DIARY_MIN_TURNS":    (("diary", "min_turns"), 15, "最小对话轮数阈值"),
    "DIARY_MAX_LENGTH":   (("diary", "max_length"), 50, "历史记录超过此条数强制写日记"),

    # RAG 记忆
    "RETRIEVAL_TOP_K":     (("rag", "retrieval_top_k"), 20, "检索返回的最大日记条数"),
    "KEEP_LAST_DIALOGUE":  (("rag", "keep_last_dialogue"), 10, "保留的近期对话条数（短期记忆）"),

    # API
    "LLM_PLATFORM":          (("api", "llm_platform"), "deepseek", "首选 LLM 平台名称（deepseek/dashscope/openai）"),
    "BACKUP_PLATFORM":       (("api", "backup_platform"), "deepseek", "备选 LLM 平台名称"),
    "VISION_PLATFORM":       (("api", "vision_platform"), "dashscope", "视觉模型平台名称"),
    "LLM_BASE_URL":          (("api", "llm_base_url"), "", "可选：覆盖首选平台内置 API 地址"),
    "BACKUP_BASE_URL":       (("api", "backup_base_url"), "", "可选：覆盖备选平台内置 API 地址"),
    "IMAGE_PROCESS_API_URL": (("api", "image_process_url"), "", "可选：覆盖视觉平台内置 API 地址"),
    "LLM_API_KEY":           (("api", "llm_api_key"), "", "首选 LLM API Key"),
    "BACKUP_API_KEY":        (("api", "backup_api_key"), "", "备选 API Key（留空则使用 llm_api_key）"),
    "IMAGE_PROCESS_API_KEY": (("api", "image_process_api_key"), "", "图像处理 API Key"),

    # 模型
    "LLM_MODEL":    (("model", "llm"), "deepseek-chat", "主对话模型"),
    "BACKUP_MODEL": (("model", "backup"), "deepseek-chat", "备用对话模型"),
    "VISION_MODEL": (("model", "vision"), "qwen3-vl-flash", "视觉/多模态模型；如不需要可留空"),
    "DISABLE_THINKING": (("model", "disable_thinking"), True, "默认关闭模型的 thinking/reasoning 输出"),

    # 连接
    "NAPCAT_WS_URL":  (("connection", "napcat_ws_url"), "ws://localhost:3001", "NapCat WebSocket 地址"),
    "NAPCAT_WS_TOKEN": (("connection", "napcat_ws_token"), "", "NapCat WebSocket 认证 Token（留空则不认证）"),
    "MAX_RETRIES":    (("connection", "max_retries"), 3, "最大重试次数"),

    # 目标
    "TARGET_QQ":     (("target", "qq"), 0, "私聊目标 QQ 号"),
    "TARGET_GROUPS": (("target", "groups"), [], "目标群聊 QQ 号列表"),

    # 时间
    "DEBOUNCE_TIME": (("timing", "debounce_time"), 32, "防抖时间（秒）"),

    # 精力值
    "INITIAL_ENERGY":     (("energy", "initial"), 100, "初始精力值"),
    "MAX_ENERGY":         (("energy", "max"), 100.0, "最大精力值上限"),
    "RECOVERY_PER_MIN":   (("energy", "recovery_per_min"), 0.8, "每分钟恢复精力值"),
    "COST_PER_REPLY":     (("energy", "cost_per_reply"), 6, "每次回复消耗精力值"),
    "MIN_ACTIVE_ENERGY":  (("energy", "min_active"), 25, "低于此值进入低活跃状态"),

    # 注意力
    "SENSITIVITY":      (("attention", "sensitivity"), 0.12, "注意力敏感度"),
    "DECAY_LEVEL":      (("attention", "decay_level"), 0.65, "注意力衰减系数"),
    "SIGMOID_CENTRE":   (("attention", "sigmoid_centre"), 50.0, "Sigmoid 中心点"),
    "SIGMOID_ALPHA":    (("attention", "sigmoid_alpha"), 0.08, "Sigmoid 陡峭度"),

    # 本地文件路径
    "VECTOR_DB_PATH":  (("paths", "vector_db"), "./yuki_memory", "向量数据库路径"),
    "EMBED_MODEL":     (("paths", "embed_model"), "./models/text2vec-base-chinese", "嵌入模型路径"),
    "HISTORY_FILE":    (("paths", "history_file"), "./data/chat_history.json", "历史记录文件路径"),
    "LOG_FILE":        (("paths", "log_file"), "./data/yuki_log.txt", "日志文件路径"),
    "CACHE_DIR":       (("paths", "cache_dir"), "./data", "缓存目录路径"),
    "CACHE_FILE":      (("paths", "cache_file"), "./data/meme_cache.json", "缓存文件路径"),

    # 注意力关键词
    "ATTENTION_KEYWORDS": (("attention", "keywords"), ["主人", "哥哥"], "注意力关键词列表（逗号分隔）"),

    # 并发 / 调试
    "MAX_CONCURRENT_MEME": (("max_concurrent_meme",), 3, "最大并发处理表情包数量"),
    "DEBUG":               (("debug",), True, "调试模式开关"),
}

# Section 注释头映射：顶级键 -> 注释头
_SECTION_HEADERS = {
    "robot_name": "# ================= 机器人身份 =================",
    "max_message_length": "# ================= 安全配置 =================",
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
    "max_concurrent_meme": "# ================= 并发与调试配置 =================",
    "debug": "# ================= 调试配置 =================",
}


class Config:
    """热重载配置中心 —— 所有配置项运行时从 configs/config.yaml 读取"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self._path = os.path.join(BASE_DIR, "configs", "config.yaml")
        self._raw = {}
        self._content_hash = ""
        self._last_good_content = ""
        self._last_check = 0
        self.reload()

    def reload(self):
        """强制重新加载配置文件，并自动补全缺失字段"""
        if os.path.exists(self._path):
            with open(self._path, "r", encoding="utf-8") as f:
                content = f.read()
            self._compute_hash(content)
        else:
            # 文件不存在时，生成带注释的默认配置并写入
            content = generate_default_config()
            with open(self._path, "w", encoding="utf-8") as f:
                f.write(content)
            self._compute_hash(content)
        self._auto_fill()

    def _auto_fill(self):
        """自动将 _ATTR_MAP 中缺失的字段补全到内存中的 _raw（不覆盖已有值，不写磁盘）"""
        added = []
        for name, (path, default, comment) in _ATTR_MAP.items():
            d = self._raw
            exists = True
            for k in path[:-1]:
                if k not in d or not isinstance(d[k], dict):
                    exists = False
                    break
                d = d[k]
            if not exists or path[-1] not in d:
                # 补全缺失字段
                d = self._raw
                for k in path[:-1]:
                    if k not in d or not isinstance(d[k], dict):
                        d[k] = {}
                    d = d[k]
                d[path[-1]] = default
                added.append(".".join(path))
        if added:
            # 仅更新内存，不写入磁盘，避免覆盖用户注释
            logger.info(f"[Config] 已自动补全 {len(added)} 个缺失字段（仅内存）: {', '.join(added)}")

    def _save_raw(self):
        """将当前 _raw 写回 configs/config.yaml"""
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            yaml.dump(self._raw, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    def _compute_hash(self, content: str) -> bool:
        """计算 hash，若内容变化则更新 _content_hash 和 _raw，返回 True"""
        new_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
        if new_hash == self._content_hash:
            return False
        is_first_load = not self._content_hash and not self._raw
        try:
            new_raw = yaml.safe_load(content) or {}
        except yaml.YAMLError as e:
            # 备份损坏的配置文件
            bak_path = self._path + ".bak"
            with open(bak_path, "w", encoding="utf-8") as f:
                f.write(content)
            if is_first_load:
                logger.error(f"[Config] 配置文件解析失败，已备份到 {os.path.basename(bak_path)}: {e}")
                raise RuntimeError(f"配置文件 {self._path} 解析失败") from e
            # 运行时自愈：恢复上一个已知的好的文件内容（保留注释）
            if self._last_good_content:
                with open(self._path, "w", encoding="utf-8") as f:
                    f.write(self._last_good_content)
                logger.warning(f"[Config] 配置文件解析失败，已备份到 {os.path.basename(bak_path)} 并恢复原文: {e}")
            else:
                self._save_raw()
                logger.warning(f"[Config] 配置文件解析失败，已备份到 {os.path.basename(bak_path)} 并恢复默认配置: {e}")
            return False
        self._content_hash = new_hash
        self._raw = new_raw
        self._last_good_content = content
        return True

    @staticmethod
    def _get_nested(data, path):
        """按路径从嵌套字典取值"""
        d = data
        for k in path:
            if isinstance(d, dict) and k in d:
                d = d[k]
            else:
                return None
        return d

    def _check(self):
        """检查文件是否有变更，如有则自动 reload（最多每秒检查一次）"""
        now = time.time()
        if now - self._last_check < 1.0:
            return
        self._last_check = now
        if os.path.exists(self._path):
            with open(self._path, "r", encoding="utf-8") as f:
                content = f.read()
            old_raw = copy.deepcopy(self._raw)
            if self._compute_hash(content):
                self._auto_fill()
                changed = []
                for name, (path, default, comment) in _ATTR_MAP.items():
                    old_val = self._get_nested(old_raw, path)
                    new_val = self._get_nested(self._raw, path)
                    if old_val != new_val:
                        changed.append((name, old_val, new_val))
                if changed:
                    logger.info("[Config] 检测到配置变更，已自动重载：")
                    _SENSITIVE_KEYS = {"LLM_API_KEY", "BACKUP_API_KEY", "IMAGE_PROCESS_API_KEY", "NAPCAT_WS_TOKEN"}
                    for name, old_val, new_val in changed:
                        if name in _SENSITIVE_KEYS:
                            old_disp = "***" if old_val else "(空)"
                            new_disp = "***" if new_val else "(空)"
                            logger.info(f"  {name}: {old_disp} → {new_disp}")
                        else:
                            logger.info(f"  {name}: {old_val!r} → {new_val!r}")

                    # 若平台/API/模型配置发生变更，通知 ProviderRegistry 重新构建
                    platform_related = {
                        "LLM_PLATFORM", "BACKUP_PLATFORM", "VISION_PLATFORM",
                        "LLM_API_KEY", "BACKUP_API_KEY", "IMAGE_PROCESS_API_KEY",
                        "LLM_BASE_URL", "BACKUP_BASE_URL", "IMAGE_PROCESS_API_URL",
                        "LLM_MODEL", "BACKUP_MODEL", "VISION_MODEL",
                    }
                    if any(n in platform_related for n, _, _ in changed):
                        try:
                            from providers.registry import ProviderRegistry
                            ProviderRegistry().reload()
                        except Exception as e:
                            logger.error(f"[Config] ProviderRegistry 重载失败: {e}")

    # ---------------- 通用属性访问 ----------------
    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        self._check()
        if name in _ATTR_MAP:
            path, default, comment = _ATTR_MAP[name]
            d = self._raw
            for k in path:
                if isinstance(d, dict) and k in d:
                    d = d[k]
                else:
                    return default
            return d
        # 兜底：直接读顶层键
        return self._raw.get(name)

    def get(self, *keys, default=None):
        """显式读取嵌套配置：cfg.get("api", "llm_api_key", default="")"""
        self._check()
        d = self._raw
        for k in keys:
            if isinstance(d, dict) and k in d:
                d = d[k]
            else:
                return default
        return d

    # ---------------- 计算属性（需动态构造） ----------------
    @property
    def ROBOT_NAME(self):
        self._check()
        return (self._raw.get("robot_name") or "yuki").lower()

    @property
    def MASTER_NAME(self):
        self._check()
        return self._raw.get("master_name") or "主人"

    @property
    def REQUEST_TIMEOUT(self):
        self._check()
        tc = self._raw.get("timing", {}).get("request_timeout", {})
        return aiohttp.ClientTimeout(
            total=tc.get("total", 60),
            connect=tc.get("connect", 10),
            sock_read=tc.get("sock_read", 30)
        )

    @property
    def TARGET_GROUPS(self):
        self._check()
        groups = self._raw.get("target", {}).get("groups", [])
        if isinstance(groups, str):
            return [int(g.strip()) for g in groups.split(",") if g.strip()]
        return [int(g) for g in groups]

    @property
    def keywords(self):
        self._check()
        base = list(self._raw.get("attention", {}).get("keywords", ["主人", "哥哥"]))
        robot = self.ROBOT_NAME
        if robot and robot not in base:
            base.append(robot)
        return base

    # ---------------- 路径解析 ----------------
    @staticmethod
    def _resolve_path(p):
        if p and isinstance(p, str) and p.startswith("./"):
            return os.path.join(BASE_DIR, p[2:])
        return p

    @property
    def VECTOR_DB_PATH(self):
        p = self._resolve_path(self._raw.get("paths", {}).get("vector_db", "./yuki_memory"))
        return p or os.path.join(BASE_DIR, "yuki_memory")

    @property
    def EMBED_MODEL(self):
        p = self._resolve_path(self._raw.get("paths", {}).get("embed_model", "./models/text2vec-base-chinese"))
        return p or os.path.join(BASE_DIR, "models", "text2vec-base-chinese")

    @property
    def HISTORY_FILE(self):
        p = self._resolve_path(self._raw.get("paths", {}).get("history_file", "./data/chat_history.json"))
        return p or os.path.join(BASE_DIR, "data", "chat_history.json")

    @property
    def LOG_FILE(self):
        p = self._resolve_path(self._raw.get("paths", {}).get("log_file", "./data/yuki_log.txt"))
        return p or os.path.join(BASE_DIR, "data", "yuki_log.txt")

    @property
    def CACHE_DIR(self):
        p = self._resolve_path(self._raw.get("paths", {}).get("cache_dir", "./data"))
        return p or os.path.join(BASE_DIR, "data")

    @property
    def CACHE_FILE(self):
        p = self._resolve_path(self._raw.get("paths", {}).get("cache_file", "./data/meme_cache.json"))
        return p or os.path.join(self.CACHE_DIR, "meme_cache.json")


def _add_inline_comments(yaml_text: str) -> str:
    """给 yaml 文本添加行尾注释和 section 注释头"""
    # 从 _ATTR_MAP 构建注释映射
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

        # 计算当前层级（yaml dump 默认缩进 2 空格）
        indent = len(line) - len(stripped)
        level = indent // 2
        path_stack = path_stack[:level]

        # Section 注释头：顶级键前插入
        if level == 0 and ":" in stripped and not stripped.startswith("#"):
            key = stripped.split(":")[0].strip()
            if key in _SECTION_HEADERS:
                result.append("")
                result.append(_SECTION_HEADERS[key])

        # 行尾注释：匹配键值对
        if ":" in stripped and not stripped.startswith("#") and not stripped.startswith("-"):
            key = stripped.split(":")[0].strip()
            path_stack.append(key)
            path_tuple = tuple(path_stack)
            if path_tuple in comment_map:
                line = f"{line}  # {comment_map[path_tuple]}"
        elif stripped.startswith("-"):
            # 列表项，不追加路径
            pass
        else:
            # 其他非键值对行，保持路径栈
            pass

        result.append(line)

    return "\n".join(result)


def generate_default_config() -> str:
    """基于 _ATTR_MAP 动态生成默认 YAML 配置文本"""
    defaults = {}

    # 1. 先放入不在 _ATTR_MAP 中的顶层配置
    defaults["robot_name"] = "yuki"
    defaults["master_name"] = "主人"

    # 2. 从 _ATTR_MAP 构建嵌套结构
    for name, (path, default, comment) in _ATTR_MAP.items():
        d = defaults
        for k in path[:-1]:
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
            d = d[k]
        d[path[-1]] = default

    # 3. 补充 paths 配置（_ATTR_MAP 中未包含）
    defaults.setdefault("paths", {
        "vector_db": "./yuki_memory",
        "embed_model": "./models/text2vec-base-chinese",
        "history_file": "./data/chat_history.json",
        "log_file": "./data/yuki_log.txt",
        "cache_dir": "./data",
        "cache_file": "./data/meme_cache.json",
    })

    # 4. 补充 timing.request_timeout（_ATTR_MAP 中未包含）
    defaults.setdefault("timing", {}).setdefault("request_timeout", {
        "total": 60,
        "connect": 10,
        "sock_read": 30,
    })

    # 5. 补充 attention.keywords（_ATTR_MAP 中未包含）
    defaults.setdefault("attention", {}).setdefault("keywords", ["主人", "哥哥"])

    header = "# Yuki-Chan Bot 配置文件\n# 所有配置均在此文件管理，请勿提交到 Git\n# 本文件已在 .gitignore 中\n\n"
    yaml_content = yaml.dump(
        defaults,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False
    )
    yaml_content = _add_inline_comments(yaml_content)
    return header + yaml_content


# 全局单例 —— 所有模块通过 `from config import cfg` 访问
cfg = Config()
