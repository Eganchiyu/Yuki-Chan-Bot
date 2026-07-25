# GPS-VPS 地理位置实时中转系统 - 技术说明文档

## 1. 项目概述

基于 WebSocket 的地理位置实时中转系统，实现云端服务器、数据发送端（模拟鸿蒙设备）和数据接收端（PC端）之间的实时位置数据转发。

### 1.1 系统架构

```
┌─────────────────┐         WebSocket          ┌─────────────────┐
│   发送端        │  ───────────────────────>   │   云端服务器     │
│ (gps_sender_sim)│                            │   (server.py)   │
└─────────────────┘                            └─────────────────┘
                                                        │
                                                        │ 广播
                                                        ↓
                                               ┌─────────────────┐
                                               │   接收端        │
                                               │ (pc_receiver)   │
                                               └─────────────────┘
```

## 2. 代码文件说明

### 2.1 云端服务器 - server.py

**文件路径**: `/root/gps-vps/server.py`

**功能**:
- 监听 `0.0.0.0:8765` 端口
- 维护所有连接的客户端集合
- 接收定位消息后缓存为最新位置
- 新客户端连接时立即推送缓存的最新位置
- 接收任意客户端消息后，广播给其他所有客户端
- 异常处理和连接日志记录

**核心逻辑**:
- 使用 `websockets` 库的异步服务器
- 客户端集合管理：`clients = set()`
- 广播函数：排除发送者，向其他客户端转发消息
- 异常捕获：`ConnectionClosed` 异常处理和客户端清理

**兼容性说明**:
- 为兼容 Python 3.6.8，handler 函数签名使用 `async def handler(websocket, path=None)`
- 使用 `asyncio.get_event_loop()` 而非 `asyncio.run()`

### 2.2 PC 接收端 - pc_receiver.py

**文件路径**: `d:\Projects\GPS-VPS\pc_receiver.py`

**功能**:
- 连接云端服务器 `ws://8.217.41.28:8765`
- 持续监听并接收广播消息
- 解析 JSON 格式的位置数据（longitude, latitude, timestamp）
- 断线自动重连机制（5秒间隔）

**输出格式**:
```
[LOCATION] longitude=114.169211, latitude=22.322653, timestamp=2026-07-24T03:19:47.991240+00:00
```

### 2.3 模拟发送端 - gps_sender_sim.py

**文件路径**: `d:\Projects\GPS-VPS\gps_sender_sim.py`

**功能**:
- 连接云端服务器 `ws://8.217.41.28:8765`
- 每 3 秒生成一次模拟 GPS 数据
- 数据格式：JSON（longitude, latitude, timestamp）
- 断线自动重连机制（5秒间隔）

**模拟数据范围**:
- 基准坐标：longitude=114.1694, latitude=22.3193（香港地区）
- 随机偏移：±0.01 度（约 ±1km）

## 3. 服务器当前状态

### 3.1 环境信息

- **操作系统**: CentOS/Alibaba Cloud Linux
- **Python 版本**: 3.6.8
- **websockets 版本**: 9.1
- **服务路径**: `/root/gps-vps/server.py`
- **日志路径**: `/root/gps-vps/server.log`

### 3.2 运行状态

- **进程状态**: 正在运行（PID: 50693）
- **监听端口**: 0.0.0.0:8765
- **启动命令**: `python3 -u server.py`
- **后台运行**: 使用 `nohup` 保持运行

### 3.3 验证命令

```bash
# 检查进程
ps -ef | grep '[p]ython3 -u server.py'

# 检查端口
ss -lntp | grep ':8765'

# 查看日志
tail -n 50 /root/gps-vps/server.log
```

## 4. 使用方法

### 4.1 云端服务器管理

**SSH 连接**:
```bash
ssh yuki
```

**启动服务**:
```bash
cd /root/gps-vps
nohup python3 -u server.py > server.log 2>&1 < /dev/null &
```

