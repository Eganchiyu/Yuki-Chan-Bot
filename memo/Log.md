
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

## 2026-10-25 README 同步当前实现

- 特性区：小女仆改写为 harness 后端 + 受控自改 + 无人值守 + 任务接续；记忆区补结构化记忆（实验中）；精力区补回复订阅；表情包区补入站图片预取；工具链工具清单按 `core/tools/tools.py` 的 14 个 ToolSpec 修正（网页/地图搜索标注为小女仆侧工具）。
- 新增「自进化与受控自改」小节（只读挂载 / staging / supervisor / 审查 + 5 门 / 回滚 / 快照 / self_evolve.jsonl）；调试区补 `/health` 探针。
- 玩法区修正过期路径（`core/tools.py` → `core/tools/tools_media.py`、`tools_message.py`、`tools_search.py`），新增网易云点歌、富文本解析两节，顺手删掉错位的分隔线。
- 项目结构树：`core/tools/` 包、`core/maid/` 新文件、`deploy/`、`utils/health_server.py`、`reply_format.py`、`reply_watch.py`、`ncm_login.py`、tests 22 个文件、docs 新增文档、数据目录（yuki_memory/memo/staging 等）。
- 快速开始补「自进化底座（可选，需 Docker）」与环境变量（`YUKI_DRY_RUN` / `YUKI_HEALTH_PORT` / `YUKI_MAID_BACKEND`）；文档表、技术栈、开发计划、测试命令、最后更新日期同步。
- 状态：仅文档改动，未跑测试。
- 2026-?? search_diary 优化：命中结果从「按写入顺序取前8」改为 random.sample 随机抽 8；新增无參数模式（date_str/keyword 都为空时随机翻看日记本 8 条）。改动：core/maid/maid_tools.py、core/tools/tools_diary.py（移除 missing_date_or_keyword 拦截）、core/tools/tools.py（spec 描述）、core/maid/maid_prompt.py、docs/toolchain-usage.md。状态：已提交 3c793cd；本机无可用 chromadb 环境，仅用 stub 验证逻辑。

## 2026-10-25 检索类 Token 收拢到 config.yaml
- 新增 `search` 配置组（SearchConfig）：`search.amap_api_key`、`search.tavily_api_key`，并在 Config 暴露 `cfg.AMAP_API_KEY` / `cfg.TAVILY_API_KEY`；`_SECTION_HEADERS` 补 section 注释。
- `core/tools/tools_search.py`、`core/maid/maid_tools.py` 由 `os.getenv("AMAP_API_KEY"/"TAVILY_API_KEY")` 改为读配置；未配置时的提示文案指向 yaml 字段。
- `configs/config.yaml` 已补 `search` 段（值留空待填）。其余 Token（LLM/图像生成、GitHub PAT、NapCat ws token）此前已在 yaml；网易云用 cookie 文件、邮件走 agently-cli OAuth，无需 token。
- 状态：语法检查通过；本机无 pyyaml 环境，未跑 config.py sync 与测试。

## 2026-10-25 日记召回（RAG）重排与打分重构
- `modules/memory/rag.py`：同群/发言者/关键词加成从绝对分改为「相对语义分的比例提升」（同群 +15%、发言者每个 +5% 上限 15%、关键词按词权上限 +30%），`current_chat_boost=10` 绝对压制取消。
- 新增时间衰减：`_diary_timestamp()` 优先解析正文 `【日记(YYYY-MM-DD HH:MM)】`，无则退回 metadata.timestamp；`_recency_decay()` 半衰期 180 天、下限 0.55。
- 关键词池保底分由 `0.85×最高语义分` 改为「词权覆盖率 × 最高语义分」，并新增 `KEYWORD_STOPWORDS` + 单字过滤，「今天/什么/一起」不再参与召回。实测同一 query 从「8 条全是只命中今天的同群日记」变为语义池主导。
- 返回结构新增 `relevance`（纯语义分，0~1）与 `decay`；`core/session_pipeline.py` 的 rag_interest 改用 `relevance` 并裁剪到 0~1。
- `core/engine/engine_decision.py`：`RAG_HORMONE_GAIN=80`（relevance 0.5 → 激素稳态≈40）、`REPLY_THRESHOLD=50`（原 55）。
- `core/maid/maid_tools.py`：`search_diary_fast` 关键词大小写变体补 title/capitalize（$contains 区分大小写）。
- 新增 `tests/test_rag_recall.py`（7 例），更新 `tests/test_modes.py` 的旧绝对加分断言；全量 `tests/run_tests.py` 失败数与 HEAD 基线一致（18 个 logger/modes/engine 历史失败）。
- 环境备注：本机可用 python 为 `~/miniconda3/envs/yuki/bin/python`（有 chromadb 1.5.9 + jieba），`maid_venv` 缺 libpython3.11 不可用。
- 同日：填入 search.amap_api_key / search.tavily_api_key，实测高德 geocode 与 Tavily search 均 200 正常。

## 2026-10-25 仓库同步

- fetch + push：本地 main 5 个提交推到 origin（01300b0 README 同步 → ba8b969 检索 Key → 3c793cd 日记随机抽取 → 7741623 日记召回重排 → c4ac6a4 日志），`main` 已设上游 `origin/main`，之后可直接 `git push`。

## 2026-10-25 清理根目录小女仆遗留产物

- 删除根目录与项目无关的生成物（d19dc46 那批「归档学习示例与调研笔记」带入的）：`2api_repos_report.md`、`MiMo-V2.6_vs_DeepSeek-V4.1-Flash_对比.md`、`beamer_demo.tex`、`beamer_minimal_template.tex`、`beamer_tutorial.md`、`cloudflared_guide.md`、`gomoku.html`、`weiqi.html`、`npu_math_employment_poster.html`、`brainfuck_demo/`、`memos/`（仅一行 test）。
- 同时清本地未跟踪目录：`amtech_analysis/`（他人站点分析副本）、空目录 `gif_images/`、`screenshots/`。
- 保留：`blacklist.txt`/`init.py`/`setup.py`/`yuki_help.png`/`manual_stickers.json`（代码或测试引用）、`future addons/`，以及运行期目录 `logs/ workspace/ staging/ output/ temp_images/ maid_venv/` 未动。
- 遗留：`docs/android-bridge-plan.md` 第 55、411 行仍引用已删除的 `cloudflared_guide.md`（该文档按用户要求保留，链接呈悬空）；`.gitignore` 仍保留 `amtech_analysis/` 规则（防止日后重新生成时误入库）。

## 2026-10-27 主人 QQ 支持多号

- 新增 `TargetConfig.masters: List[int]`（target.masters），与主号 `target.qq` 合并为主人集合；新增 `cfg.MASTER_QQS`（去重保序、过滤 0/非法值）与 `cfg.is_master_qq(user_id)`，`cfg.TARGET_QQ` 仍为主号（私聊通知默认收件人）。
- 判定点统一改用 `cfg.is_master_qq()`：`/开启` `/关闭` 权限、私聊 `master_private` 模式、群内冒充主人昵称检测、决策层主人加分与 QQ 号文本识别（`core/engine/engine_decision.py`、`memory/engine_h.py`）、`core/prompts.py` 的 master_private system prompt 分配。
- `configs/config.yaml` 已加 `target.masters: [2624538603, 7373372370]`（文件 gitignored，未入库）；注意该文件 `target.qq` 仍为 `737337230`（9 位，疑似少一位），主号需机主自行确认。
- 文档：`docs/deployment-guide.md`、`docs/module-relationship.md` 补 masters 说明。
- 验证：用 `~/miniconda3/envs/yuki/bin/python` 实测 `MASTER_QQS == [737337230, 2624538603, 7373372370]`，`is_master_qq` 对大小号均 True；`maid_venv` 仍缺 libpython3.11 不可用，环境无 pytest 故未跑单测。

