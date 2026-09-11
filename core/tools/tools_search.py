# core/tools/tools_search.py
"""外部信息检索工具：高德地图与 Tavily 网页搜索。"""
import os
from urllib.parse import quote_plus

import aiohttp

from core.toolchain import ToolResult
from utils.http_client import create_tcp_connector

_TAVILY_SEARCH_URL = "https://api.tavily.com/search"
_AMAP_AROUND_URL = "https://restapi.amap.com/v5/place/around"
_AMAP_TEXT_URL = "https://restapi.amap.com/v5/place/text"
_AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"


async def amap_search_tool(context, keywords, search_type="text", location=None, address=None, city=None, radius=3000, page_size=10):
    """高德地图统一搜索：text=关键词搜索, around=周边搜索(需坐标), geocode=地名转坐标。"""
    api_key = os.getenv("AMAP_API_KEY")
    if not api_key:
        return ToolResult(success=False, content="未配置 AMAP_API_KEY，无法调用高德地图服务。", error="missing_amap_api_key")

    timeout = aiohttp.ClientTimeout(total=15)

    if search_type == "geocode":
        if not address:
            return ToolResult(success=False, content="缺少地址信息", error="missing_address")
        params = {"key": api_key, "address": address}
        if city:
            params["city"] = city
        async with aiohttp.ClientSession(connector=create_tcp_connector(), timeout=timeout) as session:
            async with session.get(_AMAP_GEOCODE_URL, params=params) as response:
                data = await response.json(content_type=None)
        if data.get("status") != "1":
            return ToolResult(success=False, content=f"高德地图返回错误：{data.get('info', '未知错误')}", data=data, error=data.get("infocode", "amap_error"))
        geocodes = data.get("geocodes") or []
        if not geocodes:
            return ToolResult(success=False, content="未找到该地址的坐标信息。", error="no_geocode_result")
        results = [{"name": g.get("formatted_address"), "location": g.get("location"), "city": g.get("city"), "district": g.get("district")} for g in geocodes[:5]]
        return ToolResult(success=True, content=f"已定位到 {len(results)} 个地址", data={"results": results})

    if not keywords:
        return ToolResult(success=False, content="缺少搜索关键词", error="missing_keywords")

    if search_type == "around":
        if not location:
            return ToolResult(success=False, content="周边搜索需要中心点坐标（经度,纬度）", error="missing_location")
        params = {
            "key": api_key, "keywords": keywords, "location": location,
            "radius": max(100, min(int(radius), 50000)),
            "page_size": max(1, min(int(page_size), 25)),
            "page_num": 1, "show_fields": "business",
        }
        url = _AMAP_AROUND_URL
    else:
        params = {
            "key": api_key, "keywords": keywords,
            "page_size": max(1, min(int(page_size), 25)),
            "page_num": 1, "show_fields": "business",
        }
        if city:
            params["region"] = city
        url = _AMAP_TEXT_URL

    async with aiohttp.ClientSession(connector=create_tcp_connector(), timeout=timeout) as session:
        async with session.get(url, params=params) as response:
            data = await response.json(content_type=None)
            if response.status >= 400:
                return ToolResult(success=False, content="高德地图请求失败。", data=data, error=f"http_{response.status}")

    if data.get("status") != "1":
        return ToolResult(success=False, content=f"高德地图返回错误：{data.get('info', '未知错误')}", data=data, error=data.get("infocode", "amap_error"))

    pois = []
    for poi in (data.get("pois") or []):
        biz = poi.get("business") or {}
        pois.append({
            "name": poi.get("name"), "address": poi.get("address"),
            "location": poi.get("location"), "type": poi.get("type"),
            "distance": poi.get("distance"), "city": poi.get("cityname"),
            "tel": biz.get("tel"), "rating": biz.get("rating"), "cost": biz.get("cost"),
        })
    count = data.get("count", len(pois))
    summary = f"共找到 {count} 个地点" if count else "未找到相关地点"
    return ToolResult(success=True, content=summary, data={"count": count, "pois": pois})


async def browser_search_tool(context, query, max_results=5, search_depth="basic"):
    """调用 Tavily 搜索服务，返回可供 LLM 总结的网页结果。"""
    if not query:
        return ToolResult(success=False, content="缺少搜索关键词", error="missing_query")

    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        url = f"https://www.bing.com/search?q={quote_plus(query)}"
        return ToolResult(
            success=False,
            content="未配置 TAVILY_API_KEY，暂时只能返回浏览器搜索地址。",
            data={"url": url},
            error="missing_tavily_api_key",
        )

    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": search_depth,
        "max_results": max(1, min(int(max_results), 10)),
        "include_answer": True,
    }
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(connector=create_tcp_connector(), timeout=timeout) as session:
        async with session.post(_TAVILY_SEARCH_URL, json=payload) as response:
            data = await response.json(content_type=None)
            if response.status >= 400:
                return ToolResult(
                    success=False,
                    content="Tavily 搜索请求失败。",
                    data=data,
                    error=f"http_{response.status}",
                )

    results = []
    for item in data.get("results", []):
        results.append({
            "title": item.get("title"),
            "url": item.get("url"),
            "content": item.get("content"),
            "score": item.get("score"),
        })
    return ToolResult(
        success=True,
        content=data.get("answer") or f"已搜索到 {len(results)} 条结果。",
        data={"query": query, "answer": data.get("answer"), "results": results},
    )
