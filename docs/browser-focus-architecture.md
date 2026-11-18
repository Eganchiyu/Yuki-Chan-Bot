# 浏览器聚焦模式架构设计（Browser Focus Architecture）

> 状态：已落地实现并通过宿主机 Chrome 155 + DeepSeek 备选路线实测（2026-11-18）。
> 前置阅读：[focus-mode-paradigm.md](file:///home/asumi/Yuki/docs/focus-mode-paradigm.md)、[focus-mode-architecture.md](file:///home/asumi/Yuki/docs/focus-mode-architecture.md)。

---

## 一、设计目标与核心策略

浏览器聚焦模式（`browser` 域）使 Yuki 能在群聊/私聊流内直接操控宿主机的 Chrome 浏览器，保留机主既有登录态，并通过**主视觉文本 + Top 24 降序控件树 + 按需 720p 无模糊截图**实现低 Token、高精度的网页交互：

1. **宿主 Chrome 登录态复用与常驻**：
   - 容器以 `--network host` 运行，通过纯异步 CDP（`http://127.0.0.1:9222` + WebSocket）直连宿主机 Chrome，零新增镜像依赖。
   - [start_yuki_chrome.sh](file:///home/asumi/Yuki/scripts/start_yuki_chrome.sh) 默认在 `~/.cache/yuki-chrome-profile` 软链用户 `~/.config/google-chrome` 的 `Default` 与 `Local State`（绕开 Chrome 136+/155 禁止对默认目录直接开启调试端口的限制，零拷贝保留全部登录 Cookie），并优先使用 `systemd-run --user` 拉起常驻 `yuki-chrome.service`，绝不强制杀掉既有 Chrome 进程。
2. **前台置前、自动跟页与滚轮兜底**：
   - 每次附着、导航、点击或悬停前执行 `_bring_to_front()`（`/json/activate/{id}` + `Page.bringToFront`），防止 Chrome 节流后台标签页 compositor 导致 `Input.dispatchMouseEvent` 超时。
   - 点击 `target="_blank"` 链接新开标签页时，`click_at()` 自动检测 `openerId` 并跟随切换到新标签页。
   - `scroll()` 在 `Input.dispatchMouseEvent(mouseWheel)` 1.2s 无响应时自动降级为页内最近可滚动容器 / `window.scrollBy` 滚动；`/json/activate` 与 `/json/close` 走纯文本请求 `_http_request`。
3. **三段式稳定等待（跳过隐藏帧）**：
   - 每次操作后依次等待 `document.readyState === "complete"`、CDP 在途 `XHR/Fetch` 静默、以及仅针对主帧与已知可见 OOPIF 的 `MutationObserver` + 布局边界静默窗口（默认 `280ms`，总上限 `5.0s`）。
   - 跳过 `0x0` 隐藏统计 iframe 与 `document.hidden` 帧，避免 `requestAnimationFrame` 挂起拖慢点击节奏。
4. **跨域 `<iframe>` 穿透**：
   - 结合 `Page.getFrameTree`、`Target.getTargets()`（按 `parentFrameId` 补充扁平化 OOPIF）、`Target.setAutoAttach(flatten=True)` 与 `DOM.getFrameOwner` 自动穿透同源与跨域 `iframe`（例如 B 站 `www.bilibili.com/toy/*` 内嵌的 `www.bilibilitoy.com`），把所有坐标统一映射到顶层视口空间。
5. **文本与控件分离（Top 24 降序 + Main/Bar 配额）**：
   - 非交互可见文本（标题、题干、弹窗说明、状态提示）经去重、剥离与交互控件重叠的文案后，压缩进独立 `[页面文本]` 块，不占用控件编号名额。
   - 可交互控件严格控制在 `browser_max_nodes = 24` 个以内：弹窗节点最先保留；常态按 **主视觉区 ~80%（19 席） + 顶/边/底 Bar ~20%（5 席）** 分配名额（任一侧不足自动回流）。
   - 主视觉区按**视觉面积 + 控件类型 + 中心位置 + 高频动作词**打分；Bar 区优先保留**搜索框 + 个人空间/头像/登录入口 + 消息/动态/收藏/关注/点赞/评论/首页/返回**等核心交互；自动过滤继承 `cursor: pointer` 的子计数节点与整幅无文案顶栏头图链接，避免瀑布流底部卡片误占 Bar 名额；最终按综合得分**降序编为 `[#1] [#2] ...`**。
6. **按需 720p 无模糊截图与大号 Set-of-Mark 标注**：
   - 不做高斯模糊，轻量图采用 `720p` 尺度（`max_width=1280, quality=55`），高清图采用 `max_width=1600, quality=88`。
   - `browser_start` 首屏强制附带 720p 标注截图；后续动作若满足**控件明确**（有效语义控件 ≥ 3、有文字比例 ≥ 60%、且无非装饰性大面积交互 `<canvas>`/`<video>`，自动忽略 `aria-hidden` / `pointer-events: none` 背景动画画布），则跳过截图仅返回文本树；否则自动附带 720p 标注图。
   - 模型可随时通过 `action="screenshot"` 或 `screenshot="high"` 主动获取高清截图。
   - 标注编号采用随图宽自适应的大号字体（`1280px` 宽度下约 `23px`）+ 白边高对比红/橙底牌 + 碰撞避让逻辑（右侧窄边栏徽标优先贴框左侧绘制）。
7. **Yuki 人设与决策口吻**：
   - 在 `browser_start` 引导、`BROWSER.exit_hint`、工具描述与 [prompts.py](file:///home/asumi/Yuki/core/prompts.py) 中明确要求保持 Yuki 可爱灵巧的少女语气与自主好奇心，禁止 AI 腔与机械流水账汇报。

---

## 二、运行链路与状态机

```text
常态视图：仅暴露 browser_start(goal, url="")
   │
   ▼ 调用 browser_start
FocusManager.enter(chat_id, "browser") ──▶ BrowserDriver.ensure_connected()（连不上则 aborted 回滚）
   │                                           └─ 置前 + 可选导航 + 三段式稳定等待 + 首屏强制 720p 标注截图
   ▼ 同轮 ToolView 切换为聚焦视图（browser_action / browser_finish + BASE_KEEP_TOOLS）
循环操作 browser_action(action=open/click/hover/input/press/scroll/back/tabs/switch_tab/screenshot/...)
   │  ├─ 置前 + 动作执行（点击新开 tab 自动跟随 / 滚轮超时降级 scrollBy）→ 稳定等待 → 全 Frame 探针 + Top 24 + [页面文本]
   │  └─ screenshot="auto" 时判定明确性：明确则省去截图；不明确或主动要求则附带 720p/高清标注图
   │
   ▼ 调用 browser_finish(summary) 或闲置 > browser_focus_idle_turns 轮
FocusHook 原地覆写历史为 role="user" 的【浏览器操作总结】并切回常态视图
```

---

## 三、文件地图与配置项

| 文件 | 职责 |
|---|---|
| `core/browser_driver.py` | 纯异步 CDP 客户端、`BROWSER_LOCK` 串行锁、置前防节流、新开标签跟随、OOPIF/Frame 偏移聚合、跳过隐藏帧稳定等待、输入与滚轮降级原语 |
| `core/browser_tree.py` | 视口探针 JS、装饰性 Canvas 识别、头像/图标语义补全、Main/Bar 配额与降序打分、文本块去重压缩、明确性判定、大号 Set-of-Mark 标注 |
| `core/focus/domains/browser.py` | `BROWSER` `FocusDomain` 声明、`browser_start_tool`（注入 Yuki 人设引导与首屏图）、`browser_finish_tool` |
| `core/tools/tools_browser.py` | `browser_action_tool` 全量浏览器交互动作实现与轨迹记录 |
| `core/tools/tools.py` & `__init__.py` | `TOOL_SPECS` 与 handler 导出 |
| `core/prompts.py` | `MAID_SETTING` 补充 `browser_start` 亲手操作与保持 Yuki 灵巧语气提示 |
| `config.py` (`ToolsConfig`) | `browser_cdp_url`、`browser_max_nodes`、`browser_bar_quota`、`browser_wait_timeout`、`browser_settle_ms`、`browser_screenshot_*`、`browser_focus_*` |
| `scripts/start_yuki_chrome.sh` | 宿主机 Chrome CDP 启动/检测脚本（软链复用用户 Profile + `systemd-run --user` 常驻，绝不杀已有 Chrome） |
| `tests/test_focus_contract.py` & `tests/test_browser_focus.py` | 聚焦契约测试 + 排序/文本/明确性/大号标注/CDP 协议离线单测 |