## 2026-11-01 从主模型卸载五个工具（仅归档，不删除）
- 新增归档包 `core/tools/_archived/`，`git mv` 移入 `tools_search.py`、`tools_timer.py`、`tools_qzone.py`、`tools_browser.py`、`tools_status.py`；`_archived/__init__.py` 重新导出 6 个 handler 便于日后做成 skill 下放给女仆。
- 归档文件里的 `from .tools_common import` 改为 `from ..tools_common import`（唯一必要改动）；`tools_status` 依赖的 `_archived/tools_status.py` 自包含。
- `core/tools/__init__.py`、`core/tools/tools.py`：删除 5 个模块的 import，删除 `get_master_status`、`publish_qzone_mood` 两个 ToolSpec 及注释掉的 `enter_browser_interaction` 块。现役 TOOL_SPECS：delegate_to_maid、search_diary、send_master_private、poke、send_qq_file、ncm_search、ncm_download、capture_group_snapshot、search_group_snapshots、parse_rich_message、download_file、generate_image。
- `main.py`：移除 `start_monitor_service`/`stop_monitor_service` 的导入、启动与清理调用（该后台线程唯一消费者是 get_master_status）。
- `core/prompts.py`：删除 `publish_qzone_mood` 图片索引说明与「Qzone动态」两行文案。
- 测试：`test_system_state.py` 改为断言未注册并从归档导入 handler；`test_modes.py` 改断言 `enter_browser_interaction` 不在默认工具集；`test_toolchain.py` 定时任务测试改从归档导入。
- 验证：`py_compile` 全部通过；主流程代码无残留引用。环境无 pytest/yaml（`maid_venv` 缺 libpython3.11），未跑单测。

## 2026-11-01 11:58
- 清理 `core/tools/tools_maid.py`：删除 `run_inline` 死参数及其 warning 分支、移除不再使用的 `logger` 导入，注释合并为一段说明「一律后台执行」。同步修正 `docs/toolchain-usage.md`、`docs/api-reference.md` 中对 `run_inline` 的描述。提交 f7a7d55。

## 2026-11-01 补全测试环境 + 清理测试套件
- 环境：`~/miniconda3/envs/yuki/bin/python -m pip install pytest pytest-asyncio`（已有 aiohttp/yaml 等项目依赖）；`pyproject.toml` 新增 `[dependency-groups] dev`。`pytest -q` 从「204 passed / 6 failed」变为 **199 passed / 0 failed**，且本机与容器只读挂载下都全绿。
- `deploy/Dockerfile` 加独立一层 `pip install pytest pytest-asyncio`（镜像已重建为 yuki:base，`docker run yuki:base python -m pytest --version` → 9.2.0）。
- `deploy/test_gate.py` 从 `python run_tests.py` 改为 `python -m pytest -q --tb=no`（缺 pytest 时给出明确提示）；`deploy/test_baseline.json` 基线由 33 项重置为 0 项。
- 删除：`tests/run_tests.py`（自制 runner）、`tests/test_maid.py`（只有 self.fail 占位）、`tests/test_maid_search_diary.py`（直连真实记忆库的手动脚本）、`tests/tasks/state/*.json` 产物、`test_ice_break_pipeline.py` 里两个自证式伪 monitor 测试、`test_llm_client.py` 两个真实调 DeepSeek 的集成测试 + 自制 runner、`test_github_monitor.py` 的 TestGitHubClient 与需真实 token 的 monitor 用例。
- 修：`test_engine.py` 改为 `from core.engine.engine import YukiEngine`；`GitHubRepoConfig(chat_id=)` → `chat_ids=[...]`。
- 整理：新增 `tests/conftest.py`（项目根入 sys.path + win32 UTF-8），删掉 11 个测试文件里重复的 sys.path/win32 hack 与 3 个 `__main__` 块，清理未使用导入；测试落盘路径全部改到 `tmp_path`/临时目录（native_vision 5 例、reply_format 2 例、github_monitor 卡片目录、maid_features 的 LOGS_DIR），使 :ro 挂载的容器里也能跑。
- 注意：期间仓库有并发进程在动（提交 f7a7d55，且 docs/ 下 13 个文件被删），本提交只 stage 自己改的文件。

