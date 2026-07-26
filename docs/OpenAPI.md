---
title: OpenAPI
language_tabs:
  - shell: Shell
  - http: HTTP
  - javascript: JavaScript
  - ruby: Ruby
  - python: Python
  - php: PHP
  - java: Java
  - go: Go
toc_footers: []
includes: []
search: true
code_clipboard: true
highlight_theme: darkula
headingLevel: 2
generator: "@tarslib/widdershins v4.0.30"

---

# OpenAPI

本文档描述 NapCat OneBot 11 的 HTTP POST 接口协议。所有接口均通过 POST 请求调用，请求体为 JSON 格式。

Base URLs:

# Authentication

# 流式传输扩展

## POST 清理流式传输临时文件

POST /clean_stream_temp_file

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "message": "success"
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 下载语音文件流

POST /download_file_record_stream

> Body 请求参数

```json
{
    "file": "record_file_id"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» file|body|string| 否 |文件路径或 URL|
|» file_id|body|string| 否 |文件 ID|
|» chunk_size|body|number| 否 |分块大小 (字节)|
|» out_format|body|string| 否 |输出格式|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "file": "temp_record_path"
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 下载图片文件流

POST /download_file_image_stream

> Body 请求参数

```json
{
    "file": "image_file_id"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» file|body|string| 否 |文件路径或 URL|
|» file_id|body|string| 否 |文件 ID|
|» chunk_size|body|number| 否 |分块大小 (字节)|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "file": "temp_image_path"
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 测试下载流

POST /test_download_stream

> Body 请求参数

```json
{
    "url": "http://example.com/file"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» error|body|boolean| 否 |是否触发测试错误|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "success": true
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

# 流式接口

## POST 下载文件流

POST /download_file_stream

以流式方式从网络或本地下载文件

> Body 请求参数

```json
{
    "file": "http://example.com/file.png"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» file|body|string| 否 |文件路径或 URL|
|» file_id|body|string| 否 |文件 ID|
|» chunk_size|body|number| 否 |分块大小 (字节)|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "type": "stream",
        "data_type": "file_info",
        "file_name": "file.png",
        "file_size": 1024
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 上传文件流

POST /upload_file_stream

以流式方式上传文件数据到机器人

> Body 请求参数

```json
{
    "stream_id": "uuid-1234-5678",
    "chunk_data": "SGVsbG8gV29ybGQ=",
    "chunk_index": 0,
    "total_chunks": 1,
    "file_size": 11
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» stream_id|body|string| 是 |流 ID|
|» chunk_data|body|string| 否 |分块数据 (Base64)|
|» chunk_index|body|number| 否 |分块索引|
|» total_chunks|body|number| 否 |总分块数|
|» file_size|body|number| 否 |文件总大小|
|» expected_sha256|body|string| 否 |期望的 SHA256|
|» is_complete|body|boolean| 否 |是否完成|
|» filename|body|string| 否 |文件名|
|» reset|body|boolean| 否 |是否重置|
|» verify_only|body|boolean| 否 |是否仅验证|
|» file_retention|body|number| 是 |文件保留时间 (毫秒)|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "type": "stream",
        "stream_id": "uuid-1234-5678",
        "status": "chunk_received",
        "received_chunks": 1,
        "total_chunks": 1
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

# 群组扩展

## POST 删除群相册媒体

POST /del_group_album_media

> Body 请求参数

```json
{
    "group_id": "123456",
    "album_id": "album_id_1",
    "lloc": "media_id_1"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» album_id|body|string| 是 |相册ID|
|» lloc|body|string| 是 |媒体ID (lloc)|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "result": {}
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 点赞群相册媒体

POST /set_group_album_media_like

> Body 请求参数

```json
{
    "group_id": "123456",
    "album_id": "album_id_123",
    "batch_id": "112233",
    "lloc": "aabbcc12213123"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» album_id|body|string| 是 |相册ID|
|» batch_id|body|string| 是 |batch_id|
|» lloc|body|string| 否 |lloc，若对整个上传操作则不填|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "result": {}
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 取消点赞群相册媒体

POST /cancel_group_album_media_like

> Body 请求参数

```json
{
    "group_id": "123456",
    "album_id": "album_id",
    "batch_id": "112233",
    "lloc": "aabbcc"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» album_id|body|string| 是 |相册ID|
|» batch_id|body|string| 是 |batch_id|
|» lloc|body|string| 否 |lloc，若对整个上传操作则不填|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "result": {}
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 发表群相册评论

POST /do_group_album_comment

> Body 请求参数

```json
{
    "group_id": "123456",
    "album_id": "album_id_1",
    "lloc": "media_id_1",
    "content": "很有意思"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» album_id|body|string| 是 |相册 ID|
|» lloc|body|string| 是 |图片 ID|
|» content|body|string| 是 |评论内容|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "result": {}
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取群相册媒体列表

POST /get_group_album_media_list

> Body 请求参数

```json
{
    "group_id": "123456",
    "album_id": "album_id_1"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» album_id|body|string| 是 |相册ID|
|» attach_info|body|string| 否 |附加信息（用于分页）|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "media_list": [
            {
                "media_id": "media_id_1",
                "url": "http://example.com/1.jpg"
            }
        ]
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取群相册列表

POST /get_qun_album_list

> Body 请求参数

```json
{
    "group_id": "123456",
    "attach_info": ""
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» attach_info|body|string| 否 |附加信息（用于分页，从上一次返回结果中获取）|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "album_list": [
            {
                "album_id": "album_1",
                "album_name": "测试相册",
                "cover_url": "http://example.com/cover.jpg",
                "create_time": 1734567890
            }
        ],
        "attach_info": "",
        "has_more": false
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 上传图片到群相册

POST /upload_image_to_qun_album

> Body 请求参数

```json
{
    "group_id": "123456",
    "album_id": "album_id_1",
    "album_name": "相册1",
    "file": "/path/to/image.jpg"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» album_id|body|string| 是 |相册ID|
|» album_name|body|string| 是 |相册名称|
|» file|body|string| 是 |图片路径、URL或Base64|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "result": null
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 设置群加群选项

POST /set_group_add_option

> Body 请求参数

```json
{
    "group_id": "123456",
    "add_type": 1
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» add_type|body|number| 是 |加群方式|
|» group_question|body|string| 否 |加群问题|
|» group_answer|body|string| 否 |加群答案|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 设置群机器人加群选项

POST /set_group_robot_add_option

> Body 请求参数

```json
{
    "group_id": "123456"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» robot_member_switch|body|number| 否 |机器人成员开关|
|» robot_member_examine|body|number| 否 |机器人成员审核|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 设置群搜索选项

POST /set_group_search

> Body 请求参数

```json
{
    "group_id": "123456"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» no_code_finger_open|body|number| 否 |未知|
|» no_finger_open|body|number| 否 |未知|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 设置群备注

POST /set_group_remark

设置群备注

> Body 请求参数

```json
{
    "group_id": "123456",
    "remark": "测试群备注"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» remark|body|string| 是 |备注|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取群详细信息 (扩展)

POST /get_group_info_ex

> Body 请求参数

```json
{
    "group_id": "123456"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 群打卡

POST /set_group_sign

> Body 请求参数

```json
{
    "group_id": "123456789"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 群打卡

POST /send_group_sign

> Body 请求参数

```json
{
    "group_id": "123456789"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取群组今日打卡列表

POST /get_group_signed_list

> Body 请求参数

```json
{
    "group_id": "123456"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|any| 是 |群号|
|»» *anonymous*|body|string| 否 |none|
|»» *anonymous*|body|number| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

# 核心接口

## POST 设置群待办

POST /set_group_todo

将指定消息设置为群待办

> Body 请求参数

```json
{
    "group_id": "123456",
    "message_id": "123456789"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|any| 是 |群号|
|»» *anonymous*|body|string| 否 |none|
|»» *anonymous*|body|number| 否 |none|
|» message_id|body|string| 否 |消息ID|
|» message_seq|body|string| 否 |消息Seq (可选)|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 完成群待办

POST /complete_group_todo

将指定消息对应的群待办标记为已完成

> Body 请求参数

```json
{
    "group_id": "123456",
    "message_id": "123456789"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|any| 是 |群号|
|»» *anonymous*|body|string| 否 |none|
|»» *anonymous*|body|number| 否 |none|
|» message_id|body|string| 否 |消息ID|
|» message_seq|body|string| 否 |消息Seq (可选)|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 取消群待办

POST /cancel_group_todo

将指定消息对应的群待办取消

> Body 请求参数

```json
{
    "group_id": "123456",
    "message_id": "123456789"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|any| 是 |群号|
|»» *anonymous*|body|string| 否 |none|
|»» *anonymous*|body|number| 否 |none|
|» message_id|body|string| 否 |消息ID|
|» message_seq|body|string| 否 |消息Seq (可选)|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 发送戳一戳

POST /group_poke

在群聊或私聊中发送戳一戳动作

> Body 请求参数

```json
{
    "user_id": "123456789"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 否 |群号|
|» user_id|body|string| 是 |用户QQ|
|» target_id|body|string| 否 |目标QQ|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 发送戳一戳

POST /friend_poke

在群聊或私聊中发送戳一戳动作

> Body 请求参数

```json
{
    "user_id": "123456789"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 否 |群号|
|» user_id|body|string| 是 |用户QQ|
|» target_id|body|string| 否 |目标QQ|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 发送戳一戳

POST /send_poke

在群聊或私聊中发送戳一戳动作

> Body 请求参数

```json
{
    "user_id": "123456789"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 否 |群号|
|» user_id|body|string| 是 |用户QQ|
|» target_id|body|string| 否 |目标QQ|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

# 群组接口

## POST 获取群详细信息

POST /get_group_detail_info

获取群聊的详细信息，包括成员数、最大成员数等

> Body 请求参数

```json
{
    "group_id": "123456"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "group_id": 123456,
        "group_name": "测试群",
        "member_count": 100,
        "max_member_count": 500
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取群列表

POST /get_group_list

获取当前帐号的群聊列表

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» no_cache|body|any| 否 |是否不使用缓存|
|»» *anonymous*|body|boolean| 否 |none|
|»» *anonymous*|body|string| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": [
        {
            "group_id": 123456,
            "group_name": "测试群",
            "member_count": 100,
            "max_member_count": 500
        }
    ],
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取群信息

POST /get_group_info

获取群聊的基本信息

> Body 请求参数

```json
{
    "group_id": "123456"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "group_id": 123456,
        "group_name": "测试群",
        "member_count": 100,
        "max_member_count": 500
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取群成员列表

POST /get_group_member_list

获取群聊中的所有成员列表

> Body 请求参数

```json
{
    "group_id": "123456"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» no_cache|body|any| 否 |是否不使用缓存|
|»» *anonymous*|body|boolean| 否 |none|
|»» *anonymous*|body|string| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": [
        {
            "group_id": 123456,
            "user_id": 123456789,
            "nickname": "昵称",
            "card": "名片",
            "role": "member"
        }
    ],
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取群成员信息

POST /get_group_member_info

获取群聊中指定成员的信息

> Body 请求参数

```json
{
    "group_id": "123456",
    "user_id": "123456789"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» user_id|body|string| 是 |QQ号|
|» no_cache|body|any| 否 |是否不使用缓存|
|»» *anonymous*|body|boolean| 否 |none|
|»» *anonymous*|body|string| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "group_id": 123456,
        "user_id": 123456789,
        "nickname": "昵称",
        "card": "名片",
        "role": "member"
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 处理加群请求

POST /set_group_add_request

同意或拒绝加群请求或邀请

> Body 请求参数

```json
{
    "flag": "flag_123",
    "sub_type": "add",
    "approve": true
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» flag|body|string| 是 |请求flag|
|» approve|body|any| 否 |是否同意|
|»» *anonymous*|body|boolean| 否 |none|
|»» *anonymous*|body|string| 否 |none|
|» reason|body|any| 否 |拒绝理由|
|»» *anonymous*|body|string| 否 |none|
|»» *anonymous*|body|null| 否 |none|
|» count|body|number| 否 |搜索通知数量|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 退出群组

POST /set_group_leave

退出或解散指定群聊

> Body 请求参数

```json
{
    "group_id": "123456",
    "is_dismiss": false
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» is_dismiss|body|any| 否 |是否解散|
|»» *anonymous*|body|boolean| 否 |none|
|»» *anonymous*|body|string| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 设置群名称

POST /set_group_name

修改指定群聊的名称

> Body 请求参数

```json
{
    "group_id": "123456",
    "group_name": "新群名"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» group_name|body|string| 是 |群名称|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 设置群名片

POST /set_group_card

设置群聊中指定成员的群名片

> Body 请求参数

```json
{
    "group_id": "123456",
    "user_id": "123456789",
    "card": "新名片"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» user_id|body|string| 是 |用户QQ|
|» card|body|string| 否 |群名片|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取群公告

POST /_get_group_notice

获取指定群聊中的公告列表

> Body 请求参数

```json
{
    "group_id": "123456"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": [
        {
            "notice_id": "notice_123",
            "sender_id": 123456,
            "publish_time": 1710000000,
            "message": {
                "text": "公告内容",
                "image": []
            }
        }
    ],
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取群精华消息

POST /get_essence_msg_list

获取指定群聊中的精华消息列表

> Body 请求参数

```json
{
    "group_id": "123456"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": [
        {
            "message_id": 123456,
            "sender_id": 123456,
            "sender_nick": "昵称",
            "operator_id": 123456,
            "operator_nick": "昵称",
            "operator_time": 1710000000,
            "content": "精华内容"
        }
    ],
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取群忽略通知

POST /get_group_ignored_notifies

获取被忽略的入群申请和邀请通知

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "invited_requests": [],
        "InvitedRequest": [],
        "join_requests": []
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 移出精华消息

POST /delete_essence_msg

将一条消息从群精华消息列表中移出

> Body 请求参数

```json
{
    "message_id": 123456
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» message_id|body|any| 否 |消息ID|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|
|» msg_seq|body|string| 否 |消息序号|
|» msg_random|body|string| 否 |消息随机数|
|» group_id|body|string| 否 |群号|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 设置精华消息

POST /set_essence_msg

将一条消息设置为群精华消息

> Body 请求参数

```json
{
    "message_id": 123456
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» message_id|body|any| 是 |消息ID|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 删除群公告

POST /_del_group_notice

删除群聊中的公告

> Body 请求参数

```json
{
    "group_id": "123456",
    "notice_id": "notice_123"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» notice_id|body|string| 是 |公告ID|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取群禁言列表

POST /get_group_shut_list

> Body 请求参数

```json
{
    "group_id": "123456789"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": [
        {
            "user_id": 123456789,
            "nickname": "禁言用户",
            "shut_up_time": 1734567890
        }
    ],
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取群被忽略的加群请求

POST /get_group_ignore_add_request

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": [
        {
            "request_id": 12345,
            "invitor_uin": 123456789,
            "invitor_nick": "邀请者",
            "group_id": 123456789,
            "message": "加群请求",
            "group_name": "群名称",
            "checked": false,
            "actor": 0,
            "requester_nick": "请求者"
        }
    ],
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

# 扩展接口

## POST 批量踢出群成员

POST /set_group_kick_members

从指定群聊中批量踢出多个成员

> Body 请求参数

```json
{
    "group_id": "123456",
    "user_id": [
        "123456789"
    ],
    "reject_add_request": false
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» user_id|body|[string]| 是 |QQ号列表|
|» reject_add_request|body|any| 否 |是否拒绝加群请求|
|»» *anonymous*|body|boolean| 否 |none|
|»» *anonymous*|body|string| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 创建收藏

POST /create_collection

> Body 请求参数

```json
{
    "rawData": "收藏内容",
    "brief": "收藏标题"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» rawData|body|string| 是 |原始数据|
|» brief|body|string| 是 |简要描述|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "result": 0,
        "errMsg": ""
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 设置个性签名

POST /set_self_longnick

修改当前登录帐号的个性签名

> Body 请求参数

```json
{
    "longNick": "个性签名"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» longNick|body|string| 是 |签名内容|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 设置QQ头像

POST /set_qq_avatar

修改当前账号的QQ头像

> Body 请求参数

```json
{
    "file": "base64://..."
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» file|body|string| 是 |图片路径、URL或Base64|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 英文单词翻译

POST /translate_en2zh

将英文单词列表翻译为中文

> Body 请求参数

```json
{
    "words": [
        "hello"
    ]
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» words|body|[string]| 是 |待翻译单词列表|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "words": [
            "你好"
        ]
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取ClientKey

POST /get_clientkey

获取当前登录帐号的ClientKey

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "clientkey": "abcdef123456"
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 图片 OCR 识别

POST /ocr_image

识别图片中的文字内容(仅Windows端支持)

> Body 请求参数

```json
{
    "image": "image_id_123"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» image|body|string| 是 |图片路径、URL或Base64|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "texts": [
            {
                "text": "识别内容",
                "coordinates": []
            }
        ]
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 图片 OCR 识别 (内部)

POST /.ocr_image

识别图片中的文字内容(仅Windows端支持)

> Body 请求参数

```json
{
    "image": "image_id_123"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» image|body|string| 是 |图片路径、URL或Base64|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "texts": [
            {
                "text": "识别内容",
                "coordinates": []
            }
        ]
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 设置专属头衔

POST /set_group_special_title

设置群聊中指定成员的专属头衔

> Body 请求参数

```json
{
    "group_id": "123456",
    "user_id": "123456789",
    "special_title": "头衔"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» user_id|body|string| 是 |QQ号|
|» special_title|body|string| 是 |专属头衔|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取AI角色列表

POST /get_ai_characters

获取群聊中的AI角色列表

> Body 请求参数

```json
{
    "group_id": "123456"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» chat_type|body|any| 是 |聊天类型|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": [
        {
            "type": "string",
            "characters": [
                {
                    "character_id": "id",
                    "character_name": "name",
                    "preview_url": "url"
                }
            ]
        }
    ],
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

# 系统接口

## POST 处理可疑好友申请

POST /set_doubt_friends_add_request

同意或拒绝系统的可疑好友申请

> Body 请求参数

```json
{
    "flag": "12345",
    "approve": true
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» flag|body|string| 是 |请求 flag|
|» approve|body|boolean| 是 |是否同意 (强制为 true)|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取可疑好友申请

POST /get_doubt_friends_add_request

获取系统的可疑好友申请列表

> Body 请求参数

```json
{
    "count": 10
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» count|body|number| 是 |获取数量|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": [
        {
            "user_id": 123456789,
            "nickname": "昵称",
            "age": 20,
            "sex": "male",
            "reason": "申请理由",
            "flag": "flag_123"
        }
    ],
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取登录号信息

POST /get_login_info

获取当前登录帐号的信息

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "user_id": 123456789,
        "nickname": "机器人"
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取版本信息

POST /get_version_info

获取版本信息

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "app_name": "NapCat.Onebot",
        "protocol_version": "v11",
        "app_version": "1.0.0"
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 是否可以发送语音

POST /can_send_record

检查是否可以发送语音

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "yes": true
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 是否可以发送图片

POST /can_send_image

检查是否可以发送图片

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "yes": true
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取运行状态

POST /get_status

获取运行状态

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "online": true,
        "good": true,
        "stat": {}
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取 CSRF Token

POST /get_csrf_token

获取 CSRF Token

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "token": 123456789
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取登录凭证

POST /get_credentials

获取登录凭证

> Body 请求参数

```json
{
    "domain": "qun.qq.com"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» domain|body|string| 是 |需要获取 cookies 的域名|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "cookies": "uin=o123456789; skey=@abc12345;",
        "token": 123456789
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取Packet状态

POST /nc_get_packet_status

获取底层Packet服务的运行状态

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 重启服务

POST /set_restart

重启服务

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取群系统消息

POST /get_group_system_msg

获取群系统消息

> Body 请求参数

```json
{
    "count": 50
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» count|body|any| 是 |获取的消息数量|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "invited_requests": [],
        "InvitedRequest": [],
        "join_requests": []
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 清理缓存

POST /clean_cache

清理缓存

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

# 用户接口

## POST 设置好友备注

POST /set_friend_remark

设置好友备注

> Body 请求参数

```json
{
    "user_id": "123456",
    "remark": "测试备注"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» user_id|body|string| 是 |对方 QQ 号|
|» remark|body|string| 是 |备注内容|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "备注设置失败（好友不存在或非法输入）",
    "wording": "备注设置失败（好友不存在或非法输入）",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取好友列表

POST /get_friend_list

获取当前帐号的好友列表

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» no_cache|body|any| 否 |是否不使用缓存|
|»» *anonymous*|body|boolean| 否 |none|
|»» *anonymous*|body|string| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": [
        {
            "user_id": 123456789,
            "nickname": "昵称",
            "remark": "备注"
        }
    ],
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 处理加好友请求

POST /set_friend_add_request

同意或拒绝加好友请求

> Body 请求参数

```json
{
    "flag": "flag_12345",
    "approve": true,
    "remark": "新朋友"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» flag|body|string| 是 |加好友请求的 flag (需从上报中获取)|
|» approve|body|any| 否 |是否同意请求|
|»» *anonymous*|body|string| 否 |none|
|»» *anonymous*|body|boolean| 否 |none|
|» remark|body|string| 否 |添加后的好友备注|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取 Cookies

POST /get_cookies

获取指定域名的 Cookies

> Body 请求参数

```json
{
    "domain": "qun.qq.com"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» domain|body|string| 是 |需要获取 cookies 的域名|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "cookies": "uin=o123456789; skey=@abc12345;",
        "bkn": "123456789"
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取最近会话

POST /get_recent_contact

获取最近会话

> Body 请求参数

```json
{
    "count": 10
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» count|body|any| 是 |获取的数量|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": [
        {
            "peerUin": "123456",
            "peerName": "测试",
            "msgTime": "1734567890",
            "msgId": "12345",
            "lastestMsg": {}
        }
    ],
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

# 系统扩展

## POST 获取扩展 RKey

POST /get_rkey

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": [
        {
            "type": "private",
            "rkey": "rkey_123",
            "created_at": 1734567890,
            "ttl": 3600
        }
    ],
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取 RKey 服务器

POST /get_rkey_server

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "private_rkey": "&rkey=123456789",
        "group_rkey": "&rkey=123456789",
        "expired_time": 1694560000,
        "name": "NapCat 4"
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 设置在线状态

POST /set_online_status

## 状态列表

### 在线
```json5;
{ "status": 10, "ext_status": 0, "battery_status": 0; }
```

### Q我吧
```json5;
{ "status": 60, "ext_status": 0, "battery_status": 0; }
```

### 离开
```json5;
{ "status": 30, "ext_status": 0, "battery_status": 0; }
```

### 忙碌
```json5;
{ "status": 50, "ext_status": 0, "battery_status": 0; }
```

### 请勿打扰
```json5;
{ "status": 70, "ext_status": 0, "battery_status": 0; }
```

### 隐身
```json5;
{ "status": 40, "ext_status": 0, "battery_status": 0; }
```

### 听歌中
```json5;
{ "status": 10, "ext_status": 1028, "battery_status": 0; }
```

### 春日限定
```json5;
{ "status": 10, "ext_status": 2037, "battery_status": 0; }
```

### 一起元梦
```json5;
{ "status": 10, "ext_status": 2025, "battery_status": 0; }
```

### 求星搭子
```json5;
{ "status": 10, "ext_status": 2026, "battery_status": 0; }
```

### 被掏空
```json5;
{ "status": 10, "ext_status": 2014, "battery_status": 0; }
```

### 今日天气
```json5;
{ "status": 10, "ext_status": 1030, "battery_status": 0; }
```

### 我crash了
```json5;
{ "status": 10, "ext_status": 2019, "battery_status": 0; }
```

### 爱你
```json5;
{ "status": 10, "ext_status": 2006, "battery_status": 0; }
```

### 恋爱中
```json5;
{ "status": 10, "ext_status": 1051, "battery_status": 0; }
```

### 好运锦鲤
```json5;
{ "status": 10, "ext_status": 1071, "battery_status": 0; }
```

### 水逆退散
```json5;
{ "status": 10, "ext_status": 1201, "battery_status": 0; }
```

### 嗨到飞起
```json5;
{ "status": 10, "ext_status": 1056, "battery_status": 0; }
```

### 元气满满
```json5;
{ "status": 10, "ext_status": 1058, "battery_status": 0; }
```

### 宝宝认证
```json5;
{ "status": 10, "ext_status": 1070, "battery_status": 0; }
```

### 一言难尽
```json5;
{ "status": 10, "ext_status": 1063, "battery_status": 0; }
```

### 难得糊涂
```json5;
{ "status": 10, "ext_status": 2001, "battery_status": 0; }
```

### emo中
```json5;
{ "status": 10, "ext_status": 1401, "battery_status": 0; }
```

### 我太难了
```json5;
{ "status": 10, "ext_status": 1062, "battery_status": 0; }
```

### 我想开了
```json5;
{ "status": 10, "ext_status": 2013, "battery_status": 0; }
```

### 我没事
```json5;
{ "status": 10, "ext_status": 1052, "battery_status": 0; }
```

### 想静静
```json5;
{ "status": 10, "ext_status": 1061, "battery_status": 0; }
```

### 悠哉哉
```json5;
{ "status": 10, "ext_status": 1059, "battery_status": 0; }
```

### 去旅行
```json5;
{ "status": 10, "ext_status": 2015, "battery_status": 0; }
```

### 信号弱
```json5;
{ "status": 10, "ext_status": 1011, "battery_status": 0; }
```

### 出去浪
```json5;
{ "status": 10, "ext_status": 2003, "battery_status": 0; }
```

### 肝作业
```json5;
{ "status": 10, "ext_status": 2012, "battery_status": 0; }
```

### 学习中
```json5;
{ "status": 10, "ext_status": 1018, "battery_status": 0; }
```

### 搬砖中
```json5;
{ "status": 10, "ext_status": 2023, "battery_status": 0; }
```

### 摸鱼中
```json5;
{ "status": 10, "ext_status": 1300, "battery_status": 0; }
```

### 无聊中
```json5;
{ "status": 10, "ext_status": 1060, "battery_status": 0; }
```

### timi中
```json5;
{ "status": 10, "ext_status": 1027, "battery_status": 0; }
```

### 睡觉中
```json5;
{ "status": 10, "ext_status": 1016, "battery_status": 0; }
```

### 熬夜中
```json5;
{ "status": 10, "ext_status": 1032, "battery_status": 0; }
```

### 追剧中
```json5;
{ "status": 10, "ext_status": 1021, "battery_status": 0; }
```

### 我的电量
```json5;
{
  "status": 10,
    "ext_status": 1000,
      "battery_status": 0;
}
```

> Body 请求参数

```json
{
    "status": 11,
    "ext_status": 0,
    "battery_status": 100
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» status|body|any| 是 |在线状态|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|
|» ext_status|body|any| 是 |扩展状态|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|
|» battery_status|body|any| 是 |电量状态|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取机器人 UIN 范围

POST /get_robot_uin_range

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": [
        {
            "minUin": "12345678",
            "maxUin": "87654321"
        }
    ],
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取自定义表情

POST /fetch_custom_face

> Body 请求参数

```json
{
    "count": 10
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» count|body|any| 是 |获取数量|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": [
        "http://example.com/face1.png"
    ],
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取自定义表情详情

POST /fetch_custom_face_detail

> Body 请求参数

```json
{
    "count": 10
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» count|body|any| 是 |获取数量|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 添加自定义表情

POST /add_custom_face

> Body 请求参数

```json
{
    "file": "C:\\Users\\Public\\face.png",
    "is_origin": true
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» file|body|string| 是 |本地表情文件路径|
|» emoji_id|body|any| 否 |表情ID，未提供时传空字符串|
|»» *anonymous*|body|string| 否 |none|
|»» *anonymous*|body|number| 否 |none|
|» package_id|body|any| 否 |表情包ID，未提供时传0|
|»» *anonymous*|body|string| 否 |none|
|»» *anonymous*|body|number| 否 |none|
|» file_name|body|string| 否 |文件名，未提供时从file路径取basename|
|» file_size|body|any| 否 |文件大小，未提供时读取本地文件|
|»» *anonymous*|body|string| 否 |none|
|»» *anonymous*|body|number| 否 |none|
|» md5|body|string| 否 |文件MD5，未提供时读取本地文件计算|
|» is_mark_face|body|boolean| 否 |是否商城表情|
|» is_origin|body|boolean| 否 |是否原图|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 删除自定义表情

POST /delete_custom_face

> Body 请求参数

```json
{
    "res_id": "2707600964_0_0_0_D8EAA70984B402EE10B0F33DB88F4173_0_0"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» res_id|body|any| 否 |none|
|»» *anonymous*|body|string| 否 |fetch_custom_face_detail返回的resId|
|»» *anonymous*|body|[string]| 否 |none|
|» id|body|any| 否 |none|
|»» *anonymous*|body|string| 否 |native deleteFavEmoji字符串ID，通常为resId|
|»» *anonymous*|body|[string]| 否 |none|
|» ids|body|[string]| 否 |none|
|» md5|body|any| 否 |none|
|»» *anonymous*|body|string| 否 |表情MD5，不能直接删除，请先通过fetch_custom_face_detail获取resId|
|»» *anonymous*|body|[string]| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 修改自定义表情描述

POST /set_custom_face_desc

> Body 请求参数

```json
{
    "emoji_id": 1,
    "res_id": "resource-id",
    "md5": "d41d8cd98f00b204e9800998ecf8427e",
    "desc": "新的描述"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» emoji_id|body|any| 是 |表情ID|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|
|» res_id|body|string| 是 |资源ID|
|» md5|body|string| 是 |表情MD5|
|» desc|body|string| 是 |新的表情描述|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 设置输入状态

POST /set_input_status

> Body 请求参数

```json
{
    "user_id": "123456789",
    "event_type": 1
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» user_id|body|string| 是 |QQ号|
|» event_type|body|number| 是 |事件类型|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取用户在线状态

POST /nc_get_user_status

> Body 请求参数

```json
{
    "user_id": "123456789"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» user_id|body|string| 是 |QQ号|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "status": 10,
        "ext_status": 0
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取 RKey

POST /nc_get_rkey

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": [
        {
            "key": "rkey_value",
            "expired": 1734567890
        }
    ],
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取小程序 Ark

POST /get_mini_app_ark

> Body 请求参数

```json
{
    "type": "bili",
    "title": "测试标题",
    "desc": "测试描述",
    "picUrl": "http://example.com/pic.jpg",
    "jumpUrl": "http://example.com"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|any| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "data": {
            "ark": "ark_content"
        }
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 发送原始数据包

POST /send_packet

> Body 请求参数

```json
{
    "cmd": "Example.Cmd",
    "data": "123456",
    "rsp": true
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» cmd|body|string| 是 |命令字|
|» data|body|string| 是 |十六进制数据|
|» rsp|body|any| 是 |是否等待响应|
|»» *anonymous*|body|string| 否 |none|
|»» *anonymous*|body|boolean| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": "123456",
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 退出登录

POST /bot_exit

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取收藏列表

POST /get_collection_list

> Body 请求参数

```json
{
    "category": "0",
    "count": "50"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» category|body|string| 是 |分类ID|
|» count|body|string| 是 |获取数量|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "errCode": 0,
        "errMsg": "",
        "collectionSearchList": {
            "collectionItemList": [
                {
                    "cid": "123456",
                    "type": 8,
                    "status": 1,
                    "author": {
                        "type": 2,
                        "numId": "123456",
                        "strId": "昵称",
                        "groupId": "123456",
                        "groupName": "群名",
                        "uid": "123456"
                    },
                    "bid": 1,
                    "category": 1,
                    "createTime": "1769169157000",
                    "collectTime": "1769413477691",
                    "modifyTime": "1769413477691",
                    "sequence": "1769413476735",
                    "shareUrl": "",
                    "customGroupId": 0,
                    "securityBeat": false,
                    "summary": {
                        "textSummary": null,
                        "linkSummary": null,
                        "gallerySummary": null,
                        "audioSummary": null,
                        "videoSummary": null,
                        "fileSummary": null,
                        "locationSummary": null,
                        "richMediaSummary": {
                            "title": "",
                            "subTitle": "",
                            "brief": "text",
                            "picList": [],
                            "contentType": 1,
                            "originalUri": "",
                            "publisher": "",
                            "richMediaVersion": 0
                        }
                    }
                }
            ],
            "hasMore": false,
            "bottomTimeStamp": "1769413477691"
        }
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

# 消息扩展

## POST 获取表情点赞详情

POST /fetch_emoji_like

> Body 请求参数

```json
{
    "message_id": 12345,
    "emojiId": "123",
    "emojiType": 1,
    "count": 10,
    "cookie": ""
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» message_id|body|any| 是 |消息ID|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|
|» emojiId|body|any| 是 |表情ID|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|
|» emojiType|body|any| 是 |表情类型|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|
|» count|body|any| 是 |获取数量|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|
|» cookie|body|string| 是 |分页Cookie|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "emojiLikesList": [
            {
                "tinyId": "123456",
                "nickName": "测试用户",
                "headUrl": "http://example.com/avatar.png"
            }
        ],
        "cookie": "",
        "isLastPage": true,
        "isFirstPage": true,
        "result": 0,
        "errMsg": ""
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取消息表情点赞列表

POST /get_emoji_likes

> Body 请求参数

```json
{
    "message_id": "12345",
    "emoji_id": "123"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 否 |群号，短ID可不传|
|» message_id|body|string| 是 |消息ID，可以传递长ID或短ID|
|» emoji_id|body|string| 是 |表情ID|
|» emoji_type|body|string| 否 |表情类型|
|» count|body|number| 是 |数量，0代表全部|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "emoji_like_list": [
            {
                "user_id": "654321",
                "nick_name": "测试用户"
            }
        ]
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取语音转文字结果

POST /fetch_ptt_text

> Body 请求参数

```json
{
    "message_id": 123456
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» message_id|body|any| 是 |消息ID|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "text": "hello"
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 分享群 (Ark)

POST /ArkShareGroup

获取群分享的 Ark 内容

> Body 请求参数

```json
{
    "group_id": "123456"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": "{\"app\": \"com.tencent.structmsg\", ...}",
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 分享用户 (Ark)

POST /ArkSharePeer

获取用户推荐的 Ark 内容

> Body 请求参数

```json
{
    "user_id": "123456",
    "phone_number": ""
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» user_id|body|string| 否 |QQ号|
|» group_id|body|string| 否 |群号|
|» phone_number|body|string| 是 |手机号|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "ark": "..."
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 分享群 (Ark)

POST /send_group_ark_share

获取群分享的 Ark 内容

> Body 请求参数

```json
{
    "group_id": "123456"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": "{\"app\": \"com.tencent.structmsg\", ...}",
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 分享用户 (Ark)

POST /send_ark_share

获取用户推荐的 Ark 内容

> Body 请求参数

```json
{
    "user_id": "123456",
    "phone_number": ""
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» user_id|body|string| 否 |QQ号|
|» group_id|body|string| 否 |群号|
|» phone_number|body|string| 是 |手机号|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "ark": "..."
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 设置消息表情点赞

POST /set_msg_emoji_like

> Body 请求参数

```json
{
    "message_id": 12345,
    "emoji_id": "123",
    "set": true
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» message_id|body|any| 是 |消息ID|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|
|» emoji_id|body|any| 是 |表情ID|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|
|» set|body|any| 否 |是否设置|
|»» *anonymous*|body|boolean| 否 |none|
|»» *anonymous*|body|string| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "result": true
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 点击内联键盘按钮

POST /click_inline_keyboard_button

> Body 请求参数

```json
{
    "group_id": "123456",
    "bot_appid": "1234567890",
    "button_id": "btn_1",
    "callback_data": "",
    "msg_seq": "10086"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» bot_appid|body|string| 是 |机器人AppID|
|» button_id|body|string| 是 |按钮ID|
|» callback_data|body|string| 是 |回调数据|
|» msg_seq|body|string| 是 |消息序列号|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

# 文件接口

## POST 获取文件

POST /get_file

获取指定文件的详细信息及下载路径

> Body 请求参数

```json
{
    "file": "file_id_123"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» file|body|string| 否 |文件路径、URL或Base64|
|» file_id|body|string| 否 |文件ID|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "file": "/path/to/file",
        "url": "http://...",
        "file_size": 1024,
        "file_name": "test.jpg"
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取图片

POST /get_image

获取指定图片的信息及路径

> Body 请求参数

```json
{
    "file": "image_id_123"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» file|body|string| 否 |文件路径、URL或Base64|
|» file_id|body|string| 否 |文件ID|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "file": "/path/to/image",
        "url": "http://..."
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取语音

POST /get_record

获取指定语音文件的信息，并支持格式转换

> Body 请求参数

```json
{
    "file": "record_id_123",
    "out_format": "mp3"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» file|body|string| 否 |文件路径、URL或Base64|
|» file_id|body|string| 否 |文件ID|
|» out_format|body|string| 是 |输出格式|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "file": "/path/to/record",
        "url": "http://..."
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取群文件URL

POST /get_group_file_url

获取指定群文件的下载链接

> Body 请求参数

```json
{
    "group_id": "123456",
    "file_id": "file_id_123",
    "busid": 102
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» file_id|body|string| 是 |文件ID|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "url": "http://..."
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取私聊文件URL

POST /get_private_file_url

获取指定私聊文件的下载链接

> Body 请求参数

```json
{
    "user_id": "123456789",
    "file_id": "file_id_123"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» file_id|body|string| 是 |文件ID|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "url": "http://..."
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

# Go-CQHTTP

## POST 设置QQ资料

POST /set_qq_profile

修改当前账号的昵称、个性签名等资料

> Body 请求参数

```json
{
    "nickname": "新昵称",
    "personal_note": "个性签名"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» nickname|body|string| 是 |昵称|
|» personal_note|body|string| 否 |个性签名|
|» sex|body|any| 否 |性别 (0: 未知, 1: 男, 2: 女)|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取群根目录文件列表

POST /get_group_root_files

获取群文件根目录下的所有文件和文件夹

> Body 请求参数

```json
{
    "group_id": "123456"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» file_count|body|any| 是 |文件数量|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "files": [],
        "folders": []
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 删除好友

POST /delete_friend

从好友列表中删除指定用户

> Body 请求参数

```json
{
    "user_id": "123456789"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» friend_id|body|any| 否 |好友 QQ 号|
|»» *anonymous*|body|string| 否 |none|
|»» *anonymous*|body|number| 否 |none|
|» user_id|body|any| 否 |用户 QQ 号|
|»» *anonymous*|body|string| 否 |none|
|»» *anonymous*|body|number| 否 |none|
|» temp_block|body|boolean| 否 |是否加入黑名单|
|» temp_both_del|body|boolean| 否 |是否双向删除|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 检查URL安全性

POST /check_url_safely

检查指定URL的安全等级

> Body 请求参数

```json
{
    "url": "https://example.com"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» url|body|string| 是 |要检查的 URL|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "level": 1
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取在线客户端

POST /get_online_clients

获取当前登录账号的在线客户端列表

> Body 请求参数

```json
{
    "no_cache": false
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取群荣誉信息

POST /get_group_honor_info

获取指定群聊的荣誉信息，如龙王等

> Body 请求参数

```json
{
    "group_id": "123456",
    "type": "all"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» type|body|string| 否 |荣誉类型|

#### 枚举值

|属性|值|
|---|---|
|» type|all|
|» type|talkative|
|» type|performer|
|» type|legend|
|» type|strong_newbie|
|» type|emotion|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "group_id": 123456,
        "current_talkative": {},
        "talkative_list": []
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 发送群公告

POST /_send_group_notice

在指定群聊中发布新的公告

> Body 请求参数

```json
{
    "group_id": "123456",
    "content": "公告内容",
    "image": "base64://..."
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» content|body|string| 是 |公告内容|
|» image|body|string| 否 |公告图片路径或 URL|
|» pinned|body|any| 是 |是否置顶 (0/1)|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|
|» type|body|any| 是 |类型 (默认为 1)|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|
|» confirm_required|body|any| 是 |是否需要确认 (0/1)|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|
|» is_show_edit_card|body|any| 是 |是否显示修改群名片引导 (0/1)|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|
|» tip_window_type|body|any| 是 |弹窗类型 (默认为 0)|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取群艾特全体剩余次数

POST /get_group_at_all_remain

获取指定群聊中艾特全体成员的剩余次数

> Body 请求参数

```json
{
    "group_id": "123456"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "can_at_all": true,
        "remain_at_all_count_for_group": 10,
        "remain_at_all_count_for_self": 10
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 发送合并转发消息

POST /send_forward_msg

发送合并转发消息

> Body 请求参数

```json
{
    "group_id": "123456789",
    "messages": []
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» message_type|body|string| 否 |消息类型 (private/group)|
|» user_id|body|string| 否 |用户QQ|
|» group_id|body|string| 否 |群号|
|» message|body|any| 是 |OneBot 11 消息混合类型|
|»» *anonymous*|body|[anyOf]| 否 |[OneBot 11 消息段]|
|»»» *anonymous*|body|[OB11MessageText](#schemaob11messagetext)| 否 |纯文本消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» text|body|string| 是 |纯文本内容|
|»»» *anonymous*|body|[OB11MessageFace](#schemaob11messageface)| 否 |QQ表情消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» id|body|string| 是 |表情ID|
|»»»»» resultId|body|string| 否 |结果ID|
|»»»»» chainCount|body|number| 否 |连击数|
|»»» *anonymous*|body|[OB11MessageMFace](#schemaob11messagemface)| 否 |商城表情消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» emoji_package_id|body|number| 是 |表情包ID|
|»»»»» emoji_id|body|string| 是 |表情ID|
|»»»»» key|body|string| 是 |表情key|
|»»»»» summary|body|string| 是 |表情摘要|
|»»» *anonymous*|body|[OB11MessageAt](#schemaob11messageat)| 否 |@消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» qq|body|string| 是 |QQ号或all|
|»»»»» name|body|string| 否 |显示名称|
|»»» *anonymous*|body|[OB11MessageReply](#schemaob11messagereply)| 否 |回复消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» id|body|string| 否 |消息ID的短ID映射|
|»»»»» seq|body|number| 否 |消息序列号，优先使用|
|»»» *anonymous*|body|[OB11MessageImage](#schemaob11messageimage)| 否 |图片消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|any| 是 |none|
|»»»»» *anonymous*|body|object| 否 |文件消息段基础数据|
|»»»»»» file|body|string| 是 |文件路径/URL/file:///|
|»»»»»» path|body|string| 否 |文件路径|
|»»»»»» url|body|string| 否 |文件URL|
|»»»»»» name|body|string| 否 |文件名|
|»»»»»» thumb|body|string| 否 |缩略图|
|»»»»» *anonymous*|body|object| 否 |none|
|»»»»»» summary|body|string| 否 |图片摘要|
|»»»»»» sub_type|body|number| 否 |图片子类型|
|»»» *anonymous*|body|[OB11MessageRecord](#schemaob11messagerecord)| 否 |语音消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|[FileBaseData](#schemafilebasedata)| 是 |文件消息段基础数据|
|»»»»» file|body|string| 是 |文件路径/URL/file:///|
|»»»»» path|body|string| 否 |文件路径|
|»»»»» url|body|string| 否 |文件URL|
|»»»»» name|body|string| 否 |文件名|
|»»»»» thumb|body|string| 否 |缩略图|
|»»» *anonymous*|body|[OB11MessageVideo](#schemaob11messagevideo)| 否 |视频消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|[FileBaseData](#schemafilebasedata)| 是 |文件消息段基础数据|
|»»»»» file|body|string| 是 |文件路径/URL/file:///|
|»»»»» path|body|string| 否 |文件路径|
|»»»»» url|body|string| 否 |文件URL|
|»»»»» name|body|string| 否 |文件名|
|»»»»» thumb|body|string| 否 |缩略图|
|»»» *anonymous*|body|[OB11MessageFile](#schemaob11messagefile)| 否 |文件消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|[FileBaseData](#schemafilebasedata)| 是 |文件消息段基础数据|
|»»»»» file|body|string| 是 |文件路径/URL/file:///|
|»»»»» path|body|string| 否 |文件路径|
|»»»»» url|body|string| 否 |文件URL|
|»»»»» name|body|string| 否 |文件名|
|»»»»» thumb|body|string| 否 |缩略图|
|»»» *anonymous*|body|[OB11MessageIdMusic](#schemaob11messageidmusic)| 否 |ID音乐消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» type|body|string| 是 |音乐平台类型|
|»»»»» id|body|any| 是 |音乐ID|
|»»»»»» *anonymous*|body|string| 否 |none|
|»»»»»» *anonymous*|body|number| 否 |none|
|»»» *anonymous*|body|[OB11MessageCustomMusic](#schemaob11messagecustommusic)| 否 |自定义音乐消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» type|body|string| 是 |音乐平台类型|
|»»»»» id|body|null| 是 |none|
|»»»»» url|body|string| 是 |点击后跳转URL|
|»»»»» audio|body|string| 否 |音频URL|
|»»»»» title|body|string| 否 |音乐标题|
|»»»»» image|body|string| 是 |封面图片URL|
|»»»»» content|body|string| 否 |音乐简介|
|»»» *anonymous*|body|[OB11MessagePoke](#schemaob11messagepoke)| 否 |戳一戳消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» type|body|string| 是 |戳一戳类型|
|»»»»» id|body|string| 是 |戳一戳ID|
|»»» *anonymous*|body|[OB11MessageDice](#schemaob11messagedice)| 否 |骰子消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» result|body|any| 是 |骰子结果|
|»»»»»» *anonymous*|body|number| 否 |none|
|»»»»»» *anonymous*|body|string| 否 |none|
|»»» *anonymous*|body|[OB11MessageRPS](#schemaob11messagerps)| 否 |猜拳消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» result|body|any| 是 |猜拳结果|
|»»»»»» *anonymous*|body|number| 否 |none|
|»»»»»» *anonymous*|body|string| 否 |none|
|»»» *anonymous*|body|[OB11MessageContact](#schemaob11messagecontact)| 否 |联系人消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» type|body|string| 是 |联系人类型|
|»»»»» id|body|string| 是 |联系人ID|
|»»» *anonymous*|body|[OB11MessageLocation](#schemaob11messagelocation)| 否 |位置消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» lat|body|any| 是 |纬度|
|»»»»»» *anonymous*|body|string| 否 |none|
|»»»»»» *anonymous*|body|number| 否 |none|
|»»»»» lon|body|any| 是 |经度|
|»»»»»» *anonymous*|body|string| 否 |none|
|»»»»»» *anonymous*|body|number| 否 |none|
|»»»»» title|body|string| 否 |标题|
|»»»»» content|body|string| 否 |内容|
|»»» *anonymous*|body|[OB11MessageJson](#schemaob11messagejson)| 否 |JSON消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» data|body|any| 是 |JSON数据|
|»»»»»» *anonymous*|body|string| 否 |none|
|»»»»»» *anonymous*|body|object| 否 |none|
|»»»»» config|body|object| 否 |none|
|»»»»»» token|body|string| 是 |token|
|»»» *anonymous*|body|[OB11MessageXml](#schemaob11messagexml)| 否 |XML消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» data|body|string| 是 |XML数据|
|»»» *anonymous*|body|[OB11MessageMarkdown](#schemaob11messagemarkdown)| 否 |Markdown消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» content|body|string| 是 |Markdown内容|
|»»» *anonymous*|body|[OB11MessageMiniApp](#schemaob11messageminiapp)| 否 |小程序消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» data|body|string| 是 |小程序数据|
|»»» *anonymous*|body|[OB11MessageNode](#schemaob11messagenode)| 否 |合并转发消息节点|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» id|body|string| 否 |转发消息ID|
|»»»»» user_id|body|any| 否 |发送者QQ号|
|»»»»»» *anonymous*|body|number| 否 |none|
|»»»»»» *anonymous*|body|string| 否 |none|
|»»»»» uin|body|any| 否 |发送者QQ号(兼容go-cqhttp)|
|»»»»»» *anonymous*|body|number| 否 |none|
|»»»»»» *anonymous*|body|string| 否 |none|
|»»»»» nickname|body|string| 是 |发送者昵称|
|»»»»» name|body|string| 否 |发送者昵称(兼容go-cqhttp)|
|»»»»» content|body|object| 是 |消息内容 (OB11MessageMixType)|
|»»»»» source|body|string| 否 |消息来源|
|»»»»» news|body|[object]| 否 |none|
|»»»»»» text|body|string| 是 |新闻文本|
|»»»»» summary|body|string| 否 |摘要|
|»»»»» prompt|body|string| 否 |提示|
|»»»»» time|body|string| 否 |时间|
|»»» *anonymous*|body|[OB11MessageForward](#schemaob11messageforward)| 否 |合并转发消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» id|body|string| 是 |合并转发ID|
|»»»»» content|body|object| 否 |消息内容 (OB11Message[])|
|»»» *anonymous*|body|[OB11MessageOnlineFile](#schemaob11messageonlinefile)| 否 |在线文件消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» msgId|body|string| 是 |消息ID|
|»»»»» elementId|body|string| 是 |元素ID|
|»»»»» fileName|body|string| 是 |文件名|
|»»»»» fileSize|body|string| 是 |文件大小|
|»»»»» isDir|body|boolean| 是 |是否为目录|
|»»» *anonymous*|body|[OB11MessageFlashTransfer](#schemaob11messageflashtransfer)| 否 |QQ闪传消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» fileSetId|body|string| 是 |文件集ID|
|»» *anonymous*|body|string| 否 |none|
|»» *anonymous*|body|any| 否 |OneBot 11 消息段|
|»»» *anonymous*|body|[OB11MessageText](#schemaob11messagetext)| 否 |纯文本消息段|
|»»» *anonymous*|body|[OB11MessageFace](#schemaob11messageface)| 否 |QQ表情消息段|
|»»» *anonymous*|body|[OB11MessageMFace](#schemaob11messagemface)| 否 |商城表情消息段|
|»»» *anonymous*|body|[OB11MessageAt](#schemaob11messageat)| 否 |@消息段|
|»»» *anonymous*|body|[OB11MessageReply](#schemaob11messagereply)| 否 |回复消息段|
|»»» *anonymous*|body|[OB11MessageImage](#schemaob11messageimage)| 否 |图片消息段|
|»»» *anonymous*|body|[OB11MessageRecord](#schemaob11messagerecord)| 否 |语音消息段|
|»»» *anonymous*|body|[OB11MessageVideo](#schemaob11messagevideo)| 否 |视频消息段|
|»»» *anonymous*|body|[OB11MessageFile](#schemaob11messagefile)| 否 |文件消息段|
|»»» *anonymous*|body|[OB11MessageIdMusic](#schemaob11messageidmusic)| 否 |ID音乐消息段|
|»»» *anonymous*|body|[OB11MessageCustomMusic](#schemaob11messagecustommusic)| 否 |自定义音乐消息段|
|»»» *anonymous*|body|[OB11MessagePoke](#schemaob11messagepoke)| 否 |戳一戳消息段|
|»»» *anonymous*|body|[OB11MessageDice](#schemaob11messagedice)| 否 |骰子消息段|
|»»» *anonymous*|body|[OB11MessageRPS](#schemaob11messagerps)| 否 |猜拳消息段|
|»»» *anonymous*|body|[OB11MessageContact](#schemaob11messagecontact)| 否 |联系人消息段|
|»»» *anonymous*|body|[OB11MessageLocation](#schemaob11messagelocation)| 否 |位置消息段|
|»»» *anonymous*|body|[OB11MessageJson](#schemaob11messagejson)| 否 |JSON消息段|
|»»» *anonymous*|body|[OB11MessageXml](#schemaob11messagexml)| 否 |XML消息段|
|»»» *anonymous*|body|[OB11MessageMarkdown](#schemaob11messagemarkdown)| 否 |Markdown消息段|
|»»» *anonymous*|body|[OB11MessageMiniApp](#schemaob11messageminiapp)| 否 |小程序消息段|
|»»» *anonymous*|body|[OB11MessageNode](#schemaob11messagenode)| 否 |合并转发消息节点|
|»»» *anonymous*|body|[OB11MessageForward](#schemaob11messageforward)| 否 |合并转发消息段|
|»»» *anonymous*|body|[OB11MessageOnlineFile](#schemaob11messageonlinefile)| 否 |在线文件消息段|
|»»» *anonymous*|body|[OB11MessageFlashTransfer](#schemaob11messageflashtransfer)| 否 |QQ闪传消息段|
|» auto_escape|body|any| 否 |是否作为纯文本发送|
|»» *anonymous*|body|boolean| 否 |none|
|»» *anonymous*|body|string| 否 |none|
|» source|body|string| 否 |合并转发来源|
|» news|body|[object]| 否 |合并转发新闻|
|»» text|body|string| 是 |none|
|» summary|body|string| 否 |合并转发摘要|
|» prompt|body|string| 否 |合并转发提示|
|» timeout|body|number| 否 |自定义发送超时(毫秒)，覆盖自动计算值|

#### 枚举值

|属性|值|
|---|---|
|» message_type|private|
|» message_type|group|
|»»»» type|text|
|»»»» type|face|
|»»»» type|mface|
|»»»» type|at|
|»»»» type|reply|
|»»»» type|image|
|»»»» type|record|
|»»»» type|video|
|»»»» type|file|
|»»»» type|music|
|»»»»» type|qq|
|»»»»» type|163|
|»»»»» type|kugou|
|»»»»» type|migu|
|»»»»» type|kuwo|
|»»»» type|music|
|»»»»» type|qq|
|»»»»» type|163|
|»»»»» type|kugou|
|»»»»» type|migu|
|»»»»» type|kuwo|
|»»»»» type|custom|
|»»»» type|poke|
|»»»» type|dice|
|»»»» type|rps|
|»»»» type|contact|
|»»»»» type|qq|
|»»»»» type|group|
|»»»» type|location|
|»»»» type|json|
|»»»» type|xml|
|»»»» type|markdown|
|»»»» type|miniapp|
|»»»» type|node|
|»»»» type|forward|
|»»»» type|onlinefile|
|»»»» type|flashtransfer|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "message_id": 123456
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 发送群合并转发消息

POST /send_group_forward_msg

> Body 请求参数

```json
{
    "group_id": "123456789",
    "messages": []
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» message_type|body|string| 否 |消息类型 (private/group)|
|» user_id|body|string| 否 |用户QQ|
|» group_id|body|string| 否 |群号|
|» message|body|any| 是 |OneBot 11 消息混合类型|
|»» *anonymous*|body|[anyOf]| 否 |[OneBot 11 消息段]|
|»»» *anonymous*|body|[OB11MessageText](#schemaob11messagetext)| 否 |纯文本消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» text|body|string| 是 |纯文本内容|
|»»» *anonymous*|body|[OB11MessageFace](#schemaob11messageface)| 否 |QQ表情消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» id|body|string| 是 |表情ID|
|»»»»» resultId|body|string| 否 |结果ID|
|»»»»» chainCount|body|number| 否 |连击数|
|»»» *anonymous*|body|[OB11MessageMFace](#schemaob11messagemface)| 否 |商城表情消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» emoji_package_id|body|number| 是 |表情包ID|
|»»»»» emoji_id|body|string| 是 |表情ID|
|»»»»» key|body|string| 是 |表情key|
|»»»»» summary|body|string| 是 |表情摘要|
|»»» *anonymous*|body|[OB11MessageAt](#schemaob11messageat)| 否 |@消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» qq|body|string| 是 |QQ号或all|
|»»»»» name|body|string| 否 |显示名称|
|»»» *anonymous*|body|[OB11MessageReply](#schemaob11messagereply)| 否 |回复消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» id|body|string| 否 |消息ID的短ID映射|
|»»»»» seq|body|number| 否 |消息序列号，优先使用|
|»»» *anonymous*|body|[OB11MessageImage](#schemaob11messageimage)| 否 |图片消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|any| 是 |none|
|»»»»» *anonymous*|body|object| 否 |文件消息段基础数据|
|»»»»»» file|body|string| 是 |文件路径/URL/file:///|
|»»»»»» path|body|string| 否 |文件路径|
|»»»»»» url|body|string| 否 |文件URL|
|»»»»»» name|body|string| 否 |文件名|
|»»»»»» thumb|body|string| 否 |缩略图|
|»»»»» *anonymous*|body|object| 否 |none|
|»»»»»» summary|body|string| 否 |图片摘要|
|»»»»»» sub_type|body|number| 否 |图片子类型|
|»»» *anonymous*|body|[OB11MessageRecord](#schemaob11messagerecord)| 否 |语音消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|[FileBaseData](#schemafilebasedata)| 是 |文件消息段基础数据|
|»»»»» file|body|string| 是 |文件路径/URL/file:///|
|»»»»» path|body|string| 否 |文件路径|
|»»»»» url|body|string| 否 |文件URL|
|»»»»» name|body|string| 否 |文件名|
|»»»»» thumb|body|string| 否 |缩略图|
|»»» *anonymous*|body|[OB11MessageVideo](#schemaob11messagevideo)| 否 |视频消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|[FileBaseData](#schemafilebasedata)| 是 |文件消息段基础数据|
|»»»»» file|body|string| 是 |文件路径/URL/file:///|
|»»»»» path|body|string| 否 |文件路径|
|»»»»» url|body|string| 否 |文件URL|
|»»»»» name|body|string| 否 |文件名|
|»»»»» thumb|body|string| 否 |缩略图|
|»»» *anonymous*|body|[OB11MessageFile](#schemaob11messagefile)| 否 |文件消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|[FileBaseData](#schemafilebasedata)| 是 |文件消息段基础数据|
|»»»»» file|body|string| 是 |文件路径/URL/file:///|
|»»»»» path|body|string| 否 |文件路径|
|»»»»» url|body|string| 否 |文件URL|
|»»»»» name|body|string| 否 |文件名|
|»»»»» thumb|body|string| 否 |缩略图|
|»»» *anonymous*|body|[OB11MessageIdMusic](#schemaob11messageidmusic)| 否 |ID音乐消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» type|body|string| 是 |音乐平台类型|
|»»»»» id|body|any| 是 |音乐ID|
|»»»»»» *anonymous*|body|string| 否 |none|
|»»»»»» *anonymous*|body|number| 否 |none|
|»»» *anonymous*|body|[OB11MessageCustomMusic](#schemaob11messagecustommusic)| 否 |自定义音乐消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» type|body|string| 是 |音乐平台类型|
|»»»»» id|body|null| 是 |none|
|»»»»» url|body|string| 是 |点击后跳转URL|
|»»»»» audio|body|string| 否 |音频URL|
|»»»»» title|body|string| 否 |音乐标题|
|»»»»» image|body|string| 是 |封面图片URL|
|»»»»» content|body|string| 否 |音乐简介|
|»»» *anonymous*|body|[OB11MessagePoke](#schemaob11messagepoke)| 否 |戳一戳消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» type|body|string| 是 |戳一戳类型|
|»»»»» id|body|string| 是 |戳一戳ID|
|»»» *anonymous*|body|[OB11MessageDice](#schemaob11messagedice)| 否 |骰子消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» result|body|any| 是 |骰子结果|
|»»»»»» *anonymous*|body|number| 否 |none|
|»»»»»» *anonymous*|body|string| 否 |none|
|»»» *anonymous*|body|[OB11MessageRPS](#schemaob11messagerps)| 否 |猜拳消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» result|body|any| 是 |猜拳结果|
|»»»»»» *anonymous*|body|number| 否 |none|
|»»»»»» *anonymous*|body|string| 否 |none|
|»»» *anonymous*|body|[OB11MessageContact](#schemaob11messagecontact)| 否 |联系人消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» type|body|string| 是 |联系人类型|
|»»»»» id|body|string| 是 |联系人ID|
|»»» *anonymous*|body|[OB11MessageLocation](#schemaob11messagelocation)| 否 |位置消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» lat|body|any| 是 |纬度|
|»»»»»» *anonymous*|body|string| 否 |none|
|»»»»»» *anonymous*|body|number| 否 |none|
|»»»»» lon|body|any| 是 |经度|
|»»»»»» *anonymous*|body|string| 否 |none|
|»»»»»» *anonymous*|body|number| 否 |none|
|»»»»» title|body|string| 否 |标题|
|»»»»» content|body|string| 否 |内容|
|»»» *anonymous*|body|[OB11MessageJson](#schemaob11messagejson)| 否 |JSON消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» data|body|any| 是 |JSON数据|
|»»»»»» *anonymous*|body|string| 否 |none|
|»»»»»» *anonymous*|body|object| 否 |none|
|»»»»» config|body|object| 否 |none|
|»»»»»» token|body|string| 是 |token|
|»»» *anonymous*|body|[OB11MessageXml](#schemaob11messagexml)| 否 |XML消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» data|body|string| 是 |XML数据|
|»»» *anonymous*|body|[OB11MessageMarkdown](#schemaob11messagemarkdown)| 否 |Markdown消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» content|body|string| 是 |Markdown内容|
|»»» *anonymous*|body|[OB11MessageMiniApp](#schemaob11messageminiapp)| 否 |小程序消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» data|body|string| 是 |小程序数据|
|»»» *anonymous*|body|[OB11MessageNode](#schemaob11messagenode)| 否 |合并转发消息节点|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» id|body|string| 否 |转发消息ID|
|»»»»» user_id|body|any| 否 |发送者QQ号|
|»»»»»» *anonymous*|body|number| 否 |none|
|»»»»»» *anonymous*|body|string| 否 |none|
|»»»»» uin|body|any| 否 |发送者QQ号(兼容go-cqhttp)|
|»»»»»» *anonymous*|body|number| 否 |none|
|»»»»»» *anonymous*|body|string| 否 |none|
|»»»»» nickname|body|string| 是 |发送者昵称|
|»»»»» name|body|string| 否 |发送者昵称(兼容go-cqhttp)|
|»»»»» content|body|object| 是 |消息内容 (OB11MessageMixType)|
|»»»»» source|body|string| 否 |消息来源|
|»»»»» news|body|[object]| 否 |none|
|»»»»»» text|body|string| 是 |新闻文本|
|»»»»» summary|body|string| 否 |摘要|
|»»»»» prompt|body|string| 否 |提示|
|»»»»» time|body|string| 否 |时间|
|»»» *anonymous*|body|[OB11MessageForward](#schemaob11messageforward)| 否 |合并转发消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» id|body|string| 是 |合并转发ID|
|»»»»» content|body|object| 否 |消息内容 (OB11Message[])|
|»»» *anonymous*|body|[OB11MessageOnlineFile](#schemaob11messageonlinefile)| 否 |在线文件消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» msgId|body|string| 是 |消息ID|
|»»»»» elementId|body|string| 是 |元素ID|
|»»»»» fileName|body|string| 是 |文件名|
|»»»»» fileSize|body|string| 是 |文件大小|
|»»»»» isDir|body|boolean| 是 |是否为目录|
|»»» *anonymous*|body|[OB11MessageFlashTransfer](#schemaob11messageflashtransfer)| 否 |QQ闪传消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» fileSetId|body|string| 是 |文件集ID|
|»» *anonymous*|body|string| 否 |none|
|»» *anonymous*|body|any| 否 |OneBot 11 消息段|
|»»» *anonymous*|body|[OB11MessageText](#schemaob11messagetext)| 否 |纯文本消息段|
|»»» *anonymous*|body|[OB11MessageFace](#schemaob11messageface)| 否 |QQ表情消息段|
|»»» *anonymous*|body|[OB11MessageMFace](#schemaob11messagemface)| 否 |商城表情消息段|
|»»» *anonymous*|body|[OB11MessageAt](#schemaob11messageat)| 否 |@消息段|
|»»» *anonymous*|body|[OB11MessageReply](#schemaob11messagereply)| 否 |回复消息段|
|»»» *anonymous*|body|[OB11MessageImage](#schemaob11messageimage)| 否 |图片消息段|
|»»» *anonymous*|body|[OB11MessageRecord](#schemaob11messagerecord)| 否 |语音消息段|
|»»» *anonymous*|body|[OB11MessageVideo](#schemaob11messagevideo)| 否 |视频消息段|
|»»» *anonymous*|body|[OB11MessageFile](#schemaob11messagefile)| 否 |文件消息段|
|»»» *anonymous*|body|[OB11MessageIdMusic](#schemaob11messageidmusic)| 否 |ID音乐消息段|
|»»» *anonymous*|body|[OB11MessageCustomMusic](#schemaob11messagecustommusic)| 否 |自定义音乐消息段|
|»»» *anonymous*|body|[OB11MessagePoke](#schemaob11messagepoke)| 否 |戳一戳消息段|
|»»» *anonymous*|body|[OB11MessageDice](#schemaob11messagedice)| 否 |骰子消息段|
|»»» *anonymous*|body|[OB11MessageRPS](#schemaob11messagerps)| 否 |猜拳消息段|
|»»» *anonymous*|body|[OB11MessageContact](#schemaob11messagecontact)| 否 |联系人消息段|
|»»» *anonymous*|body|[OB11MessageLocation](#schemaob11messagelocation)| 否 |位置消息段|
|»»» *anonymous*|body|[OB11MessageJson](#schemaob11messagejson)| 否 |JSON消息段|
|»»» *anonymous*|body|[OB11MessageXml](#schemaob11messagexml)| 否 |XML消息段|
|»»» *anonymous*|body|[OB11MessageMarkdown](#schemaob11messagemarkdown)| 否 |Markdown消息段|
|»»» *anonymous*|body|[OB11MessageMiniApp](#schemaob11messageminiapp)| 否 |小程序消息段|
|»»» *anonymous*|body|[OB11MessageNode](#schemaob11messagenode)| 否 |合并转发消息节点|
|»»» *anonymous*|body|[OB11MessageForward](#schemaob11messageforward)| 否 |合并转发消息段|
|»»» *anonymous*|body|[OB11MessageOnlineFile](#schemaob11messageonlinefile)| 否 |在线文件消息段|
|»»» *anonymous*|body|[OB11MessageFlashTransfer](#schemaob11messageflashtransfer)| 否 |QQ闪传消息段|
|» auto_escape|body|any| 否 |是否作为纯文本发送|
|»» *anonymous*|body|boolean| 否 |none|
|»» *anonymous*|body|string| 否 |none|
|» source|body|string| 否 |合并转发来源|
|» news|body|[object]| 否 |合并转发新闻|
|»» text|body|string| 是 |none|
|» summary|body|string| 否 |合并转发摘要|
|» prompt|body|string| 否 |合并转发提示|
|» timeout|body|number| 否 |自定义发送超时(毫秒)，覆盖自动计算值|

#### 枚举值

|属性|值|
|---|---|
|» message_type|private|
|» message_type|group|
|»»»» type|text|
|»»»» type|face|
|»»»» type|mface|
|»»»» type|at|
|»»»» type|reply|
|»»»» type|image|
|»»»» type|record|
|»»»» type|video|
|»»»» type|file|
|»»»» type|music|
|»»»»» type|qq|
|»»»»» type|163|
|»»»»» type|kugou|
|»»»»» type|migu|
|»»»»» type|kuwo|
|»»»» type|music|
|»»»»» type|qq|
|»»»»» type|163|
|»»»»» type|kugou|
|»»»»» type|migu|
|»»»»» type|kuwo|
|»»»»» type|custom|
|»»»» type|poke|
|»»»» type|dice|
|»»»» type|rps|
|»»»» type|contact|
|»»»»» type|qq|
|»»»»» type|group|
|»»»» type|location|
|»»»» type|json|
|»»»» type|xml|
|»»»» type|markdown|
|»»»» type|miniapp|
|»»»» type|node|
|»»»» type|forward|
|»»»» type|onlinefile|
|»»»» type|flashtransfer|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "message_id": 123456
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 发送私聊合并转发消息

POST /send_private_forward_msg

> Body 请求参数

```json
{
    "user_id": "123456789",
    "messages": []
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» message_type|body|string| 否 |消息类型 (private/group)|
|» user_id|body|string| 否 |用户QQ|
|» group_id|body|string| 否 |群号|
|» message|body|any| 是 |OneBot 11 消息混合类型|
|»» *anonymous*|body|[anyOf]| 否 |[OneBot 11 消息段]|
|»»» *anonymous*|body|[OB11MessageText](#schemaob11messagetext)| 否 |纯文本消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» text|body|string| 是 |纯文本内容|
|»»» *anonymous*|body|[OB11MessageFace](#schemaob11messageface)| 否 |QQ表情消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» id|body|string| 是 |表情ID|
|»»»»» resultId|body|string| 否 |结果ID|
|»»»»» chainCount|body|number| 否 |连击数|
|»»» *anonymous*|body|[OB11MessageMFace](#schemaob11messagemface)| 否 |商城表情消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» emoji_package_id|body|number| 是 |表情包ID|
|»»»»» emoji_id|body|string| 是 |表情ID|
|»»»»» key|body|string| 是 |表情key|
|»»»»» summary|body|string| 是 |表情摘要|
|»»» *anonymous*|body|[OB11MessageAt](#schemaob11messageat)| 否 |@消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» qq|body|string| 是 |QQ号或all|
|»»»»» name|body|string| 否 |显示名称|
|»»» *anonymous*|body|[OB11MessageReply](#schemaob11messagereply)| 否 |回复消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» id|body|string| 否 |消息ID的短ID映射|
|»»»»» seq|body|number| 否 |消息序列号，优先使用|
|»»» *anonymous*|body|[OB11MessageImage](#schemaob11messageimage)| 否 |图片消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|any| 是 |none|
|»»»»» *anonymous*|body|object| 否 |文件消息段基础数据|
|»»»»»» file|body|string| 是 |文件路径/URL/file:///|
|»»»»»» path|body|string| 否 |文件路径|
|»»»»»» url|body|string| 否 |文件URL|
|»»»»»» name|body|string| 否 |文件名|
|»»»»»» thumb|body|string| 否 |缩略图|
|»»»»» *anonymous*|body|object| 否 |none|
|»»»»»» summary|body|string| 否 |图片摘要|
|»»»»»» sub_type|body|number| 否 |图片子类型|
|»»» *anonymous*|body|[OB11MessageRecord](#schemaob11messagerecord)| 否 |语音消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|[FileBaseData](#schemafilebasedata)| 是 |文件消息段基础数据|
|»»»»» file|body|string| 是 |文件路径/URL/file:///|
|»»»»» path|body|string| 否 |文件路径|
|»»»»» url|body|string| 否 |文件URL|
|»»»»» name|body|string| 否 |文件名|
|»»»»» thumb|body|string| 否 |缩略图|
|»»» *anonymous*|body|[OB11MessageVideo](#schemaob11messagevideo)| 否 |视频消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|[FileBaseData](#schemafilebasedata)| 是 |文件消息段基础数据|
|»»»»» file|body|string| 是 |文件路径/URL/file:///|
|»»»»» path|body|string| 否 |文件路径|
|»»»»» url|body|string| 否 |文件URL|
|»»»»» name|body|string| 否 |文件名|
|»»»»» thumb|body|string| 否 |缩略图|
|»»» *anonymous*|body|[OB11MessageFile](#schemaob11messagefile)| 否 |文件消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|[FileBaseData](#schemafilebasedata)| 是 |文件消息段基础数据|
|»»»»» file|body|string| 是 |文件路径/URL/file:///|
|»»»»» path|body|string| 否 |文件路径|
|»»»»» url|body|string| 否 |文件URL|
|»»»»» name|body|string| 否 |文件名|
|»»»»» thumb|body|string| 否 |缩略图|
|»»» *anonymous*|body|[OB11MessageIdMusic](#schemaob11messageidmusic)| 否 |ID音乐消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» type|body|string| 是 |音乐平台类型|
|»»»»» id|body|any| 是 |音乐ID|
|»»»»»» *anonymous*|body|string| 否 |none|
|»»»»»» *anonymous*|body|number| 否 |none|
|»»» *anonymous*|body|[OB11MessageCustomMusic](#schemaob11messagecustommusic)| 否 |自定义音乐消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» type|body|string| 是 |音乐平台类型|
|»»»»» id|body|null| 是 |none|
|»»»»» url|body|string| 是 |点击后跳转URL|
|»»»»» audio|body|string| 否 |音频URL|
|»»»»» title|body|string| 否 |音乐标题|
|»»»»» image|body|string| 是 |封面图片URL|
|»»»»» content|body|string| 否 |音乐简介|
|»»» *anonymous*|body|[OB11MessagePoke](#schemaob11messagepoke)| 否 |戳一戳消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» type|body|string| 是 |戳一戳类型|
|»»»»» id|body|string| 是 |戳一戳ID|
|»»» *anonymous*|body|[OB11MessageDice](#schemaob11messagedice)| 否 |骰子消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» result|body|any| 是 |骰子结果|
|»»»»»» *anonymous*|body|number| 否 |none|
|»»»»»» *anonymous*|body|string| 否 |none|
|»»» *anonymous*|body|[OB11MessageRPS](#schemaob11messagerps)| 否 |猜拳消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» result|body|any| 是 |猜拳结果|
|»»»»»» *anonymous*|body|number| 否 |none|
|»»»»»» *anonymous*|body|string| 否 |none|
|»»» *anonymous*|body|[OB11MessageContact](#schemaob11messagecontact)| 否 |联系人消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» type|body|string| 是 |联系人类型|
|»»»»» id|body|string| 是 |联系人ID|
|»»» *anonymous*|body|[OB11MessageLocation](#schemaob11messagelocation)| 否 |位置消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» lat|body|any| 是 |纬度|
|»»»»»» *anonymous*|body|string| 否 |none|
|»»»»»» *anonymous*|body|number| 否 |none|
|»»»»» lon|body|any| 是 |经度|
|»»»»»» *anonymous*|body|string| 否 |none|
|»»»»»» *anonymous*|body|number| 否 |none|
|»»»»» title|body|string| 否 |标题|
|»»»»» content|body|string| 否 |内容|
|»»» *anonymous*|body|[OB11MessageJson](#schemaob11messagejson)| 否 |JSON消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» data|body|any| 是 |JSON数据|
|»»»»»» *anonymous*|body|string| 否 |none|
|»»»»»» *anonymous*|body|object| 否 |none|
|»»»»» config|body|object| 否 |none|
|»»»»»» token|body|string| 是 |token|
|»»» *anonymous*|body|[OB11MessageXml](#schemaob11messagexml)| 否 |XML消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» data|body|string| 是 |XML数据|
|»»» *anonymous*|body|[OB11MessageMarkdown](#schemaob11messagemarkdown)| 否 |Markdown消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» content|body|string| 是 |Markdown内容|
|»»» *anonymous*|body|[OB11MessageMiniApp](#schemaob11messageminiapp)| 否 |小程序消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» data|body|string| 是 |小程序数据|
|»»» *anonymous*|body|[OB11MessageNode](#schemaob11messagenode)| 否 |合并转发消息节点|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» id|body|string| 否 |转发消息ID|
|»»»»» user_id|body|any| 否 |发送者QQ号|
|»»»»»» *anonymous*|body|number| 否 |none|
|»»»»»» *anonymous*|body|string| 否 |none|
|»»»»» uin|body|any| 否 |发送者QQ号(兼容go-cqhttp)|
|»»»»»» *anonymous*|body|number| 否 |none|
|»»»»»» *anonymous*|body|string| 否 |none|
|»»»»» nickname|body|string| 是 |发送者昵称|
|»»»»» name|body|string| 否 |发送者昵称(兼容go-cqhttp)|
|»»»»» content|body|object| 是 |消息内容 (OB11MessageMixType)|
|»»»»» source|body|string| 否 |消息来源|
|»»»»» news|body|[object]| 否 |none|
|»»»»»» text|body|string| 是 |新闻文本|
|»»»»» summary|body|string| 否 |摘要|
|»»»»» prompt|body|string| 否 |提示|
|»»»»» time|body|string| 否 |时间|
|»»» *anonymous*|body|[OB11MessageForward](#schemaob11messageforward)| 否 |合并转发消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» id|body|string| 是 |合并转发ID|
|»»»»» content|body|object| 否 |消息内容 (OB11Message[])|
|»»» *anonymous*|body|[OB11MessageOnlineFile](#schemaob11messageonlinefile)| 否 |在线文件消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» msgId|body|string| 是 |消息ID|
|»»»»» elementId|body|string| 是 |元素ID|
|»»»»» fileName|body|string| 是 |文件名|
|»»»»» fileSize|body|string| 是 |文件大小|
|»»»»» isDir|body|boolean| 是 |是否为目录|
|»»» *anonymous*|body|[OB11MessageFlashTransfer](#schemaob11messageflashtransfer)| 否 |QQ闪传消息段|
|»»»» type|body|string| 是 |none|
|»»»» data|body|object| 是 |none|
|»»»»» fileSetId|body|string| 是 |文件集ID|
|»» *anonymous*|body|string| 否 |none|
|»» *anonymous*|body|any| 否 |OneBot 11 消息段|
|»»» *anonymous*|body|[OB11MessageText](#schemaob11messagetext)| 否 |纯文本消息段|
|»»» *anonymous*|body|[OB11MessageFace](#schemaob11messageface)| 否 |QQ表情消息段|
|»»» *anonymous*|body|[OB11MessageMFace](#schemaob11messagemface)| 否 |商城表情消息段|
|»»» *anonymous*|body|[OB11MessageAt](#schemaob11messageat)| 否 |@消息段|
|»»» *anonymous*|body|[OB11MessageReply](#schemaob11messagereply)| 否 |回复消息段|
|»»» *anonymous*|body|[OB11MessageImage](#schemaob11messageimage)| 否 |图片消息段|
|»»» *anonymous*|body|[OB11MessageRecord](#schemaob11messagerecord)| 否 |语音消息段|
|»»» *anonymous*|body|[OB11MessageVideo](#schemaob11messagevideo)| 否 |视频消息段|
|»»» *anonymous*|body|[OB11MessageFile](#schemaob11messagefile)| 否 |文件消息段|
|»»» *anonymous*|body|[OB11MessageIdMusic](#schemaob11messageidmusic)| 否 |ID音乐消息段|
|»»» *anonymous*|body|[OB11MessageCustomMusic](#schemaob11messagecustommusic)| 否 |自定义音乐消息段|
|»»» *anonymous*|body|[OB11MessagePoke](#schemaob11messagepoke)| 否 |戳一戳消息段|
|»»» *anonymous*|body|[OB11MessageDice](#schemaob11messagedice)| 否 |骰子消息段|
|»»» *anonymous*|body|[OB11MessageRPS](#schemaob11messagerps)| 否 |猜拳消息段|
|»»» *anonymous*|body|[OB11MessageContact](#schemaob11messagecontact)| 否 |联系人消息段|
|»»» *anonymous*|body|[OB11MessageLocation](#schemaob11messagelocation)| 否 |位置消息段|
|»»» *anonymous*|body|[OB11MessageJson](#schemaob11messagejson)| 否 |JSON消息段|
|»»» *anonymous*|body|[OB11MessageXml](#schemaob11messagexml)| 否 |XML消息段|
|»»» *anonymous*|body|[OB11MessageMarkdown](#schemaob11messagemarkdown)| 否 |Markdown消息段|
|»»» *anonymous*|body|[OB11MessageMiniApp](#schemaob11messageminiapp)| 否 |小程序消息段|
|»»» *anonymous*|body|[OB11MessageNode](#schemaob11messagenode)| 否 |合并转发消息节点|
|»»» *anonymous*|body|[OB11MessageForward](#schemaob11messageforward)| 否 |合并转发消息段|
|»»» *anonymous*|body|[OB11MessageOnlineFile](#schemaob11messageonlinefile)| 否 |在线文件消息段|
|»»» *anonymous*|body|[OB11MessageFlashTransfer](#schemaob11messageflashtransfer)| 否 |QQ闪传消息段|
|» auto_escape|body|any| 否 |是否作为纯文本发送|
|»» *anonymous*|body|boolean| 否 |none|
|»» *anonymous*|body|string| 否 |none|
|» source|body|string| 否 |合并转发来源|
|» news|body|[object]| 否 |合并转发新闻|
|»» text|body|string| 是 |none|
|» summary|body|string| 否 |合并转发摘要|
|» prompt|body|string| 否 |合并转发提示|
|» timeout|body|number| 否 |自定义发送超时(毫秒)，覆盖自动计算值|

#### 枚举值

|属性|值|
|---|---|
|» message_type|private|
|» message_type|group|
|»»»» type|text|
|»»»» type|face|
|»»»» type|mface|
|»»»» type|at|
|»»»» type|reply|
|»»»» type|image|
|»»»» type|record|
|»»»» type|video|
|»»»» type|file|
|»»»» type|music|
|»»»»» type|qq|
|»»»»» type|163|
|»»»»» type|kugou|
|»»»»» type|migu|
|»»»»» type|kuwo|
|»»»» type|music|
|»»»»» type|qq|
|»»»»» type|163|
|»»»»» type|kugou|
|»»»»» type|migu|
|»»»»» type|kuwo|
|»»»»» type|custom|
|»»»» type|poke|
|»»»» type|dice|
|»»»» type|rps|
|»»»» type|contact|
|»»»»» type|qq|
|»»»»» type|group|
|»»»» type|location|
|»»»» type|json|
|»»»» type|xml|
|»»»» type|markdown|
|»»»» type|miniapp|
|»»»» type|node|
|»»»» type|forward|
|»»»» type|onlinefile|
|»»»» type|flashtransfer|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "message_id": 123456
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取陌生人信息

POST /get_stranger_info

获取指定非好友用户的信息

> Body 请求参数

```json
{
    "user_id": "123456789"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» user_id|body|string| 是 |用户QQ|
|» no_cache|body|any| 是 |是否不使用缓存|
|»» *anonymous*|body|boolean| 否 |none|
|»» *anonymous*|body|string| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "user_id": 123456789,
        "nickname": "昵称",
        "sex": "unknown"
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 下载文件

POST /download_file

下载网络文件到本地临时目录

> Body 请求参数

```json
{
    "url": "https://example.com/file.png",
    "thread_count": 1,
    "headers": "User-Agent: NapCat"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» url|body|string| 否 |下载链接|
|» base64|body|string| 否 |base64数据|
|» name|body|string| 否 |文件名|
|» headers|body|any| 否 |请求头|
|»» *anonymous*|body|string| 否 |none|
|»» *anonymous*|body|[string]| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "file": "/path/to/downloaded/file"
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 上传群文件

POST /upload_group_file

上传资源路径或URL指定的文件到指定群聊的文件系统中

> Body 请求参数

```json
{
    "group_id": "123456",
    "file": "/path/to/file",
    "name": "test.txt"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» file|body|string| 是 |资源路径或URL|
|» name|body|string| 是 |文件名|
|» folder|body|string| 否 |父目录 ID|
|» folder_id|body|string| 否 |父目录 ID (兼容性字段)|
|» upload_file|body|boolean| 是 |是否执行上传|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "file_id": "file_uuid_123"
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取群历史消息

POST /get_group_msg_history

获取指定群聊的历史聊天记录

> Body 请求参数

```json
{
    "group_id": "123456",
    "message_seq": 0,
    "count": 20
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» message_seq|body|string| 否 |起始消息序号|
|» count|body|number| 是 |获取消息数量|
|» reverse_order|body|boolean| 是 |是否反向排序|
|» disable_get_url|body|boolean| 是 |是否禁用获取URL|
|» parse_mult_msg|body|boolean| 是 |是否解析合并消息|
|» quick_reply|body|boolean| 是 |是否快速回复|
|» reverseOrder|body|boolean| 是 |是否反向排序(旧版本兼容)|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "messages": []
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取好友历史消息

POST /get_friend_msg_history

获取指定好友的历史聊天记录

> Body 请求参数

```json
{
    "user_id": "123456789",
    "message_seq": 0,
    "count": 20
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» user_id|body|string| 是 |用户QQ|
|» message_seq|body|string| 否 |起始消息序号|
|» count|body|number| 是 |获取消息数量|
|» reverse_order|body|boolean| 是 |是否反向排序|
|» disable_get_url|body|boolean| 是 |是否禁用获取URL|
|» parse_mult_msg|body|boolean| 是 |是否解析合并消息|
|» quick_reply|body|boolean| 是 |是否快速回复|
|» reverseOrder|body|boolean| 是 |是否反向排序(旧版本兼容)|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "messages": []
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 处理快速操作

POST /.handle_quick_operation

处理来自事件上报的快速操作请求

> Body 请求参数

```json
{
    "context": {},
    "operation": {}
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» context|body|object| 是 |事件上下文|
|»» time|body|number| 是 |事件发生时间|
|»» self_id|body|number| 是 |收到事件的机器人 QQ 号|
|»» post_type|body|string| 是 |上报类型|
|»» message_type|body|string| 否 |消息类型|
|»» sub_type|body|string| 否 |消息子类型|
|»» user_id|body|string| 是 |发送者 QQ 号|
|»» group_id|body|string| 否 |群号|
|»» message_id|body|number| 否 |消息 ID|
|»» message_seq|body|number| 否 |消息序列号|
|»» real_id|body|number| 否 |真实消息 ID|
|»» sender|body|object| 否 |none|
|»»» user_id|body|string| 是 |用户ID|
|»»» nickname|body|string| 是 |昵称|
|»»» sex|body|string| 否 |性别|
|»»» age|body|number| 否 |年龄|
|»»» card|body|string| 否 |群名片|
|»»» level|body|string| 否 |群等级|
|»»» role|body|string| 否 |群角色|
|»» message|body|object| 否 |消息内容|
|»» message_format|body|string| 否 |消息格式|
|»» raw_message|body|string| 否 |原始消息内容|
|»» font|body|number| 否 |字体|
|»» notice_type|body|string| 否 |通知类型|
|»» meta_event_type|body|string| 否 |元事件类型|
|» operation|body|object| 是 |快速操作内容|
|»» reply|body|any| 否 |OneBot 11 消息混合类型|
|»»» *anonymous*|body|[anyOf]| 否 |[OneBot 11 消息段]|
|»»»» *anonymous*|body|[OB11MessageText](#schemaob11messagetext)| 否 |纯文本消息段|
|»»»»» type|body|string| 是 |none|
|»»»»» data|body|object| 是 |none|
|»»»»»» text|body|string| 是 |纯文本内容|
|»»»» *anonymous*|body|[OB11MessageFace](#schemaob11messageface)| 否 |QQ表情消息段|
|»»»»» type|body|string| 是 |none|
|»»»»» data|body|object| 是 |none|
|»»»»»» id|body|string| 是 |表情ID|
|»»»»»» resultId|body|string| 否 |结果ID|
|»»»»»» chainCount|body|number| 否 |连击数|
|»»»» *anonymous*|body|[OB11MessageMFace](#schemaob11messagemface)| 否 |商城表情消息段|
|»»»»» type|body|string| 是 |none|
|»»»»» data|body|object| 是 |none|
|»»»»»» emoji_package_id|body|number| 是 |表情包ID|
|»»»»»» emoji_id|body|string| 是 |表情ID|
|»»»»»» key|body|string| 是 |表情key|
|»»»»»» summary|body|string| 是 |表情摘要|
|»»»» *anonymous*|body|[OB11MessageAt](#schemaob11messageat)| 否 |@消息段|
|»»»»» type|body|string| 是 |none|
|»»»»» data|body|object| 是 |none|
|»»»»»» qq|body|string| 是 |QQ号或all|
|»»»»»» name|body|string| 否 |显示名称|
|»»»» *anonymous*|body|[OB11MessageReply](#schemaob11messagereply)| 否 |回复消息段|
|»»»»» type|body|string| 是 |none|
|»»»»» data|body|object| 是 |none|
|»»»»»» id|body|string| 否 |消息ID的短ID映射|
|»»»»»» seq|body|number| 否 |消息序列号，优先使用|
|»»»» *anonymous*|body|[OB11MessageImage](#schemaob11messageimage)| 否 |图片消息段|
|»»»»» type|body|string| 是 |none|
|»»»»» data|body|any| 是 |none|
|»»»»»» *anonymous*|body|object| 否 |文件消息段基础数据|
|»»»»»»» file|body|string| 是 |文件路径/URL/file:///|
|»»»»»»» path|body|string| 否 |文件路径|
|»»»»»»» url|body|string| 否 |文件URL|
|»»»»»»» name|body|string| 否 |文件名|
|»»»»»»» thumb|body|string| 否 |缩略图|
|»»»»»» *anonymous*|body|object| 否 |none|
|»»»»»»» summary|body|string| 否 |图片摘要|
|»»»»»»» sub_type|body|number| 否 |图片子类型|
|»»»» *anonymous*|body|[OB11MessageRecord](#schemaob11messagerecord)| 否 |语音消息段|
|»»»»» type|body|string| 是 |none|
|»»»»» data|body|[FileBaseData](#schemafilebasedata)| 是 |文件消息段基础数据|
|»»»»»» file|body|string| 是 |文件路径/URL/file:///|
|»»»»»» path|body|string| 否 |文件路径|
|»»»»»» url|body|string| 否 |文件URL|
|»»»»»» name|body|string| 否 |文件名|
|»»»»»» thumb|body|string| 否 |缩略图|
|»»»» *anonymous*|body|[OB11MessageVideo](#schemaob11messagevideo)| 否 |视频消息段|
|»»»»» type|body|string| 是 |none|
|»»»»» data|body|[FileBaseData](#schemafilebasedata)| 是 |文件消息段基础数据|
|»»»»»» file|body|string| 是 |文件路径/URL/file:///|
|»»»»»» path|body|string| 否 |文件路径|
|»»»»»» url|body|string| 否 |文件URL|
|»»»»»» name|body|string| 否 |文件名|
|»»»»»» thumb|body|string| 否 |缩略图|
|»»»» *anonymous*|body|[OB11MessageFile](#schemaob11messagefile)| 否 |文件消息段|
|»»»»» type|body|string| 是 |none|
|»»»»» data|body|[FileBaseData](#schemafilebasedata)| 是 |文件消息段基础数据|
|»»»»»» file|body|string| 是 |文件路径/URL/file:///|
|»»»»»» path|body|string| 否 |文件路径|
|»»»»»» url|body|string| 否 |文件URL|
|»»»»»» name|body|string| 否 |文件名|
|»»»»»» thumb|body|string| 否 |缩略图|
|»»»» *anonymous*|body|[OB11MessageIdMusic](#schemaob11messageidmusic)| 否 |ID音乐消息段|
|»»»»» type|body|string| 是 |none|
|»»»»» data|body|object| 是 |none|
|»»»»»» type|body|string| 是 |音乐平台类型|
|»»»»»» id|body|any| 是 |音乐ID|
|»»»»»»» *anonymous*|body|string| 否 |none|
|»»»»»»» *anonymous*|body|number| 否 |none|
|»»»» *anonymous*|body|[OB11MessageCustomMusic](#schemaob11messagecustommusic)| 否 |自定义音乐消息段|
|»»»»» type|body|string| 是 |none|
|»»»»» data|body|object| 是 |none|
|»»»»»» type|body|string| 是 |音乐平台类型|
|»»»»»» id|body|null| 是 |none|
|»»»»»» url|body|string| 是 |点击后跳转URL|
|»»»»»» audio|body|string| 否 |音频URL|
|»»»»»» title|body|string| 否 |音乐标题|
|»»»»»» image|body|string| 是 |封面图片URL|
|»»»»»» content|body|string| 否 |音乐简介|
|»»»» *anonymous*|body|[OB11MessagePoke](#schemaob11messagepoke)| 否 |戳一戳消息段|
|»»»»» type|body|string| 是 |none|
|»»»»» data|body|object| 是 |none|
|»»»»»» type|body|string| 是 |戳一戳类型|
|»»»»»» id|body|string| 是 |戳一戳ID|
|»»»» *anonymous*|body|[OB11MessageDice](#schemaob11messagedice)| 否 |骰子消息段|
|»»»»» type|body|string| 是 |none|
|»»»»» data|body|object| 是 |none|
|»»»»»» result|body|any| 是 |骰子结果|
|»»»»»»» *anonymous*|body|number| 否 |none|
|»»»»»»» *anonymous*|body|string| 否 |none|
|»»»» *anonymous*|body|[OB11MessageRPS](#schemaob11messagerps)| 否 |猜拳消息段|
|»»»»» type|body|string| 是 |none|
|»»»»» data|body|object| 是 |none|
|»»»»»» result|body|any| 是 |猜拳结果|
|»»»»»»» *anonymous*|body|number| 否 |none|
|»»»»»»» *anonymous*|body|string| 否 |none|
|»»»» *anonymous*|body|[OB11MessageContact](#schemaob11messagecontact)| 否 |联系人消息段|
|»»»»» type|body|string| 是 |none|
|»»»»» data|body|object| 是 |none|
|»»»»»» type|body|string| 是 |联系人类型|
|»»»»»» id|body|string| 是 |联系人ID|
|»»»» *anonymous*|body|[OB11MessageLocation](#schemaob11messagelocation)| 否 |位置消息段|
|»»»»» type|body|string| 是 |none|
|»»»»» data|body|object| 是 |none|
|»»»»»» lat|body|any| 是 |纬度|
|»»»»»»» *anonymous*|body|string| 否 |none|
|»»»»»»» *anonymous*|body|number| 否 |none|
|»»»»»» lon|body|any| 是 |经度|
|»»»»»»» *anonymous*|body|string| 否 |none|
|»»»»»»» *anonymous*|body|number| 否 |none|
|»»»»»» title|body|string| 否 |标题|
|»»»»»» content|body|string| 否 |内容|
|»»»» *anonymous*|body|[OB11MessageJson](#schemaob11messagejson)| 否 |JSON消息段|
|»»»»» type|body|string| 是 |none|
|»»»»» data|body|object| 是 |none|
|»»»»»» data|body|any| 是 |JSON数据|
|»»»»»»» *anonymous*|body|string| 否 |none|
|»»»»»»» *anonymous*|body|object| 否 |none|
|»»»»»» config|body|object| 否 |none|
|»»»»»»» token|body|string| 是 |token|
|»»»» *anonymous*|body|[OB11MessageXml](#schemaob11messagexml)| 否 |XML消息段|
|»»»»» type|body|string| 是 |none|
|»»»»» data|body|object| 是 |none|
|»»»»»» data|body|string| 是 |XML数据|
|»»»» *anonymous*|body|[OB11MessageMarkdown](#schemaob11messagemarkdown)| 否 |Markdown消息段|
|»»»»» type|body|string| 是 |none|
|»»»»» data|body|object| 是 |none|
|»»»»»» content|body|string| 是 |Markdown内容|
|»»»» *anonymous*|body|[OB11MessageMiniApp](#schemaob11messageminiapp)| 否 |小程序消息段|
|»»»»» type|body|string| 是 |none|
|»»»»» data|body|object| 是 |none|
|»»»»»» data|body|string| 是 |小程序数据|
|»»»» *anonymous*|body|[OB11MessageNode](#schemaob11messagenode)| 否 |合并转发消息节点|
|»»»»» type|body|string| 是 |none|
|»»»»» data|body|object| 是 |none|
|»»»»»» id|body|string| 否 |转发消息ID|
|»»»»»» user_id|body|any| 否 |发送者QQ号|
|»»»»»»» *anonymous*|body|number| 否 |none|
|»»»»»»» *anonymous*|body|string| 否 |none|
|»»»»»» uin|body|any| 否 |发送者QQ号(兼容go-cqhttp)|
|»»»»»»» *anonymous*|body|number| 否 |none|
|»»»»»»» *anonymous*|body|string| 否 |none|
|»»»»»» nickname|body|string| 是 |发送者昵称|
|»»»»»» name|body|string| 否 |发送者昵称(兼容go-cqhttp)|
|»»»»»» content|body|object| 是 |消息内容 (OB11MessageMixType)|
|»»»»»» source|body|string| 否 |消息来源|
|»»»»»» news|body|[object]| 否 |none|
|»»»»»»» text|body|string| 是 |新闻文本|
|»»»»»» summary|body|string| 否 |摘要|
|»»»»»» prompt|body|string| 否 |提示|
|»»»»»» time|body|string| 否 |时间|
|»»»» *anonymous*|body|[OB11MessageForward](#schemaob11messageforward)| 否 |合并转发消息段|
|»»»»» type|body|string| 是 |none|
|»»»»» data|body|object| 是 |none|
|»»»»»» id|body|string| 是 |合并转发ID|
|»»»»»» content|body|object| 否 |消息内容 (OB11Message[])|
|»»»» *anonymous*|body|[OB11MessageOnlineFile](#schemaob11messageonlinefile)| 否 |在线文件消息段|
|»»»»» type|body|string| 是 |none|
|»»»»» data|body|object| 是 |none|
|»»»»»» msgId|body|string| 是 |消息ID|
|»»»»»» elementId|body|string| 是 |元素ID|
|»»»»»» fileName|body|string| 是 |文件名|
|»»»»»» fileSize|body|string| 是 |文件大小|
|»»»»»» isDir|body|boolean| 是 |是否为目录|
|»»»» *anonymous*|body|[OB11MessageFlashTransfer](#schemaob11messageflashtransfer)| 否 |QQ闪传消息段|
|»»»»» type|body|string| 是 |none|
|»»»»» data|body|object| 是 |none|
|»»»»»» fileSetId|body|string| 是 |文件集ID|
|»»» *anonymous*|body|string| 否 |none|
|»»» *anonymous*|body|any| 否 |OneBot 11 消息段|
|»»»» *anonymous*|body|[OB11MessageText](#schemaob11messagetext)| 否 |纯文本消息段|
|»»»» *anonymous*|body|[OB11MessageFace](#schemaob11messageface)| 否 |QQ表情消息段|
|»»»» *anonymous*|body|[OB11MessageMFace](#schemaob11messagemface)| 否 |商城表情消息段|
|»»»» *anonymous*|body|[OB11MessageAt](#schemaob11messageat)| 否 |@消息段|
|»»»» *anonymous*|body|[OB11MessageReply](#schemaob11messagereply)| 否 |回复消息段|
|»»»» *anonymous*|body|[OB11MessageImage](#schemaob11messageimage)| 否 |图片消息段|
|»»»» *anonymous*|body|[OB11MessageRecord](#schemaob11messagerecord)| 否 |语音消息段|
|»»»» *anonymous*|body|[OB11MessageVideo](#schemaob11messagevideo)| 否 |视频消息段|
|»»»» *anonymous*|body|[OB11MessageFile](#schemaob11messagefile)| 否 |文件消息段|
|»»»» *anonymous*|body|[OB11MessageIdMusic](#schemaob11messageidmusic)| 否 |ID音乐消息段|
|»»»» *anonymous*|body|[OB11MessageCustomMusic](#schemaob11messagecustommusic)| 否 |自定义音乐消息段|
|»»»» *anonymous*|body|[OB11MessagePoke](#schemaob11messagepoke)| 否 |戳一戳消息段|
|»»»» *anonymous*|body|[OB11MessageDice](#schemaob11messagedice)| 否 |骰子消息段|
|»»»» *anonymous*|body|[OB11MessageRPS](#schemaob11messagerps)| 否 |猜拳消息段|
|»»»» *anonymous*|body|[OB11MessageContact](#schemaob11messagecontact)| 否 |联系人消息段|
|»»»» *anonymous*|body|[OB11MessageLocation](#schemaob11messagelocation)| 否 |位置消息段|
|»»»» *anonymous*|body|[OB11MessageJson](#schemaob11messagejson)| 否 |JSON消息段|
|»»»» *anonymous*|body|[OB11MessageXml](#schemaob11messagexml)| 否 |XML消息段|
|»»»» *anonymous*|body|[OB11MessageMarkdown](#schemaob11messagemarkdown)| 否 |Markdown消息段|
|»»»» *anonymous*|body|[OB11MessageMiniApp](#schemaob11messageminiapp)| 否 |小程序消息段|
|»»»» *anonymous*|body|[OB11MessageNode](#schemaob11messagenode)| 否 |合并转发消息节点|
|»»»» *anonymous*|body|[OB11MessageForward](#schemaob11messageforward)| 否 |合并转发消息段|
|»»»» *anonymous*|body|[OB11MessageOnlineFile](#schemaob11messageonlinefile)| 否 |在线文件消息段|
|»»»» *anonymous*|body|[OB11MessageFlashTransfer](#schemaob11messageflashtransfer)| 否 |QQ闪传消息段|
|»» auto_escape|body|boolean| 否 |是否作为纯文本发送|
|»» at_sender|body|boolean| 否 |是否 @ 发送者|
|»» delete|body|boolean| 否 |是否撤回该消息|
|»» kick|body|boolean| 否 |是否踢出发送者|
|»» ban|body|boolean| 否 |是否禁言发送者|
|»» ban_duration|body|number| 否 |禁言时长|
|»» approve|body|boolean| 否 |是否同意请求/加群|
|»» remark|body|string| 否 |好友备注|
|»» reason|body|string| 否 |拒绝理由|

#### 枚举值

|属性|值|
|---|---|
|»»»»» type|text|
|»»»»» type|face|
|»»»»» type|mface|
|»»»»» type|at|
|»»»»» type|reply|
|»»»»» type|image|
|»»»»» type|record|
|»»»»» type|video|
|»»»»» type|file|
|»»»»» type|music|
|»»»»»» type|qq|
|»»»»»» type|163|
|»»»»»» type|kugou|
|»»»»»» type|migu|
|»»»»»» type|kuwo|
|»»»»» type|music|
|»»»»»» type|qq|
|»»»»»» type|163|
|»»»»»» type|kugou|
|»»»»»» type|migu|
|»»»»»» type|kuwo|
|»»»»»» type|custom|
|»»»»» type|poke|
|»»»»» type|dice|
|»»»»» type|rps|
|»»»»» type|contact|
|»»»»»» type|qq|
|»»»»»» type|group|
|»»»»» type|location|
|»»»»» type|json|
|»»»»» type|xml|
|»»»»» type|markdown|
|»»»»» type|miniapp|
|»»»»» type|node|
|»»»»» type|forward|
|»»»»» type|onlinefile|
|»»»»» type|flashtransfer|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 设置群头像

POST /set_group_portrait

修改指定群聊的头像

> Body 请求参数

```json
{
    "group_id": "123456",
    "file": "base64://..."
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» file|body|string| 是 |头像文件路径或 URL|
|» group_id|body|string| 是 |群号|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "result": 0,
        "errMsg": ""
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 上传私聊文件

POST /upload_private_file

上传本地文件到指定私聊会话中

> Body 请求参数

```json
{
    "user_id": "123456789",
    "file": "/path/to/file",
    "name": "test.txt"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» user_id|body|string| 是 |用户 QQ|
|» file|body|string| 是 |资源路径或URL|
|» name|body|string| 是 |文件名|
|» upload_file|body|boolean| 是 |是否执行上传|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "file_id": "file_uuid_123"
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取机型显示

POST /_get_model_show

获取当前账号可用的设备机型显示名称列表

> Body 请求参数

```json
{
    "model": "iPhone 13"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» model|body|string| 否 |模型名称|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "variants": []
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 设置机型

POST /_set_model_show

设置当前账号的设备机型名称

> Body 请求参数

```json
{
    "model": "iPhone 13",
    "model_show": "iPhone 13"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 删除群文件

POST /delete_group_file

在群文件系统中删除指定的文件

> Body 请求参数

```json
{
    "group_id": "123456",
    "file_id": "file_uuid_123"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» file_id|body|string| 是 |文件ID|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 创建群文件目录

POST /create_group_file_folder

在群文件系统中创建新的文件夹

> Body 请求参数

```json
{
    "group_id": "123456789",
    "folder_name": "新建文件夹"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» folder_name|body|string| 否 |文件夹名称|
|» name|body|string| 否 |文件夹名称|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "result": {},
        "groupItem": {}
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 删除群文件目录

POST /delete_group_folder

在群文件系统中删除指定的文件夹

> Body 请求参数

```json
{
    "group_id": "123456",
    "folder_id": "folder_uuid_123"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» folder_id|body|string| 否 |文件夹ID|
|» folder|body|string| 否 |文件夹ID|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取群文件系统信息

POST /get_group_file_system_info

获取群聊文件系统的空间及状态信息

> Body 请求参数

```json
{
    "group_id": "123456"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "file_count": 10,
        "limit_count": 10000,
        "used_space": 1024,
        "total_space": 10737418240
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取群文件夹文件列表

POST /get_group_files_by_folder

获取指定群文件夹下的文件及子文件夹列表

> Body 请求参数

```json
{
    "group_id": "123456",
    "folder_id": "folder_id"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» folder_id|body|string| 否 |文件夹ID|
|» folder|body|string| 否 |文件夹ID|
|» file_count|body|any| 是 |文件数量|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "files": [],
        "folders": []
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

# 消息接口

## POST 转发单条消息

POST /forward_friend_single_msg

转发单条消息

> Body 请求参数

```json
{
    "message_id": 12345,
    "group_id": "123456"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» message_id|body|any| 是 |消息ID|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|
|» group_id|body|string| 否 |目标群号|
|» user_id|body|string| 否 |目标用户QQ|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 转发单条消息

POST /forward_group_single_msg

转发单条消息

> Body 请求参数

```json
{
    "message_id": 12345,
    "group_id": "123456"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» message_id|body|any| 是 |消息ID|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|
|» group_id|body|string| 否 |目标群号|
|» user_id|body|string| 否 |目标用户QQ|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 标记群聊已读

POST /mark_group_msg_as_read

标记指定渠道的消息为已读

> Body 请求参数

```json
{
    "message_id": 12345
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» user_id|body|any| 否 |用户QQ|
|»» *anonymous*|body|string| 否 |none|
|»» *anonymous*|body|number| 否 |none|
|» group_id|body|string| 否 |群号|
|» message_id|body|string| 否 |消息ID|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 标记私聊已读

POST /mark_private_msg_as_read

标记指定渠道的消息为已读

> Body 请求参数

```json
{
    "message_id": 12345
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» user_id|body|any| 否 |用户QQ|
|»» *anonymous*|body|string| 否 |none|
|»» *anonymous*|body|number| 否 |none|
|» group_id|body|string| 否 |群号|
|» message_id|body|string| 否 |消息ID|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 撤回消息

POST /delete_msg

撤回已发送的消息

> Body 请求参数

```json
{
    "message_id": 12345
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» message_id|body|any| 是 |消息ID|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 标记消息已读 (Go-CQHTTP)

POST /mark_msg_as_read

标记指定渠道的消息为已读

> Body 请求参数

```json
{
    "message_id": 12345
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» user_id|body|any| 否 |用户QQ|
|»» *anonymous*|body|string| 否 |none|
|»» *anonymous*|body|number| 否 |none|
|» group_id|body|string| 否 |群号|
|» message_id|body|string| 否 |消息ID|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 标记所有消息已读

POST /_mark_all_as_read

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

# 文件扩展

## POST 移动群文件

POST /move_group_file

> Body 请求参数

```json
{
    "group_id": "123456",
    "file_id": "/file_id",
    "current_parent_directory": "/current_folder_id",
    "target_parent_directory": "/target_folder_id"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» file_id|body|string| 是 |文件ID|
|» current_parent_directory|body|string| 是 |当前父目录|
|» target_parent_directory|body|string| 是 |目标父目录|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "ok": true
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 重命名群文件

POST /rename_group_file

> Body 请求参数

```json
{
    "group_id": "123456",
    "file_id": "/file_id",
    "current_parent_directory": "/",
    "new_name": "new_name.jpg"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» file_id|body|string| 是 |文件ID|
|» current_parent_directory|body|string| 是 |当前父目录|
|» new_name|body|string| 是 |新文件名|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "ok": true
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 传输群文件

POST /trans_group_file

> Body 请求参数

```json
{
    "group_id": "123456",
    "file_id": "/file_id"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» group_id|body|string| 是 |群号|
|» file_id|body|string| 是 |文件ID|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "ok": true
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 创建闪传任务

POST /create_flash_task

> Body 请求参数

```json
{
    "files": "C:\\test.jpg",
    "name": "test_task"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» files|body|any| 是 |文件列表或单个文件路径|
|»» *anonymous*|body|[string]| 否 |none|
|»» *anonymous*|body|string| 否 |none|
|» name|body|string| 否 |任务名称|
|» thumb_path|body|string| 否 |缩略图路径|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "task_id": "task_123"
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取闪传文件列表

POST /get_flash_file_list

> Body 请求参数

```json
{
    "fileset_id": "set_123"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» fileset_id|body|string| 是 |文件集 ID|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": [
        {
            "file_name": "test.jpg",
            "size": 1024
        }
    ],
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取闪传文件链接

POST /get_flash_file_url

> Body 请求参数

```json
{
    "fileset_id": "set_123"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» fileset_id|body|string| 是 |文件集 ID|
|» file_name|body|string| 否 |文件名|
|» file_index|body|number| 否 |文件索引|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "url": "http://example.com/flash.jpg"
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 发送闪传消息

POST /send_flash_msg

> Body 请求参数

```json
{
    "fileset_id": "set_123",
    "user_id": "123456789"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» fileset_id|body|string| 是 |文件集 ID|
|» user_id|body|string| 否 |用户 QQ|
|» group_id|body|string| 否 |群号|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "message_id": 123456
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取文件分享链接

POST /get_share_link

> Body 请求参数

```json
{
    "fileset_id": "set_123"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» fileset_id|body|string| 是 |文件集 ID|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": "http://example.com/share",
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取文件集信息

POST /get_fileset_info

> Body 请求参数

```json
{
    "fileset_id": "set_123"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» fileset_id|body|string| 是 |文件集 ID|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "fileset_id": "set_123",
        "file_list": []
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取在线文件消息

POST /get_online_file_msg

> Body 请求参数

```json
{
    "user_id": "123456789"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» user_id|body|string| 是 |用户 QQ|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 发送在线文件

POST /send_online_file

> Body 请求参数

```json
{
    "user_id": "123456789",
    "file_path": "C:\\path\\to\\file.txt",
    "file_name": "test.txt"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» user_id|body|string| 是 |用户 QQ|
|» file_path|body|string| 是 |本地文件路径|
|» file_name|body|string| 否 |文件名 (可选)|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 发送在线文件夹

POST /send_online_folder

> Body 请求参数

```json
{
    "user_id": "123456789",
    "folder_path": "C:\\path\\to\\folder"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» user_id|body|string| 是 |用户 QQ|
|» folder_path|body|string| 是 |本地文件夹路径|
|» folder_name|body|string| 否 |文件夹名称 (可选)|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 接收在线文件

POST /receive_online_file

> Body 请求参数

```json
{
    "user_id": "123456789",
    "msg_id": "123",
    "save_path": "C:\\save"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» user_id|body|string| 是 |用户 QQ|
|» msg_id|body|string| 是 |消息 ID|
|» element_id|body|string| 是 |元素 ID|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 拒绝在线文件

POST /refuse_online_file

> Body 请求参数

```json
{
    "user_id": "123456789",
    "msg_id": "123"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» user_id|body|string| 是 |用户 QQ|
|» msg_id|body|string| 是 |消息 ID|
|» element_id|body|string| 是 |元素 ID|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 取消在线文件

POST /cancel_online_file

> Body 请求参数

```json
{
    "user_id": "123456789",
    "msg_id": "123"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» user_id|body|string| 是 |用户 QQ|
|» msg_id|body|string| 是 |消息 ID|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 下载文件集

POST /download_fileset

> Body 请求参数

```json
{
    "fileset_id": "set_123"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» fileset_id|body|string| 是 |文件集 ID|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取文件集 ID

POST /get_fileset_id

> Body 请求参数

```json
{
    "share_code": "123456"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» share_code|body|string| 是 |分享码或分享链接|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "fileset_id": "set_123"
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

# 用户扩展

## POST 获取带分组的好友列表

POST /get_friends_with_category

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": [
        {
            "categoryId": 1,
            "categoryName": "我的好友",
            "categoryMbCount": 1,
            "buddyList": []
        }
    ],
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取资料点赞

POST /get_profile_like

> Body 请求参数

```json
{
    "user_id": "123456789",
    "start": 0,
    "count": 10
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» user_id|body|string| 否 |QQ号|
|» start|body|any| 是 |起始位置|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|
|» count|body|any| 是 |获取数量|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "uid": "u_123",
        "time": "1734567890",
        "favoriteInfo": {
            "userInfos": [],
            "total_count": 10,
            "last_time": 1734567890,
            "today_count": 5
        },
        "voteInfo": {
            "total_count": 100,
            "new_count": 2,
            "new_nearby_count": 0,
            "last_visit_time": 1734567890,
            "userInfos": []
        }
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 设置自定义在线状态

POST /set_diy_online_status

设置自定义在线状态

> Body 请求参数

```json
{
    "face_id": "123",
    "face_type": "1",
    "wording": "自定义状态"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» face_id|body|any| 是 |图标ID|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|
|» face_type|body|any| 是 |图标类型|
|»» *anonymous*|body|number| 否 |none|
|»» *anonymous*|body|string| 否 |none|
|» wording|body|string| 是 |状态文字内容|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": "",
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取单向好友列表

POST /get_unidirectional_friend_list

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": [
        {
            "uin": 123456789,
            "uid": "u_123",
            "nick_name": "单向好友",
            "age": 20,
            "source": "来源"
        }
    ],
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

# 频道接口

## POST 获取频道列表

POST /get_guild_list

获取当前帐号已加入的频道列表

> Body 请求参数

```json
{}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": [
        {
            "guild_id": "123456",
            "guild_name": "测试频道"
        }
    ],
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 获取频道个人信息

POST /get_guild_service_profile

获取当前帐号在频道中的个人资料

> Body 请求参数

```json
{
    "guild_id": "123456"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {
        "guild_id": "123456",
        "guild_name": "测试频道",
        "guild_display_id": "123"
    },
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

# AI 扩展

## POST 获取 AI 语音

POST /get_ai_record

通过 AI 语音引擎获取指定文本的语音 URL

> Body 请求参数

```json
{
    "character": "ai_char_1",
    "group_id": "123456",
    "text": "你好"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» character|body|string| 是 |角色ID|
|» group_id|body|string| 是 |群号|
|» text|body|string| 是 |语音文本内容|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": "http://example.com/ai_voice.silk",
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

## POST 发送群 AI 语音

POST /send_group_ai_record

发送 AI 生成的语音到指定群聊

> Body 请求参数

```json
{
    "character": "ai_char_1",
    "group_id": "123456",
    "text": "你好"
}
```

### 请求参数

|名称|位置|类型|必选|说明|
|---|---|---|---|---|
|body|body|object| 否 |none|
|» character|body|string| 是 |角色ID|
|» group_id|body|string| 是 |群号|
|» text|body|string| 是 |语音文本内容|

> 返回示例

> 业务响应

```json
{
    "status": "ok",
    "retcode": 0,
    "data": {},
    "message": "",
    "wording": "",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1400,
    "data": null,
    "message": "请求参数错误或业务逻辑执行失败",
    "wording": "请求参数错误或业务逻辑执行失败",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1401,
    "data": null,
    "message": "权限不足",
    "wording": "权限不足",
    "stream": "normal-action"
}
```

```json
{
    "status": "failed",
    "retcode": 1404,
    "data": null,
    "message": "资源不存在",
    "wording": "资源不存在",
    "stream": "normal-action"
}
```

### 返回结果

|状态码|状态码含义|说明|数据模型|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|业务响应|Inline|

### 返回数据结构

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

# 数据模型

<h2 id="tocS_BaseResponse">BaseResponse</h2>

<a id="schemabaseresponse"></a>
<a id="schema_BaseResponse"></a>
<a id="tocSbaseresponse"></a>
<a id="tocsbaseresponse"></a>

```json
{
  "status": "string",
  "retcode": 0,
  "data": null,
  "message": "string",
  "wording": "string",
  "stream": "stream-action"
}

```

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|status|string|true|none||状态 (ok/failed)|
|retcode|number|true|none||返回码|
|data|any|false|none||业务数据（具体结构由各接口定义）|
|message|string|false|none||消息|
|wording|string|false|none||提示|
|stream|string|false|none||流式响应|

#### 枚举值

|属性|值|
|---|---|
|stream|stream-action|
|stream|normal-action|

<h2 id="tocS_EmptyData">EmptyData</h2>

<a id="schemaemptydata"></a>
<a id="schema_EmptyData"></a>
<a id="tocSemptydata"></a>
<a id="tocsemptydata"></a>

```json
null

```

无数据

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|null|false|none||无数据|

<h2 id="tocS_FileBaseData">FileBaseData</h2>

<a id="schemafilebasedata"></a>
<a id="schema_FileBaseData"></a>
<a id="tocSfilebasedata"></a>
<a id="tocsfilebasedata"></a>

```json
{
  "file": "string",
  "path": "string",
  "url": "string",
  "name": "string",
  "thumb": "string"
}

```

文件消息段基础数据

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|file|string|true|none||文件路径/URL/file:///|
|path|string|false|none||文件路径|
|url|string|false|none||文件URL|
|name|string|false|none||文件名|
|thumb|string|false|none||缩略图|

<h2 id="tocS_OB11MessageAt">OB11MessageAt</h2>

<a id="schemaob11messageat"></a>
<a id="schema_OB11MessageAt"></a>
<a id="tocSob11messageat"></a>
<a id="tocsob11messageat"></a>

```json
{
  "type": "at",
  "data": {
    "qq": "string",
    "name": "string"
  }
}

```

@消息段

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|type|string|true|none||none|
|data|object|true|none||none|
|» qq|string|true|none||QQ号或all|
|» name|string|false|none||显示名称|

#### 枚举值

|属性|值|
|---|---|
|type|at|

<h2 id="tocS_OB11MessageContact">OB11MessageContact</h2>

<a id="schemaob11messagecontact"></a>
<a id="schema_OB11MessageContact"></a>
<a id="tocSob11messagecontact"></a>
<a id="tocsob11messagecontact"></a>

```json
{
  "type": "contact",
  "data": {
    "type": "qq",
    "id": "string"
  }
}

```

联系人消息段

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|type|string|true|none||none|
|data|object|true|none||none|
|» type|string|true|none||联系人类型|
|» id|string|true|none||联系人ID|

#### 枚举值

|属性|值|
|---|---|
|type|contact|
|type|qq|
|type|group|

<h2 id="tocS_OB11MessageCustomMusic">OB11MessageCustomMusic</h2>

<a id="schemaob11messagecustommusic"></a>
<a id="schema_OB11MessageCustomMusic"></a>
<a id="tocSob11messagecustommusic"></a>
<a id="tocsob11messagecustommusic"></a>

```json
{
  "type": "music",
  "data": {
    "type": "qq",
    "id": null,
    "url": "string",
    "audio": "string",
    "title": "string",
    "image": "string",
    "content": "string"
  }
}

```

自定义音乐消息段

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|type|string|true|none||none|
|data|object|true|none||none|
|» type|string|true|none||音乐平台类型|
|» id|null|true|none||none|
|» url|string|true|none||点击后跳转URL|
|» audio|string|false|none||音频URL|
|» title|string|false|none||音乐标题|
|» image|string|true|none||封面图片URL|
|» content|string|false|none||音乐简介|

#### 枚举值

|属性|值|
|---|---|
|type|music|
|type|qq|
|type|163|
|type|kugou|
|type|migu|
|type|kuwo|
|type|custom|

<h2 id="tocS_OB11MessageData">OB11MessageData</h2>

<a id="schemaob11messagedata"></a>
<a id="schema_OB11MessageData"></a>
<a id="tocSob11messagedata"></a>
<a id="tocsob11messagedata"></a>

```json
{
  "type": "text",
  "data": {
    "text": "string"
  }
}

```

OneBot 11 消息段

### 属性

anyOf

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessageText](#schemaob11messagetext)|false|none||纯文本消息段|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessageFace](#schemaob11messageface)|false|none||QQ表情消息段|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessageMFace](#schemaob11messagemface)|false|none||商城表情消息段|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessageAt](#schemaob11messageat)|false|none||@消息段|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessageReply](#schemaob11messagereply)|false|none||回复消息段|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessageImage](#schemaob11messageimage)|false|none||图片消息段|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessageRecord](#schemaob11messagerecord)|false|none||语音消息段|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessageVideo](#schemaob11messagevideo)|false|none||视频消息段|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessageFile](#schemaob11messagefile)|false|none||文件消息段|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessageIdMusic](#schemaob11messageidmusic)|false|none||ID音乐消息段|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessageCustomMusic](#schemaob11messagecustommusic)|false|none||自定义音乐消息段|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessagePoke](#schemaob11messagepoke)|false|none||戳一戳消息段|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessageDice](#schemaob11messagedice)|false|none||骰子消息段|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessageRPS](#schemaob11messagerps)|false|none||猜拳消息段|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessageContact](#schemaob11messagecontact)|false|none||联系人消息段|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessageLocation](#schemaob11messagelocation)|false|none||位置消息段|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessageJson](#schemaob11messagejson)|false|none||JSON消息段|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessageXml](#schemaob11messagexml)|false|none||XML消息段|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessageMarkdown](#schemaob11messagemarkdown)|false|none||Markdown消息段|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessageMiniApp](#schemaob11messageminiapp)|false|none||小程序消息段|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessageNode](#schemaob11messagenode)|false|none||合并转发消息节点|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessageForward](#schemaob11messageforward)|false|none||合并转发消息段|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessageOnlineFile](#schemaob11messageonlinefile)|false|none||在线文件消息段|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessageFlashTransfer](#schemaob11messageflashtransfer)|false|none||QQ闪传消息段|

<h2 id="tocS_OB11MessageDice">OB11MessageDice</h2>

<a id="schemaob11messagedice"></a>
<a id="schema_OB11MessageDice"></a>
<a id="tocSob11messagedice"></a>
<a id="tocsob11messagedice"></a>

```json
{
  "type": "dice",
  "data": {
    "result": 0
  }
}

```

骰子消息段

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|type|string|true|none||none|
|data|object|true|none||none|
|» result|any|true|none||骰子结果|

anyOf

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|»» *anonymous*|number|false|none||none|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|»» *anonymous*|string|false|none||none|

#### 枚举值

|属性|值|
|---|---|
|type|dice|

<h2 id="tocS_OB11MessageFace">OB11MessageFace</h2>

<a id="schemaob11messageface"></a>
<a id="schema_OB11MessageFace"></a>
<a id="tocSob11messageface"></a>
<a id="tocsob11messageface"></a>

```json
{
  "type": "face",
  "data": {
    "id": "string",
    "resultId": "string",
    "chainCount": 0
  }
}

```

QQ表情消息段

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|type|string|true|none||none|
|data|object|true|none||none|
|» id|string|true|none||表情ID|
|» resultId|string|false|none||结果ID|
|» chainCount|number|false|none||连击数|

#### 枚举值

|属性|值|
|---|---|
|type|face|

<h2 id="tocS_OB11MessageFileBase">OB11MessageFileBase</h2>

<a id="schemaob11messagefilebase"></a>
<a id="schema_OB11MessageFileBase"></a>
<a id="tocSob11messagefilebase"></a>
<a id="tocsob11messagefilebase"></a>

```json
{
  "data": {
    "file": "string",
    "path": "string",
    "url": "string",
    "name": "string",
    "thumb": "string"
  }
}

```

文件消息基础接口

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|data|[FileBaseData](#schemafilebasedata)|true|none||文件消息段基础数据|

<h2 id="tocS_OB11MessageFile">OB11MessageFile</h2>

<a id="schemaob11messagefile"></a>
<a id="schema_OB11MessageFile"></a>
<a id="tocSob11messagefile"></a>
<a id="tocsob11messagefile"></a>

```json
{
  "type": "file",
  "data": {
    "file": "string",
    "path": "string",
    "url": "string",
    "name": "string",
    "thumb": "string"
  }
}

```

文件消息段

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|type|string|true|none||none|
|data|[FileBaseData](#schemafilebasedata)|true|none||文件消息段基础数据|

#### 枚举值

|属性|值|
|---|---|
|type|file|

<h2 id="tocS_OB11MessageFlashTransfer">OB11MessageFlashTransfer</h2>

<a id="schemaob11messageflashtransfer"></a>
<a id="schema_OB11MessageFlashTransfer"></a>
<a id="tocSob11messageflashtransfer"></a>
<a id="tocsob11messageflashtransfer"></a>

```json
{
  "type": "flashtransfer",
  "data": {
    "fileSetId": "string"
  }
}

```

QQ闪传消息段

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|type|string|true|none||none|
|data|object|true|none||none|
|» fileSetId|string|true|none||文件集ID|

#### 枚举值

|属性|值|
|---|---|
|type|flashtransfer|

<h2 id="tocS_OB11MessageForward">OB11MessageForward</h2>

<a id="schemaob11messageforward"></a>
<a id="schema_OB11MessageForward"></a>
<a id="tocSob11messageforward"></a>
<a id="tocsob11messageforward"></a>

```json
{
  "type": "forward",
  "data": {
    "id": "string",
    "content": {}
  }
}

```

合并转发消息段

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|type|string|true|none||none|
|data|object|true|none||none|
|» id|string|true|none||合并转发ID|
|» content|object|false|none||消息内容 (OB11Message[])|

#### 枚举值

|属性|值|
|---|---|
|type|forward|

<h2 id="tocS_OB11MessageIdMusic">OB11MessageIdMusic</h2>

<a id="schemaob11messageidmusic"></a>
<a id="schema_OB11MessageIdMusic"></a>
<a id="tocSob11messageidmusic"></a>
<a id="tocsob11messageidmusic"></a>

```json
{
  "type": "music",
  "data": {
    "type": "qq",
    "id": "string"
  }
}

```

ID音乐消息段

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|type|string|true|none||none|
|data|object|true|none||none|
|» type|string|true|none||音乐平台类型|
|» id|any|true|none||音乐ID|

anyOf

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|»» *anonymous*|string|false|none||none|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|»» *anonymous*|number|false|none||none|

#### 枚举值

|属性|值|
|---|---|
|type|music|
|type|qq|
|type|163|
|type|kugou|
|type|migu|
|type|kuwo|

<h2 id="tocS_OB11MessageImage">OB11MessageImage</h2>

<a id="schemaob11messageimage"></a>
<a id="schema_OB11MessageImage"></a>
<a id="tocSob11messageimage"></a>
<a id="tocsob11messageimage"></a>

```json
{
  "type": "image",
  "data": {
    "file": "string",
    "path": "string",
    "url": "string",
    "name": "string",
    "thumb": "string",
    "summary": "string",
    "sub_type": 0
  }
}

```

图片消息段

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|type|string|true|none||none|
|data|any|true|none||none|

allOf

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» *anonymous*|object|false|none||文件消息段基础数据|
|»» file|string|true|none||文件路径/URL/file:///|
|»» path|string|false|none||文件路径|
|»» url|string|false|none||文件URL|
|»» name|string|false|none||文件名|
|»» thumb|string|false|none||缩略图|

and

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» *anonymous*|object|false|none||none|
|»» summary|string|false|none||图片摘要|
|»» sub_type|number|false|none||图片子类型|

#### 枚举值

|属性|值|
|---|---|
|type|image|

<h2 id="tocS_OB11MessageJson">OB11MessageJson</h2>

<a id="schemaob11messagejson"></a>
<a id="schema_OB11MessageJson"></a>
<a id="tocSob11messagejson"></a>
<a id="tocsob11messagejson"></a>

```json
{
  "type": "json",
  "data": {
    "data": "string",
    "config": {
      "token": "string"
    }
  }
}

```

JSON消息段

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|type|string|true|none||none|
|data|object|true|none||none|
|» data|any|true|none||JSON数据|

anyOf

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|»» *anonymous*|string|false|none||none|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|»» *anonymous*|object|false|none||none|

continued

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» config|object|false|none||none|
|»» token|string|true|none||token|

#### 枚举值

|属性|值|
|---|---|
|type|json|

<h2 id="tocS_OB11MessageLocation">OB11MessageLocation</h2>

<a id="schemaob11messagelocation"></a>
<a id="schema_OB11MessageLocation"></a>
<a id="tocSob11messagelocation"></a>
<a id="tocsob11messagelocation"></a>

```json
{
  "type": "location",
  "data": {
    "lat": "string",
    "lon": "string",
    "title": "string",
    "content": "string"
  }
}

```

位置消息段

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|type|string|true|none||none|
|data|object|true|none||none|
|» lat|any|true|none||纬度|

anyOf

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|»» *anonymous*|string|false|none||none|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|»» *anonymous*|number|false|none||none|

continued

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» lon|any|true|none||经度|

anyOf

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|»» *anonymous*|string|false|none||none|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|»» *anonymous*|number|false|none||none|

continued

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» title|string|false|none||标题|
|» content|string|false|none||内容|

#### 枚举值

|属性|值|
|---|---|
|type|location|

<h2 id="tocS_OB11MessageMFace">OB11MessageMFace</h2>

<a id="schemaob11messagemface"></a>
<a id="schema_OB11MessageMFace"></a>
<a id="tocSob11messagemface"></a>
<a id="tocsob11messagemface"></a>

```json
{
  "type": "mface",
  "data": {
    "emoji_package_id": 0,
    "emoji_id": "string",
    "key": "string",
    "summary": "string"
  }
}

```

商城表情消息段

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|type|string|true|none||none|
|data|object|true|none||none|
|» emoji_package_id|number|true|none||表情包ID|
|» emoji_id|string|true|none||表情ID|
|» key|string|true|none||表情key|
|» summary|string|true|none||表情摘要|

#### 枚举值

|属性|值|
|---|---|
|type|mface|

<h2 id="tocS_OB11MessageMarkdown">OB11MessageMarkdown</h2>

<a id="schemaob11messagemarkdown"></a>
<a id="schema_OB11MessageMarkdown"></a>
<a id="tocSob11messagemarkdown"></a>
<a id="tocsob11messagemarkdown"></a>

```json
{
  "type": "markdown",
  "data": {
    "content": "string"
  }
}

```

Markdown消息段

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|type|string|true|none||none|
|data|object|true|none||none|
|» content|string|true|none||Markdown内容|

#### 枚举值

|属性|值|
|---|---|
|type|markdown|

<h2 id="tocS_OB11MessageMiniApp">OB11MessageMiniApp</h2>

<a id="schemaob11messageminiapp"></a>
<a id="schema_OB11MessageMiniApp"></a>
<a id="tocSob11messageminiapp"></a>
<a id="tocsob11messageminiapp"></a>

```json
{
  "type": "miniapp",
  "data": {
    "data": "string"
  }
}

```

小程序消息段

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|type|string|true|none||none|
|data|object|true|none||none|
|» data|string|true|none||小程序数据|

#### 枚举值

|属性|值|
|---|---|
|type|miniapp|

<h2 id="tocS_OB11MessageMixType">OB11MessageMixType</h2>

<a id="schemaob11messagemixtype"></a>
<a id="schema_OB11MessageMixType"></a>
<a id="tocSob11messagemixtype"></a>
<a id="tocsob11messagemixtype"></a>

```json
[
  {
    "type": "text",
    "data": {
      "text": "string"
    }
  }
]

```

OneBot 11 消息混合类型

### 属性

anyOf

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[[OB11MessageData](#schemaob11messagedata)]|false|none||[OneBot 11 消息段]|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|string|false|none||none|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|[OB11MessageData](#schemaob11messagedata)|false|none||OneBot 11 消息段|

<h2 id="tocS_OB11MessageNode">OB11MessageNode</h2>

<a id="schemaob11messagenode"></a>
<a id="schema_OB11MessageNode"></a>
<a id="tocSob11messagenode"></a>
<a id="tocsob11messagenode"></a>

```json
{
  "type": "node",
  "data": {
    "id": "string",
    "user_id": 0,
    "uin": 0,
    "nickname": "string",
    "name": "string",
    "content": {},
    "source": "string",
    "news": [
      {
        "text": "string"
      }
    ],
    "summary": "string",
    "prompt": "string",
    "time": "string"
  }
}

```

合并转发消息节点

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|type|string|true|none||none|
|data|object|true|none||none|
|» id|string|false|none||转发消息ID|
|» user_id|any|false|none||发送者QQ号|

anyOf

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|»» *anonymous*|number|false|none||none|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|»» *anonymous*|string|false|none||none|

continued

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» uin|any|false|none||发送者QQ号(兼容go-cqhttp)|

anyOf

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|»» *anonymous*|number|false|none||none|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|»» *anonymous*|string|false|none||none|

continued

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» nickname|string|true|none||发送者昵称|
|» name|string|false|none||发送者昵称(兼容go-cqhttp)|
|» content|object|true|none||消息内容 (OB11MessageMixType)|
|» source|string|false|none||消息来源|
|» news|[object]|false|none||none|
|»» text|string|true|none||新闻文本|
|» summary|string|false|none||摘要|
|» prompt|string|false|none||提示|
|» time|string|false|none||时间|

#### 枚举值

|属性|值|
|---|---|
|type|node|

<h2 id="tocS_OB11MessageOnlineFile">OB11MessageOnlineFile</h2>

<a id="schemaob11messageonlinefile"></a>
<a id="schema_OB11MessageOnlineFile"></a>
<a id="tocSob11messageonlinefile"></a>
<a id="tocsob11messageonlinefile"></a>

```json
{
  "type": "onlinefile",
  "data": {
    "msgId": "string",
    "elementId": "string",
    "fileName": "string",
    "fileSize": "string",
    "isDir": true
  }
}

```

在线文件消息段

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|type|string|true|none||none|
|data|object|true|none||none|
|» msgId|string|true|none||消息ID|
|» elementId|string|true|none||元素ID|
|» fileName|string|true|none||文件名|
|» fileSize|string|true|none||文件大小|
|» isDir|boolean|true|none||是否为目录|

#### 枚举值

|属性|值|
|---|---|
|type|onlinefile|

<h2 id="tocS_OB11MessagePoke">OB11MessagePoke</h2>

<a id="schemaob11messagepoke"></a>
<a id="schema_OB11MessagePoke"></a>
<a id="tocSob11messagepoke"></a>
<a id="tocsob11messagepoke"></a>

```json
{
  "type": "poke",
  "data": {
    "type": "string",
    "id": "string"
  }
}

```

戳一戳消息段

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|type|string|true|none||none|
|data|object|true|none||none|
|» type|string|true|none||戳一戳类型|
|» id|string|true|none||戳一戳ID|

#### 枚举值

|属性|值|
|---|---|
|type|poke|

<h2 id="tocS_OB11MessageRPS">OB11MessageRPS</h2>

<a id="schemaob11messagerps"></a>
<a id="schema_OB11MessageRPS"></a>
<a id="tocSob11messagerps"></a>
<a id="tocsob11messagerps"></a>

```json
{
  "type": "rps",
  "data": {
    "result": 0
  }
}

```

猜拳消息段

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|type|string|true|none||none|
|data|object|true|none||none|
|» result|any|true|none||猜拳结果|

anyOf

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|»» *anonymous*|number|false|none||none|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|»» *anonymous*|string|false|none||none|

#### 枚举值

|属性|值|
|---|---|
|type|rps|

<h2 id="tocS_OB11MessageRecord">OB11MessageRecord</h2>

<a id="schemaob11messagerecord"></a>
<a id="schema_OB11MessageRecord"></a>
<a id="tocSob11messagerecord"></a>
<a id="tocsob11messagerecord"></a>

```json
{
  "type": "record",
  "data": {
    "file": "string",
    "path": "string",
    "url": "string",
    "name": "string",
    "thumb": "string"
  }
}

```

语音消息段

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|type|string|true|none||none|
|data|[FileBaseData](#schemafilebasedata)|true|none||文件消息段基础数据|

#### 枚举值

|属性|值|
|---|---|
|type|record|

<h2 id="tocS_OB11MessageReply">OB11MessageReply</h2>

<a id="schemaob11messagereply"></a>
<a id="schema_OB11MessageReply"></a>
<a id="tocSob11messagereply"></a>
<a id="tocsob11messagereply"></a>

```json
{
  "type": "reply",
  "data": {
    "id": "string",
    "seq": 0
  }
}

```

回复消息段

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|type|string|true|none||none|
|data|object|true|none||none|
|» id|string|false|none||消息ID的短ID映射|
|» seq|number|false|none||消息序列号，优先使用|

#### 枚举值

|属性|值|
|---|---|
|type|reply|

<h2 id="tocS_OB11Message">OB11Message</h2>

<a id="schemaob11message"></a>
<a id="schema_OB11Message"></a>
<a id="tocSob11message"></a>
<a id="tocsob11message"></a>

```json
{
  "real_seq": "string",
  "temp_source": 0,
  "message_sent_type": "string",
  "target_id": 0,
  "self_id": 0,
  "time": 0,
  "message_id": 0,
  "message_seq": 0,
  "real_id": 0,
  "user_id": 0,
  "group_id": 0,
  "group_name": "string",
  "message_type": "private",
  "sub_type": "friend",
  "sender": {
    "user_id": 0,
    "nickname": "string",
    "card": "string",
    "role": "string",
    "sex": "string",
    "age": 0,
    "area": "string",
    "level": "string",
    "title": "string"
  },
  "message": [
    {
      "type": "[",
      "data": {}
    }
  ],
  "message_format": "array",
  "raw_message": "string",
  "font": 0,
  "post_type": "string",
  "raw": {},
  "emoji_likes_list": [
    {
      "emoji_id": "string",
      "emoji_type": "string",
      "likes_cnt": "string"
    }
  ]
}

```

OneBot 11 完整消息对象

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|real_seq|string|false|none||真实序列号|
|temp_source|number|false|none||临时会话来源|
|message_sent_type|string|false|none||消息发送类型|
|target_id|number|false|none||目标ID|
|self_id|number|false|none||机器人QQ号|
|time|number|true|none||消息时间戳|
|message_id|number|true|none||消息ID|
|message_seq|number|true|none||消息序列号|
|real_id|number|true|none||真实ID|
|user_id|any|true|none||发送者QQ号|

anyOf

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» *anonymous*|number|false|none||none|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» *anonymous*|string|false|none||none|

continued

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|group_id|any|false|none||群号|

anyOf

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» *anonymous*|number|false|none||none|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» *anonymous*|string|false|none||none|

continued

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|group_name|string|false|none||群名称|
|message_type|string|true|none||消息类型|
|sub_type|string|false|none||消息子类型|
|sender|[OB11Sender](#schemaob11sender)|true|none||OneBot 11 发送者信息|
|message|any|true|none||消息内容|

anyOf

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» *anonymous*|[[OB11MessageData](#schemaob11messagedata)]|false|none||[OneBot 11 消息段]|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» *anonymous*|string|false|none||none|

continued

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|message_format|string|true|none||消息格式|
|raw_message|string|true|none||原始消息|
|font|number|true|none||字体|
|post_type|string|false|none||上报类型|
|raw|object|false|none||原始消息对象|
|emoji_likes_list|[object]|false|none||表情点赞列表|
|» emoji_id|string|true|none||表情ID|
|» emoji_type|string|true|none||表情类型|
|» likes_cnt|string|true|none||点赞数|

#### 枚举值

|属性|值|
|---|---|
|message_type|private|
|message_type|group|
|sub_type|friend|
|sub_type|group|
|sub_type|normal|
|message_format|array|
|message_format|string|

<h2 id="tocS_OB11MessageText">OB11MessageText</h2>

<a id="schemaob11messagetext"></a>
<a id="schema_OB11MessageText"></a>
<a id="tocSob11messagetext"></a>
<a id="tocsob11messagetext"></a>

```json
{
  "type": "text",
  "data": {
    "text": "string"
  }
}

```

纯文本消息段

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|type|string|true|none||none|
|data|object|true|none||none|
|» text|string|true|none||纯文本内容|

#### 枚举值

|属性|值|
|---|---|
|type|text|

<h2 id="tocS_OB11MessageVideo">OB11MessageVideo</h2>

<a id="schemaob11messagevideo"></a>
<a id="schema_OB11MessageVideo"></a>
<a id="tocSob11messagevideo"></a>
<a id="tocsob11messagevideo"></a>

```json
{
  "type": "video",
  "data": {
    "file": "string",
    "path": "string",
    "url": "string",
    "name": "string",
    "thumb": "string"
  }
}

```

视频消息段

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|type|string|true|none||none|
|data|[FileBaseData](#schemafilebasedata)|true|none||文件消息段基础数据|

#### 枚举值

|属性|值|
|---|---|
|type|video|

<h2 id="tocS_OB11MessageXml">OB11MessageXml</h2>

<a id="schemaob11messagexml"></a>
<a id="schema_OB11MessageXml"></a>
<a id="tocSob11messagexml"></a>
<a id="tocsob11messagexml"></a>

```json
{
  "type": "xml",
  "data": {
    "data": "string"
  }
}

```

XML消息段

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|type|string|true|none||none|
|data|object|true|none||none|
|» data|string|true|none||XML数据|

#### 枚举值

|属性|值|
|---|---|
|type|xml|

<h2 id="tocS_OB11PostSendMsg">OB11PostSendMsg</h2>

<a id="schemaob11postsendmsg"></a>
<a id="schema_OB11PostSendMsg"></a>
<a id="tocSob11postsendmsg"></a>
<a id="tocsob11postsendmsg"></a>

```json
{
  "message_type": "private",
  "user_id": "string",
  "group_id": "string",
  "message": [
    {
      "type": "[",
      "data": {}
    }
  ],
  "messages": [
    {
      "type": "[",
      "data": {}
    }
  ],
  "auto_escape": true,
  "source": "string",
  "news": [
    {
      "text": "string"
    }
  ],
  "summary": "string",
  "prompt": "string",
  "time": "string"
}

```

OneBot 11 发送消息请求

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|message_type|string|false|none||消息类型|
|user_id|string|false|none||用户QQ号|
|group_id|string|false|none||群号|
|message|[OB11MessageMixType](#schemaob11messagemixtype)|true|none||OneBot 11 消息混合类型|
|messages|[OB11MessageMixType](#schemaob11messagemixtype)|false|none||OneBot 11 消息混合类型|
|auto_escape|any|false|none||是否作为纯文本发送|

anyOf

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» *anonymous*|boolean|false|none||none|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» *anonymous*|string|false|none||none|

continued

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|source|string|false|none||消息来源|
|news|[object]|false|none||none|
|» text|string|true|none||文本|
|summary|string|false|none||摘要|
|prompt|string|false|none||提示|
|time|string|false|none||时间|

#### 枚举值

|属性|值|
|---|---|
|message_type|private|
|message_type|group|

<h2 id="tocS_OB11Sender">OB11Sender</h2>

<a id="schemaob11sender"></a>
<a id="schema_OB11Sender"></a>
<a id="tocSob11sender"></a>
<a id="tocsob11sender"></a>

```json
{
  "user_id": 0,
  "nickname": "string",
  "card": "string",
  "role": "string",
  "sex": "string",
  "age": 0,
  "area": "string",
  "level": "string",
  "title": "string"
}

```

OneBot 11 发送者信息

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|user_id|any|true|none||发送者QQ号|

anyOf

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» *anonymous*|number|false|none||none|

or

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|» *anonymous*|string|false|none||none|

continued

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|nickname|string|true|none||发送者昵称|
|card|string|false|none||群名片|
|role|string|false|none||角色|
|sex|string|false|none||性别|
|age|number|false|none||年龄|
|area|string|false|none||地区|
|level|string|false|none||等级|
|title|string|false|none||头衔|

<h2 id="tocS_OB11GroupMember">OB11GroupMember</h2>

<a id="schemaob11groupmember"></a>
<a id="schema_OB11GroupMember"></a>
<a id="tocSob11groupmember"></a>
<a id="tocsob11groupmember"></a>

```json
{
  "group_id": 0,
  "user_id": 0,
  "nickname": "string",
  "card": "string",
  "sex": "string",
  "age": 0,
  "join_time": 0,
  "last_sent_time": 0,
  "level": "string",
  "qq_level": 0,
  "role": "string",
  "title": "string",
  "area": "string",
  "unfriendly": true,
  "title_expire_time": 0,
  "card_changeable": true,
  "shut_up_timestamp": 0,
  "is_robot": true,
  "qage": 0
}

```

OneBot 11 群成员信息

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|group_id|number|true|none||群号|
|user_id|number|true|none||QQ号|
|nickname|string|true|none||昵称|
|card|string|false|none||名片|
|sex|string|false|none||性别|
|age|number|false|none||年龄|
|join_time|number|false|none||入群时间戳|
|last_sent_time|number|false|none||最后发言时间戳|
|level|string|false|none||等级|
|qq_level|number|false|none||QQ等级|
|role|string|false|none||角色 (owner/admin/member)|
|title|string|false|none||头衔|
|area|string|false|none||地区|
|unfriendly|boolean|false|none||是否不良记录|
|title_expire_time|number|false|none||头衔过期时间|
|card_changeable|boolean|false|none||是否允许修改名片|
|shut_up_timestamp|number|false|none||禁言截止时间戳|
|is_robot|boolean|false|none||是否为机器人|
|qage|number|false|none||Q龄|

<h2 id="tocS_OB11Group">OB11Group</h2>

<a id="schemaob11group"></a>
<a id="schema_OB11Group"></a>
<a id="tocSob11group"></a>
<a id="tocsob11group"></a>

```json
{
  "group_all_shut": 0,
  "group_remark": "string",
  "group_id": 0,
  "group_name": "string",
  "member_count": 0,
  "max_member_count": 0
}

```

OneBot 11 群信息

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|group_all_shut|number|true|none||是否全员禁言|
|group_remark|string|true|none||群备注|
|group_id|number|true|none||群号|
|group_name|string|true|none||群名称|
|member_count|number|false|none||成员人数|
|max_member_count|number|false|none||最大成员人数|

<h2 id="tocS_OB11ActionMessage">OB11ActionMessage</h2>

<a id="schemaob11actionmessage"></a>
<a id="schema_OB11ActionMessage"></a>
<a id="tocSob11actionmessage"></a>
<a id="tocsob11actionmessage"></a>

```json
{
  "self_id": 0,
  "user_id": 0,
  "time": 0,
  "real_seq": "string",
  "message_type": "string",
  "sender": {
    "user_id": 0,
    "nickname": "string",
    "card": "string",
    "role": "string"
  },
  "raw_message": "string",
  "font": 0,
  "sub_type": "string",
  "message": {},
  "message_format": "string",
  "post_type": "string",
  "group_id": 0,
  "group_name": "string",
  "message_id": 0,
  "message_seq": 0,
  "emoji_likes_list": [
    {
      "emoji_id": "string",
      "emoji_type": "string",
      "likes_cnt": "string"
    }
  ]
}

```

OneBot 11 消息信息

### 属性

allOf

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|object|false|none||最后一条消息|
|» self_id|number|true|none||发送者QQ号|
|» user_id|number|true|none||接收者QQ号|
|» time|number|true|none||时间戳|
|» real_seq|string|true|none||消息序号|
|» message_type|string|true|none||消息类型|
|» sender|object|true|none||none|
|»» user_id|number|true|none||用户QQ号|
|»» nickname|string|true|none||用户昵称|
|»» card|string|false|none||用户名片|
|»» role|string|false|none||用户角色|
|» raw_message|string|true|none||原始消息|
|» font|number|true|none||字体大小|
|» sub_type|string|true|none||子类型|
|» message|object|true|none||消息内容|
|» message_format|string|true|none||消息格式|
|» post_type|string|true|none||发布类型|
|» group_id|number|true|none||群号|
|» group_name|string|true|none||群名称|

and

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|*anonymous*|object|false|none||OneBot 11 消息信息|
|» message_id|number|true|none||消息ID|
|» message_seq|number|true|none||消息序列号|
|» emoji_likes_list|[object]|true|none||none|
|»» emoji_id|string|true|none||表情符号ID|
|»» emoji_type|string|true|none||表情符号类型|
|»» likes_cnt|string|true|none||点赞数|

<h2 id="tocS_OB11Notify">OB11Notify</h2>

<a id="schemaob11notify"></a>
<a id="schema_OB11Notify"></a>
<a id="tocSob11notify"></a>
<a id="tocsob11notify"></a>

```json
{
  "request_id": 0,
  "invitor_uin": 0,
  "invitor_nick": "string",
  "group_id": 0,
  "group_name": "string",
  "message": "string",
  "checked": true,
  "actor": 0,
  "requester_nick": "string"
}

```

OneBot 11 通知信息

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|request_id|number|true|none||请求ID|
|invitor_uin|number|true|none||邀请者QQ|
|invitor_nick|string|true|none||邀请者昵称|
|group_id|number|true|none||群号|
|group_name|string|true|none||群名称|
|message|string|true|none||附言|
|checked|boolean|true|none||是否已处理|
|actor|number|true|none||操作者QQ|
|requester_nick|string|true|none||申请者昵称|

<h2 id="tocS_OB11User">OB11User</h2>

<a id="schemaob11user"></a>
<a id="schema_OB11User"></a>
<a id="tocSob11user"></a>
<a id="tocsob11user"></a>

```json
{
  "birthday_year": 0,
  "birthday_month": 0,
  "birthday_day": 0,
  "phone_num": "string",
  "email": "string",
  "category_id": 0,
  "user_id": 0,
  "nickname": "string",
  "remark": "string",
  "sex": "string",
  "level": 0,
  "age": 0,
  "qid": "string",
  "login_days": 0,
  "categoryName": "string",
  "categoryId": 0
}

```

OneBot 11 用户信息

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|birthday_year|number|false|none||出生年份|
|birthday_month|number|false|none||出生月份|
|birthday_day|number|false|none||出生日期|
|phone_num|string|false|none||手机号|
|email|string|false|none||邮箱|
|category_id|number|false|none||分组ID|
|user_id|number|true|none||QQ号|
|nickname|string|true|none||昵称|
|remark|string|false|none||备注|
|sex|string|false|none||性别|
|level|number|false|none||等级|
|age|number|false|none||年龄|
|qid|string|false|none||QID|
|login_days|number|false|none||登录天数|
|categoryName|string|false|none||分组名称|
|categoryId|number|false|none||分组ID|

<h2 id="tocS_OB11LatestMessage">OB11LatestMessage</h2>

<a id="schemaob11latestmessage"></a>
<a id="schema_OB11LatestMessage"></a>
<a id="tocSob11latestmessage"></a>
<a id="tocsob11latestmessage"></a>

```json
{
  "self_id": 0,
  "user_id": 0,
  "time": 0,
  "real_seq": "string",
  "message_type": "string",
  "sender": {
    "user_id": 0,
    "nickname": "string",
    "card": "string",
    "role": "string"
  },
  "raw_message": "string",
  "font": 0,
  "sub_type": "string",
  "message": {},
  "message_format": "string",
  "post_type": "string",
  "group_id": 0,
  "group_name": "string"
}

```

最后一条消息

### 属性

|名称|类型|必选|约束|中文名|说明|
|---|---|---|---|---|---|
|self_id|number|true|none||发送者QQ号|
|user_id|number|true|none||接收者QQ号|
|time|number|true|none||时间戳|
|real_seq|string|true|none||消息序号|
|message_type|string|true|none||消息类型|
|sender|object|true|none||none|
|» user_id|number|true|none||用户QQ号|
|» nickname|string|true|none||用户昵称|
|» card|string|false|none||用户名片|
|» role|string|false|none||用户角色|
|raw_message|string|true|none||原始消息|
|font|number|true|none||字体大小|
|sub_type|string|true|none||子类型|
|message|object|true|none||消息内容|
|message_format|string|true|none||消息格式|
|post_type|string|true|none||发布类型|
|group_id|number|true|none||群号|
|group_name|string|true|none||群名称|

