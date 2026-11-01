"""网易云音乐技能：搜索 / 下载（复用 core/tools/_archived/tools_ncm 的现成实现）。

只用项目自带依赖，把 async 工具函数包装成同步调用，供小女仆通过
`run_skill` / `terminal` 使用。返回 dict，字段固定 success/content/error/data。
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.tools._archived.tools_ncm import ncm_download_tool, ncm_search_tool


def _to_dict(res) -> dict:
    return {
        "success": bool(res.success),
        "content": res.content,
        "error": res.error or "",
        "data": res.data or {},
    }


def ncm_search(keyword: str, limit: int = 5) -> dict:
    """搜索网易云音乐歌曲，返回 {success, content, error, data:{songs:[...]}}。"""
    if not keyword or not str(keyword).strip():
        return {"success": False, "content": "关键词为空", "error": "bad_keyword", "data": {}}
    try:
        limit = max(1, min(5, int(limit)))
    except (TypeError, ValueError):
        limit = 5
    res = asyncio.run(ncm_search_tool(None, str(keyword).strip(), limit=limit))
    return _to_dict(res)


def ncm_download(song_id, quality: str = "320000", filename: str | None = None) -> dict:
    """下载歌曲到 output/ncm/，返回 {success, content, error, data:{file_path,...}}。"""
    try:
        song_id = int(song_id)
    except (TypeError, ValueError):
        return {"success": False, "content": f"song_id 非法: {song_id}", "error": "bad_song_id", "data": {}}
    res = asyncio.run(ncm_download_tool(None, song_id, quality=str(quality), filename=filename))
    return _to_dict(res)


def _main(argv: list[str]) -> int:
    if not argv:
        print(json.dumps({
            "usage": [
                "python skills/ncm.py search <关键词> [数量]",
                "python skills/ncm.py download <song_id> [码率] [文件名]",
            ]
        }, ensure_ascii=False, indent=2))
        return 2

    action = argv[0].lower()
    if action == "search":
        if len(argv) < 2:
            print(json.dumps({"success": False, "content": "缺少关键词"}, ensure_ascii=False))
            return 2
        limit = argv[2] if len(argv) > 2 else 5
        result = ncm_search(argv[1], limit)
    elif action == "download":
        if len(argv) < 2:
            print(json.dumps({"success": False, "content": "缺少 song_id"}, ensure_ascii=False))
            return 2
        quality = argv[2] if len(argv) > 2 else "320000"
        filename = argv[3] if len(argv) > 3 else None
        result = ncm_download(argv[1], quality, filename)
    else:
        print(json.dumps({"success": False, "content": f"未知操作: {action}"}, ensure_ascii=False))
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") or result.get("error") in ("ncm_cookie_expired", "ncm_login_pending") else 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