## 2026-11-01 记忆库体检（只读，未删除任何数据）
- 新增 `docs/database-profile.md`：chroma.sqlite3 结构画像（表/段/collection、metadata 键、ID 命名、磁盘布局、持久化设置）。
- 核查结论：`diaries` 6285 条（文档内日期 2026-03 → 2026-11）、`stickers` 66 条、`yuki_memory` 7830 条**仍在**（4297 条 fact/preference/relationship/event 候选 + 3533 条 legacy 日记副本），`status` 全 active，最后写入 2026-06-14；代码已无任何引用（只 get_or_create diaries/stickers）→ 孤儿数据。
- 备份快照对照（backups/yuki_memory/*）：10-24 起 diaries 6171→6285 持续增长，yuki_memory 恒为 7830，证明从未被删。此前「日记总数 14164」实为三张 collection 行数之和（6267+66+7830=14163）。

## 2026-11-01 剥离 Live2D 桌宠 + 浏览器交互模式
- 归档到 `_archive/`：`LiveYukiL2D/`（源码 3.9M，排除 node_modules 307M 与 reference/Open-LLM-VTuber 962M）、`modules/browser_interaction/`、`core/tools/tools_browser.py`、`docs/browser-interaction-mode-plan.md`、`tests/test_modes.py.original`、`docs/removal.diff`（全量代码改动）。
- 卸载点位：`main.py`（启动函数+调用）、`core/session_pipeline.py`（强制回复集合 / broadcast 分支）、`core/engine/engine_reply.py`（broadcast + record_step 分支）、`core/modes.py`（BrowserInteractionMode）、`core/prompts.py` + `core/brain.py`（browser prompt）、`core/tools/_archived/__init__.py`、`core/engine/engine.py`（注释残留）、`utils/logger.py`、`deploy/run.sh` + `deploy/README.md`、`.gitignore` + `.dockerignore`、`README.md`（含小节编号顺延）、`tests/test_modes.py`（重写为 2 个用例）。
- 文档：`_archive/README.md`（索引）、`_archive/docs/live2d-archive.md`、`_archive/docs/browser-interaction-archive.md`——记点位表、剥离清单、A/B 两套复原方案、代码用法（独立运行/开关/WS 与 REST 接口/config.json 字段/已知坑）。
- 状态：`py_compile` 全绿、`bash -n deploy/run.sh` 通过；用 `~/miniconda3/envs/yuki/bin/python -m pytest -q` 跑全量：**195 passed**（`/usr/bin/python3` 无 pytest，`maid_venv` 缺 libpython3.11.so 起不来）。新增 `tests/README.md` 记录这套测试环境。
- 保留未动：`ModeManager`/`ModeSpec`/`FocusModeState` 通用聚焦模式框架（`prompts.py` 仍注入模式状态）。

## 2026-11-01 清理记忆库：删除弃用的 yuki_memory collection
- 备份：`yuki_memory/_archive/20261101_121448/`（rsync 整目录 105 MB，备份库 integrity_check=ok）。
- 删除：容器镜像 55597bd6a186（chromadb 1.5.9）挂载同目录执行 `delete_collection("yuki_memory")`，7830 条结构化记忆一并消失；再手删 API 未清理的 HNSW 残留目录 `67437597-…`（23 MB），最后 VACUUM（15478→8294 页，freelist 6597→0）。
- 验证：collections/segments/embeddings 全部对齐（6285+66=6351），FTS 6351，独有 metadata 键计数全 0，文件内 `ymem_*`/`review_status`/`legacy_diary` 字符串 0 命中，integrity ok，API 抽查 diaries/stickers 查询正常；库 63.4 MB→34.0 MB。
- 文档：`docs/database-profile.md` 全篇重写为清理后状态（含清理记录、回滚命令、孤儿目录 f989647f 说明）。
- 状态：任务完成。注意容器 `yuki` 于 12:13 以 exit 137 自行退出（早于本次改动），当前未运行，未擅自重启。

## 2026-11-01 修复工具调用「参数截断 → 标记外泄」
- 事故复现（logs/yuki_20261031_132313.log 02:28）：delegate_to_maid 的 goal 在 1583 字符处被切断，args 非法 JSON（`finish_reason` 实为 length，由 max_tokens=1024 造成）→ 反馈只有「工具参数不是合法 JSON」→ 模型原样重发、再次截断 → 4 轮用尽后走无 tools 的收尾请求 → 模型把调用写成 `<｜｜DSML｜｜ invoke>` 正文，被 `clean_visible_reply` 原样发给用户。
- 修：`core/toolchain.py` 工具描述追加「单字符串参数 ≤ 500 字」提示、无效 JSON 反馈带原因/重试要求、`finish_reason=length` 明说截断并附 `arguments_tail`；新增 `core/tool_markup.py` 把 DSML / `<tool_call>` / `<function=名>` 文本调用还原成真实 tool_calls（按已注册工具名过滤）并剔除标记；`engine_reply` 无 tool_calls 时先尝试还原再执行，透传 finish_reason，收尾请求加「只输出文字」约束；`reply_format` 兜底清洗标记。
- 测试：新增 tests/test_tool_markup.py（10 例，含端到端自纠正），更新 test_toolchain 截断用例，全量 **206 passed**。提交 50f558e。
- 状态：任务完成。注：仓库仍有他人未提交改动（config.py / utils/llm_client.py / modules/vision/processor.py 等），未 stage。

## 2026-11-01 思考开关重构
- 删除 `model.disable_thinking`，新增 `model.thinking_effort`（low/medium/high，空=不传）。
- 主/备对话：`_request_with_failover` 按 `THINKING_EFFORT` 注入 `reasoning_effort`。
- 视觉：DeepSeek 端点写死 `reasoning_effort="none"`，不再依赖配置。
- 待办：`maid_venv` 缺 libpython3.11，测试未跑，需重建环境。

## 2026-11-01 18:2x 排查「挂几小时后 LLM 全部 Connection timeout」
- 现象：yuki_20261101 日志 16:15:45 最后一次出站成功；16:26 起所有外部请求在正好 10s 失败（= aiohttp connect=10 超时），持续到 17:51 重启。
- 同期非 LLM 出站也挂（16:32 图片下载 15s total 超时）；127.0.0.1 的 NapCat WS 一直正常。
- 主机出口是 Clash(Mihomo) TUN + fake-ip：api.deepseek.com -> 198.18.0.111；DIRECT 的国内图片域名也一起挂。
- 结论：失败点在网络出口层（Mihomo 出站/DNS）或在进程内 DNS 解析（aiohttp ThreadedResolver 与 asyncio.to_thread 共默认线程池）。重启即恢复只符合后者。
- 附带发现：BACKUP_BASE_URL 与主线路同域名，熔断切换无意义。
- 状态：待下次复现时现场取证（curl vs 容器内请求）后再改代码。

## 2026-11-01 归档 ncm（网易云）工具
- 与 a8db344 同款处理：`core/tools/tools_ncm.py` → `core/tools/_archived/tools_ncm.py`，并把 `from .tools_common import logger` 改为 `from core.tools.tools_common import logger`。
- `core/tools/_archived/__init__.py` 增加 `ncm_search_tool`、`ncm_download_tool` 导出；`core/tools/__init__.py`、`core/tools/tools.py` 删除对应 import 与两个 ToolSpec。
- 现役 TOOL_SPECS（10 个）：delegate_to_maid、search_diary、send_master_private、poke、send_qq_file、capture_group_snapshot、search_group_snapshots、parse_rich_message、download_file、generate_image。
- 保留未动：`core/ncm_login.py`（归档模块仍 import）、`config.py` 的 ncm_cookie_file / ncm_download_dir、README 的 ncm 章节。tests/test_tool_markup.py 仅把 "ncm_search" 当字符串样例，无影响。
- 测试：206 项中 205 通过；`test_vision_prefetch::test_pipeline_enqueue_schedules_prefetch_immediately` 失败（`AttributeError: _recent_msg_times`），来自工作区里他人未提交的 session_pipeline.py 改动，与本次无关。

## 2026-11-01 小女仆 ncm 技能：写好但登录未跑通，整体归档
- 女仆确有 skills 机制：`skills/<name>.md`（首行当简介，`list_skills` 读）+ `skills/<name>.py`（`read_skill` 读文档与源码），`read_skill` 支持只有 md 的说明型技能；`skills/` 是容器 RW 挂载卷。
- 写了 `skills/ncm.md` + `skills/ncm.py`（`ncm_search`/`ncm_download` 同步封装归档工具 + CLI），实测搜索能走到「需要扫码」分支。
- 卡点：容器内缺 `qrcode`（已 `pip install --user qrcode` 落到 `data/home/.local`，并加进 `pyproject.toml`）；二维码 3 分钟有效，对话往返常超时，`code 803` 被消费成 `800`，Cookie 没落盘。
- 依机主要求停止并归档：技能移入 `_archive/skills/`，三个扫码辅助脚本移入 `_archive/scripts/ncm_login/`，`_archive/README.md` 补索引与恢复步骤。工具侧归档见提交 66c46cc。
- 状态：ncm 在 Yuki 与女仆两侧均未启用；`data/home/.cache/ncm_cookie.txt` 不存在。

## 2026-11-01 新增「小本本」工具与提示词注入
- 存储：`core/notebook.py` 的 `NotebookStore`（`data/notebook.json`，全局一份，上限 `NOTEBOOK_MAX_CHARS=1024`，超长截断）。
- 工具：`core/tools/tools_notebook.py::update_notebook_tool`，注册为 `update_notebook`（覆盖写，参数 `content`）；ToolSpec 新增 `persist_result: bool = True`，该工具为 False。
- 上下文隔离：`core/engine/engine_reply.py` 的工具结果回写历史前查 spec，`persist_result=False` 时跳过（仅本轮 messages 内可见），避免污染长期上下文；工具自身只回复「已更新小本本」。
- 注入：`core/prompts.py::build_chat_context` 在【回忆】之后、最近对话之前插入 `【小本本】…`，并负面约束不提及/复述小本本，作为潜意识底色；小本本为空时不注入。
- 验证：容器 yuki 内导入 OK；`tests/test_system_state.py` 4 项通过；临时目录实测存取与超长截断、注入顺序正确。
- 状态：代码已就绪，需重启 yuki 容器后生效。

## 2026-11-01 参数简练提示改为只给 delegate_to_maid
- `core/toolchain.py`：`ARGUMENT_BREVITY_HINT` 改名 `MAID_GOAL_BREVITY_HINT`，不再由 `ToolSpec.to_schema()` 全局追加。
- `core/tools/tools.py`：只有 `delegate_to_maid` 的 description 拼接该提示，其余工具（含 update_notebook）不再被追加。
- 遗留：`toolchain.py:231` 的参数截断纠错文案仍写「压缩到 500 字以内」，对所有工具生效，未改。

## 2026-11-01 小本本上限调低到 512 字
- `core/notebook.py`：`NOTEBOOK_MAX_CHARS = 512`（读写都截断）；`core/tools/tools.py` 工具描述与参数说明同步改为 512 字符。
- 原因：`engine_reply.py` 单轮 `max_tokens=1024`，1024 中文字符 + JSON 结构会被截断。

## 2026-11-01 人设参考图：master / Yuki
- 机主提供两张人设图，存为 `output/assets/character/master_reference.png`（主人，1254×1254，三视图）与 `output/assets/character/yuki_reference.png`（Yuki，1024×1536，覆盖旧图；旧图备份到同目录 `_backup/yuki_reference_20261029.png`）。两张原文件实际是 PNG 字节，按 .png 存放。
- `core/tools/tools.py` 的 `generate_image` ToolSpec 描述与 `image_paths` 参数说明改为列出这两张固定人设参考图（含外貌/服装要点），替换原来只提 Yuki 单张的措辞。
- 校验：容器 yuki 内 `_resolve_reference_image` 对两条路径均通过（output 目录白名单 + 5MB 内 + PNG 魔数）；两文件均在 `output/` 下，被 .gitignore 忽略，不进版本库。提交 b6d0823。
- 状态：代码已提交，需重启 yuki 容器/会话才能让新工具描述生效。

## 2026-11-02 18:2x 再次复现（16:57–17:32）
- 排除挂起：/sys/power/suspend_stats/success=0；所有 yuki 日志 30s 心跳无 >60s 空洞（进程从未冻结）；journal 无 suspend 记录；xfce4-power-manager inactivity-on-ac=0。
- 熄屏/锁屏确实在发生但与网络无关：`xset q` DPMS Enabled, Standby 600 / Off 900；light-locker 在跑；xfce4-power-manager 无 dpms-* 键 → 用默认值，"设置了不熄屏"实际没生效。
- 16:57–17:32 并非只 deepseek 挂：图片下载同样 15s 超时；16:50 api.rua.chat 还完全正常。
- 18:16 容器内实测 TLS 0.12s / llm_chat 返回 OK → 已自愈，无需重启 → "重启 run.sh 就好" 大概率是巧合。
- 12:27 NapCat(QQ) 掉线是独立事件：3001 端口 Connect refused。
- journal 未持久化（/var/log/journal 空）→ 旧 boot 证据全丢；取证需要 sudo 开 Storage=persistent。

## 2026-11-02 18:3x 加固 + 关掉自动熄屏
- utils/http_client.py: 新增 DedicatedDnsResolver（独立 4 线程池 + 8s 超时），绕开与 asyncio.to_thread 共用默认池的解析排队风险。
- utils/llm_client.py: 全局会话改用该解析器；chat_completion_raw 拆出 _post_once，连接层异常（Timeout/Connector/OSError/Disconnected）时 reset_global_session() 重建会话并立即重试一次，等价于"轻量重启"。
- 测试：tests/test_llm_client.py + test_llm_retry.py 20 passed；容器内实测正常请求 0.7s、坏端口触发重建后恢复。
- 系统设置：xfce4-power-manager dpms-enabled=false，dpms-on-*/blank-on-* (ac+battery)=0 → xset 显示 DPMS is Disabled，不再自动熄屏/锁屏。inactivity 原本就是 0（不挂起）。
- 待办：合盖动作仍是 4（休眠），合盖仍会断网；journal 未持久化。

