# LiveYukiL2D 架构索引

本文档用于快速定位项目中的核心逻辑文件、黑箱模块以及它们之间的调用关系。

## 项目概述

LiveYukiL2D 是一个桌面 Live2D 宠物应用，由 Python 后端（aiohttp + WebSocket）和 TypeScript 前端（Vite + Live2D Cubism SDK）组成。

- 启动方式：`python main.py`
- 后端端口：`127.0.0.1:18765`
- 前端入口：`frontend/minimal/src/main.ts`

---

## 核心逻辑文件（重要）

以下文件是项目的主要逻辑，修改时需要注意上下游影响。

### 1. 后端

| 文件 | 职责 | 调用关系 |
|------|------|----------|
| [main.py](d:/Projects/LiveYukiL2D/main.py) | 启动入口，判断是否启动 Electron 桌面模式 | → `server.py` / `desktop_electron.py` |
| [server.py](d:/Projects/LiveYukiL2D/server.py) | aiohttp 后端主服务：托管前端静态文件、Live2D 模型资源、WebSocket 通信、REST API | ← `main.py`；→ 前端通过 WS/HTTP 调用 |
| [desktop_electron.py](d:/Projects/LiveYukiL2D/desktop_electron.py) | 桌面模式启动器：确保后端运行，然后启动 Electron | ← `main.py`；→ `server.py` + `npm run desktop` |
| [config.json](d:/Projects/LiveYukiL2D/config.json) | 桌面宠物窗口配置（透明、置顶、鼠标穿透等）和模型参数 | ← `server.py`（`load_config()`） |
| [liveyuki_l2d/protocol.py](d:/Projects/LiveYukiL2D/liveyuki_l2d/protocol.py) | WebSocket 消息协议构造工具（set-model、say、audio 等消息格式） | ← 外部调用方（如 Open-LLM-VTuber 集成时） |

### 2. 前端

| 文件 | 职责 | 调用关系 |
|------|------|----------|
| [frontend/minimal/src/main.ts](d:/Projects/LiveYukiL2D/frontend/minimal/src/main.ts) | **前端主入口**：WebSocket 连接、消息分发（set-model/say/audio）、模型加载、鼠标跟随、编辑模式 | ← 浏览器加载；→ `lappdefine`、`LAppLive2DManager`、`LAppDelegate` |
| [frontend/minimal/src/WebSDK/src/lappdefine.ts](d:/Projects/LiveYukiL2D/frontend/minimal/src/WebSDK/src/lappdefine.ts) | 全局配置常量（Canvas 尺寸、模型路径、缩放、优先级等）和 `updateModelConfig()` | ← 所有 WebSDK 模块 |
| [frontend/minimal/src/WebSDK/src/lappdelegate.ts](d:/Projects/LiveYukiL2D/frontend/minimal/src/WebSDK/src/lappdelegate.ts) | 应用单例，管理 Cubism Framework 初始化、渲染循环、模型切换 | ← `main.ts`；→ `lappview`、`lappglmanager`、`lapppal` |
| [frontend/minimal/src/WebSDK/src/lappglmanager.ts](d:/Projects/LiveYukiL2D/frontend/minimal/src/WebSDK/src/lappglmanager.ts) | WebGL 上下文管理（获取 canvas、创建 GL 上下文） | ← `lappdelegate`、`lappview` |
| [frontend/minimal/src/WebSDK/src/lapplive2dmanager.ts](d:/Projects/LiveYukiL2D/frontend/minimal/src/WebSDK/src/lapplive2dmanager.ts) | Live2D 模型生命周期管理（创建、销毁、切换模型） | ← `lappdelegate`、`main.ts` |
| [frontend/minimal/src/WebSDK/src/lappmodel.ts](d:/Projects/LiveYukiL2D/frontend/minimal/src/WebSDK/src/lappmodel.ts) | 单个 Live2D 模型实例：加载 MOC3、纹理、物理、表情、动作 | ← `lapplive2dmanager`；→ Framework 模型层 |

### 3. 模型资源

| 文件/目录 | 职责 |
|-----------|------|
| [models/Yuki/Yuki.model3.json](d:/Projects/LiveYukiL2D/models/Yuki/Yuki.model3.json) | 模型主配置文件（引用 MOC3、纹理、动作组） |
| [models/Yuki/Yuki.moc3](d:/Projects/LiveYukiL2D/models/Yuki/Yuki.moc3) | 模型二进制数据 |
| [models/Yuki/Yuki.physics3.json](d:/Projects/LiveYukiL2D/models/Yuki/Yuki.physics3.json) | 物理参数（头发、身体摆动） |
| [models/Yuki/Yuki.cdi3.json](d:/Projects/LiveYukiL2D/models/Yuki/Yuki.cdi3.json) | 口型同步参数 |
| [models/Yuki/Yuki.1024/](d:/Projects/LiveYukiL2D/models/Yuki/Yuki.1024) | 模型纹理图集 |

---

## 黑箱模块（可不用深度关注）

