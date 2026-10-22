
## 2026-10-22 自进化方案与基础设施

- 侦查结论：Yuki 单进程 asyncio 长驻、未容器化、config 无热重载（"启动时一次性加载"），小女仆同进程后台 task 但可用 terminal 改任意文件；无 health 探针/无回滚；`data/yuki.lock` 单实例锁使蓝绿并行不可行；`yuki_memory/` 是 ChromaDB 持久化目录（103M，文件锁型）。
- 决定：进程内 reload 排除，采用「容器化 + 离线校验 + 短窗口切换 + 自动回滚」。
- 已装 Docker 26.1.5（Debian trixie，overlay2/cgroup2），asumi 已入 docker 组。
- 已写准则：`docs/evolution-charter.md`（人读）+ `core/maid/maid_charter.py`（代码侧单一来源：路径分级、限额、验证门、prompt 片段）。人格（`core/prompts.py`）与 `configs/` 设为硬禁区，无例外。
- 待办 P0：Dockerfile/只读代码挂载、`/health`、`YUKI_DRY_RUN`、supervisor 校验回滚、小女仆 propose_patch/verify_patch/request_self_reload、保留策略脚本。