## 2026-11-02 18:3x 新增群聊 /重启 指令
- modules/QQNapcatListen/listen_main.py：handle_group_switch 增加 "/重启"（仅 master）。
  流程：_restart_flow → 先 await gateway.send 发「正在重启」→ 再往 staging/restart_<ts>/request.json
  写 {"type": "restart"}；宿主 supervisor 每 3s 轮询，执行 deploy/run.sh 重建容器 + /health 探活。
- 额度保护：_recent_restart_count() 读 deploy/state.json，近 1 小时重启 ≥ MAX_RESTART_PER_HOUR(5) 时直接拒绝。
- 端到端验证：18:26:54 投递 → 18:27:00 容器重建 → 18:27:07 supervisor 记录 restarted 且健康；记忆快照 backups/yuki_memory/20261102_182655。
- 已知：run.sh 用 docker rm -f（SIGKILL），不是优雅停机；靠 supervisor 重启前的记忆快照兜底。NapCat 离线时 /notify 会 500，不影响重启。
- 测试：test_napcat_gateway / test_napcat_inbound / test_modes 14 passed。

## 2026-11-02 18:3x /重启 补发「重启完成」
- listen_main.py 新增：_write_restart_notice / _pop_restart_notice / send_pending_restart_notice。
  /重启 时先把「Yuki 重启完成，我回来啦~」写进 data/restart_notice.json（含 chat_id/mode/ts），
  新进程在 start_background_tasks 里补发，最多重试 20 次×3s，超过 10 分钟视为过期丢弃。
- 端到端实测：18:29:28 投递 → 18:29:32 容器重建 → 18:29:39 WS 连上 → 「已向 1057020972 补发重启完成通知」
  → data/restart_notice.json 已被消费删除。

## 2026-11-02 白名单BOT不再强制回复 + 纯BOT发言降欲 0.75
- listen_main.py：`called` 前置 `not incoming_message.is_bot`，即白名单放行的 BOT 消息即使叫名字/@ 也不带 force_reply，不再跳过防抖，避免两个 BOT 互相召唤死循环。
- engine_decision.py：防套娃惩罚 `desire *= 0.8` 改为 `0.75`（纯 BOT 发言时降回复欲）。
- 验证：容器内 tests/test_ice_break_pipeline.py 13 passed；提交 51bbb38。

## 2026-11-03 新增 skip 工具（模型主动保持安静）
- core/tools/tools_skip.py：skip_reply_tool 返回 ToolResult(data={"skip_reply": True})；非 group 模式直接失败（私聊必须回复）。
- core/toolchain.py：新增 SKIP_REPLY_MARKER；execute_tool_call 见 data.skip_reply 就置 context.metadata["skip_reply"]，execute_tool_calls 随即 break（同批后续工具不再执行，避免跳过之后又发消息）。
- core/engine/engine_reply.py：工具轮结束后若已 skip，直接返回 SKIP_REPLY_MARKER，不再发起收尾请求。
- core/session_pipeline.py：generate_reply 收到标记 → replace_session 保留用户消息、记日志、stop=True，跳过 send/finalize，全程不发任何消息。
- 测试：tests/test_skip_tool.py 4 passed（工具注册/批量中断/私聊拒绝/管线不发消息）。既有 3 个失败（test_tool_spec_to_schema、test_chat_with_tools_executes_text_form_call、test_chat_with_tools_returns_working_notice_when_cleaned_empty）在改动前就已失败。
- 提交 cd0377f；core/prompts.py 与 tools.py 里 generate_image 描述属之前未提交的改动，未纳入本次提交。

## 2026-11-03 skip 不留痕
- engine_reply：同批工具里有 skip 时不发送也不记录阶段文本（避免「我……<调用skip>」先漏出去）。
- session_pipeline 新增 _prune_skipped_round：以本轮进入时的快照为基，丢掉本轮追加的阶段文本/工具返回/skip 痕迹，只保留工具期间新到的用户消息（防止模型沉默导致丢消息）。
- tests/test_skip_tool.py 补 test_skip_leaves_no_trace_in_history（真实 ToolCallManager 跑 skip，断言 history 没有 tool/skip 记录）；全量 206 passed，4 个既有失败与本次无关。

## 2026-11-03 修复 4 个过期测试（全量 211 passed）
- test_toolchain.test_tool_spec_to_schema：删掉"to_schema 统一拼简练提示"的过时断言（0c15e01 起提示只挂在 delegate_to_maid），新增 test_brevity_hint_only_on_delegate_tool 校验这一点。
- test_tool_markup / test_reply_format 里的假 registry 补 get_spec（persist_result 接口引入后缺失）。
- test_vision_prefetch：__new__ 构造的 pipeline 补 _recent_msg_times（_record_human_timestamp 依赖）。
- 均为测试桩同步，无产品代码改动。

## 2026-11-03 修 skip 的返回值个数 bug
- 线上日志：skip 执行成功但紧接着 `[Engine] LLM 调用失败: too many values to unpack (expected 2)`，最后发了一句「暂时连接不上网络」。
- 原因：chat_with_tools 的契约是 2 元组 (raw, visible)，api_reply 也只拆 2 个；skip 分支我写成了 3 元组。之前那个 "too many values to unpack" 的测试失败其实是真 bug，我误判成测试问题把测试改了。
- 修复：skip 分支改回 `return SKIP_REPLY_MARKER, SKIP_REPLY_MARKER`；tests/test_skip_tool.py 的断言同步改回 2 元组。全量 211 passed。

## 2026-11-03 日记注入条数改为配置可控
- 原来 core/session_pipeline.py 里 `n_results=8` 硬编码；rag.retrieval_top_k 只给 search_memory 用，改名易误解。
- 新增 `rag.inject_top_k`（默认 5）+ `cfg.INJECT_TOP_K`，pipeline 改用它；configs/config.yaml 已同步 `inject_top_k: 5`（该文件被 gitignore）。
- 状态：语法检查通过；本机 venv 缺 libpython3.11 / 系统 python3 缺 yaml，未能实跑验证，需重启服务确认。commit 3cc39d8。

## 2026-11-03 记忆召回跨轮保留上一轮 top-1
- core/session_pipeline.py::retrieve_memories 之后加 `_merge_recent_recall`：按 chat_id 记录最近两轮各自「新召回」的 top-1，下一轮把这两条带进注入列表，剩余名额用本轮新召回补齐，去重键为 timestamp+正文。
- 效果：t1 = 5/4/3/2/1；t2 = 带 t1 的 1 + 新召回 top4；t3 = 带 t1 的 1、t2 的 1' + 新召回 top3。
- 注意：_compute_rag_interest 现在吃的是合并后的列表（含保留条目）；注入顺序经 prompts 的 reversed() 后变为「新召回 → 保留条目」。状态：语法检查 + 逻辑脚本验证通过，未实跑。

## 2026-11-03 召回保留条目落盘
- 新增 core/recall_cache.py：`RecallCacheStore`（/ `recall_cache_store` 单例）把每个 chat_id 最近两轮召回的 top-1 写到 data/recall_best.json，惰性加载 + 线程锁 + 临时文件 os.replace 原子写。
- core/session_pipeline.py::_merge_recent_recall 改用它读写，去掉内存字典，重启后保留条目仍在；只留最近两轮。
- 状态：store 读写/裁剪/落盘用脚本验证通过，pipeline 语法检查通过，未实跑。

## 2026-11-03 召回顺序反转 + 兴趣度只看新召回
- _merge_recent_recall 列表顺序改为「新召回(高→低) + 保留条目(远→近)」，经 prompts reversed() 注入后提示词顺序变成「保留条目(近→远) + 新召回(低→高)」，与预期的 1 4' 3' 2' 1' / 1 1' 3'' 2'' 1'' 一致。
- retrieve_memories 额外写 context["recall_new_results"]（本轮原始召回），decide_reply_action 的 _compute_rag_interest 改用它，群聊兴趣度不再被保留条目拉偏。
- 状态：语法 + 顺序/去重脚本验证通过，未实跑。