以下模块功能明确、接口稳定，日常开发一般不需要深入阅读源码。

### 1. Live2D Cubism Framework（TS 底层）

位于 `frontend/minimal/src/WebSDK/Framework/src/`，是 Live2D Cubism SDK for TypeScript 的官方实现。

- **作用**：提供模型解析、物理计算、动作播放、WebGL 渲染等底层能力
- **关注建议**：除非要修渲染问题或升级 SDK，否则无需修改
- **关键子模块**：
  - `model/` — MOC3 加载、模型实例
  - `motion/` — 动作和表情管理
  - `physics/` — 物理模拟
  - `rendering/` — WebGL 渲染器和着色器
  - `math/` — 矩阵和向量运算
  - `id/` — 字符串 ID 管理

### 2. Live2D Cubism Core（JS 原生）

位于 `frontend/minimal/src/WebSDK/Core/`，是 Live2D Cubism Core 的 WebAssembly/JS 绑定。

- **作用**：MOC3 文件解析的原生实现
- **关注建议**：黑箱，不修改

### 3. Electron 壳层

位于 `frontend/minimal/electron-main.cjs` 和 `electron-preload.cjs`。

- **作用**：将前端打包为桌面窗口，处理透明窗口、鼠标穿透、窗口拖动
- **关注建议**：如需调整桌面窗口行为时查看，否则可忽略

### 4. Live2D WebSDK 辅助模块

位于 `frontend/minimal/src/WebSDK/src/` 下的以下文件：

| 文件 | 说明 |
|------|------|
| `lappadapter.ts` | 适配 Live2D 模型表达式接口，黑箱 |
| `lapppal.ts` | 平台抽象层（日志、时间等），黑箱 |
| `lappsprite.ts` | 2D 精灵渲染辅助，黑箱 |
| `lapptexturemanager.ts` | 纹理加载和缓存，黑箱 |
| `lappwavfilehandler.ts` | 音频波形驱动唇形同步，黑箱 |
| `touchmanager.ts` | 触摸/鼠标事件管理，黑箱 |

### 5. 前端构建配置

| 文件 | 说明 |
|------|------|
| `frontend/minimal/package.json` | npm 依赖和脚本定义 |
| `frontend/minimal/vite.config.ts` | Vite 构建配置 |
| `frontend/minimal/tsconfig.json` | TypeScript 编译配置 |
| `frontend/minimal/index.html` | HTML 入口 |

### 6. 参考实现

位于 `frontend/vendor/open-llm-vtuber-live2d/` 和 `reference/Open-LLM-VTuber/`。

- **作用**：Open-LLM-VTuber 的 Live2D 前端实现，作为本项目前端的参考来源
- **关注建议**：不修改，仅作参考

---

## 调用关系图

```
main.py (入口)
  │
  ├─ desktop_electron.py (桌面模式)
  │    ├─ server.py (后端服务)
  │    └─ npm run desktop (Electron 前端)
  │
  └─ server.py (浏览器模式)
       ├─ 托管 frontend/minimal/dist/ (前端静态文件)
       ├─ 托管 models/ (Live2D 模型资源)
       └─ WebSocket (/ws)
            │
            ▼
       frontend/minimal/src/main.ts
            │
            ├─ lappdefine.ts (全局配置)
            ├─ LAppLive2DManager (模型管理)
            │    └─ lappmodel.ts (单模型实例)
            │         └─ Framework 模型层 (MOC3 加载)
            │
            ├─ LAppDelegate (应用控制器)
            │    ├─ lappglmanager.ts (WebGL)
            │    └─ lappview.ts (渲染视图)
            │         └─ Framework 渲染层
            │
            └─ WebSocket 消息处理
                 ├─ set-model → 加载模型
                 ├─ say → 显示字幕 + 播放动作
                 └─ audio → 播放音频 + 唇形同步
```

---

## 数据流

```
外部调用方
  │
  │ HTTP POST /api/say?text=xxx
  │ HTTP POST /api/audio
  │ WebSocket message: { type: "say", text: "xxx" }
  ▼
server.py
  │
  │ WebSocket broadcast
  ▼
frontend/main.ts (handleMessage)
  │
  ├─ set-model → loadModel() → LAppLive2DManager → lappmodel → Framework
  ├─ say → sayText() → 更新字幕 + playTalkMotion()
  └─ audio → playAudioBase64() → Audio 元素 + WAV 唇形同步
```

---

## 维护建议

- **修改前端逻辑**：优先看 `main.ts`，然后顺着调用关系进入 WebSDK 层
- **修改后端逻辑**：优先看 `server.py`，关注路由和 WebSocket 消息处理
- **切换模型**：修改 `config.json` 或通过 `/api/model` 接口
- **调整窗口行为**：查看 `config.json` 的 `desktopPet` 段和 `electron-main.cjs`
- **修渲染/物理问题**：才需要进入 `Framework/` 层
- **不要修改**：`Framework/`、`Core/`、`vendor/`、`reference/`，这些是外部依赖或参考实现
