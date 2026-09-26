# Yuki Android 桥接（Android Bridge）技术规划

> 状态：方案评估与技术规划，尚未实现
> 目标：让 Yuki 在主人授权下，远程访问主人手机（无 root）的 adb 能力
> 前置条件：手机 Android 11-16、无 root、手机与 PC 均安装 Tailscale、手机侧可常驻 Termux

---

## 1. 目标与边界

### 1.1 目标

让 Yuki 能够通过 adb 远程访问主人的手机，实现状态感知、内容读取与受限操作，且**不依赖 USB 数据线、不依赖同一局域网**。

### 1.2 必须先厘清的能力边界

这是本方案最重要的一节。**"根目录全部权限" 在无 root 前提下无法实现**，必须先把目标校准为 "shell 级权限"。

`adb shell` 的登录身份是 **`shell` 用户（uid 2000）**，而非 root。这是 Android 的权限模型决定的，不是 adb 工具本身的限制。

| 能力 | 无 root adb | 真 root |
|---|---|---|
| `/sdcard` 全读写（含 `Android/data`、`Android/obb`） | ✅ | ✅ |
| 截屏 / 录屏 | ✅ | ✅ |
| 注入点击与文本输入（`input tap/text/swipe`） | ✅ | ✅ |
| 通知读取、进程列表、电量、`dumpsys`、`getprop` | ✅ | ✅ |
| 安装 / 卸载 / 停用应用 | ✅ | ✅ |
| 修改系统设置（`settings put`）、授权限 | ✅ | ✅ |
| 启停任意 Activity（`am start/force-stop`） | ✅ | ✅ |
| 其他 App 私有数据 `/data/data/<pkg>` | ❌ 仅 `run-as` 可调试应用 | ✅ |
| 写 `/system`、`/vendor`、`/product` | ❌ | ✅ |
| 读 `/data` 根、`/data/media` 原始层 | ❌ | ✅ |
| 修改 SELinux 策略 | ❌ | ✅ |

**结论**：本方案的实际目标是 **shell 级权限**。这已经比普通 App 高一个量级——Termux 自身被 SELinux 拒之门外的 `screencap`、`pm`、`settings`、`input`、`dumpsys` 全部可用——但**不等于根目录全部权限**。

如果未来需要 App 侧也获得同级别权限，Shizuku 是同等级的替代路径（不需要 root，复用 adb 通道），可另行评估。

### 1.3 明确的非目标

- 不做公网端口暴露（任何形式的 `5555` 或 adbd 端口映射到公网）。
- 不追求"零物理接触"完成初始化（技术上不可能，见 3.1）。
- 不实现 root 化或绕过 SELinux。

---

## 2. 当前环境评估

### 2.1 本机（PC）现有条件

| 项 | 状态 | 说明 |
|---|---|---|
| 操作系统 | Arch Linux x86_64，内核 7.2.6 | 主机名 `asumi` |
| adb | **37.0.0**（`/usr/bin/adb`） | 已是 ADB Wi-Fi 2.0 版本，属最新代 |
| cloudflared | 已安装 `/home/asumi/.local/bin/cloudflared` | 但授权登录未完成、未绑域名（见 `cloudflared_guide.md`） |
| SSH 客户端 | 已有 `/usr/bin/ssh` | `~/.ssh/config` 中已配 `Amtech` → `47.100.136.185` |
| Tailscale | **未安装** | 需要新增 |
| Python 项目环境 | uv + `.venv`，Python 3.11.15 | 见 `pyproject.toml` |

### 2.2 YukiV6 现有可复用基础