## 2026-11-04 19:2x 断网真因：mihomo IPv4 出站失效（非休眠）+ 网络看门狗
- 机主报「一两小时后 LLM/图片下载/CLI 凭证全 connection timeout，NapCat 正常，开屏输密码就恢复」。
- 取证推翻休眠：/sys/power/suspend_stats/success=0、up 2 天 6 小时、19:12 期间 30s 心跳无空洞；
  journal 无 suspend；DPMS 早已禁用。
- 真正现象（19:12:00–19:13:27）：Yuki 连 api.deepseek.com 全部 ConnectTimeout；mihomo 日志显示这些
  连接已被规则命中（GeoIP(cn)→DIRECT）却无 dial 结果；同一分钟 cli-proxy-api(8317) 的上游
  daily-cloudcode-pa.googleapis.com TLS 握手超时。即「经 TUN 的 IPv4 新建连接全挂」。
- NapCat 假正常：QQ 走 IPv6（240e:...）直连，不经 TUN，且既有长连接不断。
- 恢复点：19:13:34 解锁 → 19:13:36 mihomo `Start initial configuration`（重载）→ 立刻恢复；
  11-04 全天仅此一次重载，前几次「开屏就好」同源。
- 触发线索：18:46–18:48 WiFi 在 4 个 AP 间连续漫游（`Connection to AP ... lost`）；mihomo 历史上
  多次 `[TUN] default interface lost by monitor`。结论：WiFi 变化后 mihomo 默认出站接口失效且不自愈。
- 方案（已落地）：deploy/netwatch.py（root，systemd `yuki-netwatch.service`，30s 探活 direct/proxy
  两条路径）+ NM dispatcher `90-mihomo-reload`（网卡 up/down/DHCP 变化后 debounce 60s 重载）。
  修复阶梯：重载 mihomo → 清 DNS/fake-ip 后重载 →（仅链路层异常时）nmcli reapply/重连 WiFi；
  限流 90s/12 次每小时；触发时快照写 logs/netwatch_diag_*.json，日志 logs/netwatch.log。
- 验证：reload API 204 且 27ms 生效；dispatcher 事件可触发重载、第二次被 debounce 拦；
  模拟失败跑通整条阶梯并正确判定「链路层正常→只重置 mihomo」；服务 enabled+active，探活 200ms 级。
- 副产品结论：mihomo 重载不丢节点选择（仍是 🇯🇵 日本W04）；不再监听 connectivity-change（重载本身会
  触发该事件，会形成循环）。
- 状态：线上生效。若下次仍断且日志显示「重载后探活仍失败」，说明问题在 mihomo 之外（节点/校园网），
  快照文件里有当时的 route/AP/并发连接数可直接判定。

## 2026-11-04 19:3x QQ `/刷新` 指令（真实探活 + 原会话回报）
- 需求：NapCat 不会断，主人用 `/刷新` 手动刷网络；在哪个会话发就在哪里回；实际测试连通性后回「测试已连通」。
- 容器侧（modules/QQNapcatListen/listen_main.py）：`/刷新` 加入 `/关闭 // 开启 // 重启` 同款指令集（master 限定，
  非 master 回「只有哥哥大人才能刷新网络哦！」）；群聊走 handle_group_switch，私聊新增
  handle_private_command（只认 /刷新，其余指令行为不变）。容器不碰网络：写
  data/netforce_pending/<id>.json，轮询 data/netforce_result.json（id 匹配），45s 超时兜底。
- 宿主侧（deploy/netwatch.py 新增 force 子命令）：systemd `yuki-netforce.path`
  （DirectoryNotEmpty=data/netforce_pending）触发 `yuki-netforce.service` → 跑两条路径 HTTPS 探活；
  正常就直接回写结果（不重载），失败才走修复阶梯（限流同 watch 循环），回写 ok/probes/actions。
- 回复文案：成功「测试已连通（direct 通，proxy 通）」；失败「没连通（direct 不通，proxy 通），已尝试：…」；
  超时「宿主看门狗没有响应，刷新超时了…」。
- 验证：宿主侧真实请求 → path 单元 2s 内触发、结果回写；模拟失败分支跑完整阶梯并回写 ok=false；
  容器内以假 gateway 跑通群聊/私聊/非 master/普通消息四种路径，回复的 chat_id 与 mode 均与来源一致；
  tests/test_netforce_command.py 5 项通过，napcat_inbound/gateway/modes 14 项仍通过。
- 已按 supervisor 通道重启容器（快照 20261104_193404）让指令生效，health ok、napcat_online=true。
- 提交 1b689ac；docs/architecture.md 3.10 补了说明。

## 2026-11-04 20:2x /刷新 未生效排查 + 关闭熄屏锁屏
- 多方日志：/刷新 指令链路正常（20:15/20:16 均回写结果），失败在修复动作：20:09 BEACON-LOSS、20:10:32 WiFi 漫游
  → dispatcher 触发重载 → mihomo 重载卡死（控制接口 10s 超时），期间所有新连接瞬间 SSLEOFError。
- 修复（73ea17e）：修复阶梯改为 重载(6s 超时) → 接口活着才清缓存重载 → SIGTERM core（mihomo-party 自动拉起，
  实测 3.4s 恢复）→ WiFi 兜底；dispatcher 只处理 up/dhcp 变化并等 connected+默认路由后再重载；
  find_core_pid 改 pgrep -x；单元 stdout 置空消除日志双写。
- 熄屏/锁屏：X 屏保 timeout=600 仍在（xfce power-manager 只管 DPMS），到点黑屏后 light-locker 锁屏。
  已 xset s off/noblank/-dpms，停掉 light-locker；~/.config/autostart 覆盖 light-locker（Hidden=true）
  并新增 yuki-no-blank.desktop 登录时关屏保（副本在 deploy/desktop/）。
- netwatch 修复阶梯第一步新增 wake_desktop：loginctl unlock-sessions、chvt 回桌面 VT、xset dpms force on、
  重新关屏保、杀 light-locker。root 实测通过。

## 2026-11-04 整合重写 tests/ 测试套件
- 将原 22 个碎片化测试文件整合重写为 11 个按领域内聚的模块：`test_config.py`、`test_logger.py`、`test_llm_client.py`、`test_napcat.py`、`test_vision.py`、`test_memory.py`、`test_reply_format.py`、`test_toolchain.py`、`test_pipeline.py`、`test_maid.py`、`test_github_monitor.py`。
- 移除针对已归档 `core/tools/_archived` 的冗余测试（`test_system_state.py` 及 `manage_timer_task_tool` 用例）、清理 `test_ice_break_pipeline.py` 尾部手写 runner 死代码、消除跨文件重复假对象，统一使用 `pytest-asyncio` 自动模式、`tmp_path` 与 `monkeypatch`。
- 新增 `core/recall_cache.py`（跨轮 top-1 召回持久化与管线合并）和 `core/notebook.py`（小本本截断与损坏容错）探测用例。
- 状态：`pytest` 全量 61 项内聚测试全绿（耗时从 ~21s 降至 ~11s），`deploy/test_gate.py` 通过。

## 2026-11-04 归档 `core/` 未挂载模块与历史遗留代码
- 在 `_archive/` 下按功能新建 9 个分类目录并各附 `README.md`（说明功能、原埋点与接入步骤）：
  - `ncm_tools/`（`core/ncm_login.py`、`core/tools/_archived/tools_ncm.py`）
  - `qzone_tool/`（`core/tools/_archived/tools_qzone.py`）
  - `search_tools/`（`core/tools/_archived/tools_search.py`）
  - `master_status/`（`core/tools/_archived/tools_status.py`）
  - `timer_tool/`（`core/tools/_archived/tools_timer.py`）
  - `user_resolve_tool/`（`core/tools/tools.py` 尾部注释的 `resolve_user_tool`）
  - `maid_legacy/`（`core/maid/maid_{loop,prompt,runtime,approval,selfevolve,worklog}.py` 及 `maid_{tools,memory,common,facade}` 中旧内置循环部分，保留线上 `maid_harness` / `maid_charter` / `search_diary_fast` 等核心路径）
  - `focus_modes/`（`core/modes.py` 与 `core/toolchain.py::ToolRegistryProvider`）
  - `core_legacy_snippets/`（`core/brain.py`、`core/history_manager.py`、`core/engine/engine.py`、`core/toolchain.py` 中未挂载方法与旧兼容转发器）
- 更新 `tests/test_maid.py` 与 `tests/test_pipeline.py` 对齐精简后的核心模块，更新 `_archive/README.md` 索引。
- 状态：语法编译、核心导入自检与 `pytest` 61 项单测全部通过。

