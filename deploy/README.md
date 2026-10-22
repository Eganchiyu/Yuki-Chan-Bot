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
├── retention.py      保留策略（trace 归档 / 日志截断 / staging 清理）
└── state.json        last_good 提交与自改历史（只留最近 50 条）
```

## 一次自进化的完整时序

```
小女仆 propose_patch      → staging/<task>/files/
小女仆 verify_patch       → 容器内快速自检（语法/规模/定义数）
小女仆 request_self_reload → staging/<task>/request.json
    ↓
supervisor（宿主，每 3 秒轮询）
    1. 路径分级校验      禁区直接拒（人格/配置/数据/部署/准则）
    2. 速率与冷却检查    每小时 3 次、每天 10 次、连败 2 次冷却 6 小时
    3. yuki_memory 快照  rsync --link-dest 增量，秒级，保留 7 份
    4. 应用 + git commit self-evolve: <summary>
    5. verify.sh         编译 → 导入 → 单测 → 试启动 → 探针（仅受限区）
    6. 重启容器          deploy/run.sh
    7. 健康检查          GET /health，最多等 150s
    8. 失败 → git reset --hard <last_good> → 重启 → 复查
    9. 成功 → git tag good-<ts>，写 logs/self_evolve.jsonl
    ↓
staging/<task>/result.json  ← 结果回传给小女仆
```

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

## 已知限制

- 切换期间 Yuki 离线 15~30s（初始化 7~17s + 模型加载）。
- 不能蓝绿并行：`data/yuki.lock` 单实例锁 + `yuki_memory` 是文件锁型 ChromaDB。
- 容器内跑不了 Live2D 桌宠（Electron/GUI），已用 `YUKI_DESKTOP_PET=0` 关闭。
- `.dockerignore` 排除了 `models/`，模型以只读卷挂载（不重复占盘）。
