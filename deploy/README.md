# Yuki 自进化部署

## 这套东西解决什么问题

让小女仆能改 Yuki 自己的代码，但**改不坏、可追溯、失败了能自己退回去**。

核心是三个隔离：

| 隔离 | 手段 | 效果 |
|---|---|---|
| 代码 | 容器内 `/app` 只读挂载 | agent 物理上改不了正在运行的代码 |
| 写入 | 唯一可写代码位置是 `staging/` | 候选补丁必须经宿主审核才生效 |
| 权限 | 只有宿主 `supervisor.py` 能改代码/重启 | 权限收敛到一个可审计的进程 |

## 组件

```
deploy/
├── Dockerfile        运行镜像（只装依赖，不含代码）
├── run.sh            启动生产容器（代码只读 + 数据卷 + --network host）
├── verify.sh         5 道校验门（临时容器，断网，tmpfs 数据）
├── supervisor.py     宿主守护：应用补丁 → 提交 → 校验 → 切换 → 回滚
├── maid_runner.py    ★ 小女仆执行器：轮询 tasks/dsh/ → 拉起 dsh 子进程 → 回写事件与结果
├── dsh-home/         ★ yuki-maid profile（人格 + AGENTS.md 准则 + 沙箱策略）
├── dsh-runtime/      ★ 固定版本的 @deepseek-ai/dsh（npm 装在项目内，版本锁死）
├── retention.py      保留策略（trace 归档 / 日志截断 / staging + dsh 任务清理）
└── state.json        last_good 提交与自改历史（只留最近 50 条）
```

## 小女仆 harness 后端（★）

小女仆的执行不再由 Yuki 进程内的自建循环负责，而是交给宿主侧的 DeepSeek Harness。

| 层 | 位置 | 职责 |
|---|---|---|
| 任务派发 | 容器内 `core/maid/maid_harness.py` | 写 `tasks/dsh/<task>/request.json`，盯 `events.jsonl`，把结果翻译成 Yuki 的格式 |
| 执行 | 宿主 `deploy/maid_runner.py` | 拉起 `dsh --profile yuki-maid --json`，逐行落盘事件，写 `result.json` |
| 行为 | 宿主 `deploy/dsh-home/` | 人格（`cordis.patch.yml` 的 personaPrefix）、准则（`AGENTS.md`）、沙箱与审批策略 |
| 切换 | 环境变量 `YUKI_MAID_BACKEND` | 默认 `harness`；设成 `legacy` 回退到原来的内置循环 |

协议只走文件，两边不开端口：

```
tasks/dsh/<task_id>/request.json    容器 → 宿主   {goal, session_id?, timeout_s?}
tasks/dsh/<task_id>/events.jsonl    宿主 → 容器   dsh --json 原始事件（逐行追加）
tasks/dsh/<task_id>/result.json     宿主 → 容器   {status, result, session_id, steps, tools, elapsed}
tasks/dsh/<task_id>/running.lock    宿主独占标记
```

三条约束：

1. **cwd 是草稿区**。`maid_runner` 把 cwd 设成 `workspace/dsh_<task_id>/`，沙箱全放行也只放行到那儿；
   要改生产代码仍然走 `propose_patch` → `staging/` → supervisor 审查，与 harness 无关。
2. **审批策略是 never**。headless 无人值守没有可问的对象，`workspace-write` 下越界操作会挂住等一个
   永远不来的回答，所以 profile 里显式设成 `danger-full-access` + `never`。这是机主的明确选择。
3. **版本锁死**。`deploy/dsh-runtime/package.json` 固定 `@deepseek-ai/dsh` 版本，升级要先跑一批回归任务，
   因为事件流字段（`tool_call` / `final` / `turn_end`）与版本绑定。

### 小女仆相关命令

```bash
# 安装/更新服务（含执行器；需要 sudo）
sudo bash deploy/install-service.sh

# 看执行器状态与日志
systemctl status yuki-maid-runner
tail -f logs/maid_runner.log

# 手动派一个任务（模拟容器侧行为，调试用）
mkdir -p tasks/dsh/manual_1 && cat > tasks/dsh/manual_1/request.json <<'EOF'
{"goal": "报告当前工作目录与磁盘剩余空间", "timeout_s": 120}
EOF
python3 deploy/maid_runner.py --once
cat tasks/dsh/manual_1/result.json

# 单个任务的完整事件流
cat tasks/dsh/<task_id>/events.jsonl | jq -r 'select(.type=="tool_call") | .tool'
```

### 续做

`result.json` 里有 `session_id`。中断任务的快照写在 `tasks/state/<task_id>.json`，
把该 id 作为 `resume_task_id` 传给 `harness_evolution_loop` 即可让 harness 接着上一次会话继续，
不需要重放历史消息。

## 一次自进化的完整时序