## 2026-11-04 精简并全面更新 `/docs` 文档
- 移除重复或已过期的 `docs/module-relationship.md`、`docs/module-interface.md`、`docs/development-plan.md`、`docs/Log.md`。
- 重写 `docs/architecture.md`：更新为容器只读挂载 + 宿主三守护服务（`supervisor`/`maid_runner`/`netwatch`）运行拓扑、最新目录树、8 阶段管线数据流及「代码定位速查表（LLM 交接索引）」。
- 重写 `docs/toolchain-usage.md`：同步现役 12 个工具（含 `update_notebook`、`skip`）、`persist_result=False`、`_prune_skipped_round` 及 `_archive/` 已归档工具索引。
- 重写 `docs/contributing.md` 为《开发与 LLM 交接指南》：明确本机 `~/miniconda3/envs/yuki/bin/python` 测试环境、只读容器生效方式、常见开发流程与数据/人格安全红线。
- 重写 `docs/troubleshooting.md`、`docs/changelog.md` 并微调 `docs/evolution-charter.md`，彻底清除 `rm -rf yuki_memory/`、`data/yuki_log.txt`、`ws_connection.py` 等废旧断言。
- 状态：`pytest -q` 61 passed，已提交 git。

## 2026-11-04 重写 setup.py、去除部署脚本硬编码并补充大众/Agent 部署指南
- 重写 `setup.py`：消除顶部第三方库硬导入（裸 Python 环境可直接运行 `--help` / `--check --json`）；支持 `uv sync` 或通过标准库 `tomllib` 解析 `pyproject.toml` 调用 `pip` 安装；对齐最新 `config.py` 字段（移除旧 `llm_platform` 等废弃字段，补齐 `connection.qq` 等）；新增 `-y / --non-interactive`、CLI 快捷参数、`--set key.path=val`、环境变量注入及 `--check [--json]` 环境/依赖/模型/配置/NapCat端口连通性自检。
- `pyproject.toml`：`requires-python` 从 `==3.11.15` 放宽为 `>=3.11`。
- `deploy/`（`run.sh`、`verify.sh`、`install-service.sh`、`supervisor.py`、`maid_runner.py`、`retention.py`、`reviewer.py`）：默认 `ROOT` 改为动态解析当前仓库根目录，保留 `YUKI_ROOT` 环境变量覆盖。
- 更新 `README.md`：重写大众部署指南（本地直跑 + Docker 进阶），新增完整的「Agent 自动化部署指南（Agent向文档）」5 步非交互式 SOP，同步现役 12 个工具与最新文档索引。
- 状态：裸 Python 与 conda 环境验证 `--check` 通过，`pytest -q` 61 passed。

## 2026-11-04 克隆实测与消除向量模型双倍磁盘/双倍内存占用
- 在 `~/githubmono/Yuki-Chan-Bot` 从零克隆实测，定位并修复 3 个真实部署阻塞点：
  1. `uv.lock`（锁死 `==3.11.15` 且无包列表）从 git 移除，`.python-version` 放宽为 `3.11`，`pyproject.toml` 精简为顶层直接依赖 `>=` 约束，解决跨平台/跨小版本装包报错。
  2. 重写 `utils/download_model.py`：默认优先走国内魔搭社区 ModelScope API 直连源（实测 13.16 MB/s，29s 完成，自动回退 `hf-mirror` / `huggingface`），直接流式写入 `./models/text2vec-base-chinese/` 并带实时进度条，不再经 `~/.cache/huggingface` 产生第二份 391MB 磁盘副本；同时已清理本机 `~/.cache/huggingface` 冗余副本（释放 391MB）。
  3. 新增 `get_embed_model()` 与 `get_chroma_client()` 进程内单例缓存，让 `MemoryRAG` 与 `StickerManager` 共享同一 `SentenceTransformer` 实例与 `MemeProcessor`，消除启动时重复加载两次 391MB 向量模型的问题（节省 ~400MB 内存，`pytest` 全量耗时从 15.1s 降至 7.9s）。
- 状态：ModelScope 下载端到端实测通过，`YUKI_DRY_RUN=1` 确认模型只加载一次，`pytest -q` 61 passed。

## 2026-11-04 发布 v1.0.0 Changelog 与版本标签
- 更新 `docs/changelog.md` 将 `[未发布]` 归档为 `[1.0.0] - 2026-11-04`，补入一键部署、Agent向文档、ModelScope 向量模型直下与进程内单例共享等条目；同步 `pyproject.toml` 版本为 `1.0.0`。
- 打标签 `v1.0.0` 并推送到远端。






## 2026-11-05 主模型亲手操作工具（bash / phone_action）
- 新增 `core/tools/tools_bash.py`：单条 shell 执行，cwd 固定项目根，默认 20s（上限 60s，进程组整棵杀）；输出脱敏 `sk-*`/`tvly-*` 及 `*_key/token/secret=` 形态，拦 `rm -rf /`、`mkfs`、关机、凭证文件读取；`remember=false` → `data.no_persist` 由引擎跳过写历史。
- 新增 `core/tools/tools_phone.py`：adb 控制手机。`uiautomator dump` 精简为 `[#编号] [类型] 文案 @(cx,cy)`（去重、剔除不可见与整屏空壳、上限 `tools.phone_max_nodes`）；动作后自动等待刷新并回传新控件树；控件树文字 < 3 或 `include_screenshot=true` 时截屏缩放到 720px 宽并画编号红框（Set-of-Mark），注册进 `ImageStore` 供多模态上下文。
- 新增 `core/tool_prune.py`：按会话统计连续未调用工具轮数，达 `tools.prune_idle_turns`（默认 2）后把 `role="tool"` 消息折叠成 `【历史操作·已折叠】…备注…` 存根，零额外 LLM 开销。
- `EngineReplyService`：支持工具动态 `no_persist`、`_attach_tool_screenshots` 把工具截图渲染成 `image_url` 块、`_after_turn` 折叠钩子；`max_rounds` 由 `tools.max_rounds`（默认 8）控制。
- `config.py` 新增 `tools` 配置段；`deploy/Dockerfile` 增加 `adb`；`docs/toolchain-usage.md` 工具清单更新为 14 个。
- 测试：新增 `tests/test_tool_hands.py`（17 例），全套 `pytest -q` 78 passed。
- 状态：代码已提交 `7f4b299`。**待机主处理**：宿主未安装 platform-tools（`adb` 不在 PATH），容器镜像需重建才会装上 adb 客户端；中文输入需手机端 ADBKeyboard。

## 2026-11-05 手机工具实地打通（华为 MAO-AL00 / 2JPYD23819000295）
- 宿主安装 `android-tools-adb`（adb 1.0.41 服务端），手机授权后 `adb devices` 可见；`deploy/Dockerfile` 已含 `adb` 客户端，镜像重建（`yuki:base` e509f2310389）并通过 `supervisor.restart_container()` 平滑重启，`/health` ready。
- 手机安装 ADBKeyboard 并 `ime enable com.android.adbkeyboard/.AdbIME`：`tools_phone._input_text` 改为「临时切 IME → ADB_INPUT_TEXT 广播 → 还原原 IME」，实测 Termux 中输入 `echo 电池测试OK > /sdcard/yuki_ime.txt` 后文件内容正确，原输入法已还原。
- 控件树去重增强：同一中心点的同类节点只保留一个（首页天气控件原先重复 3 条）。
- `launch` 改为 `_launch()`：检测 monkey 的 `aborted`/`No activities found`（退出码仍为 0），失败时回传已安装第三方包名；补充 浏览器/备忘录/termux 别名。
- 实机验证：inspect 首页 18 个节点正常；`include_screenshot=True` 截图 720x1592/152KB，红框编号与图标对齐。
- 测试：`tests/test_tool_hands.py` 增至 19 例（含 ASCII 与中文输入路径、IME 还原断言），全套 80 passed。

## 2026-11-05 日记只记聊天，轮数不计工具
- 新增 `core/history_filter.py`（`is_dialogue_message` / `dialogue_messages` / `dialogue_length`），把「聊天消息」定义为 user/assistant。
- `SessionPipeline.finalize_conversation`：强制写日记的阈值从 `len(session) > diary.max_length` 改为按聊天条数判断，工具消息不再顶数。
- `EngineMonitorService` 空闲巡检：`diary.min_turns` 同样只数聊天条数（日志改成「聊天轮数」）。
- `EngineDiaryService.do_summarize`：总结输入只喂聊天消息，工具输出/工具调用痕迹不进日记；回写历史保留 system + 最近 KEEP_LAST_DIALOGUE 条聊天。
- 测试：新增 `tests/test_diary_filter.py`（7 例）覆盖过滤器、总结输入过滤、两个阈值；全套 87 passed。容器已平滑重启，/health ready。

