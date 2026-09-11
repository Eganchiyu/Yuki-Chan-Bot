# YukiV6 故障排查指南

本指南提供 YukiV6 常见错误及解决方案。

---

## 一、启动问题

### 1.1 程序启动后立即退出

**症状**：运行 `python main.py` 后程序立即退出，无错误信息。

**可能原因**：
1. Python 版本过低
2. 依赖未完整安装
3. 配置文件缺失
4. 模块导入错误

**排查步骤**：

```bash
# 1. 检查 Python 版本
python --version
# 确保版本 ≥ 3.10

# 2. 检查依赖安装
pip list | grep -E "aiohttp|websockets|openai|chromadb"
# 确保所有依赖已安装

# 3. 检查配置文件
ls configs/config.yaml
# 确保配置文件存在

# 4. 查看详细错误信息
python main.py 2>&1 | tee startup_error.log
```

**解决方案**：

```bash
# 升级 Python
# 从 https://www.python.org/downloads/ 下载最新版本

# 重新安装依赖
pip install -r requirements.txt

# 运行配置向导
python setup.py

# 检查模块导入
python -c "import config; import core.engine; import utils.llm_client"
```

### 1.2 模块导入错误

**症状**：`ModuleNotFoundError: No module named 'xxx'`

**可能原因**：
1. 虚拟环境未激活
2. 依赖未安装
3. Python 路径问题

**排查步骤**：

```bash
# 1. 检查虚拟环境
# Windows
where python
# 应指向 venv\Scripts\python.exe

# Linux/macOS
which python
# 应指向 venv/bin/python

# 2. 检查依赖
pip list | grep <module-name>
```

**解决方案**：

```bash
# 激活虚拟环境
# Windows
venv\Scripts\activate

# Linux/macOS
source venv/bin/activate

# 安装缺失依赖
pip install <module-name>

# 或重新安装所有依赖
pip install -r requirements.txt
```

---

## 二、连接问题

### 2.1 无法连接到 NapCatQQ

**症状**：日志显示 `WebSocket connection failed` 或 `Connection refused`

**可能原因**：
1. NapCatQQ 未运行
2. WebSocket 地址错误
3. 端口被占用
4. 防火墙阻止

**排查步骤**：

```bash
# 1. 检查 NapCatQQ 是否运行
# Windows
tasklist | findstr napcat

# Linux
ps aux | grep napcat

# 2. 检查端口是否监听
netstat -tulpn | grep 3001

# 3. 测试连接
# Windows
Test-NetConnection -ComputerName 127.0.0.1 -Port 3001

# Linux
telnet 127.0.0.1 3001
```

**解决方案**：

1. 启动 NapCatQQ
2. 检查配置文件中的 WebSocket 地址：
   ```yaml
   connection:
     napcat_ws_url: "ws://127.0.0.1:3001"
   ```
3. 确保端口 3001 未被占用
4. 检查防火墙设置

### 2.2 同一个 NapCat 上挂了两个 Yuki 实例

**症状**：群里偶发重复回复；`ss -tnp | grep 3001` 看到多条来自 `python` 的连接；
Context Debug WebUI（8777）连不上。

**原因**：两个 `python main.py` 都在消费同一条 NapCat 事件流，各自跑一遍管线。

**排查**：

```bash
# 看有几条连到 3001 的客户端连接，以及是谁
ss -tnp | grep 3001

# 看有几个 main.py
ps -eo pid,stat,etime,cmd | grep "main.py" | grep -v grep
```

注意被 SIGSTOP 挂起（`STAT` 为 `T`）的进程仍会占着 WebSocket 与端口，需要显式 kill。

**解决方案**：

1. 只保留一个实例：`kill <多余的 pid>`
2. 启动时会自动检查 `data/yuki.lock`（flock，随进程退出释放），已有实例在跑
   会直接中止并提示，不会再出现静默双开
3. 确实需要并行跑第二个实例（例如调试）时设置 `YUKI_ALLOW_MULTI_INSTANCE=1`

### 2.3 WebSocket 连接断开