```
小女仆 propose_patch      → staging/<task>/files/
小女仆 verify_patch       → 容器内快速自检（语法/规模/定义数）
小女仆 request_self_reload → staging/<task>/request.json，并**同步等待**结果
    ↓
supervisor（宿主，每 3 秒轮询）
    1. 路径分级校验      禁区直接拒（人格/配置/数据/部署/准则）
    2. 速率与冷却检查    每小时 3 次、每天 10 次、连败 2 次冷却 6 小时
    3. 独立模型审查      deploy/reviewer.py：相关性/删功能/数据安全/正确性/副作用
       └─ 驳回 → 写 review_rejected，**不写盘不重启**，意见同步回传
    4. yuki_memory 快照  rsync --link-dest 增量，秒级，保留 7 份
    5. 应用 + git commit self-evolve: <summary>（只含补丁路径）
    6. verify.sh         编译 → 导入 → 单测 → 试启动 → 探针（仅受限区）
    7. 重启容器          deploy/run.sh
    8. 健康检查          GET /health，最多等 150s
    9. 失败 → git reset --hard <本次基线> → 重启 → 复查
   10. 成功 → git tag good-<ts>，写 logs/self_evolve.jsonl
    ↓
staging/<task>/result.json  ← 结果回传给小女仆
```

### 自改审查的两级判定

`deploy/reviewer.py` 输出两级，**只有 blocking 会驳回**：

| 级别 | 内容 | 后果 |
|---|---|---|
| `blocking`（必修） | 导入/运行时错误、删掉既有防护、数据面或外发面扩大、无界读取/循环、阻塞事件循环、无依据的符号引用、无关改动 | 驳回，不写盘、不重启，意见同步回传 |
| `advisory`（建议） | 命名/描述不一致、注释、风格、可选优化、推测性风险 | 通过，意见写进 result 当参考 |

这样做的原因：以前是二值判定，一条「文字表述不一致」也能把整个修复卡死。历史 21 次自改里
11 次被驳回，翻回去看都是真问题（未证明存在的 import、无界响应体读取、白名单混进数据目录），
说明审查本身有价值——问题在于它分不清轻重，而旧的内置循环只有 20 轮，改不动就耗尽了。
换成 harness 后端后可以反复迭代，所以保留审查、只把「建议」从驳回理由里摘出去。

配套的防打转机制：`staging/<task>/review.json` 记录 `rounds` / `rejects` / `detail`，
同一份补丁最多驳回 `YUKI_MAX_REVIEW_REJECTS`（默认 3）次，超了明确要求停手报告，不许原样重试。

### 同步反馈 vs 异步重启

| 结果 | 是否重启进程 | 小女仆能否就地继续 |
|---|---|---|
| `review_rejected` / `verify_failed` / `apply_failed` / `rejected` | 否 | ✅ 拿到意见立刻改，不用等下一次任务 |
| `ok` / `restarted` | 是 | ❌ 进程被中断，重启后 `resume_task` 续做 |

### 历史交接工具

- `list_previous_work(keyword, limit)`：查历史任务与自改记录（目标/状态/结果/commit）
- `read_work_trace(task_id)`：读某次任务的完整步骤轨迹
- `resume_task(task_id)`：恢复被中断任务的上下文

## 常用命令

```bash
# 首次构建镜像（约 3~5GB，十几分钟到半小时）
docker build -f deploy/Dockerfile -t yuki:base .

# 启动生产
bash deploy/run.sh

# 守护进程（前台调试）
python3 deploy/supervisor.py --once    # 处理一轮
python3 deploy/supervisor.py           # 常驻

# 手动校验当前代码（不碰生产容器）
bash deploy/verify.sh

# 存储保留（建议每天 cron 04:00）
python3 deploy/retention.py --dry-run
python3 deploy/retention.py

# 看最近自改记录
tail -5 logs/self_evolve.jsonl
cat deploy/state.json
```

## 回滚

```bash
cd /home/asumi/Yuki
git tag | grep good- | tail -5        # 看历史可用版本
git reset --hard good-20261022_140000
bash deploy/run.sh
```

## 安全边界（不要随意放宽）

- **不要**给容器加 `-v /:/host`（读写）。要读宿主文件只加 `:ro`。
- **不要**把 `.git`、`configs/`、`yuki_memory/` 从只读挂载里挪到可写。
- **不要**让容器内有 docker socket（等于把重启/回滚权交给被测方）。
- `deploy/`、`core/prompts.py`（人格）、`core/maid/maid_charter.py`（准则）在代码侧是硬禁区。
- `deploy/dsh-home/profiles/yuki-maid/` 是 harness 的人格与沙箱定义，改它等于改小女仆的权限，
  必须人工审阅（改完 `systemctl restart yuki-maid-runner` 生效，不用重启容器）。

## 已知限制

- 切换期间 Yuki 离线 15~30s（初始化 7~17s + 模型加载）。
- 小女仆每任务起一个 dsh 进程（Node 冷启动 ~1s，系统提示 ~6k token 基线）；任务密集时排队串行执行。
- `deploy/maid_runner.py` 是独立 systemd 服务，不随容器重启；它挂了任务会以
  `runner_unavailable` 明确失败，不会静默卡住（容器侧 90 秒内无动静即判定）。
- 不能蓝绿并行：`data/yuki.lock` 单实例锁 + `yuki_memory` 是文件锁型 ChromaDB。
- 容器内跑不了 Live2D 桌宠（Electron/GUI），已用 `YUKI_DESKTOP_PET=0` 关闭。
- `.dockerignore` 排除了 `models/`，模型以只读卷挂载（不重复占盘）。