| 能力 | 位置 | 复用方式 |
|---|---|---|
| 工具声明协议 | `core/toolchain.py:79` `ToolSpec` | 新增手机工具直接登记 |
| 工具装配表 | `core/tools/tools.py:18` `TOOL_SPECS` | 在此登记新工具 |
| 结果封装 | `core/toolchain.py:15` `ToolResult` | handler 统一返回 |
| 模式级工具组 | `core/toolchain.py:135` `ToolRegistryProvider` | 可为手机模式隔离工具组 |
| 主人状态工具范式 | `core/tools/tools_status.py:186` | `phone_status` 可照此写 |
| 视觉理解链路 | `modules/vision/` | 手机截屏可复用 |
| 危险命令拦截范式 | `core/maid/maid_runtime.py:187` `_is_terminal_command_allowed` | 白名单思路可借鉴（但 adb 需更严） |
| 安全分级先例 | `future addons/desktop_pet_plan.md` 第 11 节 | 权限模式与风险分级可直接沿用 |
| 配置系统 | `config.py` + `config_field()` | 手机配置走同一套 |

**已有先例参考**：`future addons/GPS-VPS/` 已实现过"手机 → VPS WebSocket → PC"的数据中转通路并验证可用。本方案在网络层思路上与之一致（都是"手机侧主动挂到可达网络"），但技术选型升级为 Tailscale + SSH，更适合低延迟交互式命令。

---

## 3. 核心技术约束

### 3.1 约束一：首次开启必须有人在场

adb 的信任模型基于 RSA 密钥对：

- **Android 11+ 无线调试**：手机上点击"使用配对码配对设备"，PC 侧 `adb pair <ip>:<port> <code>` 完成配对。配对端口是临时端口，配对码需从手机屏幕上读取。
- **Android 10 及以下 / `adb tcpip`**：必须 USB 连接一次，执行 `adb tcpip 5555`，手机端会弹 RSA 授权弹窗需人工点"允许"。

**这两种方式都无法远程完成**。除非手机已 root 并有开机脚本，但那属于完全不同的复杂度层级。

因此本方案的现实形态是：**一次性现场初始化（约 15 分钟）+ 之后长期全远程**。

### 3.2 约束二：端口漂移（本方案的主要难点）

| 模式 | 端口行为 | 重启后 |
|---|---|---|
| Android 11+ 无线调试 | **连接端口随机**，每次重启手机、重开无线调试开关都会变 | 需重新连接，部分机型开关还会自动关闭 |
| Android 17 + adb 37.0.0（ADB Wi-Fi 2.0） | 受信网络自动重连 | 自动恢复，**无需人工干预** |
| 传统 `adb tcpip 5555` | 端口固定 5555 | adbd 重启即失效，需重新触发 |

本机 adb 已是 37.0.0，但 **ADB Wi-Fi 2.0 的自动重连需要手机侧是 Android 17**。用户手机为 Android 11-16，**无法享受该特性**，因此端口漂移必须由本方案自行补偿。

### 3.3 约束三：mDNS 不能跨网

`adb mdns services` 可以在局域网内自动发现设备端口，从而绕开端口漂移问题。但：

- mDNS 是链路本地多播协议，**不跨网段，也不跨 Tailscale 隧道**。
- 而本方案的默认场景恰恰是跨网（手机在移动网络、PC 在家）。

**结论：不能依赖 mDNS 做远程端口发现。** 这是选择"Termux 自连"架构的决定性原因。

---

## 4. 方案对比与选型

### 4.1 网络通道选型

前提：手机与 PC 之间要有 IP 可达通路。手机在移动网络下大概率处于 CGNAT 之后，公网端口映射基本不可行，且把 adb 暴露到公网是明显的安全事故。

| 方案 | 原理 | 优点 | 缺点 | 结论 |
|---|---|---|---|---|
| **Tailscale** | 两端装 VPN，走 100.x 私有网段，自动 NAT 穿透 | 免端口映射、全程加密、手机端只需装 App；业界远程 adb 的标准做法 | 需登录账号；手机需常驻 VPN | ✅ **采用** |
| ZeroTier | 同类 P2P VPN | 若已有 ZeroTier 网络则零成本 | 无既定基础设施 | 备选 |
| VPS 反向 SSH 隧道 | 手机侧 Termux 主动 `ssh -R` 到 VPS | 可复用已有 VPS（`47.100.136.185`） | 多一跳、手机侧必须能跑 ssh、VPS 需防爆破 | 备选 |
| cloudflared | 内网穿透 | 本机已装 | 无成熟 Android 客户端；tunnel 授权未完成、未绑域名 | ❌ 不采用 |
| 公网端口映射 | 路由器直接开 5555 | 配置简单 | CGNAT 下不可用；安全隐患极大 | ❌ 明确禁止 |

