# 开发日志

## 2026-10-15 图片占位符泄漏修复（表情包识别为空）

### 现象
群里发图片/表情包时，模型收到的是 `【"池宇健"】说: [图片占位符] | 再试一次yuki`，
即占位符没有换成识别结果，模型完全看不到图。

### 根因（两层）
1. 视觉请求发给 `deepseek-flash`（推理模型），`max_tokens=50` 被 `reasoning_content`
   全部吃掉，`content` 返回空串、`finish_reason=length`。
   证据：日志 `processor.py:249 识别结果: `（空）且 API 于 20:43:13.190 已返回，
   管线 20:43:15.778 才消费 —— 不是「没来得及返回」的竞态。
   直连 API 复现：`reasoning_effort:"none"` / `thinking:{type:disabled}` / `max_tokens=800`
   三种方式都能正常出描述。
2. `core/session_pipeline.py` 用 `elif is_meme and desc:` 判断，空串为假 → 该图不产生
   任何替换文本 → 占位符原样进 LLM 上下文与历史；空结果还被写进 `data/meme_cache.json`
   （url 键 + 哈希键各一条），同一张图会永久识别为空。

### 改动
- `modules/vision/processor.py`
  - 新增 `_clean_description()` / `_valid_description()`：非字符串、空白一律视为空；
    缓存命中必须是非空字符串。
  - 新增 `MemeProcessor._no_thinking_kwargs()`：仅当 `disable_thinking` 开启且视觉端点是
    DeepSeek 时下发 `reasoning_effort="none"`（避免其它视觉端点因未知参数 400），
    视觉请求与降级 HTTP 分支都带上。
  - `understand_from_url` / `understand_bytes`：空描述按「未知图片/表情」返回且**不写缓存**；
    读取缓存时忽略空值脏数据。
  - 降级 HTTP 分支取 `message.get("content") or ""`，不再对空 content 抛 KeyError/None。
- `core/session_pipeline.py`
  - 每张图必定消费一个占位符：识别为空时填 `[表情:未知图片/表情]` / `[图片:未知图片/表情]`。
  - 替换循环之后加全局兜底清扫：任何残留 `[图片占位符]` 降级为 `[图片]`（覆盖「CQ 码被
    截断、没解析出图片」等路径），确保占位符永远不进模型上下文。
- `data/meme_cache.json`：清理 2 条空描述脏数据（stats 同步清理）。

### 验证
- 新增 `tests/test_vision_placeholder.py`（7 例）：空描述仍消费占位符、无图片时清扫残留、
  日志文本不含占位符、空结果不入缓存、脏缓存不命中、辅助函数、关思考参数只对 DeepSeek 下发。
- 新增 `tests/run_tests.py`：无 pytest 环境下的最小 runner（本机 pytest 缺失）。
- 实测真实 API（本地 HTTP 服务提供测试图，跑真实 `understand_from_url`）：
  第一次返回 `图片文字是OK，表达同意、没问题。`，第二次命中缓存；实测条目已回收。
- 回归：`test_vision_prefetch.py`、`test_native_vision.py`、`test_vision_placeholder.py` 全绿。

### 环境备注（未处理，需机主决定）
- `maid_venv` 是从别的机器拷贝来的，`pyvenv.cfg` 指向 `/home/tianbot/miniconda3/...`，
  本机跑不起来；本机可用解释器为 `/home/asumi/miniconda3/envs/yuki/bin/python`（无 pytest）。
- 主链路同源风险：`session_pipeline.py:534` 拦截「Yuki回复了空字符」的那条路径同样可能被
  推理 token 吃光 max_tokens 导致空回复，本次未动（超出本次修复范围）。

## 2026-10-21 小女仆依赖自动安装报错（maid_venv 失效）修复

### 现象
`maid_runtime.py:156 [Maid] 自动安装依赖异常: [Errno 2] No such file or directory: 'maid_venv/bin/pip'`，
随后模型改用 conda python 绕过；日志中 `maid_venv/bin/python` 报 `No module named 'encodings'`。

### 根因
1. `maid_venv` 是从别的机器（`/home/tianbot/miniconda3/envs/yuki`、`--copies`）拷来的，
   `pyvenv.cfg` 的 `home` 在本机不存在 → 解释器无法定位标准库，`import encodings` 致命失败。
2. `_is_maid_env_usable()` 只用 `python --version` 判活，该命令不需要标准库也能返回 0，
   于是坏环境被判为「可用」，重建逻辑从未触发。
3. `bin/pip` 的 shebang 是 `#!/home/asumi/projects/YukiV6/maid_venv/bin/python`（不存在），
   直接执行该脚本必然 `[Errno 2]`。

