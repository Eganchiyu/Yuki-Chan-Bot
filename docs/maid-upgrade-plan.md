# 小女仆（Maid）能力升级：计划与交接文档

> 状态：P0+P1 未开工（本文件即开工说明）。P2/P3 仅记录设计，不实施。
> 最后更新：2026-10-21

## 1. 当前环境与仓库状态

| 项目 | 值 |
| --- | --- |
| 工作目录 | `/home/asumi/Yuki` |
| 远端 | `git@github.com:Eganchiyu/Yuki-Chan-Bot.git`（已从 HTTPS 改为 SSH） |
| 当前分支 | `fix/maid-env-vision-prefetch` |
| HEAD | `b7754de docs: 记录仓库接回与测试基线` |
| 本地 `main` | 与 HEAD 同一提交，未推送 |
| Yuki 运行解释器 | `/home/asumi/miniconda3/envs/yuki/bin/python`（3.11.15，主进程 `python main.py`） |
| 小女仆环境 | `maid_venv`，已原地修复（`home=/home/asumi/miniconda3/envs/yuki/bin`，pip 24.0，197 个包保留） |
| 备份 | `/tmp/maid_bin.bak`、`/tmp/maid_pyvenv.cfg.bak`（临时目录，重启机器会丢） |

### 测试基线
```bash
cd /home/asumi/Yuki
/home/asumi/miniconda3/envs/yuki/bin/python tests/run_tests.py
```
- 当前：`passed=86 failed=23`，其中 3 个 `LOAD ERROR`。
- 23 项失败在 `origin/main` 基线上同样存在（缺依赖、真实 LLM 调用失败、终端宽度假设），
  **判定为环境性失败，不是回归**。新增改动后对比该基线即可。
- 注意：`tests/test_config.py`、`test_github_monitor.py`、`test_napcat_gateway.py` 加载失败是
  缺依赖/单例冲突，不要在本次任务里顺手修。

## 2. 已完成（本分支内）

1. `fix(maid)`：虚拟环境失效自愈
   - `_is_maid_env_usable()` 真实执行 `-c "import encodings, sys"`，并校验 `pyvenv.cfg` 的 `home`。
   - pip 统一走 `python -m pip`（`_run_pip` / `_get_maid_pip_cmd`），不再依赖 `bin/pip` 脚本 shebang。
   - `_upgrade_maid_env()`：版本一致时 `venv.EnvBuilder(upgrade=True)` 原地修复，保留 site-packages；
     失败才 `_rebuild_maid_env()` 全量重建。`_repair_maid_pip()` 用 ensurepip 兜底。
2. `fix(vision)`、`fix(utils)`、`docs`：与本次 Maid 升级无关，仅作为上下文。

## 3. 本次目标（P0 + P1）

原则：**只改 `core/maid/`，外加少量接入点**；不碰主链路业务逻辑；不引入新运行时依赖。

### P0-1 安全改动守卫
- 新增 `safe_edit_file(path, old_text, new_text)`（`core/maid/maid_runtime.py`）：
  - 限制在项目根目录内（`os.path.commonpath`），拒绝 `maid_venv/`、`data/`、`configs/`。
  - 写入前备份到 `backups/maid_edit/<YYYYmmdd_HHMMSS>/<相对路径>`。
  - 修改后若为 `.py`，执行 `py_compile`；失败则自动还原并返回错误详情。
  - 返回：备份路径、改动行数、编译结果。
- 提示词明确：改代码只能用它，禁止用 `terminal` 直接 `sed`/重定向改 `.py`。
- 验收：语法错误补丁 → 文件内容不变 + 返回错误；正常补丁 → 备份存在且 `py_compile` 通过。

### P0-2 任务状态快照（可诊断 / 可续跑）
- 新文件 `tasks/state/<task_id>.json`，每轮工具执行后写一次，字段：
  `task_id, goal, chat_id, round, last_step, messages, created_at, updated_at, status`
  （`messages` 直接存，单条工具结果已被 `_truncate_text` 限制在 3000 字符内）。
- `finish` / 超时 / 异常退出时删除快照，并在汇总里记 `last_state` 路径。
- 对外接口（`core/maid/maid_memory.py`）：
  `save_task_state() / load_task_state() / list_unfinished_states()`。
- **不做自动续跑**：启动自动 resume 会往群里发消息，需机主另行决定；本期只提供
  `maid_evolution_loop(resume_state=...)` 的入口能力 + 人工/后续接入。

### P0-3 预算双闸
- `core/maid/maid_common.py` 增加 `MAID_MAX_WALL_SECONDS = 900`（15 分钟）。
- loop 每轮开始检查 `time.monotonic()`，超限 → 走“优雅超时”分支（带 `last_step`，状态 `timeout`），
  不再继续消耗 LLM 调用。
- 验收：把上限临时调成 5 秒的单元测试，任务应在 2 轮内返回 `timeout`，且不再调用 LLM 第二次。

### P1-1 任务历史索引 + 检索
- `logs/task_index.jsonl`，每次任务结束追加一行：
  `{task_id, goal, status, result(≤500字), rounds, elapsed, chat_id, skills, files, finished_at}`
- 工具 `search_history(keyword=None, limit=10)`：按 goal/result 子串匹配，返回摘要列表。
- 任务开始时把**最近 3 条**摘要（每条 ≤120 字）注入 prompt，格式：
  `[最近任务] 2026-10-21 13:00 | finished | 目标：xxx | 结果：xxx`
