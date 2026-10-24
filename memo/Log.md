
## 2026-10-22 自进化方案与基础设施

- 侦查结论：Yuki 单进程 asyncio 长驻、未容器化、config 无热重载（"启动时一次性加载"），小女仆同进程后台 task 但可用 terminal 改任意文件；无 health 探针/无回滚；`data/yuki.lock` 单实例锁使蓝绿并行不可行；`yuki_memory/` 是 ChromaDB 持久化目录（103M，文件锁型）。
- 决定：进程内 reload 排除，采用「容器化 + 离线校验 + 短窗口切换 + 自动回滚」。
- 已装 Docker 26.1.5（Debian trixie，overlay2/cgroup2），asumi 已入 docker 组。
- 已写准则：`docs/evolution-charter.md`（人读）+ `core/maid/maid_charter.py`（代码侧单一来源：路径分级、限额、验证门、prompt 片段）。人格（`core/prompts.py`）与 `configs/` 设为硬禁区，无例外。
- 待办 P0：Dockerfile/只读代码挂载、`/health`、`YUKI_DRY_RUN`、supervisor 校验回滚、小女仆 propose_patch/verify_patch/request_self_reload、保留策略脚本。

## 2026-10-22 P0 自进化闭环完成（已端到端验证）

- 容器：`deploy/Dockerfile` 只装依赖（3.5 分钟构建，`yuki:base`）；代码整树 `:ro` 挂载，数据目录单独 rw，`--network host` 直连宿主 NapCat，容器以宿主 uid 运行（否则 staging 属主是 root，宿主写不了 result.json）。
- 探针：`utils/health_server.py` 独立线程标准库服务，`main.py` 注入 `/health`（ready/napcat_online/maid 队列）；`napcat_online` 改用 `NapCatGateway.connected`，不再用乐观默认值。
- 试启动：`YUKI_DRY_RUN=1` 只做初始化自检，跳过 NapCat 接管与配置回写。
- 校验门：`deploy/verify.sh` 5 门（compileall/import/tests/dry_run/health），临时容器断网 + tmpfs 数据；测试门改基线差集（既有 33 个环境性失败），只对新增失败报警。
- 守护：`deploy/supervisor.py` 轮询 `staging/*/request.json` → 分级校验 → yuki_memory 硬链接快照 → 应用 → 只提交补丁路径 → 校验 → 重启 → `/health` → 失败 `git reset --hard <本次基线>` → 写 result.json/self_evolve.jsonl。
- 小女仆工具：`core/maid/maid_selfevolve.py` 四个工具接入 `maid_loop.py`，准则注入 `maid_prompt.py`。
- 保留：`deploy/retention.py`（trace 归档 7 天→按周 tar.gz 上限 200MB、日志截断、staging 3 天清理、快照留 7 份）。
- 实测：成功路径 34 秒完成（快照+5门+重启+health+tag）；坏补丁路径 `verify_failed` 精确回传 SyntaxError 行号并回滚到基线；速率限制（3 次/小时）与禁区拦截均生效。
- 坑：`git add -A` 会把 staging 卷进自改提交、回滚时删掉 request 目录 → 已改为只 add 补丁路径；`staging/`、`deploy/state.json` 已入 .gitignore。
- 待办：安装常驻服务 `sudo bash deploy/install-service.sh`；health 的 napcat 字段已修但未在容器内复验。

## 2026-10-22 修复：容器化后表情包/文件发不出去

- 根因：NapCat 在宿主机，Yuki 用 `file:///<绝对路径>` 发图；容器内路径是 `/app/...`，宿主无 `/app`，NapCat 找不到文件，发送静默失败（`send()` 不等响应所以日志只显示“发送完成”）。
- 修法：容器挂载改成与宿主同路径 `-v $ROOT:$ROOT:ro`（数据卷同样同路径），`WORKDIR` 与 `-w` 改为 `$ROOT`；`verify.sh` 的 tmpfs 与 `-w` 同步；`test_gate.py` 的 ROOT 默认改用 `$YUKI_ROOT` 或 cwd。
- 验证：容器内 `os.path.abspath('data/stickers')` == 宿主路径；真实发送测试 `send_private_msg` 返回 `retcode: 0`（message_id 85613626）。
- 顺带确认：`screenshots/` 在只读区但不被代码写；`temp_images/ output/ staging/` 等已 rw 挂载。

## 2026-10-22 小女仆新增 restart_yuki 工具

- 需求：小女仆需要能重启 Yuki（重载配置/重连 NapCat/清内存），但容器内没有 docker 权限，不能也不该给。
- 实现：`request_restart()` 写 `staging/<task>/request.json`（type=restart，无 files）→ supervisor 快照 → `run.sh` 重建容器 → `/health` 探活 → 写 result.json。结果值 `restarted` / `restart_failed`，单独限额 5 次/小时，不计入自改配额。
- prompt 已说明适用/不适用场景，并提醒模型：调用后自身约 3 秒内被终止，靠 resume_task 续做。
- 验证：容器 ID 574ab38 → ab0efc3，result=restarted，快照 20261022_181155，health ok；5 道门全过。
- 注意：改 `deploy/` 下脚本后必须 `sudo systemctl restart yuki-supervisor` 才生效（本次踩到：旧服务把 restart 请求判成 files 为空）。

