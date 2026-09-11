# YukiV6 项目开发公约

本文件定义 YukiV6 项目的工程约定，所有开发者（含 AI）必须遵守。规则优先以现有代码为最终依据，本文件仅索引关键约束。

---

## 一、代码规范

### 1.1 命名与风格

- **文件命名**：小写 + 下划线，按职责分目录分文件，如 `core/tools/tools_media.py`、`core/engine/engine_reply.py`；测试文件以 `test_` 开头。
- **类**：PascalCase（`YukiEngine`、`HistoryManager`）。
- **函数/方法/变量**：snake_case；私有加 `_` 前缀（`_get_data_locked`）；常量/配置属性全大写（`cfg.TOOL_CALL_TIMEOUT` 之类以 `cfg.*` 访问）。
- **异步**：用 `async def` 声明，不加 `async_` 前缀；内部一律 `await`，避免在 async 中做阻塞 IO（长阻塞用 `asyncio.to_thread`）。
- **缩进**：4 空格，不用 Tab；单行建议 ≤100 字符；导入顺序：标准库 → 第三方 → 项目内部。
- **注释/docstring**：使用中文，复杂逻辑必须注释，公共函数写 docstring。

### 1.2 配置访问（config.py）

- 配置以 `config.py` 中 dataclass 为单一数据源，运行时统一 `from config import cfg` 访问，**禁止散落硬编码常量**（API Key、超时、路径等一律走 `cfg`）。
- 新增配置项：在对应 dataclass 用 `config_field()` / `config_field_factory()` 定义，然后运行 `python config.py sync` 同步 yaml。
- `configs/config.yaml` 含敏感字段，已在 `.gitignore`，禁止提交。

### 1.3 工具链协议（core/toolchain.py）

- 新增工具：在 `core/tools/tools_*.py` 内实现 handler，返回 `ToolResult`（成功失败统一封装），再到 `core/tools/tools.py` 的 `TOOL_SPECS` 中登记 `ToolSpec(name, description, parameters, handler)`。
- handler 签名固定为 `handler(context, **args)`，入参来自 LLM 的 `arguments` JSON；必须抛异常或返回 `ToolResult.failure(...)` 而非裸报错。
- 工具内使用 `ToolResult(success=..., content=..., data=..., error=...)`；不要直接写 CQ 文件码，发文件优先用 `send_qq_file`。

### 1.4 模块结构

- 职责单一、按领域分包：`core/engine/*`（门面 + decision/diary/monitor/reply 子服务）、`core/tools/*`（工具）、`core/maid/*`（小女仆）、`core/toolchain.py`（注册与调用执行）。
- 新增/调整模块结构须同步 `docs/architecture.md`。

### 1.5 并发与数据安全

- 共享状态用锁保护：`HistoryManager` 用 `threading.Lock`；写入用「临时文件 + `os.replace`」实现原子落盘，杜绝半写。
- 批量/阻塞操作后台化：用 `asyncio.create_task` / `asyncio.to_thread`；避免在 async 函数里用阻塞文件/网络调用。

### 1.6 网络请求（必须走 utils.http_client）

所有外部 HTTPS 请求统一经 `utils/http_client.py`，禁止直接用系统默认证书链，否则会触发 `[ASN1: NOT_ENOUGH_DATA]` 类 SSL 错误。

- aiohttp：`aiohttp.ClientSession(connector=create_tcp_connector(), timeout=...)`。
- urllib：`utils.http_client.urlopen()`。
- requests / httpx：`verify=requests_verify()`。
- WebSocket：`wss://` 必须传 `ssl=create_ssl_context()`，`ws://` 不需要。

```python
from utils.http_client import create_tcp_connector
async with aiohttp.ClientSession(connector=create_tcp_connector(), timeout=aiohttp.ClientTimeout(total=120)) as session:
    async with session.get(url) as resp:
        data = await resp.read()
```

---

## 二、Git 提交规范

- 信息格式 `type(scope): subject`，subject 用中文、≤50 字符、不以句号结尾；`type` ∈ feat/fix/refactor/docs/style/perf/test/chore。
- 一次提交只做一件事，避免无关文件；提交前检查：无敏感信息、`.gitignore` 正确、相关改动可运行。

---

## 三、文档规范

以下文档须随对应代码变更同步更新：

| 文档 | 更新时机 |
|------|----------|
| `docs/changelog.md` | 每次提交，记录到 `[未发布]` |
| `docs/architecture.md` | 模块/职责/数据流变更 |
| `docs/development-plan.md` | 任务与里程碑变更 |
| `README.md` | 项目说明变更 |

新增工具时请参考 `docs/toolchain-usage.md` 的既有约定，避免文档与代码脱节。

---

## 四、安全与发布

- **敏感信息**：API Key / 密码 / token 一律走 `cfg` + 环境变量，禁止硬编码；通过 `.gitignore` 排除，提交前自查。
- **版本号**：遵循语义化版本 `vX.Y.Z`；发版时把 `docs/changelog.md` 的 `[未发布]` 换成版本号，再打 Tag 与 GitHub Release。

---

## 五、AI 助手约束

- **必须**：遵循上文命名/网络/工具链规范；保留既有对外入口的兼容（如 `YukiEngine` 的门面方法），不破坏现调用方；改动最小化。
- **禁止**：硬编码敏感信息、删除现有功能、引入无必要的新依赖、忽略错误处理与降级。
- **变更后**：更新 `docs/changelog.md`，必要时更新架构/规划文档。
- **运行/测试/lint 前**：先激活 uv 项目虚拟环境（`.venv/Scripts/activate`）。

> 本文件只收录与代码直接相关的硬规则；凡发现与现有代码冲突，以代码为准并反馈修正本文件。

**文档版本**：v2.0.0
**最后更新**：2026-09-11