- 验收：跑一次任务 → index 多一行；`search_history` 能命中；新任务 prompt 含最近摘要。

### P1-2 跨会话留言（notes）
- `memory/maid_notes.jsonl`，字段：`id, ts, content, tags[], chat_id, read_at`。
- 工具：`leave_note(content, tags)`、`read_notes(tags=None, unread_only=True, limit=20)`。
- 任务开始时注入未读 note（≤10 条），并在成功注入后写 `read_at`（避免反复占用上下文）。
- 注意：`memory/` 已被 `.gitignore` 忽略，笔记不会进仓库。
- 验收：写 note → 新任务 prompt 出现 → 再次任务不重复出现。

### P1-3 草稿固化 + 技能成功率
- 工具 `promote_skill(name, summary, self_test=None)`：
  - 源：`workspace/<name>.py`；目标：`skills/<name>.py` + `skills/<name>.md`（首行 = summary）。
  - `self_test` 为必填的断言式自测代码（或缺省时拒绝固化），在 maid_venv 中执行，
    退出码 0 才允许固化；已存在同名技能时先备份到 `backups/skills/`。
- `list_skills()` 增加最近 30 天成功率（从 `task_index.jsonl` 统计 `skills` 字段），
  格式：`- name: 简介（近30天 成功x/失败y）`。
- 验收：自测失败 → 不落盘；成功 → `skills/` 两个文件存在，`read_skill` 可读。

### P1-4 汇报增强
- `build_maid_report()` 追加：耗时、轮次、改动文件、trace 路径。
- 保持 `【小女仆完成! 小女仆汇报】` 前缀不变（上层有解析/测试依赖该格式）。

## 4. 需要改的文件清单

| 文件 | 改动 |
| --- | --- |
| `core/maid/maid_common.py` | 新增 `MAID_MAX_WALL_SECONDS`、`TASK_INDEX_FILE`、`NOTES_FILE`、`TASK_STATE_DIR` |
| `core/maid/maid_memory.py`（新建） | 索引读写、notes 读写、状态快照读写 |
| `core/maid/maid_runtime.py` | `safe_edit_file()`、`promote_skill()`、`list_skills()` 成功率 |
| `core/maid/maid_loop.py` | 新工具分发、预算检查、快照写入、开始时注入历史/笔记、结束时写索引 |
| `core/maid/maid_prompt.py` | 新工具说明 + 使用纪律（改代码只走 `safe_edit_file`、固化需自测） |
| `core/maid/maid_boundary.py` | `build_maid_report()` 增加耗时/轮次/文件 |
| `core/maid/maid.py` | 导出新符号（保持 `__all__` 一致） |
| `tests/test_maid_memory.py`（新建） | 索引、notes、快照、预算、promote 的单元测试 |

## 5. 明确不做（留待 P2/P3，需单独确认）

- `ask_yuki` 半双工提问 / 任务挂起恢复。
- `propose_patch` 提案式改代码。
- 任何形式的热重载（`importlib.reload` 会残留旧对象与重复注册的 asyncio 任务/定时器；
  正确做法是外置 supervisor + `os.execv` 自重启，属于运维层决策）。
- 多 worker 并行消费 `maid_task_queue`。

## 6. 约束与坑

1. **单进程**：`maid_evolution_loop` 在 Yuki 的事件循环里跑。任何新工具不得阻塞
   （文件 IO 一律 `asyncio.to_thread`，子进程用 `create_subprocess_exec` + `wait_for`）。
2. `_clean_workspace()` 在任务结束时清空 `workspace/`，**promote 必须在 finish 前完成**。
3. 所有新工具的输出都要过 `_truncate_text`，避免撑爆上下文。
4. 不要提交：`configs/config.yaml`（含 key）、`data/`、`models/`、`logs/`、`memory/`、`maid_venv/`、
   `skills/`、`backups/`（均已在 `.gitignore` 内）。
5. 推送分支用 `fix/maid-env-vision-prefetch`，**不要直推 `main`**。
6. 别动 `tests/test_maid.py`（占位失败用例）和其它环境性失败用例。

## 7. 恢复上下文 / 开发流程

```bash
cd /home/asumi/Yuki
git status && git log --oneline -3
/home/asumi/miniconda3/envs/yuki/bin/python tests/run_tests.py            # 全量
/home/asumi/miniconda3/envs/yuki/bin/python tests/run_tests.py test_maid_memory  # 单模块
./maid_venv/bin/python -c "import encodings; print('env ok')"             # 小女仆环境自检
```

实施顺序建议：`maid_common` → `maid_memory` → `maid_runtime` → `maid_loop` → `maid_prompt` →
`maid_boundary`/`maid.py` → 测试 → 更新 `docs/Log.md` → 提交。

每个任务独立提交，前缀沿用 `feat(maid): ...`；完成后更新本文件顶部的状态行。

## 8. 未决问题（下个 session 先确认）

1. `MAID_MAX_WALL_SECONDS` 取 900 秒是否合适（当前 20 轮 × LLM 延迟，实际约 3~8 分钟）？
2. `promote_skill` 的自测是“必填”还是“允许模型跳过、但记录未自测标记”？
3. 历史注入条数 3 条、notes 注入 10 条是否够用（可先用常量，跑一周再调）？
4. `build_maid_report` 格式变更是否需要同步 `tests/`（当前无对应断言，预计安全）。
