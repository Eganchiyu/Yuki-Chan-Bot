# 外部检索工具（高德地图 & Tavily 网页搜索）归档

## 1. 这段代码是干什么的
`tools_search.py`（原 `core/tools/tools_search.py` / `core/tools/_archived/tools_search.py`）提供主模型直接调用的两个外部信息检索工具：
- `amap_search_tool(context, keywords, search_type="text", location=None, address=None, city=None, radius=3000, page_size=10)`：调用高德地图 Web 服务 API，支持关键词搜索（`text`）、周边搜索（`around`）和地理编码/地名转坐标（`geocode`）。
- `browser_search_tool(context, query, max_results=5, search_depth="basic")`：调用 Tavily Search API 进行实时网页检索，返回摘要答案与网页列表；未配置 Key 时回退返回 Bing 搜索链接。

（注：同类能力已下沉给后台小女仆执行，主模型不再直接挂载以精简每轮对话的 Tool Schema 开销。）

## 2. 原来的埋点在哪里
- **工具实现路径**：`core/tools/tools_search.py`（后移入 `core/tools/_archived/tools_search.py`）
- **工具注册埋点**：`core/tools/tools.py` 的 `TOOL_SPECS` 列表及 `core/tools/__init__.py`。
- **配置项依赖**：`config.py` / `configs/config.yaml` 中的 `cfg.AMAP_API_KEY`（`search.amap_api_key`）与 `cfg.TAVILY_API_KEY`（`search.tavily_api_key`）。

## 3. 怎样接入
1. 将文件复制回 `core/tools/tools_search.py`：
   ```bash
   cp _archive/search_tools/tools_search.py core/tools/tools_search.py
   ```
2. 在 `core/tools/tools.py` 中导入并加入 `TOOL_SPECS`：
   ```python
   from .tools_search import amap_search_tool, browser_search_tool

   # 在 TOOL_SPECS 中追加：
   ToolSpec(
       name="browser_search",
       description="使用搜索引擎检索实时网页信息、新闻、百科或技术资料。",
       parameters={
           "type": "object",
           "properties": {
               "query": {"type": "string", "description": "搜索关键词或问题"},
               "max_results": {"type": "integer", "description": "返回结果数量，1-10，默认 5", "default": 5},
               "search_depth": {"type": "string", "enum": ["basic", "advanced"], "default": "basic"},
           },
           "required": ["query"],
       },
       handler=browser_search_tool,
   ),
   ToolSpec(
       name="amap_search",
       description="高德地图搜索：关键词查地点(text)、坐标查周边(around)、地名转坐标(geocode)。",
       parameters={
           "type": "object",
           "properties": {
               "keywords": {"type": "string", "description": "搜索关键词（如餐厅、电影院）"},
               "search_type": {"type": "string", "enum": ["text", "around", "geocode"], "default": "text"},
               "location": {"type": "string", "description": "中心点坐标（经度,纬度），around 模式必填"},
               "address": {"type": "string", "description": "地址名称，geocode 模式必填"},
               "city": {"type": "string", "description": "限定城市名称（可选）"},
               "radius": {"type": "integer", "description": "搜索半径（米），默认 3000", "default": 3000},
               "page_size": {"type": "integer", "description": "返回数量，1-25，默认 10", "default": 10},
           },
       },
       handler=amap_search_tool,
   ),
   ```