**症状**：日志显示 `WebSocket disconnected` 或 `Connection lost`

**可能原因**：
1. 网络不稳定
2. NapCatQQ 重启
3. 心跳超时

**排查步骤**：

```bash
# 查看连接日志
grep -i "websocket" data/yuki_log.txt | tail -20

# 检查网络连接
ping 127.0.0.1
```

**解决方案**：

1. 程序会自动重连，等待即可
2. 检查网络稳定性
3. 检查 NapCatQQ 状态

---

## 三、API 调用问题

### 3.1 LLM API 调用失败

**症状**：日志显示 `API request failed` 或 `LLM chat failed`

**可能原因**：
1. API Key 错误
2. API 地址不可访问
3. 网络问题
4. API 配额用尽

**排查步骤**：

```bash
# 1. 检查 API Key
grep "llm_api_key" configs/config.yaml

# 2. 测试 API 连接
curl -X POST "https://api.deepseek.com/v1/chat/completions" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"test"}]}'

# 3. 查看 API 日志
grep -i "api" data/yuki_log.txt | tail -20
```

**解决方案**：

1. 检查 API Key 是否正确
2. 检查 API 地址是否可访问
3. 检查网络连接
4. 检查 API 配额

### 3.2 API 响应超时

**症状**：日志显示 `Request timeout` 或 `TimeoutError`

**可能原因**：
1. 网络延迟高
2. API 响应慢
3. 超时配置过短

**排查步骤**：

```bash
# 测试网络延迟
ping api.deepseek.com

# 检查超时配置
grep -A 5 "request_timeout" configs/config.yaml
```

**解决方案**：

1. 增加超时配置：
   ```yaml
   timing:
     request_timeout:
       total: 120  # 增加总超时时间
       connect: 20  # 增加连接超时时间
       sock_read: 60  # 增加读取超时时间
   ```
2. 检查网络连接
3. 联系 API 提供商

### 3.3 工具调用失败

**症状**：日志显示 `[ToolCall] xxx 执行失败`

**可能原因**：
1. 工具参数错误
2. 工具函数异常
3. 权限问题

**排查步骤**：

```bash
# 查看工具调用日志
grep "[ToolCall]" data/yuki_log.txt | tail -20

# 查看具体错误
grep -A 5 "执行失败" data/yuki_log.txt
```

**解决方案**：

1. 检查工具参数是否正确
2. 检查工具函数实现
3. 检查文件权限
4. 查看详细错误日志

---

## 四、内存与性能问题

### 4.1 内存占用过高

**症状**：程序内存占用持续增长，系统变慢。

**可能原因**：
1. 对话历史过大
2. 向量数据库膨胀
3. 内存泄漏

**排查步骤**：

```bash
# 查看内存使用
ps -p $(pgrep -f main.py) -o pid,vsz,rss,comm

# 检查对话历史大小
ls -lh data/chat_history.json

# 检查向量数据库大小
du -sh yuki_memory/
```

**解决方案**：

```bash
# 1. 清理对话历史
# 手动编辑 data/chat_history.json，删除旧对话

# 2. 清理向量数据库
rm -rf yuki_memory/
# 程序会自动重建

# 3. 重启程序
pkill -f main.py
python main.py
```

### 4.2 CPU 占用过高

**症状**：程序 CPU 占用持续较高。

**可能原因**：
1. 频繁的 API 调用
2. 向量检索频繁
3. 死循环

**排查步骤**：

```bash
# 查看 CPU 使用
top -p $(pgrep -f main.py)

# 查看进程状态
ps -p $(pgrep -f main.py) -o pid,stat,comm

# 查看日志频率
wc -l data/yuki_log.txt
tail -f data/yuki_log.txt
```

**解决方案**：

1. 检查是否有死循环
2. 减少 API 调用频率
3. 优化向量检索
4. 重启程序

---

## 五、数据问题

### 5.1 对话历史丢失

**症状**：程序重启后对话历史丢失。

**可能原因**：
1. 文件写入失败
2. 文件路径错误
3. 权限问题

**排查步骤**：

