# SnowLuma 接入指南

本文说明如何把 YukiV6 的 QQ 接入从 NapCat 切换到 SnowLuma。适配层是单文件
[network/snowluma.py](../network/snowluma.py)，复用 `NapCatGateway` 的收发与协议逻辑，
只覆盖 SnowLuma 的差异点。

## 1. 前置条件

- SnowLuma 已启动并完成 QQ 扫码登录（SnowLuma 只支持扫码登录）。
- 在 SnowLuma 的 OneBot 网络配置中启用了**正向 WebSocket 服务端**（`wsServers`）。
- YukiV6 与 SnowLuma 能互相访问对应端口。

SnowLuma 涉及三个端口，不要混用：

| 端口 | 用途 | 是否填进 Yuki |
|------|------|---------------|
| 3001 | OneBot WebSocket（`wsServers` 默认） | **是** |
| 3000 | OneBot HTTP API | 否 |
| 5099 | SnowLuma WebUI 管理面板 | 否 |

## 2. SnowLuma 侧配置

编辑 `config/onebot.json`（账号级覆盖在 `config/onebot_<uin>.json`），保留一个 `wsServers` 条目：

```json
{
  "networks": {
    "httpServers": [],
    "httpClients": [],
    "wsServers": [
      {
        "name": "yuki",
        "enabled": true,
        "host": "127.0.0.1",
        "port": 3001,
        "path": "/",
        "role": "Universal",
        "accessToken": "换成你的访问令牌",
        "messageFormat": "array",
        "reportSelfMessage": false
      }
    ],
    "wsClients": []
  },
  "musicSignUrl": ""
}
```

关键字段：

- `role`：必须是 `Universal`，只接事件或只收动作会出现“收得到消息、发不出回复”。
- `path`：固定 `/`，Yuki 当前不支持自定义 WebSocket 路径。
- `messageFormat`：必须是 `array`。Yuki 的 @ 判定优先读结构化 `message` 段。
- `accessToken`：Yuki 连接时用的令牌，**不是** WebUI 登录密码。
- `reportSelfMessage`：保持 `false`，否则机器人自己的消息可能回流触发对话。

修改后重启 SnowLuma，确认 WebSocket 端口真的在监听。

## 3. Yuki 侧配置

复用现有 `connection` 段，不需要新增配置项。把地址与令牌指向 SnowLuma：

```yaml
connection:
  napcat_ws_url: "ws://127.0.0.1:3001"
  napcat_ws_token: "换成你的访问令牌"
  max_retries: 3
```

字段名虽然还叫 `napcat_*`，但 `SnowLumaGateway` 同样读取这两项，避免为切换后端新增配置键。

## 4. 切换网关

在 [main.py](../main.py) 的初始化里把网关换成 `SnowLumaGateway`：

```python
from network.snowluma import SnowLumaGateway

sender = SnowLumaGateway(cfg.NAPCAT_WS_URL, cfg.NAPCAT_WS_TOKEN)
```

其余启动流程、入站监听、会话管线都不用改。切换后可删除 `NapCatGateway` 的导入（如无其他引用）。

## 5. 适配层做了什么

| 差异点 | NapCat | SnowLuma | 适配处理 |
|--------|--------|----------|----------|
| 鉴权方式 | `?access_token=` 查询参数 | `Authorization: Bearer <token>` | 覆盖 `_connect`，用请求头鉴权 |
| 事件消息格式 | 可配 string/array | 默认且建议 `array` | `raw_message` 缺失时按消息段还原 CQ 文本 |
| 戳一戳 | `send_poke` | `send_poke`（自动路由），也可 `group_poke` | 优先 `send_poke`，失败回退 `group_poke` |
| 收发/帧路由 | `NapCatGateway` | 同为 OneBot 11 正向 WS | 直接复用，未重复实现 |

连接后的行为与 NapCat 一致：`echo` 响应唤醒 `call()`，`post_type` 事件进队列，
断线 3 秒重连，`listen()` 只应由一个消费者迭代。

## 6. 能力差异与限制

- **本地文件**：`send_local_image` / `send_local_file` 仍使用 `file:///` 本机绝对路径。
  SnowLuma 跑在 Docker 或远端时看不到宿主机路径，需要把目录挂载进容器，或改用 URL。
- **群文件下载**：SnowLuma 的 `get_file` 只覆盖图片/语音缓存；群文件要用
  `get_group_file_url`。继承的 `download_file` 未做这条分流，下载群文件可能失败。
- **消息格式**：如果 SnowLuma 事件里的 `message` 不是数组，`raw_message` 兜底仍可用，
  但 @ 判定只能退回 CQ 文本匹配，建议始终使用 `array`。
- **心跳**：Yuki 启动时默认在线；收到 `status.online=false` 的心跳后才挂起后台任务，
  SnowLuma 不推心跳也不会阻塞消息处理。
- **配置键名**：不同 SnowLuma 版本可能使用 `messageFormat` 或 `messagePostFormat`，
  以事件里的 `message` 实际是数组为准。

## 7. 验证清单

1. 启动 SnowLuma 并登录机器人 QQ，确认 `wsServers` 已启用。
2. 配好 `connection` 并切换为 `SnowLumaGateway`，运行 `python main.py`。
3. 日志出现 `[SnowLuma] 连接已建立: ...`。
4. 用主人 QQ 私聊机器人，确认能收到回复。
5. 在目标群里 @ 机器人，确认能回复。
6. 戳一戳机器人，确认事件被处理。
7. 发送 `help`，确认帮助图能发出（若图片失败，先查本地路径/挂载）。

## 8. 常见问题

| 现象 | 排查方向 |
|------|----------|
| 401 / 403 | 填成了 WebUI 登录密码，应填 OneBot `accessToken` |
| 连不上 | `wsServers` 是否启用、端口是否与 `napcat_ws_url` 一致、路径是否为 `/` |
| 收得到事件但发不出消息 | `role` 是否为 `Universal` |
| 群里不响应 @ | `messageFormat` 是否为 `array`、群号是否在 `TARGET_GROUPS` 白名单 |
| 本地图片/文件发送失败 | SnowLuma 是否在容器内、路径是否可见 |
| 私聊正常群里不回 | 群是否被 `/关闭` 休眠、是否命中防抖或破冰逻辑 |

参考：SnowLuma 官方文档 <https://snowluma.github.io/zh/>。