### 修复（core/maid/maid_runtime.py）
- `_is_maid_env_usable()`：改为执行 `-c "import encodings, sys"` 真初始化，并校验
  `pyvenv.cfg` 的 `home` 目录存在（`_check_venv_home`）。
- pip 一律走 `_run_pip()` → `python -m pip`（`_get_maid_pip_cmd`），绕开失效的 bin/pip 脚本；
  `_ensure_skill_deps()` / `install_package()` 全部改用该入口。
- 新增 `_upgrade_maid_env()`：版本一致时用 `venv.EnvBuilder(upgrade=True)` 原地重建
  bin/ 与 pyvenv.cfg（保留 site-packages），失败再走 `_rebuild_maid_env()` 全量重建。
- 新增 `_repair_maid_pip()`：环境可跑但缺 pip 时先 `ensurepip` 补，仍失败才重建。

### 处置与验证
- 已对真实 `maid_venv` 执行原地修复（备份：`/tmp/maid_bin.bak`、`/tmp/maid_pyvenv.cfg.bak`）。
- `maid_venv/bin/python` → 3.11.15，`python -m pip --version` → pip 24.0，197 个旧依赖保留。
- 端到端：`_ensure_skill_deps` 对 `import paramiko` 的脚本自动装了 paramiko 5.1.0，脚本执行返回 0。
- 需重启 `main.py` 让新代码生效。

## 2026-10-21 仓库接回 GitHub（本地补齐 .git）

- 本地目录原本没有 `.git`，代码与 `origin/main` 内容差异仅 7 个代码文件；
  其余 220+ 差异是权限位 644→755（已设 `core.fileMode=false`）。
- 已 `git init -b main`、`git remote add origin`、`git reset --mixed origin/main`，
  并补回本地缺失的 18 个上游文件（`.gitignore`/`.python-version`/`.github`/`.trae`/docs/demo）。
- 本地改动分为 4 个提交：vision 预取与占位符、maid 环境自愈、path/生图尺寸、docs。
- 测试基线：`origin/main` 与本地各有 23 项环境性失败（缺依赖、真实 LLM 调用、终端宽度），
  无新增回归。
- 推送待机主提供凭据：`git push -u origin HEAD:fix/maid-env-vision-prefetch`。

## 2026-10-22 小女仆能力升级（记忆/预算/授权/看图）

按机主反馈重排范围，砍掉 safe_edit_file、notes、技能固化与成功率统计，只补运行体感缺口。

- S1 `read_file_content`：64KB / 单行 2000 字符 / `offset` 续读，base64 不再吃满上下文。
- S2 有效轮提到 40，网络与解析失败独立计错（≤5，不占轮），新增 900s 墙钟。
- S3 新增 `maid_memory`：每轮写 `tasks/state/<task_id>.json`，开始时注入最近 3 条摘要，
  新增 `resume_task`（仅允许恢复一次，避免重置轮次死循环），结束写 `logs/task_index.jsonl`。
- S4 新增 `maid_approval`：硬拦截只留 sudo/关机/mkfs/dd/删根目录/fork 炸弹，其余可疑命令
  交给继承当前 session 上下文的 Yuki 静默判定；`MAID_ESCALATE_TO_MASTER=1` 可升级问机主。
- S5 新增 `read_image`：原生 image_url 图块直塞 maid 模型，图块只存活一轮后降级为文本。
- S6 temp_skill 支持 timeout/interpreter，注入 PYTHONPATH，缓存 pip list 与环境自检
  （重复执行 1.4s → 0.01s）。
- S7 提示词只加必要条目，报告末尾追加轮次/耗时/trace。

验证：`tests/run_tests.py` → `passed=114 failed=23`，失败集合与基线完全一致；
新增 `tests/test_maid_features.py` 14 例全过。需重启 `main.py` 生效。

## 2026-10-22 自进化（小女仆改自身代码 + 容器热重载 + 降级回滚）落地

### 目标
让 Yuki 能修改自身代码并生效，同时保证「改坏了也能自己退回去」：
容器化热重载 + 错误降级反馈 + 可追溯 + 不爆存储 + `yuki_memory` 重点保护 + 人格不可改。

### 为什么不做进程内热重载
`importlib.reload` 只会替换模块对象，已持有引用的 `cfg` 单例、`FunctionRegistry`、
全局 aiohttp session、ChromaDB client、NapCat WS 连接、运行中的 maid 协程全部保留旧版，
结果是「代码是新的、行为是旧的」。且 `config.py` 明确写着「启动时一次性加载，无热重载」。
因此采用**整进程替换**（容器重建）作为唯一生效方式。

