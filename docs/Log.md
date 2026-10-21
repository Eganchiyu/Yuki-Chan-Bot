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
