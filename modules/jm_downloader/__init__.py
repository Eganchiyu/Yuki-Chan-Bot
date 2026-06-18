"""JM 下载器模块 — 可独立于 AstrBot 运行

模块:
  - cache       缓存路径管理 + 清理
  - converter   webp→jpg / PDF / ZIP
  - downloader  jmcomic 下载封装
  - handler     YukiV6 适配层（消息拦截+文件发送）
"""
from .cache import init_cache, get_jm_cache_path, clear_all_cache, ensure_cache_limits
from .converter import webp_to_jpg_bytes, convert_to_jpg, images_to_pdf, images_to_zip
from .downloader import fetch_album_info, download_chapter, download_album
from .handler import handle_jm_command
from .obfuscator import obfuscate_file, deobfuscate_file