### 4.2 连接架构选型：PC 直连 adb vs Termux SSH 中继

| 问题 | A. PC 直连手机 adb | B. Termux 自连 + SSH 中继 |
|---|---|---|
| 端口每次变化 | ❌ 无法远程发现（3.3 已论证） | ✅ Termux 侧本地发现，主人无感 |
| adbd 是否接受非本机来源 IP | ⚠️ 不确定，需实测 | ✅ 走 loopback，必然可用 |
| adb 协议版本兼容 | ⚠️ 需 PC adb 与手机 adbd 版本匹配 | ✅ 由手机侧自理 |
| 链路跳数 | 1 跳 | 2 跳（多约 1-3ms，可忽略） |
| 需要手机常驻程序 | 仅 Tailscale | Tailscale + Termux + sshd |

**选型：B（Termux 自连 + SSH 中继）**。

理由：方案 A 的端口漂移问题无解（因为 mDNS 跨不过隧道），会导致每次手机重启后都需要主人手动把屏幕上的端口号报给 Yuki。方案 B 用两跳的微小延迟换取"完全无人值守"，这个交换非常划算。

Termux 在自己的 loopback 上完成 adb 连接后，端口漂移问题**在手机内部就被吃掉了**，PC 侧永远只连一个固定的 SSH 端口（8022）。

---

## 5. 推荐架构

```text
┌────────────────── 手机（Android 11-16，无 root）──────────────────┐
│                                                                    │
│  Termux（+ Termux:Boot 开机自启）                                   │
│   ├─ android-tools 提供的 adb 客户端                                │
│   ├─ adb pair / adb connect 127.0.0.1:<adbd端口>                   │
│   │     └─ 端口漂移在此层被本地吸收，PC 侧不可见                      │
│   ├─ 保活与重连脚本（检测 adbd 断开后自动重连）                       │
│   └─ sshd 监听 :8022                                               │
│                                                                    │
│  Tailscale App ── 持有 100.x.y.z 私有地址                          │
└───────────────────────────┬────────────────────────────────────────┘
                            │  Tailscale 加密隧道（NAT 穿透，无端口映射）
┌───────────────────────────┴────────────────────────────────────────┐
│  PC / YukiV6                                                        │
│                                                                    │
│  modules/android_bridge/                                            │
│   ├─ ssh 通道管理（连接、重连、健康检查）                             │
│   ├─ 命令构造与白名单                                                │
│   ├─ 结果解析（stdout/stderr → 结构化数据）                          │
│   └─ 审计日志                                                        │
│                            ↓                                        │
│  core/tools/tools_android.py  →  ToolSpec  →  工具链                 │
│                            ↓                                        │
│  YukiEngine（群聊 / 私聊 / 桌宠模式均可调用）                          │
└────────────────────────────────────────────────────────────────────┘
```

### 5.1 关键设计点

1. **PC 侧不直连 adb**。PC 侧只连 SSH，所有 adb 命令在手机本地执行。这样 PC 侧不关心端口、不关心 adb 版本、不关心 adbd 的来源 IP 限制。
2. **连接层与工具层分离**。工具 handler 不拼接 shell 命令字符串，而是调用 `android_bridge` 的语义化方法（`get_status()` / `screenshot()` / `open_app(pkg)`），由桥接层负责构造命令与校验。
3. **单点配置**。手机 Tailscale 地址、SSH 端口、允许的能力集全部走 `config.py`，禁止硬编码。

---

## 6. 模块规划

### 6.1 新增目录

```text
modules/android_bridge/
├── __init__.py
├── bridge.py        # SSH 通道管理：连接、重连、超时、健康检查
├── commands.py      # 命令构造与白名单校验（唯一拼接 shell 的地方）
├── parsers.py       # 输出解析：电量、网络、进程、通知等 → 结构化 dict
└── audit.py         # 操作审计日志
```

职责划分：

