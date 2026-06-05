# YukiV6 部署运维手册

本手册提供 YukiV6 项目的部署、配置和运维指南。

---

## 一、环境要求

### 1.1 系统要求

- **操作系统**：Windows 10/11、Linux（推荐 Ubuntu 20.04+）、macOS
- **Python 版本**：≥ 3.10
- **内存**：≥ 4GB（推荐 8GB+）
- **磁盘空间**：≥ 2GB（用于模型和数据存储）

### 1.2 外部服务

- **NapCatQQ**：QQ 协议端，提供 WebSocket 和 HTTP 接口
- **DeepSeek API**：LLM 服务（或其他 OpenAI 兼容 API）
- **DashScope API**：视觉模型服务（可选）

---

## 二、部署步骤

### 2.1 环境准备

#### 2.1.1 安装 Python

```bash
# Windows
# 从 https://www.python.org/downloads/ 下载并安装 Python 3.10+

# Linux (Ubuntu/Debian)
sudo apt update
sudo apt install python3.10 python3.10-venv python3-pip

# macOS
brew install python@3.10
```

#### 2.1.2 创建虚拟环境

```bash
# 进入项目目录
cd YukiV6

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows
venv\Scripts\activate

# Linux/macOS
source venv/bin/activate
```

### 2.2 安装依赖

```bash
# 使用 pip 安装
pip install -r requirements.txt

# 或使用 uv（推荐）
pip install uv
uv pip install -r requirements.txt
```

### 2.3 配置 NapCatQQ

#### 2.3.1 安装 NapCatQQ

