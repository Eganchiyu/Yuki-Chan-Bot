# 小女仆（Maid）能力升级：实施记录

> 状态：已实施（S1–S7 全部完成）。
> 最后更新：2026-10-22

## 1. 背景

原计划（P0/P1 工程方案：安全改动守卫、跨会话留言、技能固化、预算双闸）在评审后被砍。
机主给出的实际阻碍是运行体感问题：

1. `write_and_run_temp_skill` 摩擦大，模型倒向 terminal；terminal 的关键词黑名单常误杀正常命令。
2. 没有读取本地图片的能力。
3. 20 轮上限不够用，网络/解析失败还占轮次。
4. 每个 session 相互隔离，任务无法断点续跑。

原则：**不做工程解，只补功能缺口；同时尽量不抢占模型注意力。**

## 2. 明确砍掉（不再实施）

- `safe_edit_file`（权限已是最高，不考虑安全）
- `leave_note` / `read_notes`（小题大做）
- `promote_skill` / 技能固化 / 技能成功率（改为记忆驱动，整块不做）
- `search_history`（由自动摘要注入替代）

## 3. 已实施

### S1 文件读取防爆（`maid_tools.py`）
`read_file_content(path, max_lines, offset, max_bytes)`：单次 64KB、单行 2000 字符、
按行截断，返回总行数/字节数与续读 `offset`；content 含 NUL 或目录直接报错。
曾有 base64 文件把上下文顶到 98 万字符，现在 900KB 单行文件只返回约 2KB。

### S2 预算与轮次（`maid_common.py` / `maid_loop.py`）
- `MAX_MAID_ROUNDS = 40`（有效轮）
- `MAX_MAID_ERRORS = 5`：网络失败 / JSON 解析失败独立计数，**不占有效轮**
- `MAID_MAX_WALL_SECONDS = 900`：每轮开头检查，超限走带 `last_step` 的 timeout 分支
- `TERMINAL_MAX_TIMEOUT` 提到 600s

### S3 断点（`maid_memory.py` 新建 + loop）
- `tasks/state/<task_id>.json` 每轮覆盖写（messages 单条 ≤3000、剔除图块）
- 正常结束删快照；超时/中断保留快照，`status=interrupted`
- 任务开始注入最近 3 条任务摘要（≤120 字/条）+ 未完成快照提示
- `resume_task(task_id)`：读回消息续跑，**每次任务只允许恢复一次**（否则会重置轮次死循环）
- `logs/task_index.jsonl` 每任务一行

### S4 终端授权（`maid_approval.py` 新建）
- 硬拦截只剩：`sudo`、关机/重启、`mkfs`/`format X:`、`dd of=/dev/`、删根目录、fork 炸弹
- `rm -rf /tmp/x` 不再被 `"rm -rf /"` 子串误杀，改为走授权判定
- 可疑命令（删改文件、装依赖、kill、git 历史操作、`curl|bash`、写项目外路径）交给
  **继承了当前 session 人格与上下文的 Yuki** 做一次 JSON 判定，30s 超时、解析失败按拒绝
- 无 approver 的路径（CLI、toolchain inline）直接放行并记日志
- `MAID_ESCALATE_TO_MASTER=1` 时，Yuki 拒绝后可升级为群内询问机主（默认关闭）

### S5 图片读取（`maid_runtime.prepare_image_message` + loop）
`read_image(path, question)`：复用 `MemeProcessor.compress_image` 压到 768/70，
构造 `image_url` 图块插入本轮消息；图块只存活一轮，下一轮降级为文本占位并剔除出快照。
已用 `deepseek-flash` 实测识别 `yuki_help.png` 成功，无需视觉模型转写兜底。

### S6 临时技能降摩擦（`maid_runtime.py`）
- `write_and_run_temp_skill` / `run_skill` 支持 `timeout`（默认 120、上限 600）与
  `interpreter`（`maid` 隔离环境 / `yuki` 主环境）
- 子进程注入 `PYTHONPATH=项目根`，模型可直接 `import config/utils/core`
- 成功也回传 stderr；失败只给末 40 行
- `pip list` 与虚拟环境可用性进程内缓存：重复执行 1.4s → 0.01s
- 依赖自动安装加 180s 超时

### S7 提示词与汇报
- 提示词只加：新工具各一行（`read_image`/`resume_task`）、`timeout`/`interpreter` 说明、
  3 条纪律、「被 Yuki 判定拒绝时换方案」；修掉重复的「8.」编号（3569 → 4251 字符）
- `build_maid_report` 前缀不变，末尾追加 `轮次 | 耗时 | trace | 快照`
- `core/maid/maid.py` 导出新符号

## 4. 验证

```bash
/home/asumi/miniconda3/envs/yuki/bin/python tests/run_tests.py                  # 全量
/home/asumi/miniconda3/envs/yuki/bin/python tests/run_tests.py test_maid_features
```

- 基线：`passed=100 failed=23`（3 个 LOAD ERROR，均为环境性失败）
- 当前：`passed=114 failed=23`，失败集合与基线完全一致（新增 14 个用例全过）
- 新增 `tests/test_maid_features.py`：读文件截断/续读、墙钟预算、错误轮不计数、
  快照与索引往返、续跑、命令分级、授权拒绝/放行、图块注入与降级

## 5. 已知代价与后续

1. 授权判定是额外一次 LLM 调用（约 1~3s），只对可疑命令触发；Yuki 的批准不等于权限隔离
   （同一模型换上下文再采样），它是懂语境的过滤器，不是安全边界。
2. `maid_worker` 串行消费任务队列，授权判定期间队列停摆（但不再有 300s 人类等待）。
3. `tasks/state/` 已加入 `.gitignore`；未完成的快照会保留，需要时可手动清理。
4. 未做：`ask_yuki` 半双工提问、热重载、多 worker 并行；`agently_*` 分支缺 import 的旧 bug 未修。