```bash
# 检查文件是否存在
ls -lh data/chat_history.json

# 检查文件权限
ls -l data/

# 检查磁盘空间
df -h
```

**解决方案**：

1. 检查文件路径配置：
   ```yaml
   paths:
     history_file: "./data/chat_history.json"
   ```
2. 确保目录存在且有写入权限
3. 检查磁盘空间

### 5.2 记忆检索失败

**症状**：RAG 记忆检索返回空结果。

**可能原因**：
1. 向量数据库未初始化
2. 嵌入模型未加载
3. 数据库损坏

**排查步骤**：

```bash
# 检查向量数据库目录
ls -lh yuki_memory/

# 检查嵌入模型目录
ls -lh models/text2vec-base-chinese/

# 查看 RAG 日志
grep -i "rag\|memory" data/yuki_log.txt | tail -20
```

**解决方案**：

```bash
# 1. 重新下载嵌入模型
python utils/download_model.py

# 2. 重建向量数据库
rm -rf yuki_memory/
python main.py  # 程序会自动重建

# 3. 检查配置
grep -A 5 "rag" configs/config.yaml
```

---

## 六、小女仆问题

### 6.1 小女仆任务不执行

**症状**：小女仆任务提交后无响应。

**可能原因**：
1. 任务队列满
2. 小女仆进程异常
3. 权限问题

**排查步骤**：

```bash
# 查看小女仆日志
grep -i "maid" data/yuki_log.txt | tail -20

# 查看任务队列状态
grep "task_queue" data/yuki_log.txt
```

**解决方案**：

1. 检查任务队列状态
2. 重启程序
3. 查看详细错误日志

### 6.2 小女仆技能执行失败

**症状**：小女仆技能执行报错。

**可能原因**：
1. 技能脚本错误
2. 依赖缺失
3. 权限问题

**排查步骤**：

```bash
# 查看技能日志
grep -i "skill" data/yuki_log.txt | tail -20

# 检查技能目录
ls -lh skills/
```

**解决方案**：

1. 检查技能脚本
2. 安装缺失依赖
3. 检查文件权限

---

## 七、配置问题

### 7.1 配置不生效

**症状**：修改配置后程序行为未改变。

**可能原因**：
1. 配置文件路径错误
2. 配置未重新加载
3. 配置格式错误

**排查步骤**：

```bash
# 检查配置文件路径
grep "config.yaml" config.py

# 检查配置文件内容
cat configs/config.yaml

# 检查配置加载日志
grep -i "config" data/yuki_log.txt | tail -20
```

**解决方案**：

1. 确认配置文件路径正确
2. 重新加载配置：
   ```python
   from config import cfg
   cfg.reload()
   ```
3. 检查配置格式

### 7.2 配置同步失败

**症状**：运行 `python config.py sync` 失败。

**可能原因**：
1. 配置文件损坏
2. 权限问题
3. 格式错误

**排查步骤**：

```bash
# 检查配置文件
python -c "import yaml; yaml.safe_load(open('configs/config.yaml'))"

# 检查文件权限
ls -l configs/
```

**解决方案**：

1. 恢复备份配置：
   ```bash
   cp configs/config.yaml.backup configs/config.yaml
   ```
2. 运行配置向导：
   ```bash
   python setup.py
   ```

---

## 八、获取帮助

### 8.1 查看日志

```bash
# 查看最新日志
tail -f data/yuki_log.txt

# 查看错误日志
grep -i "error" data/yuki_log.txt

# 查看警告日志
grep -i "warning" data/yuki_log.txt
```

### 8.2 收集诊断信息

```bash
# 收集系统信息
python --version
pip list
uname -a  # Linux/macOS
systeminfo  # Windows

# 收集项目信息
git log --oneline -5
cat configs/config.yaml | grep -v "api_key\|secret\|password"
```

### 8.3 报告问题

报告问题时请提供：
1. 错误现象描述
2. 复现步骤
3. 相关日志
4. 系统环境信息
5. 配置文件（隐藏敏感信息）

---

**文档版本**：v1.0  
**最后更新**：2026-06-04  
**维护人员**：项目开发团队
