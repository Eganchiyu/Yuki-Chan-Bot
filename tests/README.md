# tests/ — 测试说明

## 测试环境

容器内定向运行（推荐，镜像已内置完整依赖）：

```bash
docker exec yuki python -m pytest tests/test_memory.py -q
```

或宿主机 conda 环境：

```bash
~/miniconda3/envs/yuki/bin/python -m pytest tests/test_memory.py -q
```

## 测试模块地图（按领域内聚）

| 文件 | 覆盖范围 |
| --- | --- |
| `test_config.py` | 配置 Schema/Loader、多 Provider 队列、YAML 读写合并与损坏备份、旧版大写属性兼容 |
| `test_logger.py` | 终端宽度折行、多行折叠、内嵌 dict 压缩、噪声过滤、文件截断与堆栈保留 |
| `test_llm_client.py` | URL 规范化、多节点熔断顺延与自动恢复、空回复重试、非原生视觉渠道自动降级 |
| `test_napcat.py` | OneBot WS 帧隔离与重连、CQ 码解析、文件动作上传、`/刷新` `/切换` `/查询` `/强制关闭` 指令 |
| `test_vision.py` | 原生多模态图块路由与配额、短索引防串图、空描述防缓存、入站后台预取与 TTL |
| `test_memory.py` | RAG 召回打分/衰减/Chroma `$and` 去重、跨轮召回缓存、双区小本本、群黑话挖掘匹配、情境表达习惯 |
| `test_reply_format.py` | `<layout>` / `[MEME:]` 清洗剥离、文本工具调用提取、分片 `HistoryManager` 迁移与修复、LLM 语义断句 |
| `test_toolchain.py` | `ToolSpec` 与注册表、`ToolCallManager` 执行与 JSON 自纠、`skip` 静默抹痕、富文本与本地发文件 |
| `test_pipeline.py` | `SessionPipeline` 阶段编排、单 System 组装、破冰、追击订阅、锚点并发写日记与对话过滤 |
| `test_sft_logger.py` | SFT 全量轨迹脱敏落盘、图片资产归档、出站 `message_id` 索引、主人贴表情与引用打标 |
| `test_maid.py` | 小女仆 Harness 契约、并行编号与 `stop_maid` 强制叫停、自进化路径分级、重启补报 |
| `test_focus_contract.py` | 多域聚焦架构通用契约（`FocusDomain` / `FocusManager` / `ToolView` / 退出覆写自证） |
| `test_focus_snapshot.py` | 聚焦同轮视图切换、防同轮重入、闲置超时退出、同批退出防泄漏、启动孤儿清扫 |
| `test_tool_hands.py` | 手机 ADB 基础动作、控件树压缩、红框标注截图与 `ToolHistoryPruner` 闲置折叠 |
| `test_tool_phone_macro.py` | 手机组合技录制/去噪/参数化回放、`phone` 聚焦进出、`AndroidDriver` 压缩退避与轨迹记录 |
| `test_art_focus.py` | 艺术创作聚焦模式、角色资产登记检索、无参提示词抽卡（含 Zako 语料）与 `/抽图` 直达跳跃 |
| `test_browser_focus.py` | 浏览器 CDP 聚焦驱动、OOPIF 穿透、视口 Top 控件排序、自适应标注截图与省图策略 |
| `test_mode_router.py` | 多主循环模式路由（`chat`/`debate`/`workshop`）、非活跃群冻结缓冲与补台派发 |
| `test_autonomous_sandbox.py` | 自主轮准入判定、内心辩论检索窗、复盘分流、工坊续作、五层记忆与心情高涨闭环 |
| `test_github_monitor.py` | GitHub Monitor 状态持久化与 PushEvent Compare API 卡片渲染 |

## 约定

- 套件必须**全离线**：不联网、不需要真实 API Key（`pyproject.toml` 已配置 `asyncio_mode = "auto"` 与 `asyncio_default_fixture_loop_scope = "function"`）。
- `conftest.py` 自动将 `sft_trace_logger` 与 `init.GROUP_STATE_FILE` 隔离至 `tmp_path`，测试落盘一律使用 `tmp_path` 或 `monkeypatch`。