- `bridge.py`：持有 `ssh` 子进程或 `asyncssh` 连接，实现 `run(command) -> (code, stdout, stderr)`。断线自动重连，连接失败返回明确错误码而非抛裸异常。
- `commands.py`：定义所有允许执行的 adb 命令模板。**命令参数必须经过白名单与转义**，禁止把 LLM 传入的原始字符串直接拼进命令（防命令注入）。
- `parsers.py`：把 `dumpsys battery`、`dumpsys wifi` 等冗长输出解析为精简结构，避免把整段原始输出塞进 LLM 上下文。
- `audit.py`：记录每次操作的时间、能力、目标、结果，落盘到 `data/` 下，供事后追溯。

### 6.2 工具层

新增 `core/tools/tools_android.py`，在 `core/tools/tools.py:18` 的 `TOOL_SPECS` 中登记。

建议**按能力粒度拆工具**，而不是给一个万能 shell——这样每个工具的权限边界清晰，也便于按模式隔离工具组。

| 工具名 | 能力 | 风险 | 说明 |
|---|---|---|---|
| `phone_status` | 电量、网络、存储、前台应用、屏幕状态 | safe | 只读，参考 `tools_status.py:186` 写法 |
| `phone_notifications` | 读取最近通知 | low | 含隐私内容，建议脱敏摘要 |
| `phone_screenshot` | 截屏并交给视觉链路理解 | medium | 需敏感场景过滤（见 8.3） |
| `phone_open_app` | 按包名/应用名启动应用 | medium | 白名单应用 |
| `phone_notify` | 在手机上发通知 | medium | — |
| `phone_input` | 注入点击/滑动/文本 | **high** | 默认关闭，逐次确认 |
| `phone_file` | push/pull 文件 | **high** | 路径白名单 |
| `phone_app_manage` | 安装 / 卸载 / 停用应用 | **high** | 默认关闭 |

### 6.3 配置项

在 `config.py` 新增 `AndroidConfig` dataclass，用 `config_field()` 定义，然后运行 `python config.py sync` 同步 yaml：

```text
android.enabled               bool    总开关，默认 false
android.ssh_host              str     手机 Tailscale 地址（如 100.x.y.z）
android.ssh_port              int     Termux sshd 端口，默认 8022
android.ssh_user              str     默认 root（Termux 默认用户）
android.ssh_key_path          str     PC 侧私钥路径
android.connect_timeout       float   SSH 连接超时（秒）
android.command_timeout       float   单条 adb 命令超时（秒）
android.allowed_capabilities  list    允许的能力集，默认 ["status", "notifications"]
android.require_confirm       list    需要逐次确认的能力，默认 ["input", "file", "app_manage"]
android.sensitive_keywords    list    截屏敏感场景关键词，复用桌宠规划的关键词表
android.audit_log_path        str     审计日志路径
android.screenshot_dir        str     手机截屏本地落盘目录
```

---

## 7. 分阶段实施路线

### Phase 0：一次性现场初始化（需要主人在手机旁）

- 开启开发者选项 → 无线调试
- 安装 Tailscale，登录，记录手机 100.x 地址
- 从 **F-Droid 或 GitHub Releases** 安装 Termux（Play 版在 Android 11+ 已废弃，会出现各种异常）
- Termux 内：`pkg install android-tools openssh`
- Termux 内自连：`adb pair 127.0.0.1:<配对端口> <配对码>` → `adb connect 127.0.0.1:<连接端口>` → `adb devices` 验证
- 启动 sshd、设置密码、配置 PC 侧公钥免密
- 验证：PC 侧 `ssh -p 8022 <手机tailscale-ip> "adb devices"` 有输出

预计耗时 15 分钟。风险：低。

### Phase 1：连接层与只读能力

- 搭 `modules/android_bridge/`（`bridge.py` + `commands.py` + `parsers.py`）
- 实现 `phone_status` 工具，接入 `TOOL_SPECS`
- Termux 侧保活脚本 + Termux:Boot 开机自启
- 验证：群聊中让 Yuki 报手机电量，能返回正确值

风险：低-中。这是打通链路的关键阶段。

