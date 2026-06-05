# 配置系统迁移指南

## 概述

本文档描述了 YukiV6 配置系统从旧版（基于 `__getattr__` 的动态属性访问）迁移到新版（基于 `dataclass` 的类型安全配置）的过程。

## 新版配置系统特性

### 1. 类型安全
- 使用 Python `dataclass` 定义配置结构
- IDE 自动补全和类型检查支持
- 编译时错误检测

### 2. 简化架构
- 移除了复杂的 `__getattr__` 动态属性访问
- 移除了热重载机制（启动时一次性加载）
- 简化了路径解析逻辑

### 3. 向后兼容
- 保持 `from config import cfg` 导入方式
- 保持 `cfg.xxx` 属性访问方式
- 保持 `cfg.get()` 方法
- 保持 `_ATTR_MAP` 和 `_SECTION_HEADERS` 用于 WebUI

### 4. 单一数据源（增强功能）
- **只在 dataclass 中定义**，yaml 自动生成
- 使用 `config_field()` 工厂函数添加注释
- 运行 `python config.py sync` 自动同步 yaml

## 迁移步骤

### 步骤 1：更新导入

**旧版导入：**
```python
from config import cfg
```

**新版导入（保持不变）：**
```python
from config import cfg
```

### 步骤 2：访问配置项

**旧版访问方式：**
```python
# 通过大写常量访问
api_key = cfg.LLM_API_KEY
model = cfg.LLM_MODEL
robot_name = cfg.ROBOT_NAME
```

**新版访问方式（推荐）：**
```python
# 通过 dataclass 属性访问（类型安全）
api_key = cfg.api.llm_api_key
model = cfg.model.llm
robot_name = cfg.robot_name

# 或者使用计算属性（向后兼容）
api_key = cfg.LLM_API_KEY  # 仍然可用
model = cfg.LLM_MODEL  # 仍然可用
robot_name = cfg.ROBOT_NAME  # 仍然可用
```

### 步骤 3：使用计算属性

新版配置系统保留了所有计算属性，确保向后兼容：

```python
# 机器人名称（小写）
cfg.ROBOT_NAME  # -> "yuki"

# 主人称呼
cfg.MASTER_NAME  # -> "主人"

# 目标群组列表
cfg.TARGET_GROUPS  # -> [123, 456]

# 注意力关键词（包含机器人名称）
cfg.keywords  # -> ["主人", "哥哥", "yuki"]

# 路径属性（自动解析相对路径）
cfg.VECTOR_DB_PATH  # -> "D:\Projects\YukiV6\yuki_memory"
cfg.EMBED_MODEL  # -> "D:\Projects\YukiV6\models\text2vec-base-chinese"
cfg.HISTORY_FILE  # -> "D:\Projects\YukiV6\data\chat_history.json"
cfg.LOG_FILE  # -> "D:\Projects\YukiV6\data\yuki_log.txt"
cfg.CACHE_DIR  # -> "D:\Projects\YukiV6\data"
cfg.CACHE_FILE  # -> "D:\Projects\YukiV6\data\meme_cache.json"

# 请求超时配置
cfg.REQUEST_TIMEOUT  # -> aiohttp.ClientTimeout(total=60, connect=10, sock_read=30)
```

### 步骤 4：使用 get() 方法

**旧版：**
```python
api_key = cfg.get("api", "llm_api_key", default="")
```

**新版（保持不变）：**
```python
api_key = cfg.get("api", "llm_api_key", default="")
```

### 步骤 5：重新加载配置

**旧版：**
```python
cfg.reload()
```

**新版（保持不变）：**
```python
cfg.reload()
```

## 配置结构对照表

| 旧版访问方式 | 新版访问方式 | 说明 |
|-------------|-------------|------|
| `cfg.LLM_API_KEY` | `cfg.api.llm_api_key` | API 密钥 |
| `cfg.LLM_BASE_URL` | `cfg.api.llm_base_url` | API 地址 |
| `cfg.LLM_MODEL` | `cfg.model.llm` | 模型名称 |
| `cfg.ROBOT_NAME` | `cfg.robot_name` | 机器人名称 |
| `cfg.MASTER_NAME` | `cfg.master_name` | 主人称呼 |
| `cfg.DEBUG` | `cfg.debug` | 调试模式 |
| `cfg.TARGET_GROUPS` | `cfg.target.groups` | 目标群组 |
| `cfg.NAPCAT_WS_URL` | `cfg.connection.napcat_ws_url` | WebSocket 地址 |
| `cfg.DIARY_IDLE_SECONDS` | `cfg.diary.idle_seconds` | 日记触发时间 |
| `cfg.ENERGY_INITIAL` | `cfg.energy.initial` | 初始精力值 |