另一个硬约束：`data/yuki.lock` 单实例锁 + `yuki_memory` 是文件锁型 ChromaDB，
无法蓝绿并行，只能「离线校验 → 短窗口切换」。

### 交付物
- `deploy/Dockerfile`：只装依赖（约 2.27GB），代码不进镜像 → 改代码只需重启容器，不必重建镜像
- `deploy/run.sh`：代码树 `:ro` 挂载、数据目录 rw 卷、`--network host`、宿主 uid 运行、容器内外**同绝对路径**
- `deploy/verify.sh`：5 道门（compileall / import / tests / dry_run / health），临时容器断网 + tmpfs
- `deploy/test_gate.py` + `test_baseline.json`：测试门用基线差集（既有 33 项环境性失败不阻塞）
- `deploy/reviewer.py`：宿主侧独立模型审查（deepseek-flash，温度 0.2，JSON 输出）
- `deploy/supervisor.py`：宿主守护，串联分级校验→审查→快照→应用→commit→校验→重启→回滚
- `deploy/retention.py`：trace 7 天→按周 tar.gz（上限 200MB）、日志截断、staging 3 天、快照 7 份
- `deploy/yuki-supervisor.service` + `install-service.sh`：常驻 + 每日 cron
- `utils/health_server.py` + `main.py` 接入：`/health` 探针、`YUKI_DRY_RUN` 试启动
- `docs/evolution-charter.md` + `core/maid/maid_charter.py`：准则与路径分级（单一来源）
- `core/maid/maid_selfevolve.py`：`propose_patch` / `verify_patch` / `request_self_reload` /
  `read_evolution_result` / `request_restart`
- `core/maid/maid_worklog.py`：`list_previous_work` / `read_work_trace`（跨任务交接）

### 安全模型
三层隔离：代码只读挂载（agent 改不到运行中的代码）→ 唯一可写代码位置是 `staging/`
→ 只有宿主 supervisor 能改代码/重启。禁区由路径分级强制：`deploy/`、`.git/`、`configs/`、
`data/`、`yuki_memory/`、`memory/`、`logs/`、`models/`、`maid_venv/`、
**`core/prompts.py`（人格，无例外）**、准则文件本身。

### 有效性与反馈的分层
| 结果 | 是否重启 | 模型能否就地继续 |
|---|---|---|
| review_rejected / verify_failed / apply_failed | 否 | 是（同步拿到意见） |
| ok / restarted | 是 | 否（重启后 resume_task） |

### 踩过的坑
1. 容器路径 `/app` 与宿主不一致 → `file:///` 表情包/文件/语音全部静默发不出去。改为同路径挂载。
   `send()` 不等响应，所以日志只显示「发送完成」，极难发现。
2. 只读挂载下 `compileall` 写 `.pyc` 失败 → 用 `PYTHONPYCACHEPREFIX` 指向 tmpfs。
3. 容器以 root 写 staging → 宿主无法回写 `result.json` → 改以宿主 uid 运行。
4. `git add -A` 把 staging 与运行时状态卷进自改提交，回滚时连 request 目录一起删。
   改为只 add 补丁路径；`staging/`、`deploy/state.json` 入 `.gitignore`。
5. 回滚目标是「本次改动前的 HEAD」而不是 `last_good`（后者可能未初始化）。
6. 改 `deploy/` 后必须 `sudo systemctl restart yuki-supervisor`，否则守护进程跑旧逻辑。
7. 测试 fixture 直接放进 `staging/` 且带 `request.json`，运行中的旧 supervisor 立刻消费，
   把 `while True: pass` 提交进 `core/tools/tools_common.py`（commit 89d39cd）。已回滚。
   教训：放 fixture 前先停守护进程；此事也印证了审查层的必要性。

### 验证结果
- 成功路径 46s：审查 2.6s → 应用 → commit → 5 门 → 重启 → health → tag `good-20261022_182221`
- 坏补丁路径：`verify_failed`，回滚到基线，回传 `SyntaxError` 精确行号
- 审查驳回路径：同步返回具体问题与改法，进程保持存活
- 重启工具：容器 ID 变更、`result=restarted`、快照生成
- 表情包：`send_private_msg` 返回 `retcode: 0`
- 5 道门稳定通过（测试门新增失败 0）

### 待办
- P1：连续失败进入安全模式（`YUKI_SAFE_MODE=1` 只读启动并通知机主）
- P1：切换后观察窗口（如 5 分钟内 error 率超阈值自动回滚）
- P2：审查抽检（人工复核被放行的 patch）、影子只读回放