### Phase 2：云端联调与截屏理解

- `phone_screenshot`，落盘后交给 `modules/vision/` 走原生视觉
- 敏感场景过滤（第 8.3 节）
- 审计日志落盘
- 验证：让 Yuki 描述当前手机屏幕内容

风险：中（隐私）。必须先做过滤再做截屏。

### Phase 3：受限操作能力

- `phone_notify`、`phone_open_app`（白名单）
- 引入 `ActionGuard` 式确认流：高风险操作需主人在群聊/私聊中确认
- 权限模式可视化与一键断开

风险：中-高。

### Phase 4：可选扩展

- 输入注入 `phone_input`（默认关闭）
- Shizuku 路径评估（若未来需要 App 侧同权限）
- 与桌宠联动（手机作为 Yuki 的第二个"感知终端"）

风险：高。

---

## 8. 安全体系

### 8.1 权限模式

沿用 `future addons/desktop_pet_plan.md` 第 11 节的四级思路，映射到手机场景：

```text
observe_only    只读状态，不截屏，不操作                      ← 默认
assist_read     增加通知读取与截屏分析
assist_control  增加启动应用、发通知（需确认）
high_risk       增加输入注入、文件传输、应用管理（逐次确认 + 审计）
```

### 8.2 强制要求

- 默认只读，高风险能力默认关闭
- 高风险操作逐次确认，禁止"授权一次永久放行"
- 所有操作写审计日志（时间、能力、参数、结果）
- 提供全局开关与一键断开（关闭手机侧调试 + 清理 SSH 连接）
- 命令白名单：只允许预定义命令模板，参数强制转义，**禁止 LLM 原始输入拼接**

### 8.3 隐私过滤

截屏与通知读取前，先检测敏感场景。命中即拒绝，只返回安全提示。

敏感关键词（可参考桌宠规划第 8.2 节并扩展）：

```text
password, 密码, 登录, login, 支付, 银行, bank, wallet, token, key,
私信, 私聊, 账单, 订单, checkout, pay, alipay, wechat pay,
后台管理, production, admin, secret, credential, 身份证, 验证码
```

实现方式：先用 `dumpsys window` 或 `dumpsys activity` 取当前前台窗口标题/包名做关键词匹配，命中则拒绝截屏，不做"先截再判断"。

### 8.4 已知风险清单

| 风险 | 说明 | 缓解 |
|---|---|---|
| adb 权限过高 | shell 可读通知、相册、截屏、注入输入、装卸应用 | 能力分级 + 默认只读 + 确认流 |
| 手机丢失 / Tailscale 被入侵 | 攻击者可经 Tailscale 到达手机 | Tailscale ACL 限制仅 PC 可访问 8022 与 adbd 端口；启用 Tailscale 密钥过期 |
| SSH 弱口令爆破 | Termux sshd 暴露在 tailnet 内 | 强制公钥认证，禁用密码登录 |
| 命令注入 | LLM 生成的参数被拼进 shell | 命令模板 + 参数转义 + 无字符串拼接 |
| 端口/地址漂移导致误连 | 手机换网后 Tailscale 地址变化 | 使用 Tailscale MagicDNS 主机名而非裸 IP |
| 隐私泄露到 LLM | 截屏/通知内容进入上下文与日志 | 敏感场景前置过滤 + 不保存原始截屏 + 摘要化 |

---

## 9. 已知不确定点（需实测确认）

以下事项无法仅凭文档确定，需要在目标设备上验证：

1. **无线调试开关是否要求 Wi-Fi 关联**。Android 11+ 的无线调试通常要求设备关联到某个 Wi-Fi（不要求有互联网，但要有 Wi-Fi 关联）。若手机长期仅用移动数据，该开关可能无法开启。**这条直接决定方案是否可用，必须优先验证。**
2. **重启后无线调试是否自动保持**。部分机型重启后该开关会关闭，导致 adbd 不监听，Termux 也无法自连。若是这种情况，则本方案存在"每次重启需人工拨一次开关"的残余环节，Termux:Boot 只能自动完成重连，无法自动打开开关。
3. **PC 直连手机 Tailscale IP 是否可行**。若可行，可作为 Termux 中继失效时的降级路径。取决于 adbd 是否接受非本机来源 IP，需实测。
4. **不同厂商 ROM 的行为差异**。小米 / 华为 / OPPO 等对后台进程与自启的管理策略不同，Termux 常驻可能被杀。需按具体机型调整电池优化白名单。

