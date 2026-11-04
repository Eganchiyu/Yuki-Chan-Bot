# 主人桌面状态监控与查询工具归档

## 1. 这段代码是干什么的
`tools_status.py`（原 `modules/system_state` 模块，后合并至 `core/tools/tools_status.py` -> `core/tools/_archived/tools_status.py`）用于感知机主在电脑前的实时活动状态与前台窗口：
- **跨平台空闲与窗口探测**：
  - Windows：通过 `ctypes.windll.user32`（`GetForegroundWindow` / `GetLastInputInfo`）获取前台窗口标题和系统输入空闲秒数。
  - Linux：通过 `xprop` 读取 `_NET_ACTIVE_WINDOW` 获取 X11 前台窗口标题，通过 `loginctl show-session <XDG_SESSION_ID> -P IdleSinceHint` 获取会话空闲时长（带 5s 缓存）。
- **后台状态监控线程**：`start_monitor_service()` 启动 `master-state-monitor` 守护线程，每秒刷新最近活跃时间戳，将状态划分为 `online`（≤30s）、`paused`（≤2min）、`away`（≤10min）、`offline`（>10min）。
- **Function Call 工具**：`get_master_status_tool(context)` 返回主人是否在线、是否活跃、当前状态与当前前台窗口标题。

## 2. 原来的埋点在哪里
- **工具实现路径**：`core/tools/tools_status.py`（后移入 `core/tools/_archived/tools_status.py`）
- **后台线程启动埋点**：原在 `main.py` 初始化阶段调用 `start_monitor_service()`，退出清理时调用 `stop_monitor_service()`。
- **工具注册埋点**：`core/tools/tools.py` 的 `TOOL_SPECS` 列表。

## 3. 怎样接入
1. 将文件复制回 `core/tools/tools_status.py`：
   ```bash
   cp _archive/master_status/tools_status.py core/tools/tools_status.py
   ```
2. 在 `main.py` 的 `initialize_components()`（或主入口启动处）启动后台监控线程：
   ```python
   from core.tools.tools_status import start_monitor_service, stop_monitor_service
   start_monitor_service()
   ```
   并在 `_do_cleanup()` 中加入 `stop_monitor_service()`。
3. 在 `core/tools/tools.py` 中注册 `ToolSpec`：
   ```python
   from .tools_status import get_master_status_tool

   # 在 TOOL_SPECS 中追加：
   ToolSpec(
       name="get_master_status",
       description="查询主人当前的电脑在线状态、活跃程度以及正在使用的前台窗口标题。",
       parameters={"type": "object", "properties": {}},
       handler=get_master_status_tool,
   ),
   ```
   （注：若 Yuki 运行在 Docker 容器内，Linux 侧需挂载宿主机 X11 socket、设置 `DISPLAY` / `XAUTHORITY` 与 `XDG_SESSION_ID` 才能读取宿主窗口与空闲状态。）
