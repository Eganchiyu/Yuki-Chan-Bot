# Live2D 桌宠：部署点位、剥离清单与复原手册

归档日期：2026-11-01
归档源码：`_archive/LiveYukiL2D/`（原 `modules/LiveYukiL2D/`）
完整改动 diff：`_archive/docs/removal.diff`

---

## 一、当初部署在哪些点位

Live2D 桌宠不是独立后台进程，而是**寄生在主程序的三种事件路径上**，共 6 处硬耦合 + 若干配置/文档点位。

### 1. 启动点位（主程序入口）

| 文件 | 位置 | 作用 |
|---|---|---|
| `main.py` | `start_desktop_pet_if_enabled(pipeline, pipeline_loop)`（原 141-179 行） | 开关判定 + 起 aiohttp 服务 + 拉起 Electron 窗口；开关优先级 `YUKI_DESKTOP_PET`(1/0) > `modules/LiveYukiL2D/config.json` 的 `desktopPet.enabled` |
| `main.py` | `run_runtime()` 内 `await asyncio.to_thread(start_desktop_pet_if_enabled, session_pipeline, asyncio.get_running_loop())` | 在线程里启动，避免阻塞消息管线事件循环；位置在 `napcat_listen` 之前 |

### 2. 输出点位（Yuki 说话 → 桌宠气泡）

| 文件 | 位置 | 作用 |
|---|---|---|
| `core/session_pipeline.py` | `send_answer()` 内 `if mode in {"desktop_pet", "browser_interaction"}: from modules.LiveYukiL2D.server import broadcast ...` | 桌宠/浏览器模式不走 QQ API，改为 WS 广播 `state=speaking` → `say` → `state=idle`，然后 `return` |
| `core/engine/engine_reply.py` | `EngineReplyService.send_tool_thought()` 内同类分支 | 工具链阶段性文本以 `broadcast({"type":"say"})` 直发桌宠，不发 QQ |

### 3. 输入点位（桌宠说话 → 主管线）

| 文件 | 位置 | 作用 |
|---|---|---|
| `modules/LiveYukiL2D/server.py` | WebSocket `chat` 消息处理（约 230-250 行） | 把桌宠输入包装成 `enqueue_message("desktop_pet", "desktop_pet", message_obj=...)` 注入主会话管线（`force_reply=True`） |

### 4. 行为分支点位

| 文件 | 位置 | 作用 |
|---|---|---|
| `core/session_pipeline.py` | `decide_reply_action()`：`if context["mode"] in {"private","master_private","desktop_pet","browser_interaction"}` | 桌宠模式跳过群聊潜水判定，永远回复 |
| `utils/logger.py` | `NOISY_NAMESPACES`/日志命名空间列表里的 `"desktop_pet"` | 统一日志分类 |

### 5. 部署与文档点位

| 文件 | 位置 |
|---|---|
| `deploy/run.sh` | 容器启动参数 `-e YUKI_DESKTOP_PET=0`（容器无 GUI，强制关闭） |
| `deploy/README.md` | 「容器内跑不了 Live2D 桌宠」说明行 |
| `.gitignore` | `modules/LiveYukiL2D/frontend/minimal/node_modules/`、`frontend/vendor/`、`reference/Open-LLM-VTuber/` |
| `.dockerignore` | `modules/LiveYukiL2D/reference/`、`modules/LiveYukiL2D/frontend/` |
| `README.md` | 功能列表、目录树、依赖表、快速开始「4. Live2D 桌宠」整节 |

### 6. 模块内部结构（归档内容）

```
modules/LiveYukiL2D/
├── desktop.py              # 桌面启动器：自检 Electron 二进制 → ensure_server() → launch_window()
├── server.py               # aiohttp 后端：静态托管 dist/models + WS /ws + REST /api/*
├── config.json             # desktopPet 窗口参数（透明/置顶/穿透/跟随鼠标）+ model.kScale
├── liveyuki_l2d/
│   ├── cursor.py           # 跨平台光标坐标（Win: GetCursorPos / X11: XQueryPointer / Hyprland: IPC）
│   ├── events.py           # 错误事件构造
│   └── protocol.py         # set-model-and-conf 消息构造
├── models/Yuki/            # Yuki 模型（moc3/model3/physics3/cdi3/纹理 1024）
├── frontend/minimal/       # Vite + TS 前端 + Electron 壳（electron-main.cjs / electron-preload.cjs）
└── docs/                   # 模块自带 architecture/development-plan/root-files 文档
```

后端监听 `127.0.0.1:18765`；前端构建产物在 `frontend/minimal/dist/`（已归档，可直接跑）。

---

## 二、这次剥离做了什么