## 子配置组

新版配置系统将配置项分组到以下子配置类中：

```python
# API 配置
cfg.api.llm_api_key
cfg.api.llm_base_url
cfg.api.backup_api_key
cfg.api.backup_base_url
cfg.api.image_process_api_key
cfg.api.image_process_url

# 模型配置
cfg.model.llm
cfg.model.backup
cfg.model.vision
cfg.model.disable_thinking

# 连接配置
cfg.connection.napcat_ws_url
cfg.connection.napcat_ws_token
cfg.connection.max_retries

# 目标配置
cfg.target.qq
cfg.target.groups

# 日记配置
cfg.diary.idle_seconds
cfg.diary.min_turns
cfg.diary.max_length

# RAG 配置
cfg.rag.retrieval_top_k
cfg.rag.keep_last_dialogue

# 精力值配置
cfg.energy.initial
cfg.energy.max
cfg.energy.recovery_per_min
cfg.energy.cost_per_reply
cfg.energy.min_active

# 注意力配置
cfg.attention.sensitivity
cfg.attention.decay_level
cfg.attention.sigmoid_centre
cfg.attention.sigmoid_alpha
cfg.attention.keywords

# 路径配置
cfg.paths.vector_db
cfg.paths.embed_model
cfg.paths.history_file
cfg.paths.log_file
cfg.paths.cache_dir
cfg.paths.cache_file

# 时间配置
cfg.timing.debounce_time
cfg.timing.request_timeout.total
cfg.timing.request_timeout.connect
cfg.timing.request_timeout.sock_read
```

## 测试验证

运行单元测试验证配置系统：

```bash
python -m pytest tests/test_config.py -v
```

预期输出：
```
============================= 40 passed in 0.09s ==============================
```

## 添加新配置项（增强功能）

### 步骤 1：在 dataclass 中定义

在 `config.py` 中找到对应的配置类，使用 `config_field()` 添加新字段：

```python
@dataclass
class MyConfig:
    """我的配置"""
    # 现有字段...

    # 新增字段
    new_option: str = config_field(
        "default_value",           # 默认值
        comment="新选项的说明",      # 注释（会显示在 yaml 中）
        section="my_section"       # 所属分组
    )
```

### 步骤 2：同步配置文件

运行同步命令，自动更新 yaml：

```bash
python config.py sync
```

输出：
```
[Config Sync] 已备份原配置到: configs/config.yaml.backup
[Config Sync] 配置已同步到: configs/config.yaml
[Config Sync] 新增字段: {'my_section'}
```

### 步骤 3：使用新配置

```python
from config import cfg

# 通过 dataclass 访问
value = cfg.my_config.new_option

# 或通过旧版方式访问（自动兼容）
value = cfg.NEW_OPTION
```

## CLI 命令

```bash
# 同步配置（保留用户值，添加新字段）
python config.py sync

# 同步到指定路径
python config.py sync --path configs/config.yaml

# 生成默认配置（覆盖）
python config.py generate

# 生成到指定路径
python config.py generate --output configs/config.yaml

# 显示帮助
python config.py help
```

## 常见问题

### Q1: 旧版代码需要修改吗？

**A:** 不需要。新版配置系统完全向后兼容，旧版代码可以继续使用 `cfg.LLM_API_KEY` 等访问方式。

### Q2: 如何获取原始字典格式？

**A:** 使用 `dataclasses.asdict()`：
```python
from dataclasses import asdict
config_dict = asdict(cfg)
```

### Q3: 如何保存配置？

**A:** 使用 `save_config()` 函数：
```python
from config import save_config
save_config(cfg)
```

### Q4: 热重载功能还在吗？

**A:** 新版移除了热重载功能，配置在启动时一次性加载。如需重新加载，调用 `cfg.reload()`。

## 总结

新版配置系统提供了：
1. **类型安全** - IDE 自动补全和类型检查
2. **简化架构** - 更清晰的代码结构
3. **向后兼容** - 旧版代码无需修改
4. **更好的可维护性** - 配置项分组管理

迁移过程对现有代码完全透明，无需修改任何现有代码。