## 2026-11-05 手机组合技（phone_macro）：操作历史 + 语义定位器 + 回放
- 新增 `core/phone_macro.py`：语义定位器（text/cls/rel 比例坐标）、界面指纹 `state_of`、expect 生成（动作后新增文案，过滤「加载中」类过程提示）、`PhoneHistory`（jsonl 滚动 500/留 300）、`MacroStore`（原子写、同名覆盖 version+1、used/ok/fail 统计）、`clean_steps` 清洗、`{{参数}}` 渲染/字面量替换。
- `core/tools/tools_phone.py` 重构：抽出 `_prepare_step`（工具参数 → 可记录单步）与 `_exec_step`（录制/回放共用的执行器）、`_wait_expect`（回放校验）；动作前 dump 兼作 before 快照，成功后写历史；`remember=false` 不落历史。
- 新增工具 `phone_macro`（`core/tools/tools_phone_macro.py`）：`list / history / show / save / play / delete`；save 支持 `from_history=N`、`exclude=[#n]`、`param_defs`+`replace` 参数化；play 逐步校验 expect，失败即停并回传控件树+截图，launch 步只校验包名（App 会恢复上次页面）。
- 清洗规则：往返折叠（tap…back 后界面指纹回到 tap 前 → 整段丢弃）、空转按键（before/after 指纹相同，多为输入法吃掉 back）、相邻重复点击（2.5s 内同定位器）；历史本身不改，只在存宏时清洗。
- 配置：`tools.phone_expect_timeout=3.0`；`phone_action` 的 `remember` 语义扩展到操作历史。
- 校验：真机（华为 MAO-AL00）实测 launch 设置 → tap WLAN → back，存宏自动折叠 2 步只留 launch，play 通过；曾遇「输入法吞 back」导致空转，已用指纹规则覆盖。离线测试新增 `tests/test_tool_phone_macro.py` 21 例，全套 108 passed。
- 已通过 `deploy/supervisor.py` 的 `restart_container()` 平滑重启，/health ready，容器内确认 `phone_macro` 已注册（15 个工具）。

## 2026-11-05 手机自动化工具链四层架构重构
- 新增 `core/phone_driver.py`（设备驱动层 `AndroidDriver`）：
  - 动态临时 dump 路径 `/data/local/tmp/yuki_ui_{serial_or_pid}.xml`，消除多进程/多设备冲突；
  - `ensure_device` 自动通过 `wm size` 缓存真实物理分辨率、通过 `ime list -a` 预检并缓存 ADBKeyboard 安装状态；
  - 连续 2 次 ADB 超时自动触发 `adb kill-server` / `start-server` 自愈；
  - 修复 ASCII 输入 `%s` 转义漏洞，手势加入 `long_press` `(x+2, y+2)` 防忽略与 `swipe` 坐标/时长微扰，`wait_expect` 改为指数退避轮询。
- 新增 `core/phone_agent.py`（智能提炼与守护层）：
  - `SystemWatcher`：识别权限请求、开屏广告、更新提示等系统/应用遮罩并自动点击消除；
  - `MacroDistiller`：在规则清洗基础上调用 Sub-LLM 剔除无效探索滑动，自动提取业务变量生成 `param_defs` 与 `replace`（异常无感降级回 `clean_steps`）；
  - `MacroHealer`：宏回放受阻时调用 Sub-LLM 在当前控件树匹配改版/偏移后的语义等价控件，跑通后自动回写 `MacroStore` 自我进化。
- 升级 `core/phone_macro.py`：定位器纳入 `resource-id`（`id`），实现 5 级匹配优先级（`text+id` > `text+cls` > `id+距离容差` > `fuzzy` > `coord`）。
- 升级 `core/tools/tools_phone.py` 与 `core/tools/tools_phone_macro.py`：
  - `_compact_tree` 保留无文字全屏 `scrollable` 容器、中心点重合保留面积更小节点、超限按交互优先级智能截断并按从上到下重排；
  - `phone_action` 新增复合动作 `scroll_to_find`（自动循环滑动查找目标文案，最多 5 次）；
  - 按机主指示不设支付/密码拦截护栏（使用隔离账号环境）；
  - 全套测试 `pytest tests -q` 118 passed。

## 2026-11-05 手机聚焦模式（Phone Focus Mode）：按需展开 ToolSpec + 退出总结覆写
- 新增 `core/phone_focus.py`（`PhoneFocusManager` + `phone_start_tool` + `phone_finish_tool`）：
  - 常态下 `FunctionRegistry.get_tools(phone_focus=False)` 隐藏 `phone_action` / `phone_macro` / `phone_finish` 的长篇 schema，只暴露极简入口 `phone_start(goal)`；
  - 调用 `phone_start` 后进入手机聚焦模式，自动返回当前屏幕控件树与已有组合技简表，并将当轮及后续轮次的 ToolSpec 切换为聚焦集（`phone_action` / `phone_macro` / `phone_finish` + `skip` / `send_master_private` / `send_qq_file`），收起日记、小本本、画图、小女仆等无关工具；
  - 聚焦期间保持群聊在线状态，可正常发言，期间插入的群友消息按序保留；
  - 调用 `phone_finish(summary="...")`（或连续闲置 > 5 轮自动退出）时：清除聚焦期间产生的所有手机工具调用与阶段思考记录，保留期间正常聊天消息，并以 `role="user"` 身份注入 `【手机操作总结】{summary}`，恢复常态 ToolSpec 空间。
- 新增 `docs/focus-mode-paradigm.md` 整理「聚焦模式（Focus Mode）」通用设计范式与 4 步工程模板（供后续扩展浏览器、Bilibili 等聚焦模式复用），同步更新 `docs/toolchain-usage.md`。
- 修复容器内 `_restart_adb_server()` 误杀宿主 `adb server` 并在无 `/dev/bus/usb` 的容器命名空间拉起 daemon 导致找不到 USB 手机的问题：容器环境下（`/.dockerenv`）改为 `adb reconnect`；同时修复 `phone_finish` 持久化历史重复注入总结与未连接设备时自动回退聚焦状态。
- 全套测试 `pytest tests -q` 121 passed。

## 2026-11-06 /手机聚焦自动唤醒解锁
- `core/phone_driver.py` 新增 `wake_and_unlock()`：`dumpsys power` 判 mWakefulness（asleep 才发 KEYCODE_WAKEUP）→ `dumpsys window` 查 keyguard（isKeyguardShowing / mDreamingLockscreen）→ 按真实分辨率上滑（带抖动，最多 2 次）→ KEYCODE_MENU 兜底；返回 (是否解锁, 中文说明)。
- `core/phone_focus.py::phone_start_tool` 在进入聚焦后、inspect 前调用，结果写进 header「唤醒/解锁: ...」与 data["unlocked"]；失败时提示可先上滑/按电源键。
- 本机无锁屏密码（机主确认），故不做凭据输入。
- 实测：KEYCODE_SLEEP 后 phone_start → 「已点亮屏幕、上滑解锁成功(第1次)」，inspect 拿到 bili 首页；`pytest tests` 121 passed。
- 改成静默：`phone_start` 输出与 data 不再出现唤醒/解锁字样（仅 logger.warning 记录失败），模型只看到屏幕内容；实测休眠→自动解锁→inspect 正常，121 passed。

## 2026-11-06 /手机控件树精简 + 退避重试 + 100轮上限 + /phone 实时监控WebUI
- `core/phone_driver.py::dump_xml`：常规 dump 失败自动尝试 `uiautomator dump --compressed`（绕过淘宝等 WebView/DinamicX 触发的 NAF 空指针崩溃），并按 0.6s -> 1.2s -> 2.0s 退避等待加载重试；仍失败时降级为空控件树+截图模式，不再整轮抛错掉线。
- `core/tools/tools_phone.py::_compact_tree`：彻底移除纯静态 `文本` 节点（静态文字直接由默认附带的标注截图承载），仅保留可交互节点（`输入`/`可点`/`滚动`）；过滤 `[\ua000-\uf8ff]` iconfont 乱码字符；可点击容器自身无文字时自动聚合内部非交互子文本或同位置透明点击层标签（如淘宝底栏「店铺/客服/收藏/加入购物车/领券购买」）；过滤包裹子按钮的无标签外层容器，并跳过全屏滚动容器的大红框标注。
- `core/engine/engine_reply.py` & `config.py`：手机聚焦模式 `phone_focus_max_rounds` 默认设为 100；`_attach_tool_screenshots` 自动替换上一步旧的 `【工具截图】`，保证百轮操作不耗尽 `native_vision_max_images` 配额。
- `modules/debug/phone_trace.py` & `modules/debug/webui_server.py`：复用 8777 端口新增 `http://127.0.0.1:8777/phone` 页面与 `/api/phone/*` 接口，实时展示手机当前画面、当步 Yuki 看到的标注画面/原图、Yuki 收到的用户原文本、Yuki 回复的原文本、当步回传控件树与每步耗时分解，并持久化至 `data/phone_traces/` 支持历史回翻（`pytest` 时自动跳过默认目录写盘防止污染）。