1. **删除目录**：`modules/LiveYukiL2D/`（源码已完整归档）、`modules/browser_interaction/`（见另一篇）。
2. **`main.py`**：删掉 `start_desktop_pet_if_enabled()` 整个函数和 `run_runtime()` 里的调用。
3. **`core/session_pipeline.py`**：`send_answer()` 里删除 `desktop_pet`/`browser_interaction` 广播分支（现在这两个 mode 会走正常 QQ 发送路径）；`decide_reply_action()` 的强制回复集合移除 `desktop_pet`、`browser_interaction`。
4. **`core/engine/engine_reply.py`**：`send_tool_thought()` 删除 broadcast 分支，统一走 `self.sender.send()`；删除 `browser_interaction` 的 `record_step` 分支。
5. **`core/modes.py`**：删除 `BrowserInteractionMode` 与 `_specs` 中对应条目（`ModeManager`/`ModeSpec`/`FocusModeState` 通用框架保留）。
6. **`core/brain.py` / `core/prompts.py`**：删除 `get_yuki_setting_browser_interaction()` 及其引用；群聊提示词里「浏览器交互等聚焦模式」一句改为中性描述。
7. **`core/tools/_archived/tools_browser.py`**：移入归档，`__init__.py` 删除其 import/导出。
8. **`core/engine/engine.py`**：删掉两行注释掉的 `BROWSER_TOOL_SPECS` 引用。
9. **`utils/logger.py`**：删除 `"desktop_pet"` 命名空间。
10. **`deploy/run.sh` / `deploy/README.md`**：删除 `YUKI_DESKTOP_PET=0` 与相关说明。
11. **`.gitignore` / `.dockerignore`**：删除 LiveYukiL2D 相关忽略规则（目录已不存在）。
12. **`README.md`**：删掉功能列表两条、目录树两行、依赖表一行、快速开始整节；后续小节编号顺延（表情包 → 4，自进化底座 → 5）。
13. **`tests/test_modes.py`**：删除 5 个 browser 相关测试，改为断言「已无聚焦模式可注册」+ 保留 RAG 打分测试。原文件快照见 `_archive/tests/test_modes.py.original`。

**没动的东西**：`desktop_pet` / `browser_interaction` 这两个 mode 字符串在 NapCat/历史数据里没有外部写入方，只由桌宠自身注入，因此没有历史数据清洗需求。`FocusModeState`、`ModeManager`、`ToolRegistryProvider.mode_specs` 等通用设施保留，将来加新聚焦模式可直接复用。

---

## 三、怎么加回去

### 方案 A：按 diff 反向复原（最快，适合原样恢复）

```bash
cd /home/asumi/Yuki

# 1) 目录回归
rsync -a _archive/LiveYukiL2D/ modules/LiveYukiL2D/
rsync -a _archive/modules/browser_interaction/ modules/browser_interaction/
cp _archive/core/tools/tools_browser.py core/tools/_archived/tools_browser.py
cp _archive/tests/test_modes.py.original tests/test_modes.py
cp _archive/docs/browser-interaction-mode-plan.md docs/

# 2) 代码改动反向应用（README/.gitignore 等一起回滚）
git apply -R _archive/docs/removal.diff
# 若 git 状态不干净或用不上 git，可手工按 diff 逐段粘贴

# 3) 前端依赖（node_modules 未归档，需要重装）
cd modules/LiveYukiL2D/frontend/minimal
npm install
npm run build
```

注意 `_archive/core/tools/_archived/__init__.py` 不在 diff 里（它属于运行时小改），恢复时手工把 `enter_browser_interaction_tool` 的 import 和 `__all__` 条目加回去。

### 方案 B：手工重挂（只想要桌宠，不要浏览器模式）

只要桌宠的话，最小改动是 3 处：

1. **`main.py`** — 在 `run_runtime()` 里、`napcat_listen` 之前插回：

```python
    async def run_runtime() -> None:
        try:
            _install_restart_notifier()
            await asyncio.to_thread(
                start_desktop_pet_if_enabled, session_pipeline, asyncio.get_running_loop()
            )
            await napcat_listen(session_pipeline.sender, session_pipeline, "mixed")
        finally:
            ...
```

并把 `start_desktop_pet_if_enabled()` 函数体从 `_archive/docs/removal.diff` 直接复制回来（完整函数就在 diff 的第一段）。

2. **`core/session_pipeline.py`** — 在 `send_answer()` 计算完 `answer_text` / `voice` 之后加回：

```python
        if mode == "desktop_pet":
            try:
                from modules.LiveYukiL2D.server import broadcast
                await broadcast({"type": "state", "state": "speaking"})
                await broadcast({"type": "say", "text": answer_text})
                await broadcast({"type": "state", "state": "idle"})
            except Exception as exc:
                logger.error(f"[DesktopPet] 发送到 Live2D 失败: {exc}")
            return context
```

同时把 `decide_reply_action()` 的集合改回 `{"private", "master_private", "desktop_pet"}`，并把 `"desktop_pet"` 加回 `utils/logger.py` 的命名空间列表（可选，只影响日志分类）。

3. **`core/engine/engine_reply.py`**（可选，只影响工具链阶段性文本是否弹气泡）：

```python
        if display_content:
            if mode == "desktop_pet":
                from modules.LiveYukiL2D.server import broadcast
                await broadcast({"type": "say", "text": display_content})
            else:
                send_mode = "private" if mode == "master_private" else mode
                await self.sender.send(chat_id, display_content, mode=send_mode)
```