## 2026-10-22 自改流程升级：模型审查 + 同步接续 + 历史交接

- 限额：3 文件/200 行 → **10 文件/1000 行**（硬限额只做防呆，放行判断交给审查）。
- 新增 `deploy/reviewer.py`：宿主侧独立审查（deepseek-flash，温度 0.2，JSON 输出），
  看相关性/删功能/数据安全/正确性/回滚性/副作用；驳回则不写盘不重启，意见同步回传。
  自带极简 yaml 解析（宿主 python3 无 PyYAML）。
- `request_self_reload` 改为 async 同步轮询 result.json（≤180s）：审查驳回、apply_failed、
  verify_failed 都不重启进程，模型可在同一 session 继续改；一旦通过进入重启才断开。
- 新增 `core/maid/maid_worklog.py`：`list_previous_work` / `read_work_trace`，用于跨任务交接；
  self_evolve.jsonl 记录补上 summary 字段。
- 实测：通过路径 46s（审查 2.6s + 校验 + 重启 + health + tag good-20261022_182221）；
  驳回路径同步返回具体问题与改法，进程存活。
- 事故（已回滚）：测试 fixture 直接放进 staging 且带 request.json，运行中的旧 supervisor
  立刻消费并把 `while True: pass` 提交进 core/tools/tools_common.py（commit 89d39cd）。
  已 reset --soft 回滚并保留工作区改动。教训：往 staging 放 fixture 前必须先停 supervisor；
  这恰好证明审查层的必要性。
- 注意：改 `deploy/` 后必须 `sudo systemctl restart yuki-supervisor`。

## 2026-10-24 小女仆后端切换到宿主侧 DeepSeek Harness

- 动机：内置 `core/maid/maid_loop.py` 是自建 LLM 循环 + JSON function-call 协议 + 人肉工具分派（3147 行），
  工具质量、沙箱、上下文压缩都远不如 harness；而 harness 本来就是解耦的 agent，可直接当执行体。
- 形态（方案 A）：容器不加 node、不塞 key。容器写 `tasks/dsh/<id>/request.json`，宿主
  `deploy/maid_runner.py` 拉起 `dsh --profile yuki-maid --json`，逐行落 `events.jsonl`，写 `result.json`。
  容器侧 `core/maid/maid_harness.py` 把事件流翻译成原 `maid_evolution_loop` 的结果结构，上层零改动。
- profile：`deploy/dsh-home/`（入 git）——personaPrefix 小女仆人设、AGENTS.md 准则、
  `danger-full-access` + 审批 `never`（机主明确选择，headless 无人可问）、`workspaceRoot=process.cwd()`。
  `deploy/dsh-runtime/` 锁 `@deepseek-ai/dsh@0.2.1-rc.2`。
- 安全：cwd 固定为 `workspace/dsh_<task>`，沙箱全放行也只放到草稿区；改生产代码仍走
  `staging/` + supervisor 审查 + 5 门 + 回滚，与 harness 无关。AGENTS.md 里写了完整自改协议与 status 应对表。
- 回退：`YUKI_MAID_BACKEND=legacy` 恢复旧循环，代码都还在。
- 实测：单任务 5~8s / 3~8 步；人格、cwd、写权限、AGENTS.md 全部生效；
  自改协议演练（写 staging/files + REQUEST.json.draft）字段完全正确；runner --once 端到端跑通。
- 成本：系统提示基线 ~6.4k token（旧 maid prompt 约 1.5k），换来的是全套工具与压缩策略。
- 待机主：`sudo bash deploy/install-service.sh` 安装 `yuki-maid-runner` 服务（含 sudo，未执行）。
- 教训：`pkill -f "deploy/maid_runner.py"` 会匹配到自己那条 bash 命令，把自己杀掉；先用 `ps -eo pid,args` 精确看。

## 2026-10-24 无人值守收口：禁提问 + 探索预算

- 机主要求：小女仆不许向用户提问（Yuki 是 QQ 机器人，没人实时回答）。
- 实际排查：`ask_user_question` 工具本来就没挂进 headless bundle；但 `user-questions`
  与 `plan-mode` 两个服务还活着，后者的文案会引导「呈现计划等批准」——同样是死等。
  两条在 profile 里都禁用。
- 实测踩到的坑：任务越模糊越危险。第一次跑「那个脚本好像坏了」，模型 34 步 / 61 次 bash
  一路穷举到超时，且 timeout 时 final 为空 → 结果全丢，只回报一句「超时」。
- 两处修：AGENTS.md 加探索预算（定位类 ≤8 步、写代码 ≤20 步、同一错误连败 3 次停手，
  宁可给不完整结论也不要跑到被杀）；maid_runner 超时时用「最后的话 + 最后一个动作 + 工具尾段」
  拼部分结论。同样任务复测：14 步 / 77s 收敛，结论具体（定位到 reset_and_import_meme.py
  的 sys.path 与 manual_stickers.json 相对路径问题）+ 待确认清单。
- 经验：harness 没有轮次上限，开放式委托必须靠提示词约束收敛；任务描述越含糊越要设预算。
