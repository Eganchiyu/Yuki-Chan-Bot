# tests/ — 测试说明

## 测试环境（本机）

```bash
~/miniconda3/envs/yuki/bin/python -m pytest -q
```

- 解释器固定用这个：`~/miniconda3/envs/yuki/bin/python`（Python 3.11，pytest 9.2.0，pytest-asyncio 1.4.1）
- **不要用** `/usr/bin/python3`（没装 pytest）、也不要试 `maid_venv/bin/python`（缺 `libpython3.11.so.1.0`，起不来）
- 目录、全量套件、单文件、单用例：

```bash
cd /home/asumi/Yuki
~/miniconda3/envs/yuki/bin/python -m pytest -q                  # 全量（当前 195 passed）
~/miniconda3/envs/yuki/bin/python -m pytest tests/test_modes.py -q
~/miniconda3/envs/yuki/bin/python -m pytest tests/test_modes.py::test_rag_relative_boosts_do_not_dominate_semantic_score -q
```

缺依赖时补装到同一个环境：

```bash
~/miniconda3/envs/yuki/bin/python -m pip install pytest pytest-asyncio
```

容器里跑（Docker 镜像已内置 pytest）：

```bash
docker run --rm -v /home/asumi/Yuki:/home/asumi/Yuki:ro -w /home/asumi/Yuki yuki:base python -m pytest -q
```

## 约定

- 套件必须**全离线**：不联网、不需要真实 API Key（见 `pyproject.toml` 的 `[tool.pytest.ini_options]`，`asyncio_mode = "auto"`，`testpaths = ["tests"]`）
- `conftest.py` 已把项目根塞进 `sys.path`，测试文件里不用再写 `sys.path` hack
- 落盘一律用 `tmp_path` 或临时目录，不要在仓库里留产物（容器是只读挂载）
