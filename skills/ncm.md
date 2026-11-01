# ncm：搜索与下载网易云音乐歌曲，返回歌曲 ID 或本地文件绝对路径

## 功能
复用项目内已归档的网易云工具（`core/tools/_archived/tools_ncm.py`），在命令行里搜索歌曲、下载 mp3。
**不要发送文件或消息**，只把路径/结果返回给 Yuki，由 Yuki 自己发。

## 参数
- `ncm_search(keyword, limit=5)` → dict
  - `keyword` (str): 歌名、歌手或"歌名 歌手"
  - `limit` (int, optional): 返回条数，默认 5，最多 5
- `ncm_download(song_id, quality="320000", filename=None)` → dict
  - `song_id` (int): 来自 `ncm_search` 结果里的 id
  - `quality` (str, optional): 码率，"320000"（默认）或 "128000"
  - `filename` (str, optional): 保存文件名，可省略（默认用"歌名 - 歌手.mp3"）

## 返回
dict，字段固定为 `success` / `content` / `error` / `data`：
- 成功搜索：`data.songs` 是 `[{id, name, artists, album, duration}, ...]`
- 成功下载：`data.file_path`、`data.file_size`、`data.song_id`，`content` 里也有人话总结
- 失败：`success=False`，看 `error` 与 `content`

## 命令行用法（推荐：用 `terminal` 工具，interpreter 走项目环境）
```bash
python skills/ncm.py search "晴天 周杰伦" 3
python skills/ncm.py download 186016 320000
```
输出为 JSON，直接读 `songs` / `file_path` 字段。

## 扫码登录（重要）
本机**没有登录 Cookie**时，第一次调用会失败并返回：
```json
{"success": false, "error": "ncm_cookie_expired", "data": {"qr_image_path": ".../output/ncm/ncm_qr_login.png", "login_required": true}}
```
处理流程：
1. 把 `data.qr_image_path` 原样返回给 Yuki，说明"需要机主用网易云 App 扫码"。
2. Yuki 会把这张图发给机主。**扫码前不要反复重试**，重试只会推进轮询。
3. 机主扫码确认后，再次执行同一条命令即可；Cookie 会自动保存到 `~/.cache/ncm_cookie.txt`，之后长期有效。
4. 若 `error` 是 `ncm_login_pending`，同上：二维码已生成，等扫码后再重试。

## 依赖
- 项目自带（aiohttp、qrcode、Pillow），用项目的 python 执行，不需要 `install_package`。
- 必须能访问 music.163.com（走本机代理/直连均可）。

## 备注
- VIP/版权受限歌曲下载会失败，换 `quality="128000"` 或换一首歌。
- 下载默认落到 `./output/ncm/`，返回的是绝对路径，可直接交给 Yuki 用 `send_qq_file` 发送。
- 单次搜索/下载超时约 20-60 秒，`terminal` 的 timeout 建议给 120。
