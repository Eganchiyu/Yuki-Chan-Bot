# 小女仆旧版内置循环后端（Legacy Maid Loop）归档

## 1. 这段代码是干什么的
在切换至宿主机 `DeepSeek Harness (dsh)` 执行器（`core/maid/maid_harness.py` + `deploy/maid_runner.py`）之前，小女仆在容器内自行实现了一套基于 JSON 输出格式的 Function Call 循环与工具集。本目录保存该完整旧版后端：

| 文件 | 原路径 | 职责说明 |
|---|---|---|
| `maid_loop.py` | `core/maid/maid_loop.py` | 内置多轮 JSON Agent 主循环（`maid_evolution_loop` / `call_cloud_maid_robust`），含轮次预算（40 轮）、错误轮容忍（5 次）、墙钟预算、图片消息单轮后降级与 23 个工具手工分派 |
| `maid_prompt.py` | `core/maid/maid_prompt.py` | 旧内置循环的 `MAID_SYSTEM_PROMPT`（包含 23 个工具的 JSON 调用说明与 `EVOLUTION_CHARTER` 注入） |
| `maid_runtime.py` | `core/maid/maid_runtime.py` | `maid_venv` 隔离虚拟环境管理（创建/原地升级/重建/自动解析 AST 装包）、临时与固化 Skill 读写执行（`write_temp_skill` / `run_skill`）、受限终端执行（`terminal_command_maid`）与本地图片压缩读取（`prepare_image_message`） |
| `maid_approval.py` | `core/maid/maid_approval.py` | 终端命令分级授权：`classify_command`（`allow` / `ask` / `block` 硬拦截）与 `judge_by_yuki`（由继承会话上下文的 Yuki 静默判定可疑命令）、`build_approver` |
| `maid_selfevolve.py` | `core/maid/maid_selfevolve.py` | 旧循环专用的自进化工具封装：`propose_patch`、`verify_patch`、`request_self_reload`、`request_restart`、`read_last_result`（在 Harness 后端中，dsh 直接按 `deploy/dsh-home/AGENTS.md` 读写 `staging/` 目录） |
| `maid_worklog.py` | `core/maid/maid_worklog.py` | 跨任务交接工具：`list_previous_work` 与 `read_work_trace`（读取 `logs/task_index.jsonl`、`logs/self_evolve.jsonl` 与 `logs/trace_<id>.md`） |
| `maid_tools_legacy.py` | `core/maid/maid_tools.py` | 完整备份原 `maid_tools.py`（其中 `search_diary_fast` 仍保留在 `core/maid/maid_tools.py` 供主模型 `search_diary` 工具调用；其余 `read_file_content`、`list_directory_content`、`manage_timer_task_maid`、`browser_search_maid`、`amap_search_maid` 为旧循环专用） |
| `maid_memory_legacy.py` | `core/maid/maid_memory.py` | 完整备份原 `maid_memory.py`（其中 `append_task_index` 与 `delete_task_state` 仍保留在 `core/maid/maid_memory.py` 供 `maid_harness.py` 使用；其余 `save_task_state`、`load_task_state`、`list_unfinished_states`、`build_startup_context`、`resume_state`、`build_resumed_messages` 为旧循环完整 messages 快照续跑专用） |
| `maid_common_legacy.py` | `core/maid/maid_common.py` | 完整备份原 `maid_common.py`（含 `MAID_VENV_DIR`、`MAX_MAID_ROUNDS`、`clean_json_output`、`clean_code_block`、`_truncate_text`、`_decode_process_output`、`_extract_json_from_mixed` 等旧循环辅助函数） |
| `maid_facade_legacy.py` | `core/maid/maid.py` | 原门面全量导出及 `if __name__ == "__main__":` CLI 调试入口 |
| `test_maid.py.original` | `tests/test_maid.py` | 针对旧循环预算、快照续跑、`read_file_content` 与终端审批的原单元测试 |

## 2. 原来的埋点在哪里
- **后端切换点**：`core/maid/maid_backend.py`，原通过环境变量 `YUKI_MAID_BACKEND=legacy` 切换到 `core.maid.maid_loop.maid_evolution_loop`，默认走 `core.maid.maid_harness.harness_evolution_loop`。
- **Worker 审批注入点**：`core/maid/maid_worker.py` 中原调用 `approver = build_approver(...)` 并传给 `maid_evolution_loop(..., approver=approver)`（而 `maid_harness.py` 首行即 `del approver` 忽略该参数）。
- **门面导出点**：`core/maid/maid.py`。

## 3. 怎样接入
若需要恢复 `legacy` 内置循环后端：
1. 将本目录下的模块复制回 `core/maid/`：
   ```bash
   cp _archive/maid_legacy/maid_loop.py core/maid/maid_loop.py
   cp _archive/maid_legacy/maid_prompt.py core/maid/maid_prompt.py
   cp _archive/maid_legacy/maid_runtime.py core/maid/maid_runtime.py
   cp _archive/maid_legacy/maid_approval.py core/maid/maid_approval.py
   cp _archive/maid_legacy/maid_selfevolve.py core/maid/maid_selfevolve.py
   cp _archive/maid_legacy/maid_worklog.py core/maid/maid_worklog.py
   cp _archive/maid_legacy/maid_tools_legacy.py core/maid/maid_tools.py
   cp _archive/maid_legacy/maid_memory_legacy.py core/maid/maid_memory.py
   cp _archive/maid_legacy/maid_common_legacy.py core/maid/maid_common.py
   cp _archive/maid_legacy/maid_facade_legacy.py core/maid/maid.py
   ```
2. 在 `core/maid/maid_backend.py` 中恢复按环境变量切换逻辑：
   ```python
   import os

   BACKEND = (os.environ.get("YUKI_MAID_BACKEND") or "harness").strip().lower()
   if BACKEND == "legacy":
       from core.maid.maid_loop import maid_evolution_loop as _legacy_loop
       async def maid_evolution_loop(user_goal, chat_id=None, approver=None, mode=None, **kwargs):
           return await _legacy_loop(user_goal, chat_id, approver)
   else:
       from core.maid.maid_harness import harness_evolution_loop as maid_evolution_loop
   ```
3. 在 `core/maid/maid_worker.py` 中恢复 `build_approver` 构造并传入 `maid_evolution_loop`。
4. 启动时设置环境变量 `YUKI_MAID_BACKEND=legacy` 即可使用旧内置循环。
