# 根目录文件说明

本文档说明项目根目录中的主要文件用途，方便维护和协作。

## 文件说明

### `.gitignore`
用于忽略 Python 虚拟环境、缓存、构建产物等本地生成文件。

### `.python-version`
记录项目使用的 Python 版本，当前为 `3.13`。

### `README.md`
项目总说明文档，包含项目定位、启动方式、通信接口和模型可用性说明。

### `main.py`
项目启动入口，只负责调用 `server.main()`。

### `server.py`
Python 后端服务主文件，负责：
- 启动 aiohttp 服务
- 托管前端静态文件
- 托管 Live2D 模型资源
- 处理 WebSocket 连接
- 提供 `/api/model`、`/api/say`、`/api/audio` 接口

### `pyproject.toml`
Python 项目配置文件，定义项目元数据、依赖和脚本入口。

### `uv.lock`
`uv` 的锁定文件，记录依赖解析结果，保证环境一致性。

### `liveyuki_l2d/`
后端辅助模块目录，目前主要放 WebSocket 协议相关工具。

### `models/`
Live2D 模型资源目录，当前包含 `Yuki` 模型文件。

### `frontend/`
前端资源目录。

- `frontend/minimal/`：最小 Vite + TypeScript 前端工程
- `frontend/vendor/`：外部参考或拷贝的第三方代码

### `.venv/`
本地 Python 虚拟环境目录，通常不纳入版本控制。

## 根目录文件关系

- `main.py` 是启动入口。
- `server.py` 是实际运行逻辑。
- `README.md` 给出使用方式。
- `pyproject.toml` 和 `uv.lock` 管理 Python 依赖。
- `models/` 和 `frontend/` 共同支撑本地 Live2D 展示。

## 维护建议

- 新增根目录文件时，及时补充本说明。
- 如果修改启动方式、端口或依赖版本，也同步更新 `README.md` 与本文件。