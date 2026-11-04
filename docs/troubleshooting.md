# Yuki 运维与故障排查指南

> **红线警告**：`yuki_memory/` 与 `data/` 是不可再生核心数据资产。排查任何故障时**严禁执行 `rm -rf yuki_memory/` 或清空 `data/chat_history.json`**。如需回滚记忆库，请使用 `backups/yuki_memory/` 下的快照。

---

## 一、核心状态与日志速查

### 1.1 检查容器与宿主服务状态

```bash
# 1. 查看生产容器状态
docker ps -a --filter name=yuki

# 2. 查看容器内健康探针（ready / napcat_online / maid 队列）
curl -s http://127.0.0.1:8778/health

# 3. 查看宿主三大守护服务
systemctl status yuki-supervisor yuki-maid-runner yuki-netwatch --no-pager
```

### 1.2 日志文件位置（均在 `logs/` 下）

| 日志路径 | 内容说明 |
|---|---|
| `logs/yuki.log` / `logs/yuki_<时间戳>.log` | Yuki 主程序全量 DEBUG 日志（排查对话、工具、报错首选） |
| `logs/supervisor.log` | 宿主自改/重启守护日志 |
| `logs/maid_runner.log` | 宿主小女仆 DSH 执行器日志 |
| `logs/netwatch.log` & `logs/netwatch_diag_*.json` | 网络看门狗探活、修复阶梯与现场路由快照 |
| `logs/self_evolve.jsonl` | 历次代码自改的摘要、状态与 commit 台账 |
| `logs/task_index.jsonl` & `logs/trace_*.md` | 小女仆历次任务索引与详细执行轨迹 |

---

## 二、常见故障与处理

### 2.1 外部 API 全部 Connection Timeout，但 NapCat 收发正常

- **原因**：NapCat 走本地回环/IPv6 长连接，而外部 API（DeepSeek、图片下载等）走宿主机 mihomo TUN 的 IPv4 出站。WiFi 漫游后 mihomo 默认出站接口可能失效，或 mihomo 重载卡死。
- **自动恢复**：宿主 `yuki-netwatch.service` 每 30s 探活 `direct`（DeepSeek）与 `proxy`（gstatic），失败时自动按阶梯执行「重载 mihomo → 清缓存重载 → SIGTERM 重启 mihomo core → 重连 WiFi」；客户端侧 `utils/llm_client.py` 也会自动重建 aiohttp Session 并使用独立 DNS 线程池重试。
- **手动触发恢复**：
  - 在 QQ 群聊或私聊（主人号）发送：`/刷新`（触发 `yuki-netforce.path` 真实探活并回报结果）。
  - 或在宿主机终端执行：`sudo python3 deploy/netwatch.py force`。

### 2.2 修改了代码或配置，但线上没生效

- **原因**：生产容器 `yuki` 将代码树以 `:ro` 只读挂载，且部分启动期对象在进程启动时初始化。
- **解决**：
  - QQ 群聊（主人号）发送 `/重启`（会先回复「正在重启」，容器重建连上 NapCat 后自动补发「重启完成」）；
  - 或宿主机执行 `bash deploy/run.sh`；
  - 若修改的是 `deploy/` 下的宿主脚本（`supervisor.py`、`maid_runner.py`、`netwatch.py`），需执行 `sudo systemctl restart yuki-supervisor`（或对应服务）。

### 2.3 启动报错「已有 Yuki 实例在运行（data/yuki.lock 被占用）」或群里重复回复

- **原因**：`main.py` 通过 `data/yuki.lock` 的 `flock` 防止双开同时消费同一条 NapCat 事件流。
- **排查**：
  ```bash
  ps -eo pid,stat,etime,cmd | grep "main.py" | grep -v grep
  ss -tnp | grep 3001
  ```
- **解决**：确认只有一个生产容器在跑，杀掉多余的宿主机 `python main.py` 进程（注意 `STAT=T` 被挂起的进程也会占锁，需 `kill -9`）。并行调试时可设 `YUKI_ALLOW_MULTI_INSTANCE=1`。

### 2.4 表情包 / 本地图片发送成功但群里没收到

- **原因**：NapCat 运行在宿主机，Yuki 发送本地图片时传递 `file:///<绝对路径>`，且 `gateway.send()` 不等待响应回包。若容器内外绝对路径不一致或文件不存在，NapCat 会静默丢弃。
- **排查**：确认容器由 `bash deploy/run.sh` 启动（挂载为 `-v /home/asumi/Yuki:/home/asumi/Yuki:ro`），且目标图片在宿主机同路径下真实存在、权限可读。

### 2.5 小女仆任务卡住、超时或重启后未汇报

- **排查**：
  1. 检查宿主执行器是否存活：`systemctl status yuki-maid-runner`（若未运行，容器内等待 90s 无事件会报 `runner_unavailable`）。
  2. 查看任务目录 `tasks/dsh/<task_id>/` 下的 `request.json`、`events.jsonl`、`result.json`。
- **补报机制**：若任务执行期间 `yuki` 容器发生重启，新容器启动后 `core/maid/maid_resume.py` 会每 30s 扫描已完成但无 `reported.ok` 标记的任务并自动补报。

### 2.6 运行 pytest 报缺库或 `libpython3.11.so` 找不到

- **原因**：仓库下的 `maid_venv/` 是跨机残留不可用，系统 `/usr/bin/python3` 未装项目依赖。
- **解决**：固定使用 `~/miniconda3/envs/yuki/bin/python -m pytest -q`，或使用容器镜像测试：
  ```bash
  docker run --rm -v /home/asumi/Yuki:/home/asumi/Yuki:ro -w /home/asumi/Yuki yuki:base python -m pytest -q
  ```
