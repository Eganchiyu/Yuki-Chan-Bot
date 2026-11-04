# 开发与 LLM 交接指南

本文档面向后续接手本项目的 LLM Agent 与开发者，提供环境事实、开发闭环、测试命令与安全红线。

---

## 一、LLM 交接必读（环境事实）

1. **工作目录与生产形态**：
   - 宿主机项目根路径：`/home/asumi/Yuki`
   - 线上 Yuki 运行在 Docker 容器 `yuki`（镜像 `yuki:base`）内，**容器与宿主机使用完全相同的绝对路径挂载**（`/home/asumi/Yuki:/home/asumi/Yuki:ro`），否则 `file:///` 发送本地图片/表情包会因宿主机 NapCat 找不到路径而静默失败。
   - 容器内代码树是 `:ro` 只读挂载；修改宿主机上的 Python 源码后，**必须重启 `yuki` 容器**（`bash deploy/run.sh` 或经 `staging/` 请求重启）才会在线上生效。
2. **Python 解释器（极其重要）**：
   - 本机唯一完整可用的 Python + pytest 环境是：**`~/miniconda3/envs/yuki/bin/python`**（Python 3.11 + pytest 9.2 + chromadb + aiohttp）。
   - **不要用** `/usr/bin/python3`（无项目依赖与 pytest），**不要用** `./maid_venv/bin/python`（跨机残留，缺 `libpython3.11.so`）。
3. **安全红线（参见 `docs/evolution-charter.md`）**：
   - **数据优先**：`yuki_memory/`、`data/`、`memory/` 是不可再生资产，**严禁删除、清空、覆盖或重建**。
   - **人格硬禁区**：未经机主本人明确要求，任何自动/半自动流程不得修改 `core/prompts.py` 中的人格设定与 `configs/config.yaml`。
4. **开发日志**：
   - 每次完成有效开发或排障后，在 `/home/asumi/Yuki/memo/Log.md` 末尾追加简短记录（做了什么、验证结果、当前状态）。

---

## 二、测试与校验

测试套件位于 `tests/`（共 11 个测试文件，全部离线 mock，无需网络和真实 API Key）：

```bash
# 1. 本机运行全量测试（推荐）
~/miniconda3/envs/yuki/bin/python -m pytest -q

# 2. 运行单个测试文件或用例
~/miniconda3/envs/yuki/bin/python -m pytest tests/test_toolchain.py -q
~/miniconda3/envs/yuki/bin/python -m pytest tests/test_memory.py -k "recall" -q

# 3. 在只读容器环境中运行测试
docker run --rm -v /home/asumi/Yuki:/home/asumi/Yuki:ro -w /home/asumi/Yuki yuki:base python -m pytest -q

# 4. 跑完整 5 道自进化校验门（compileall / import / pytest / YUKI_DRY_RUN / health）
bash deploy/verify.sh
```

**测试编写约定**：
- 新增测试按模块归入现有 11 个 `tests/test_*.py` 文件（见 `tests/README.md`）。
- 涉及文件落盘一律使用 `tmp_path` 或 `monkeypatch`，不得污染 `data/`、`logs/`、`yuki_memory/`，确保在 `:ro` 挂载的容器内也能全绿通过。

---

## 三、常见开发任务手册

### 3.1 新增配置项
1. 打开 `config.py`，在对应 `@dataclass`（如 `ModelConfig`、`RAGConfig`）添加字段，并在 `_ATTR_MAP` 中添加 `("ATTR_NAME", (("section", "key"), default_val, "中文注释"))`。
2. 如需特殊类型转换，在 `Config` 类中增加 `@property`。
3. 业务代码直接通过 `from config import cfg; cfg.ATTR_NAME` 读取（支持每秒自动检查 mtime 热重载）。

### 3.2 新增主模型 Function Call 工具
1. 在 `core/tools/tools_*.py` 中实现异步函数 `async def xxx_tool(context: ToolContext, ...) -> ToolResult`。
2. 在 `core/tools/tools.py` 的 `TOOL_SPECS` 中注册 `ToolSpec`。若工具输出不需要写入持久化对话历史（如内部状态更新），设 `persist_result=False`。
3. 在 `tests/test_toolchain.py` 补充离线单测。

### 3.3 新增小女仆技能 (`skills/`)
- `skills/` 在容器内是读写挂载，修改后**立即生效，无需重启容器**。
- 每个技能由 `skills/<name>.py`（可执行脚本或函数）和 `skills/<name>.md`（第一行为技能简介，后续为调用说明）组成。

### 3.4 修改入站指令或唤醒规则
- 群聊/私聊斜杠指令（`/开启`、`/关闭`、`/重启`、`/刷新`、`/help`）、`@` 唤醒、白名单 BOT 过滤、戳一戳均在 `modules/QQNapcatListen/listen_main.py`。
- 对应单测在 `tests/test_napcat.py`。

### 3.5 修改宿主守护或部署脚本 (`deploy/`)
- 修改 `deploy/supervisor.py`、`deploy/reviewer.py`、`deploy/maid_runner.py`、`deploy/netwatch.py` 后，需机主执行 `sudo systemctl restart yuki-supervisor`（或对应服务名）才会生效。
- 让线上 `yuki` 容器加载最新代码：
  - 宿主机有 docker 权限时：直接运行 `bash deploy/run.sh`（约 7~10 秒完成重建）。
  - 容器内部或无 docker 权限时：往 `staging/restart_<时间戳>/request.json` 写入 `{"type": "restart"}`，由宿主 `yuki-supervisor` 在 3 秒内自动快照并重建容器。

---

## 四、代码与 Git 规范

- **代码风格**：Python 3.11+，4 空格缩进，内部模块统一使用 `from utils.logger import get_logger` 记录日志，阻塞操作在异步链路中必须用 `asyncio.to_thread()` 包装。
- **Git 提交**：只 `git add` 本次任务修改的具体文件路径，**严禁 `git add -A` 或 `git add .`**（防止把 `staging/`、`output/`、临时产物或他人未提交改动卷入提交）。
- **提交信息**：`<type>(<scope>): <简短中文或英文说明>`（如 `feat(tools): ...`、`fix(pipeline): ...`、`docs: ...`）。
