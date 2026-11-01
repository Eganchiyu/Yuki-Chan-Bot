# _archive 索引

2026-11-01 从 Yuki 主程序中**剥离并卸载**的两个功能，源码与复原说明都在这里。

| 归档内容 | 原始路径 | 归档路径 | 说明 |
|---|---|---|---|
| Live2D 桌宠 | `modules/LiveYukiL2D/` | `_archive/LiveYukiL2D/` | 完整源码（前端 + 后端 + 模型 + 自带文档），**不含** `frontend/minimal/node_modules`、`reference/` |
| 浏览器交互聚焦模式 | `modules/browser_interaction/` | `_archive/modules/browser_interaction/` | 占位工具模块，随 Live2D 一起下线 |
| 浏览器模式入口工具 | `core/tools/_archived/tools_browser.py` | `_archive/core/tools/tools_browser.py` | 原本已从主模型卸载，这次一并移出仓库 |
| 浏览器模式设计稿 | `docs/browser-interaction-mode-plan.md` | `_archive/docs/browser-interaction-mode-plan.md` | 原实现方案 |
| 改动前的测试快照 | `tests/test_modes.py` | `_archive/docs/../tests/test_modes.py.original` | 含被删掉的 5 个 browser 测试 |
| 全部代码改动 diff | — | `_archive/docs/removal.diff` | 逐文件 unified diff，复原时反向应用即可 |

**文档入口**

- [`docs/live2d-archive.md`](docs/live2d-archive.md) — Live2D 部署点位、剥离清单、复原步骤、代码用法
- [`docs/browser-interaction-archive.md`](docs/browser-interaction-archive.md) — 浏览器交互模式的同样三件事
- [`docs/removal.diff`](docs/removal.diff) — 本次剥离的完整 diff

**未归档（按约定丢弃，可再生）**

- `modules/LiveYukiL2D/frontend/minimal/node_modules/`（307M，`npm install` 可再生）
- `modules/LiveYukiL2D/reference/Open-LLM-VTuber/`（962M，第三方上游参考仓库，含 Windows `.venv`）
- 所有 `__pycache__/`

---

## 2026-11-01 追加：NCM（网易云）工具与技能归档

Yuki 主程序的 `ncm_search` / `ncm_download` 已从 `TOOL_SPECS` 摘除（提交 `66c46cc`），
为小女仆试写的 ncm 技能因扫码登录未跑通，一并在这里封存。

| 归档内容 | 原始路径 | 归档路径 | 说明 |
|---|---|---|---|
| 工具实现 | `core/tools/tools_ncm.py` | `core/tools/_archived/tools_ncm.py` | 只摘注册、文件留在 `_archived`，可直接 import 复用 |
| 女仆技能（文档） | `skills/ncm.md` | `_archive/skills/ncm.md` | 首行简介 + 参数/扫码流程/调用方式说明 |
| 女仆技能（代码） | `skills/ncm.py` | `_archive/skills/ncm.py` | `ncm_search` / `ncm_download` 同步封装 + CLI |
| 扫码登录辅助脚本 | `staging/ncm_login_*.py` | `_archive/scripts/ncm_login/` | 一次性调试脚本，见下 |

**扫码登录辅助脚本说明**

- `ncm_login_wait.py` — 生成二维码 + 170s 容错轮询，成功即写 cookie（最简单的一版）
- `ncm_login_ascii.py` — 同上，额外把二维码打成 ASCII，方便在无 GUI 终端扫码
- `ncm_login_daemon.py` — 自刷新守护：二维码过期自动重生成同一个 PNG，最长 20 轮，状态写 `output/ncm/login_status.txt`

三个脚本都要在容器内跑：`docker exec -w /home/asumi/Yuki -e PYTHONPATH=/home/asumi/Yuki yuki python <脚本>`

**没能跑通的原因（2026-11-01 实测）**

1. 容器内原本缺 `qrcode`，扫码登录必然失败 → 已 `pip install --user qrcode`（落在 `data/home/.local`，重启不丢），并在 `pyproject.toml` 声明 `qrcode==8.2`。
2. 二维码有效期约 3 分钟，而对话往返经常超过这个窗口：机主扫码时轮询进程已超时退出，`code 803 授权登陆成功` 无人接收，unikey 随后被消费成 `code 800`。
3. 已扫码证据：事后手工单查 unikey 得到 `code 803`；第二次再查变成 `800 过期`，说明「登录被消费但 Cookie 没落盘」。
4. 结论：要跑通需要**同一份进程既生成又接收**（`ncm_login_daemon.py` 已按此实现），并在二维码刷新后立刻扫。

**恢复路径**：把 `_archive/skills/ncm.*` 复制回 `skills/`，女仆即可 `list_skills` 看到；主程序侧把 `_archived/tools_ncm.py` 的两个 `ToolSpec` 加回 `core/tools/tools.py` 即恢复 Yuki 的 ncm 工具。

**当前 Cookie 状态**：未拿到，`data/home/.cache/ncm_cookie.txt` 不存在。
