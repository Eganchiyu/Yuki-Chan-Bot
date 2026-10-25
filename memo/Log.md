
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

## 2026-10-24 自改审查改为两级（保留审查，去掉"一条建议就驳回"）

- 机主先问「还要审批门吗」，随后改主意要求保留审查但别把人卡死。
- 先看证据：`logs/self_evolve.jsonl` 21 条记录里 11 条 `review_rejected`。逐条翻，驳回内容全是真问题
  ——未证明存在的 import、对响应体无界 `await read()`、白名单里混进 `data/image_store`（历史图片可外发）、
  DNS 校验失败反而放行。所以审查本身有效，问题在**二值判定**：命名/注释/推测性风险与
  「会 ImportError」同权，一条不一致就整份打回；旧内置循环只有 20 轮，几次驳回就耗尽，模型改不动。
- 改法（不拆任何安全门）：
  - `reviewer.py` 输出 `blocking` / `advisory` 两级，只有 blocking 驳回。blocking 限定六类会出真事的问题；
    命名/注释/风格/"如果可能"一律 advisory，写进 detail 当参考。兼容旧的 approve/problems/suggestions 格式。
  - 提示词要求采信 reason 里的验证证据，且 blocking 必须写"需要哪条具体证据才能放行"，
    不接受"建议再确认一下"这种无法执行的意见。
  - `supervisor.py` 落 `staging/<task>/review.json`（rounds/rejects/detail，重启后可读），
    同一补丁最多驳回 3 次（`YUKI_MAX_REVIEW_REJECTS`），超了明确要求停手报告。
  - `AGENTS.md`：提交前必须贴 `py_compile` / `diff` / `grep` 证据；一次一个最小可验证改动。
- 实测：无害改动（加一行注释）→ 通过 + 3 条 advisory；引用不存在符号 → high 风险驳回。
  审查员自己在 case2 里有一处幻觉（说"该文件中存在该符号"），但结论与改法是对的。
- 待机主：`sudo systemctl restart yuki-supervisor`（reviewer/supervisor 都是宿主进程内加载的）。

## 2026-10-24 重启补报：让一轮自改有始有终

- 补上一个链路缺口：自改补丁生效要重启容器，容器里等 `result.json` 的协程随进程消失；
  而宿主的 dsh 不受容器重启影响，会继续把结论写进 `tasks/dsh/<id>/result.json` →
  任务做完了没人汇报，Yuki 不会主动说。
- `core/maid/maid_resume.py`：常驻巡检（默认 30s），把「有 result.json 但没有 reported.ok」
  的任务捡回来，走 maid_worker 同一条通道（写会话历史 + process_callback 主动回复），
  完成后打 `reported.ok` 只报一次。完成时间超过 120s 的在前缀注明「Yuki 刚重启过」；
  NapCat 离线最多等 5 分钟再留到下一轮；无 chat_id 的调试任务只标记不打扰。
- 正常路径也在汇报成功后打标记（maid_worker + inline 委托），避免重启前后重复说一遍。
- harness 的 request.json 新增 `mode`，补报才知道发群还是发私聊；`maid_backend` 吸收 mode 参数，
  legacy 签名保持兼容。
- 实测（mock 通道）：造一条 10 分钟前完成未汇报的任务 → 文案正确（重启说明 + commit/tag +
  轮次/耗时/trace）、callback 收到 group/force_reply、reported.ok 落盘、复扫为空。
- 生效条件：容器重启（新代码）＋ `yuki-maid-runner` 服务已安装。

## 2026-10-24 重启通知通道（/notify）

- 需求：容器重启十几秒期间，在等结果的人要知道发生了什么。
- 限制：`dsh --profile headless` 是 one-shot，任务正文走 stdin 后就关了，**没有注入通道**；
  往 harness 的 conversation 里塞消息做不到。所以消息发到 **QQ 会话**，不是发给 harness。
- 链路：`supervisor.restart_container()` → `POST 127.0.0.1:8778/notify` → 容器内回调
  （有 NapCat WS 连接）→ `maid_active_chats` 里的会话 → 发完才重启。
- 兜底：没有活跃任务时（手动重启/任务刚做完），退回到 `tasks/dsh` 里最近一条 request.json
  的 chat_id；这条是实测时补的——第一版会因为「队列空」而闷声不响。
- 通知失败只记日志，绝不阻塞重启；回滚重启也会通知。
- 实测：容器重建 7 秒就绪；`POST /notify` 返回 `{"ok":true,"detail":"已通知 1 个会话，失败 0"}`，
  目标群 1057020972（取自最近任务的 request.json，mode=group）。
- 另：`deploy/run.sh` 只 `docker rm` + `docker run`，不 build，代码是只读挂载；
  重建容器 ≈ 7~9 秒（14:56 那次 9s，15:05 这次 7s），不会重装 torch。
- 待机主：`sudo systemctl restart yuki-supervisor` 才能让「自动重启前发通知」生效。

## 2026-10-25 回复订阅（subscribe_reply）
- 新增 `core/reply_watch.py`：按 chat_id 维护「待回执」订阅，下限 30s，最多 2 次追击，
  超时经 `process_callback(force_reply=True)` 注入 `【等待超时】` 事件，让 Yuki 自己决定补一句/追问/收尾。
- 新增工具 `subscribe_reply`（action=subscribe/cancel/status），注册进 `core/tools/`。
- `SessionPipeline.enqueue_message` 收到真人消息即 `resolve_watch`，机器人/定时/订阅事件不算。
- 测试：`tests/test_reply_subscription.py` 8 项全过；全套 122 过 23 失败均为基线已知失败，无新增。
- 状态：代码已落盘，生产容器（只读挂载）需重启才生效。
- 简化（同日）：工具只剩 `subscribe_reply(time)`，去掉 action/expectation；到点注入「XX秒到啦～没有人回复」
  走正常 enqueue；有人回复则订阅静默取消；最多自动提醒 2 次。测试 7 项全过，全套无新增失败。
- 改为自动订阅、删除 `subscribe_reply` 工具（工具必然导致多说话，无法无感）。
  评分=结尾问句0.45+触发词0.15+精力0.20+生物钟0.15+活跃0.15，±0.15 抖动后过 0.55 才订阅；
  等待时长=最近平均消息间隔+20s（无样本默认60s，下限30s）。挂在 finalize_conversation 后，
  破冰/定时任务/提醒事件轮不订阅。测试 12 项全过，全套无新增失败。
- 参数定稿：QUESTION 0.40 / TRIGGER 0.15 / ENERGY 0.05 / BIOCLOCK 0.15 / ACTIVITY 0.15，
  抖动 0.10、门槛 0.55；触发词去掉 呢/嘛（口癖不算求回应）。真实日志回放：订阅率 10~16%，
  追击消息 ≤11%（最坏热度），符合「≤20%」目标。

## 2026-10-25 仓库同步
- 忽略 DSH 运行时数据：deploy/dsh-home/attachments/、deploy/dsh-home/llm-deepseek/；删除实验用临时头像 temp/qq_avatar_now.png、temp/yuki_avatar_square.png
- 提交 618c69f（.gitignore + 女仆提示词微调），推送 fix/maid-env-vision-prefetch
- 推送 main 原有 5 个提交，再合并特性分支（--no-ff，7ea5298）并推送
- 当前：main == origin/main，工作区干净