## 2026-11-06 /无XML二级弹窗 OpenCV 视觉检测候选框 + 屏幕物理分辨率对齐
- 原因排查：淘宝规格选择弹窗（`SkuDialogFragment`）由 Weex2/Unicorn Canvas 自绘，Android ViewRoot 内部无 AccessibilityNodeInfo（XML 仅 12 个全屏空 FrameLayout）；同时 XML 根节点高度为 `2267`（扣除了底部 121px 手势导航区），而 `screencap` 实际物理分辨率为 `1080x2388`，导致模型按 `2267` 猜 `(540, 2200)` 落在橙色按钮 (`y=2229..2341`) 上方空白处。
- 修复：
  1. `core/phone_driver.py::resolve_screen_size` 始终优先对齐 `wm size` / 截图真实物理分辨率 `1080x2388`。
  2. `core/tools/tools_phone.py::_populate_visual_nodes`：当 XML 可交互节点 `< 3` 时，自动用 OpenCV (`Canny + 形态学闭运算 + IoU/包含去重`) 从当前截图中提取按钮/规格卡片/图标边界框（约 15ms），生成 `[#1]..[#N]` 视觉候选框并画上红框标注，模型直接 `target="#编号"` 即可精准点中中心坐标，无需盲猜坐标。

## 2026-11-06 /WebUI 甜酷千禧粉重写 + 深度遥测埋点与可视化大屏
- `modules/debug/context_snapshot.py` & `core/session_pipeline.py` & `core/engine/engine_reply.py`：
  - 修正 `PIPELINE_STAGES` 阶段顺序（`retrieve_memories` -> `decide_reply_action`）；
  - 绑定运行时 `YukiState`，新增 `yuki_runtime_state()`（采集 24h 生物钟采样曲线与当前相位、各群实时精力/活跃度/说话欲望、小女仆与手机聚焦状态）；
  - 单轮快照补充发送者、RAG 兴趣度、当轮群精力/热度/生物钟倍率、多轮 LLM 耗时与工具调用链轨迹 `tool_trace`；
  - 新增 `analytics()` 聚合回复决策分布、8 阶段平均耗时瀑布、最近 24 轮 Token 角色堆叠趋势、热门工具 Top 榜与手机自动化统计。
- `modules/debug/webui_server.py`：
  - 重写为甜酷千禧粉（Sweet-Cyber Pink）亮色毛玻璃统一单页工作台（兼容 `/`、`/analytics`、`/phone` 直接访问与丝滑切换），带轻量樱花粒子动效、本轮收发速览卡、System Prompt 默认折叠、24h 生物钟 SVG 面积曲线、双粉色手机拟物外框与控件树搜索过滤。

## 2026-11-05 QQ `/切换` 主备模型线路对调
- 需求：发送 `/切换` 时把全局请求模型从主模型切到备用（或反向），做简单的模型切换。
- 机主确认：整条线路对调（模型名 + base_url + api_key + 原生视觉开关）、只内存生效（重启回配置）、群聊与私聊都可用。
- 实现：`config.Config.swap_llm_route()` 对调 `api.llm_*` / `model.*`（备用 Key 为空时回填，避免主线路没 Key）；`utils/llm_client.reset_route_state()` 清主备熔断状态；`listen_main.switch_llm_route()` 封装切换并回报当前主/备模型名，接进 `handle_group_switch`（master 限定）与 `handle_private_command`。
- 测试：`tests/test_napcat.py::test_switch_command_swaps_route_and_auth`；容器内 `pytest tests/test_napcat.py tests/test_llm_client.py tests/test_config.py -q` 23 passed。
- 状态：代码完成，容器需重启（`deploy/run.sh` 或 supervisor）后生效。

## 2026-11-08 分支 feature/diary-adversarial：日记建图与可视化（外部程序组）
- 需求：为 6000+ 篇日记做关键词共现图谱 + 物理仿真可视化（节点可看内容），作为后续「话题随机游走/自主对抗定长期目标」的地基；本分支只做建图与可视化。
- 新增独立程序组 `diary_graph/`（自带 `.venv`，不污染主项目/容器依赖）：`loader.py` 纯 sqlite3 只读 chroma.sqlite3 的 diaries collection（6485 篇）；`extract.py` jieba + custom_dict/aliases/stopwords + 词性过滤 + TF-IDF Top-K；`graph.py` 共现建图 + 时间衰减（半衰期）+ 剪枝 + Louvain 簇 + 介数/桥接；`render.py` pyvis（`cdn_resources=in_line`，离线单文件）注入侧栏，点节点看相关日记片段；`__main__.py` 提供 `build`/`serve`。
- 关键词缓存带词典指纹（custom_dict/stopwords/aliases/extra_stop/top_k 改动即失效）。
- 全量实测：6485 篇 → 剪枝后 2517 节点/12283 边；默认输出 1200 节点/9897 边/15 簇，HTML 约 7MB，本地 `serve` 冒烟 HTTP 200。
- 已知：jieba 的 nr 不可靠（蔚蓝档案/安卓被标人名），未自动去人名；高频群友名（Momo、白姐姐…）成超级枢纽，用 `--extra-stop` 手工排除。
- 状态：可跑，未提交待提交。

## 2026-11-08 分支 feature/diary-adversarial：修掉"毛线球 + 颤抖"
- 渲染层（`render.py`）：forceAtlas2Based 参数改为 排斥 -70 / 向心 0.03 / 弹簧 90 / 阻尼 0.85 / avoidOverlap 0.5；监听 `stabilizationIterationsDone`+`stabilized` 后 `physics:{enabled:false}` 彻底冻结，并 fit 到最大连通分量；"继续布局"按钮会重新下发 physics 配置再 startSimulation；只有度 ≥ `--label-degree`(12) 的枢纽常显标签（pyvis 会用构造函数的 font_color 覆盖 add_node 的 font，需事后改 `net.node_map[id]["font"]`）。
- 抽取层（`extract.py`）：按文本长度自适应 K（`min(top_k, max(3, len//50))`）+ TF-IDF ∩ TextRank 混合（交集优先，不足用 TF-IDF 补），开关 `--fixed-k` / `--no-textrank`；缓存指纹包含这两项策略。
- 建图层（`graph.py`）：边额外记录原始共现篇数；新增 PMI 显著性剪枝（`--min-pmi`，默认 0）、每节点局部骨架 `--keep-per-node`（默认 5）。
- 实测：6485 篇 → 899 节点 / 1775 边 / 49 簇 / 平均度 3.95（原为 1200 节点 / 9897 边 / 15 簇），无头 Chrome 截图确认簇团分明、物理已冻结（spread≈3000，标签可读）。
- 状态：已完成并提交。

## 2026-11-09 聚焦模式主循环批判性审查（只读）
- 对照 `docs/focus-mode-paradigm.md` 审查 `core/engine/engine_reply.py::chat_with_tools`、`core/phone_focus.py`、`core/toolchain.py`、`core/tool_prune.py`。
- 结论：手机域硬编码散布 5 个模块；发现同批 phone_action+phone_finish 历史泄漏、隐藏工具可被执行、聚焦中 pruner 误折叠、finish 后轮次上限不回落、重启丢状态等问题。
- 提出 `core/focus/` 通用域 + 轮次 Hook 管线 + ToolView 的分阶段重构规划（P0~P5），待机主确认取舍后开工。未改代码。
- 机主决策：P4 只修 B1（同批 finish 泄漏）+ B5（重启清孤儿记录）；聚焦状态不落盘；先写设计文档。目的：为「艺术创作聚焦模式 art」铺路，让新增模式按范式声明式接入、可自迭代。
- 产出 `docs/focus-mode-architecture.md`（FocusDomain/FocusManager/ToolView/TurnState+Hooks/写入闸门/孤儿清扫/art 示例/契约测试/P0~P6 路线）。状态：设计稿，未实施。