`server.py` 里的输入注入（`enqueue_message("desktop_pet", "desktop_pet", ...)`）在模块内部，随目录回归自动恢复，无需改主程序。

### 加回去之后的验收

```bash
YUKI_DESKTOP_PET=1 python main.py
# 期望日志：[DesktopPet] 启动 Electron: ... / [DesktopPet] Live2D 桌宠已启动 (pid=...)
# 期望现象：透明窗口出现、模型待机呼吸、鼠标跟随；在桌宠里输入文字 → 主程序有回复气泡
LIVEYUKI_DEBUG=1 python main.py   # 窗口几何 / 光标来源 / 穿透判定打到 stdout
```

---

## 四、这份代码怎么用

### 独立运行（不接主程序，只看模型和窗口）

```bash
cd modules/LiveYukiL2D
python server.py          # 只起后端：http://127.0.0.1:18765 ，浏览器可直接看模型
python desktop.py         # 后端 + Electron 桌面窗口（不接 session_pipeline，聊天会提示"需要从主程序启动"）
```

`desktop.py` 单独跑时 `session_pipeline=None`，WS 的 `chat` 消息会返回 `桌宠聊天需要从 YukiV6 主程序启动`，其余（模型加载、表情动作、鼠标跟随、拖拽）都正常。

### 开关

| 开关 | 位置 | 语义 |
|---|---|---|
| `YUKI_DESKTOP_PET` | 环境变量 | `1/true/yes/on` 强制开；`0/false/no/off` 强制关；不设则看 config.json |
| `desktopPet.enabled` | `modules/LiveYukiL2D/config.json` | 缺省视为 `true`（注意：归档时代码里 `DEFAULT_CONFIG` 是 true，仓库内置 config.json 写的是 false） |
| `desktopPet.width/height/x/y` | 同上 | 窗口尺寸与位置 |
| `desktopPet.transparent/frameless/alwaysOnTop/resizable` | 同上 | 窗口属性 |
| `desktopPet.mousePassthrough` | 同上 | 鼠标穿透（Linux 由主进程推光标做命中判定） |
| `desktopPet.lookAtMouse` | 同上 | 头部跟随鼠标 |
| `model.kScale` / `model.scrollToResize` | 同上 | 模型缩放 / 滚轮缩放 |
| `YUKI_L2D_OZONE_PLATFORM` | 环境变量 | `x11`（默认）/`wayland`/`auto`，决定 Electron 后端 |
| `LIVEYUKI_DEBUG` | 环境变量 | 打印窗口几何、光标来源、穿透判定 |

### 前后端接口（改造/联动时用）

- `GET /ws` — WebSocket，服务端下行消息：
  - `{"type":"state","state":"speaking"|"idle"}`
  - `{"type":"say","text":"..."}`
  - `{"type":"audio","audio":<base64>,"volumes":[...],"actions":[...]}`（口型同步）
  - `{"type":"set-model-and-conf","model_info":{...}}`
  - 客户端上行：`{"type":"chat","text":"..."}` / `cancel` / `clear-history`
- REST：`GET /api/config`、`/api/model`、`/api/say?text=`、`/api/cursor`、`POST /api/audio`
- 静态：`/models/{path}`（模型资源）、`/{path}`（前端 dist）

### 代码里怎么"让桌宠说话"

```python
from modules.LiveYukiL2D.server import broadcast

await broadcast({"type": "state", "state": "speaking"})
await broadcast({"type": "say", "text": "主人下午好"})
await broadcast({"type": "state", "state": "idle"})
```

`broadcast()` 跨线程安全：若当前不在服务端事件循环，会用 `run_coroutine_threadsafe` 转发到 `SERVER_LOOP`。

### 前端开发

```bash
cd modules/LiveYukiL2D/frontend/minimal
npm run dev        # Vite 热更新，http://127.0.0.1:5173
npm run build      # 产物到 dist/，后端直接托管
npm run desktop    # 直接用 electron CLI 起窗口（等价 desktop.py 的窗口部分）
```

前端入口 `src/main.ts`（WS 连接、消息分发、鼠标跟随、编辑模式），`src/WebSDK/` 是 Live2D Cubism SDK（Core + Framework，黑箱）。编辑模式快捷键 `Ctrl+Alt+Y`。

### 已知坑（归档前就存在的）

- **Electron 二进制必须与平台匹配**：`node_modules/electron/dist/` 里若是 Windows 的 `electron.exe`，Linux 上会被 wine 接管，窗口行为异常。`desktop.py` 会做 ELF/PE 魔数自检并报错，修复方式是 `rm -rf node_modules/electron && npm install`。
- **Linux 默认 XWayland**：桌宠依赖全局光标坐标、绝对窗口定位、窗口拖动，原生 Wayland 客户端拿不到；Hyprland 下光标走 compositor IPC。
- **容器里跑不了**：Electron 需要 GUI，Docker 部署必须保持关闭（原 `deploy/run.sh` 的 `YUKI_DESKTOP_PET=0` 就是为此）。
- **归档里没有 `node_modules`**：`frontend/minimal/dist` 已归档可直接用，但重装依赖后要重新 `npm run build`。
