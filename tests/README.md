# tests/ — 测试说明

## 测试环境（本机）

```bash
~/miniconda3/envs/yuki/bin/python -m pytest -q
```

- 解释器固定用：`~/miniconda3/envs/yuki/bin/python`（Python 3.11，pytest 9.2.0，pytest-asyncio 1.4.1）
- **不要用** `/usr/bin/python3`（没装 pytest）、也不要试 `maid_venv/bin/python`
- 全量套件、单文件、单用例：

```bash
cd /home/asumi/Yuki
~/miniconda3/envs/yuki/bin/python -m pytest -q
~/miniconda3/envs/yuki/bin/python -m pytest tests/test_memory.py -q
~/miniconda3/envs/yuki/bin/python -m pytest tests/test_memory.py::test_rag_scoring_boosts_and_decay -q
```

容器里跑（Docker 镜像已内置 pytest）：

```bash
docker run --rm -v /home/asumi/Yuki:/home/asumi/Yuki:ro -w /home/asumi/Yuki yuki:base python -m pytest -q
```

## 测试模块列表

| 文件 | 探测范围 |
| --- | --- |
| `test_config.py` | 配置默认值、监控默认关闭、YAML 读写/合并/损坏备份、路径解析、全局 `cfg` 兼容 |
| `test_logger.py` | 终端宽度折行、窄屏布局、多行折叠、内嵌 dict 压缩、噪声过滤、文件截断与堆栈保留 |
| `test_llm_client.py` | URL 规范化、payload 清洗、空回复判定、空回复/故障重试与防空提示、耗尽降级、备用线路非视觉降级 |
| `test_napcat.py` | 本地假 OneBot 帧隔离与断线重连、CQ 码解析、成员缓存、`@` 检测、防抖唤醒、BOT 白名单、戳一戳、`/刷新` 指令 |
| `test_vision.py` | 原生多模态图块路由与上限、短索引防串图、`[图片占位符]` 兜底清扫、空描述不入缓存、入站后台预取与 TTL |
| `test_memory.py` | RAG 召回打分/衰减/覆盖率、Chroma `where_document` 快查、跨轮召回缓存 `RecallCacheStore`、小本本 `NotebookStore` |
| `test_reply_format.py` | `<layout>` / `[MEME:]` 容错与剥离、DSML/`<tool_call>` 文本工具调用提取、`HistoryManager` 标记自修复、`WORKING_NOTICE` 收尾 |
| `test_toolchain.py` | `ToolSpec` 与注册表、`ToolCallManager` 保序执行与 JSON 截断自纠、`skip` 静默抹痕、`send_qq_file`、`parse_rich_message` |
| `test_pipeline.py` | `SessionPipeline` 阶段流转与元数据、破冰指令与计数、`reply_watch` 自动订阅与超时提醒、空闲总结、`ModeManager` |
| `test_maid.py` | 小女仆读文件防爆、墙钟预算、JSON 错误容忍、任务快照/索引/`resume_task` 续跑、终端分级审批、看图降级 |
| `test_github_monitor.py` | GitHub Monitor 状态持久化与 PushEvent Compare API 渲染 |

## 约定

- 套件必须**全离线**：不联网、不需要真实 API Key（见 `pyproject.toml` 的 `[tool.pytest.ini_options]`，`asyncio_mode = "auto"`，`testpaths = ["tests"]`）
- `conftest.py` 已把项目根塞进 `sys.path`，测试文件里不用再写 `sys.path` hack
- 落盘一律用 `tmp_path` 或 `monkeypatch`，不要在仓库或 `/tmp` 留未清理产物（容器是只读挂载）