参考 [NapCatQQ 官方文档](https://napneko.github.io/) 安装。

#### 2.3.2 启用正向 WebSocket

1. 打开 NapCatQQ 配置文件
2. 启用正向 WebSocket 服务
3. 设置端口（默认 3001）
4. 重启 NapCatQQ

### 2.4 配置 YukiV6

#### 2.4.1 运行配置向导

```bash
python setup.py
```

配置向导将引导你完成：
- API Key 配置
- 模型选择
- 连接设置
- 目标群组设置

#### 2.4.2 手动配置

如果需要手动配置，编辑 `configs/config.yaml`：

```yaml
# API 配置
api:
  llm_api_key: "your-api-key-here"
  llm_base_url: "https://api.deepseek.com/v1"
  backup_api_key: "your-backup-api-key"
  backup_base_url: "https://api.deepseek.com/v1"

# 模型配置
model:
  llm: "deepseek-chat"
  backup: "deepseek-chat"
  vision: "qwen-vl-plus"

# 连接配置
connection:
  napcat_ws_url: "ws://127.0.0.1:3001"
  napcat_ws_token: ""

# 目标配置
target:
  qq: "your-qq-number"
  groups:
    - 123456789
    - 987654321
```

---

## 三、启动与运行

### 3.1 启动程序

```bash
# 确保虚拟环境已激活
python main.py
```

### 3.2 后台运行

#### Windows

使用 `start.cmd` 或创建计划任务：

```batch
@echo off
cd /d D:\Projects\YukiV6
call venv\Scripts\activate
python main.py
pause
```

#### Linux

使用 systemd 服务：

```ini
# /etc/systemd/system/yuki.service
[Unit]
Description=YukiV6 Bot
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/path/to/YukiV6
ExecStart=/path/to/YukiV6/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable yuki
sudo systemctl start yuki
sudo systemctl status yuki
```

### 3.3 日志查看

```bash
# 实时查看日志
tail -f data/yuki_log.txt

# 查看最近日志
tail -n 100 data/yuki_log.txt
```

---

## 四、配置说明

### 4.1 配置文件位置

- **主配置**：`configs/config.yaml`
- **配置管理**：`config.py`
- **配置向导**：`setup.py`

### 4.2 主要配置项

#### API 配置

```yaml
api:
  llm_api_key: "sk-xxx"  # 首选 LLM API Key
  llm_base_url: "https://api.deepseek.com/v1"  # 首选 API 地址
  backup_api_key: "sk-xxx"  # 备选 API Key
  backup_base_url: "https://api.deepseek.com/v1"  # 备选 API 地址
  image_process_api_key: "sk-xxx"  # 图像处理 API Key
  image_process_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"  # 图像处理 API 地址
```

#### 模型配置

```yaml
model:
  llm: "deepseek-chat"  # 主对话模型
  backup: "deepseek-chat"  # 备用对话模型
  vision: "qwen-vl-plus"  # 视觉模型
  disable_thinking: true  # 是否禁用思考输出
```

#### 连接配置

```yaml
connection:
  napcat_ws_url: "ws://127.0.0.1:3001"  # NapCat WebSocket 地址
  napcat_ws_token: ""  # WebSocket 认证 Token
  max_retries: 3  # 最大重试次数
```

#### 目标配置

```yaml
target:
  qq: "737337230"  # 私聊目标 QQ 号
  groups:  # 目标群聊列表
    - 1057020972
    - 1034986009
```

#### 精力值配置

```yaml
energy:
  initial: 60  # 初始精力值
  max: 100.0  # 最大精力值
  recovery_per_min: 0.8  # 每分钟恢复精力值
  cost_per_reply: 5  # 每次回复消耗精力值
  min_active: 15  # 低活跃阈值
```

#### 注意力配置

```yaml
attention:
  sensitivity: 0.12  # 注意力敏感度
  decay_level: 0.65  # 注意力衰减系数
  sigmoid_centre: 50.0  # Sigmoid 中心点
  sigmoid_alpha: 0.08  # Sigmoid 陡峭度
  keywords:  # 注意力关键词
    - "主人"
    - "哥哥"
```

#### 时间配置

```yaml
timing:
  debounce_time: 18  # 防抖时间（秒）
  tool_call_delay_seconds: 1.2  # 工具调用前等待时间（秒）
  request_timeout:
    total: 60  # 总超时时间（秒）
    connect: 10  # 连接超时时间（秒）
    sock_read: 30  # 读取超时时间（秒）
```

### 4.3 配置热重载

```python
from config import cfg

# 重新加载配置
cfg.reload()

# 保存配置
cfg.save()
```

---

## 五、数据目录

### 5.1 目录结构

```
YukiV6/
├── data/                      # 运行时数据
│   ├── chat_history.json      # 对话历史
│   ├── yuki_log.txt           # 运行日志
│   ├── meme_cache.json        # 表情包缓存
│   └── stickers/              # 本地表情包文件
├── models/                    # 本地嵌入模型
├── yuki_memory/               # ChromaDB 向量数据库
└── skills/                    # 小女仆技能存储
```

### 5.2 数据备份

建议定期备份以下目录：

```bash
# 备份数据
tar -czf yuki_backup_$(date +%Y%m%d).tar.gz data/ yuki_memory/ skills/

# 备份配置
cp configs/config.yaml configs/config.yaml.backup
```

---

## 六、监控与维护

### 6.1 进程监控

```bash
# 查看进程
ps aux | grep python | grep main.py

# 查看端口占用
netstat -tulpn | grep 3001
```

### 6.2 日志分析

```bash
# 查看错误日志
grep -i "error" data/yuki_log.txt

# 查看警告日志
grep -i "warning" data/yuki_log.txt

# 查看工具调用日志
grep "[ToolCall]" data/yuki_log.txt
```

### 6.3 性能监控

```bash
# 查看内存使用
ps -p $(pgrep -f main.py) -o pid,vsz,rss,comm

# 查看 CPU 使用
top -p $(pgrep -f main.py)
```

---

## 七、常见问题

### 7.1 启动失败

**问题**：程序启动后立即退出

**解决方案**：
1. 检查 Python 版本是否 ≥ 3.10
2. 检查依赖是否完整安装：`pip install -r requirements.txt`
3. 检查配置文件是否存在：`configs/config.yaml`
4. 查看日志文件：`data/yuki_log.txt`

### 7.2 连接失败

**问题**：无法连接到 NapCatQQ

**解决方案**：
1. 检查 NapCatQQ 是否运行
2. 检查 WebSocket 地址是否正确
3. 检查防火墙设置
4. 检查 NapCatQQ 日志

### 7.3 API 调用失败

**问题**：LLM API 调用失败

**解决方案**：
1. 检查 API Key 是否正确
2. 检查 API 地址是否可访问
3. 检查网络连接
4. 查看 API 响应日志

### 7.4 内存占用过高

**问题**：程序内存占用持续增长

**解决方案**：
1. 检查对话历史是否过大
2. 清理向量数据库
3. 重启程序
4. 增加系统内存

---

## 八、升级指南

### 8.1 备份数据

```bash
# 备份重要数据
cp -r data/ data_backup/
cp -r yuki_memory/ yuki_memory_backup/
cp -r skills/ skills_backup/
cp configs/config.yaml configs/config.yaml.backup
```

### 8.2 更新代码

```bash
# 拉取最新代码
git pull origin main

# 更新依赖
pip install -r requirements.txt
```

### 8.3 迁移配置

```bash
# 运行配置迁移工具
python config.py sync
```

### 8.4 重启程序

```bash
# 停止旧程序
pkill -f main.py

# 启动新程序
python main.py
```

---

## 九、安全建议

### 9.1 API Key 保护

- 不要将 API Key 提交到 Git
- 使用环境变量或配置文件存储 API Key
- 定期轮换 API Key

### 9.2 网络安全

- 使用 HTTPS/WSS 加密连接
- 限制 WebSocket 访问来源
- 配置防火墙规则

### 9.3 数据安全

- 定期备份重要数据
- 限制文件访问权限
- 加密敏感数据

---

**文档版本**：v1.0  
**最后更新**：2026-06-04  
**维护人员**：项目开发团队
