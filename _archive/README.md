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
