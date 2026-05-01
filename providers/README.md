# Yuki Provider 体系

本文档介绍 Yuki 的模型 Provider 架构、使用方法以及如何扩展新平台。

---

## 架构概述

Yuki 采用 **Provider 模式** 管理所有 AI 模型调用。核心设计：

- **BaseProvider**：抽象基类，定义 `chat()` / `close()` 接口
- **OpenAICompatibleProvider**：OpenAI 兼容格式的通用实现
- **平台子类**：继承通用实现，封装特定平台的 URL 和参数差异
- **FallbackProvider**：主备故障转移，自动熔断与恢复
- **ProviderRegistry**：单例注册中心，根据配置自动创建和管理 Provider

所有模块通过 `ProviderRegistry()` 获取 Provider，**无需关心底层 HTTP 细节**。

### 配置热重载

Config 中心每秒检测 `configs/config.yaml` 的变更。当 **平台 / API Key / 模型 / URL** 发生变化时：

1. `Config._check()` 检测到差异，记录变更日志
2. 自动调用 `ProviderRegistry().reload()` 清空并重建所有 Provider
3. `YukiEngine.provider` 通过 `@property` 实时获取，**无需重启程序**

这意味着修改 `llm_platform` 后，下一次对话立即生效。

---

## 内置 Provider

| 平台名称 | Provider 类 | 内置 URL | 说明 |
|---------|------------|---------|------|
| `deepseek` | `DeepSeekProvider` | `https://api.deepseek.com/v1` | DeepSeek 官方 |
| `ytea` | `YteaProvider` | `https://api.ytea.top/v1` | TeaTop 代理 |
| `dashscope` | `DashScopeProvider` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 阿里云 |
| `openai` | `OpenAICompatibleProvider` | `https://api.openai.com/v1` | OpenAI 官方 |
| `custom` | `OpenAICompatibleProvider` | — | 需手动填写 `base_url` |

> 选择非 `custom` 平台后，**URL 由框架自动提供**，`base_url` 字段会被忽略。只有 `custom` 平台会读取你填写的自定义地址。

---

## 使用方法

### 1. 配置文件 (`configs/config.yaml`)

```yaml
api:
  llm_platform: "deepseek"        # 首选平台名称
  llm_api_key: "sk-xxx"           # 对应平台的 API Key
  llm_base_url: ""                # 仅当 platform 为 "custom" 时生效

  backup_platform: "deepseek"     # 备用平台
  backup_api_key: ""              # 空且平台与首选一致时，自动复用 llm_api_key
  backup_base_url: ""

  vision_platform: "dashscope"    # 视觉模型平台
  image_process_api_key: "sk-yyy"
  image_process_url: ""

model:
  llm: "deepseek-chat"            # 主对话模型
  backup: "deepseek-chat"         # 备用模型
  vision: "qwen3-vl-flash"        # 视觉模型
  disable_thinking: true          # 默认减少 reasoning 输出
```

### 2. 代码中使用

框架内部自动获取，**业务代码无需手动创建**：

```python
from providers.registry import ProviderRegistry

# 获取默认文本对话 Provider（主备 Fallback）
provider = ProviderRegistry().get("default")
result = await provider.chat(messages=[...], model="deepseek-chat")

# 获取视觉模型 Provider
vision = ProviderRegistry().get("vision")
result = await vision.chat(messages=[...], model="qwen3-vl-flash")
```

> `ProviderRegistry` 是单例，首次调用时自动根据 `config.yaml` 初始化所有 Provider。

---

## 平台差异处理

各平台子类通过覆盖 `sanitize_payload()` 处理参数差异：

```python
class DashScopeProvider(OpenAICompatibleProvider):
    def sanitize_payload(self, payload):
        # 视觉模型过滤不支持的 response_format
        if "vl" in str(payload.get("model", "")).lower():
            payload.pop("response_format", None)
        return payload
```

基类还默认注入 `reasoning_effort: "low"`（当 `disable_thinking: true` 时），用于减少 OpenAI o1/o3 等推理模型的 thinking 输出。

---

## 扩展教程：添加新平台

以添加 **SiliconFlow** 平台为例：

### 步骤 1：创建 Provider 类

新建 `providers/siliconflow.py`：

```python
from typing import Dict, Any
from providers.openai_compatible import OpenAICompatibleProvider
from utils.logger import get_logger

logger = get_logger("provider.siliconflow")


class SiliconFlowProvider(OpenAICompatibleProvider):
    """SiliconFlow 平台 Provider"""

    PLATFORM_NAME = "siliconflow"
    DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"

    def sanitize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # 如有平台特有参数差异，在此处理
        logger.debug(
            f"[SiliconFlowProvider/{self.name}] 请求参数: {list(payload.keys())}"
        )
        return payload
```

### 步骤 2：约定注册

只要类满足以下条件，框架会自动发现并注册：
- 继承自 `BaseProvider`（通常通过 `OpenAICompatibleProvider`）
- 定义了 `PLATFORM_NAME` 类属性

```python
class SiliconFlowProvider(OpenAICompatibleProvider):
    PLATFORM_NAME = "siliconflow"
    DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"
```

框架首次初始化 `ProviderRegistry` 时会**自动扫描** `providers/` 目录，读取所有符合条件的类并完成注册。**无需任何额外代码**。

### 步骤 3：使用

```yaml
# configs/config.yaml
api:
  llm_platform: "siliconflow"
  llm_api_key: "sk-your-key"
```

完成。框架会自动创建 `SiliconFlowProvider`，URL 和模型调用无需额外改动。

---

## 常见问题

**Q：如何切换平台？**  
A：修改 `config.yaml` 中的 `llm_platform` 即可，URL 由框架自动切换。**无需重启**，下一次对话生效。

**Q：自定义代理地址（如本地 OneAPI）？**  
A：将 `llm_platform` 设为 `"custom"`，然后在 `llm_base_url` 中填写你的代理地址。非 `custom` 平台填写的 `base_url` 会被忽略。

**Q：备用 Key 为空时会怎样？**  
A：若 `backup_platform` 与 `llm_platform` 相同，且 `backup_api_key` 为空，框架会自动复用 `llm_api_key`。

**Q：如何关闭 thinking 过滤？**  
A：在 `config.yaml` 中设置 `model.disable_thinking: false`。

**Q：为什么配置文件中会自动出现新字段？**  
A：程序启动时会自动将代码中定义的新配置字段补全到内存，**退出时自动写回文件**，确保配置文件始终与代码定义保持同步。