---

## 10. 实施分工

### 10.1 我可以做的（需要你在场确认的部分除外）

- 搭建 `modules/android_bridge/` 全部代码：SSH 通道、命令白名单、输出解析、审计日志
- 实现 `core/tools/tools_android.py` 及各能力工具，登记到 `TOOL_SPECS`
- 在 `config.py` 新增 `AndroidConfig` 并执行 `config.py sync` 同步 yaml
- 编写 Termux 侧保活/重连脚本
- 在 PC 侧安装与配置 Tailscale（需要你提供账号登录授权）
- 编写 `tests/test_android_bridge.py` 单元测试（针对命令构造与解析层，不依赖真机）
- 更新 `docs/changelog.md` 与 `docs/architecture.md`

### 10.2 必须你本人做的（我无法代替）

我无法物理接触你的手机，以下操作只能由你完成：

1. **在手机上开启开发者选项与无线调试**——包括读取配对码和端口号
2. **在手机上安装并登录 Tailscale**
3. **在手机上安装 Termux 并完成首次 adb 自连配对**
4. **在手机上处理所有系统弹窗**（RSA 授权、无线调试确认等）
5. **提供 Tailscale 手机地址**（或配置 MagicDNS 主机名）

### 10.3 关于"把手机 adb 权限直接给我操作"

这条是可行的，但要说清楚它的实际含义与前提：

**可行的部分**：一旦上述 Phase 0 完成、SSH 通道建立，我就可以在这台机器上直接执行 adb 命令操作你的手机——包括读取状态、截屏、装应用、注入输入等。那时我确实是在"直接操作你的手机"。

**不可行的部分**：Phase 0 本身无法由我远程完成。原因见第 3.1 节——adb 的配对信任必须在手机侧人工确认。所以流程上一定是"你做完初始化 → 我接管后续"。

**需要你明确的**：如果把 adb 权限交给 Yuki，等于把手机的通知、相册、屏幕内容、应用控制权都开放出来。建议：

- 先只开只读能力（Phase 1-2），跑一段时间确认行为可控
- 再决定是否开放操作类能力（Phase 3+）
- 全程保留一键断开

**我还需要你提供的信息**：

- 手机品牌与型号
- 具体 Android 版本号
- 手机日常主要用 Wi-Fi 还是移动数据
- 是否愿意在 PC 侧安装 Tailscale（需要你登录账号）

---

## 11. 结论

| 维度 | 结论 |
|---|---|
| 技术可行性 | ✅ 可行，业界有成熟先例（scrcpy / VS Code Remote Android / OpenClaw 均用类似路径） |
| "零物理接触" | ❌ 不可能，首次配对必须在手机侧人工完成 |
| "根目录全部权限" | ❌ 无 root 不可能，实际可拿到 shell 级权限（已比普通 App 高一个量级） |
| 长期无人值守 | ⚠️ 取决于手机重启后无线调试是否自保持，需实测 |
| 推荐架构 | Termux 自连 + SSH 中继 + Tailscale |
| 主要风险 | 权限过高、隐私泄露、命令注入，均需工程手段控制 |

**建议推进顺序**：先花 15 分钟做完 Phase 0 验证"通路是否成立"（尤其第 9 节的第 1、2 条不确定点），确认后再投入 Phase 1 的代码实现。如果无线调试开关无法在纯移动数据下开启，则本方案需重新评估。

---

**文档版本**：v1.0
**创建时间**：2026-09-23
**相关文档**：`future addons/desktop_pet_plan.md`（权限分级范式）、`future addons/GPS-VPS/docs/technical-documentation.md`（手机到 PC 中转先例）、`cloudflared_guide.md`（已排除的通道方案）
