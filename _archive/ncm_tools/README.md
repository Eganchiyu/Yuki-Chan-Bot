# 网易云音乐（NCM）工具与扫码登录归档

## 1. 这段代码是干什么的
提供网易云音乐歌曲搜索、音频直链获取与降级下载，以及无第三方加密库依赖（基于系统 `openssl`）的 eapi 二维码扫码登录与 Cookie 持久化能力：
- `ncm_login.py`（原 `core/ncm_login.py`）：生成扫码登录 `unikey` 与二维码 PNG 图片（`generate_qr`）、轮询扫码状态并提取完整 `MUSIC_U` Cookie（`poll_login`）、跨调用持久化待扫码状态（`save_pending` / `load_pending` / `clear_pending`）及保存 Cookie 到 `cfg.paths.ncm_cookie_file`（`save_cookie`）。
- `tools_ncm.py`（原 `core/tools/_archived/tools_ncm.py`）：
  - `ncm_search_tool(context, keyword, limit=5)`：按关键词搜索歌曲，返回歌曲名、歌手、专辑、时长与歌曲 `id`。
  - `ncm_download_tool(context, song_id, quality="320000", filename=None)`：获取播放直链并支持去 `authSecret`/去查询串三级 CDN 降级下载到本地 `output/ncm/`。
  - `_ncm_ensure_login(context, action_desc)`：当 Cookie 缺失或失效时自动生成登录二维码并返回图片路径，提示模型调用 `send_qq_file` 发送二维码给用户扫码。

## 2. 原来的埋点在哪里
- **登录模块路径**：`core/ncm_login.py`
- **工具实现路径**：`core/tools/tools_ncm.py`（后移入 `core/tools/_archived/tools_ncm.py`）
- **工具注册埋点**：`core/tools/tools.py` 的 `TOOL_SPECS` 列表，以及 `core/tools/__init__.py` 的公开导出。
- **配置项埋点**：`config.py` / `configs/config.yaml` 中的 `cfg.paths.ncm_cookie_file`（默认 `~/.cache/ncm_cookie.txt`）与 `cfg.paths.ncm_download_dir`（默认 `./output/ncm`）。
- **关联归档文件**：小女仆侧的同步封装与扫码守护脚本见 `_archive/skills/ncm.py`、`_archive/skills/ncm.md` 与 `_archive/scripts/ncm_login/`。

## 3. 怎样接入
### 方式 A：重新挂载为主模型 Function Call 工具
1. 将文件移回原位置：
   ```bash
   cp _archive/ncm_tools/ncm_login.py core/ncm_login.py
   cp _archive/ncm_tools/tools_ncm.py core/tools/tools_ncm.py
   ```
2. 在 `core/tools/tools.py` 中导入并加入 `TOOL_SPECS`：
   ```python
   from .tools_ncm import ncm_download_tool, ncm_search_tool

   # 在 TOOL_SPECS 中追加：
   ToolSpec(
       name="ncm_search",
       description="搜索网易云音乐歌曲，返回歌曲列表（含 song_id、歌手、专辑、时长）。",
       parameters={
           "type": "object",
           "properties": {
               "keyword": {"type": "string", "description": "搜索关键词（歌名/歌手）"},
               "limit": {"type": "integer", "description": "返回条数，1-5，默认 5", "default": 5},
           },
           "required": ["keyword"],
       },
       handler=ncm_search_tool,
   ),
   ToolSpec(
       name="ncm_download",
       description="按 song_id 下载网易云音乐歌曲到本地 MP3，下载后可用 send_qq_file 发送。",
       parameters={
           "type": "object",
           "properties": {
               "song_id": {"type": "integer", "description": "网易云歌曲 ID"},
               "quality": {"type": "string", "description": "码率，默认 320000", "default": "320000"},
               "filename": {"type": "string", "description": "自定义保存文件名（可选）"},
           },
           "required": ["song_id"],
       },
       handler=ncm_download_tool,
   ),
   ```

### 方式 B：作为小女仆 Skill 接入
1. 将 `_archive/ncm_tools/ncm_login.py` 放回 `core/ncm_login.py`，`tools_ncm.py` 放回 `core/tools/tools_ncm.py`（或直接被 skill 引用）。
2. 将 `_archive/skills/ncm.py` 与 `_archive/skills/ncm.md` 复制回 `skills/`（详见 `_archive/README.md` 中 NCM 章节）。