**停止服务**:
```bash
# 查找进程ID
ps -ef | grep '[p]ython3 -u server.py'

# 停止进程
kill <PID>
```

**查看日志**:
```bash
tail -f /root/gps-vps/server.log
```

### 4.2 本地接收端运行

**安装依赖**:
```bash
pip install websockets
```

**启动接收端**:
```bash
python pc_receiver.py
```

**预期输出**:
```
[CONNECT] 正在连接服务器: ws://8.217.41.28:8765
[CONNECTED] 已连接服务器，开始监听位置数据
[LOCATION] longitude=114.169211, latitude=22.322653, timestamp=2026-07-24T03:19:47.991240+00:00
```

### 4.3 本地模拟发送端运行

**安装依赖**:
```bash
pip install websockets
```

**启动发送端**:
```bash
python gps_sender_sim.py
```

**预期输出**:
```
[CONNECT] 正在连接服务器: ws://8.217.41.28:8765
[CONNECTED] 已连接服务器，开始发送模拟 GPS 数据
[SEND] {"longitude": 114.167412, "latitude": 22.310039, "timestamp": "2026-07-24T03:19:44.983570+00:00"}
```

### 4.4 完整测试流程

1. **确认云端服务运行**:
   ```bash
   ssh yuki "ps -ef | grep '[p]ython3 -u server.py'"
   ```

2. **启动本地接收端**（终端1）:
   ```bash
   python pc_receiver.py
   ```

3. **启动本地发送端**（终端2）:
   ```bash
   python gps_sender_sim.py
   ```

4. **观察接收端输出**，应能看到位置数据实时更新。

## 5. 数据格式

### 5.1 JSON 消息结构

```json
{
  "longitude": 114.169211,
  "latitude": 22.322653,
  "timestamp": "2026-07-24T03:19:47.991240+00:00"
}
```

**字段说明**:
- `longitude`: 经度（浮点数，保留6位小数）
- `latitude`: 纬度（浮点数，保留6位小数）
- `timestamp`: UTC 时间戳（ISO 8601 格式）

## 6. 注意事项

### 6.1 网络要求

- 云端服务器需开放 8765 端口（TCP）
- 客户端需能访问 `8.217.41.28:8765`

### 6.2 兼容性

- 云端服务器代码已适配 Python 3.6.8
- 本地客户端使用 Python 3.9+ 语法（类型注解）
- websockets 版本：云端 9.1，本地 16.1.1

### 6.3 日志说明

- 云端日志包含：连接、断开、接收、转发、错误等信息
- 日志文件可能包含中文乱码（终端编码问题），不影响功能
- 建议定期清理日志文件：`> /root/gps-vps/server.log`

### 6.4 异常处理

- 客户端断线后自动重连（5秒间隔）
- 服务器自动清理异常断开的客户端连接
- 转发失败时自动移除目标客户端

## 7. 测试验证结果

**测试时间**: 2026-07-24

**测试结果**: ✅ 通路正常

**验证数据**:
```
[LOCATION] longitude=114.169211, latitude=22.322653, timestamp=2026-07-24T03:19:47.991240+00:00
[LOCATION] longitude=114.167108, latitude=22.310431, timestamp=2026-07-24T03:19:50.994869+00:00
```

**云端日志确认**:
```
[RECEIVE] 来自 ('103.151.173.197', 61423): {"longitude": 114.169211, ...}
[FORWARD] 向 1 个客户端转发消息: {"longitude": 114.169211, ...}
```

## 8. 后续扩展建议

1. **数据持久化**: 添加数据库存储位置数据
2. **认证机制**: 添加客户端身份验证
3. **多房间支持**: 按设备ID分组广播
4. **数据过滤**: 支持按时间、距离等条件过滤
5. **监控告警**: 添加服务健康检查和告警机制
6. **SSL/TLS**: 加密 WebSocket 连接

---

**文档版本**: v1.0  
**最后更新**: 2026-07-24  
**维护者**: GPS-VPS 开发团队
