# core/tools/tools_media.py
"""媒体类工具：文件下载与图像生成。"""
import asyncio
import base64
import datetime
import os
import re
from html import unescape as html_unescape
from urllib.parse import urlparse

import aiohttp

from config import cfg
from core.toolchain import ToolResult
from utils import BASE_DIR
from utils.http_client import create_tcp_connector

from .tools_common import logger


def _clean_file_reference(value):
    if not value:
        return ""
    text = html_unescape(str(value)).strip().strip("`'\"").strip()
    return text.strip("`'\"").strip()


def _is_download_url(value):
    parsed = urlparse(_clean_file_reference(value))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _guess_download_filename(url, filename=None):
    if filename:
        return filename
    path_name = os.path.basename(urlparse(url).path)
    if path_name:
        return path_name
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"download_{timestamp}"


async def _download_url_to_workspace(url, filename=None):
    from network.napcat import DOWNLOAD_DIR

    url = _clean_file_reference(url)
    filename = _guess_download_filename(url, filename)
    save_path = os.path.join(DOWNLOAD_DIR, filename)
    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(connector=create_tcp_connector(), timeout=timeout) as session:
        async with session.get(url) as response:
            content = await response.read()
            if response.status >= 400:
                error_text = content.decode("utf-8", errors="ignore")[:300]
                return {
                    "success": False,
                    "error": f"HTTP {response.status}: {error_text or response.reason}",
                    "data": {"url": url},
                }

    with open(save_path, "wb") as f:
        f.write(content)
    logger.info(f"[DownloadFile] URL 文件已保存: {save_path}")
    return {
        "success": True,
        "file_path": os.path.abspath(save_path),
        "filename": filename,
        "url": url,
    }


async def download_file_tool(context, file_id=None, filename=None):
    """
    下载群聊/私聊中的文件到本地。

    当收到文件消息时，消息中会包含 [文件:file_id=xxx] 标记。
    使用此工具可以通过 file_id 下载文件到本地，然后可以委托小女仆分析文件内容。

    Args:
        file_id: 文件 ID（从消息中的 [文件:file_id=xxx] 获取）
        filename: 保存的文件名（可选，默认使用原文件名）
    """
    if not file_id:
        # 尝试从最近的消息中提取 file_id 或视频下载 URL
        recent_text = context.combined_text or ""
        file_ids = re.findall(r'\[(?:文件|视频|语音):(?:[^\]]*,)?file_id=([^\]]+)\]', recent_text)
        if file_ids:
            file_id = file_ids[0]
            logger.info(f"[DownloadFile] 从消息中提取 file_id: {file_id}")
        else:
            urls = re.findall(r'https?://[^\s\]`\'\"]+', recent_text)
            if urls:
                file_id = urls[0]
                logger.info("[DownloadFile] 从消息中提取下载 URL")
            else:
                return ToolResult(
                    success=False,
                    content="缺少文件 ID。请从消息中的 [文件:file_id=xxx] 获取。",
                    error="missing_file_id"
                )

    file_id = _clean_file_reference(file_id)

    try:
        if _is_download_url(file_id):
            result = await _download_url_to_workspace(file_id, filename)
        else:
            result = await context.sender.download_file(file_id, filename)

        if result.get("success"):
            file_path = result.get("file_path")
            saved_filename = result.get("filename")

            if file_path:
                return ToolResult(
                    success=True,
                    content=f"文件已下载: {saved_filename}",
                    data={
                        "file_path": file_path,
                        "filename": saved_filename,
                        "file_id": file_id,
                    }
                )
            elif result.get("url"):
                return ToolResult(
                    success=True,
                    content=f"文件 URL: {result['url']}",
                    data={
                        "url": result["url"],
                        "filename": saved_filename,
                        "file_id": file_id,
                    }
                )
        else:
            return ToolResult(
                success=False,
                content=f"下载文件失败: {result.get('error', '未知错误')}",
                data=result.get("data"),
                error=result.get("error", "download_failed")
            )
    except Exception as e:
        logger.error(f"[DownloadFile] 下载文件异常: {e}")
        return ToolResult(success=False, content=f"下载文件失败: {str(e)}", error=str(e))


# ---------------------------------------------------------------- 参考图支持
# 单次最多 4 张，单张 5MB、总计 15MB；仅接受常见位图格式并做魔数校验。
MAX_REFERENCE_IMAGES = 4
MAX_REFERENCE_IMAGE_BYTES = 5 * 1024 * 1024
MAX_REFERENCE_TOTAL_BYTES = 15 * 1024 * 1024
_REFERENCE_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
_REFERENCE_DIRS = (
    os.path.join(BASE_DIR, "output"),
    os.path.join(BASE_DIR, "workspace"),
    os.path.join(BASE_DIR, "temp_images"),
    os.path.join(BASE_DIR, "data", "image_store"),
)


def _reference_dir_allowed(path):
    """参考图必须来自会话图片目录或 Yuki 自己的工作目录，避免任意本地文件外发。"""
    real_path = os.path.realpath(path)
    for root in _REFERENCE_DIRS:
        root_real = os.path.realpath(root)
        try:
            if os.path.commonpath([real_path, root_real]) == root_real:
                return True
        except ValueError:
            continue
    return False


def _sniff_image_mime(path):
    """按文件头识别 png/jpeg/webp，防止把非图片文件发给图像接口。"""
    try:
        with open(path, "rb") as f:
            head = f.read(12)
    except OSError:
        return ""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return ""


def _resolve_reference_image(context, ref):
    """把 [img:XXX] 索引或本地路径解析成可校验的参考图信息。

    索引解析复用 context.image_store.resolve（与 tools_common._resolve_image_path 同一机制）。
    返回 (info, error)，任一项失败即返回错误文案。
    """
    text = _clean_file_reference(ref)
    if not text:
        return None, "参考图路径为空"

    index_match = re.match(r'^\[img:(\d{1,3})\]$', text)
    if index_match:
        idx = f"{int(index_match.group(1)):03d}"
        image_store = getattr(context, "image_store", None)
        if not image_store:
            return None, f"当前会话没有图片索引，无法解析 {text}"
        resolved = image_store.resolve(idx)
        if not resolved:
            return None, f"图片索引 {text} 不存在或已过期（索引只保留近期图片）"
        path = resolved
        source = text
    elif re.match(r'^\[shot:\d+\]$', text):
        return None, "截屏记忆 [shot:N] 不支持作为参考图，请改用 [img:XXX] 或本地图片路径"
    else:
        path = os.path.expanduser(text)
        if not os.path.isabs(path):
            path = os.path.join(BASE_DIR, path)
        source = text

    path = os.path.realpath(path)
    if not os.path.isfile(path):
        return None, f"参考图不存在: {source}"
    if not _reference_dir_allowed(path):
        return None, (
            "参考图必须位于 output/workspace/temp_images 或会话图片目录: "
            f"{source}"
        )

    ext = os.path.splitext(path)[1].lower()
    if ext not in _REFERENCE_IMAGE_EXTS:
        return None, f"参考图格式不支持（仅 png/jpg/jpeg/webp）: {source}"

    try:
        size = os.path.getsize(path)
    except OSError as e:
        return None, f"读取参考图失败: {source} ({e})"
    if size <= 0:
        return None, f"参考图是空文件: {source}"
    if size > MAX_REFERENCE_IMAGE_BYTES:
        return None, f"单张参考图不能超过 {MAX_REFERENCE_IMAGE_BYTES // (1024 * 1024)}MB: {source}"

    mime = _sniff_image_mime(path)
    if not mime:
        return None, f"文件内容不是有效的 PNG/JPEG/WEBP 图片: {source}"

    return {
        "path": path,
        "size": size,
        "mime": mime,
        "source": source,
    }, ""


def _collect_reference_images(context, image_paths):
    """校验参考图列表：数量、索引/路径解析、目录、格式、体积。返回 (infos, error)。"""
    if image_paths is None or image_paths == "":
        return [], ""
    if isinstance(image_paths, str):
        refs = [image_paths]
    elif isinstance(image_paths, (list, tuple)):
        refs = list(image_paths)
    else:
        return [], "image_paths 必须是字符串数组"

    refs = [_clean_file_reference(r) for r in refs]
    refs = [r for r in refs if r]
    if not refs:
        return [], ""
    if len(refs) > MAX_REFERENCE_IMAGES:
        return [], f"参考图最多 {MAX_REFERENCE_IMAGES} 张，当前传入 {len(refs)} 张"

    images = []
    seen = set()
    total = 0
    for ref in refs:
        info, error = _resolve_reference_image(context, ref)
        if error:
            return [], error
        if info["path"] in seen:
            logger.info(f"[ImageGen] 跳过重复参考图: {info['source']}")
            continue
        seen.add(info["path"])
        total += info["size"]
        if total > MAX_REFERENCE_TOTAL_BYTES:
            return [], f"参考图总大小不能超过 {MAX_REFERENCE_TOTAL_BYTES // (1024 * 1024)}MB"
        images.append(info)
    return images, ""


def _encode_reference_data_uris(images):
    """把参考图编码成 DashScope 接受的 data URI（base64）。"""
    uris = []
    for info in images:
        with open(info["path"], "rb") as f:
            data = f.read(MAX_REFERENCE_IMAGE_BYTES + 1)
        if not data:
            raise ValueError(f"参考图在读取时变为空文件: {info['source']}")
        if len(data) > MAX_REFERENCE_IMAGE_BYTES:
            raise ValueError(f"参考图在读取时超过大小上限: {info['source']}")
        uris.append(f"data:{info['mime']};base64,{base64.b64encode(data).decode('ascii')}")
    return uris


async def generate_image_tool(context, prompt, size="1024*1024", image_paths=None):
    """调用图像生成模型生成图片，保存到 output 目录并返回路径。

    image_paths 可选：参考图列表，元素为 [img:XXX] 索引或本地图片路径，
    用于让生成结果参考这些图片（图生图/图像编辑）。
    """
    if not prompt:
        return ToolResult(success=False, content="缺少图像描述", error="missing_prompt")

    reference_images, reference_error = _collect_reference_images(context, image_paths)
    if reference_error:
        return ToolResult(
            success=False,
            content=reference_error,
            error="invalid_reference_image",
        )
    for info in reference_images:
        logger.info(
            f"[ImageGen] 参考图: {info['source']} -> {info['path']} "
            f"({info['size']} bytes, {info['mime']})"
        )

    api_key = cfg.IMAGE_GEN_API_KEY
    if not api_key:
        return ToolResult(success=False, content="未配置 image_gen_api_key", error="missing_api_key")

    base_url = cfg.IMAGE_GEN_URL
    model = cfg.IMAGE_GEN_MODEL
    # OpenAI 兼容接口要求 WIDTHxHEIGHT 格式，非 gpt-image 的旧模型可能用 "1024*1024"
    size = size.replace("*", "x").replace("X", "x")

    # wan 系列走 DashScope 原生 API，其他走 OpenAI 兼容接口
    use_native = model.startswith("wan")

    if use_native:
        host_match = re.match(r'(https://[^/]+)/compatible-mode/v1', base_url)
        if host_match:
            api_endpoint = f"{host_match.group(1)}/api/v1/services/aigc/multimodal-generation/generation"
        else:
            api_endpoint = f"{base_url.rstrip('/')}/api/v1/services/aigc/multimodal-generation/generation"

        reference_data_uris = []
        if reference_images:
            try:
                reference_data_uris = await asyncio.to_thread(
                    _encode_reference_data_uris, reference_images
                )
            except Exception as e:
                logger.error(f"[ImageGen] 读取参考图失败: {e}")
                return ToolResult(
                    success=False,
                    content=f"读取参考图失败: {e}",
                    error="reference_image_read_failed",
                )

        # DashScope 多模态接口：参考图以 image 条目放在 content 里，文本放最后
        content = [{"image": uri} for uri in reference_data_uris] + [{"text": prompt}]
        payload = {
            "model": model,
            "input": {
                "messages": [
                    {"role": "user", "content": content}
                ]
            },
            "parameters": {"size": size, "n": 1},
        }

        async def _do_generate():
            timeout = aiohttp.ClientTimeout(total=120)
            async with aiohttp.ClientSession(connector=create_tcp_connector(), timeout=timeout) as session:
                async with session.post(
                    api_endpoint,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                ) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status != 200:
                        raise Exception(f"API 返回 {resp.status}: {data}")
                    return data

        try:
            data = await _do_generate()
        except Exception as e:
            logger.error(f"[ImageGen] 生成失败: {e}")
            return ToolResult(success=False, content=f"图像生成失败: {str(e)}", error=str(e))

        try:
            image_url = data["output"]["choices"][0]["message"]["content"][0]["image"]
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"[ImageGen] 解析返回数据失败: {data}")
            return ToolResult(success=False, content="模型返回数据格式异常", error=str(e))

        # 下载图片到本地
        output_dir = os.path.join(BASE_DIR, 'output')
        os.makedirs(output_dir, exist_ok=True)
        filename = datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '.png'
        filepath = os.path.join(output_dir, filename)

        try:
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(connector=create_tcp_connector(), timeout=timeout) as session:
                async with session.get(image_url) as resp:
                    if resp.status != 200:
                        raise Exception(f"下载图片失败: HTTP {resp.status}")
                    img_bytes = await resp.read()
                    with open(filepath, 'wb') as f:
                        f.write(img_bytes)
        except Exception as e:
            logger.error(f"[ImageGen] 下载图片失败: {e}")
            return ToolResult(success=False, content=f"图片下载失败: {str(e)}", error=str(e))

        logger.info(f"[ImageGen] 图片已保存: {filepath} ({len(img_bytes)} bytes)")

    else:
        # OpenAI 兼容接口（如 gpt-image 等）
        if reference_images and model.startswith("dall-e-3"):
            return ToolResult(
                success=False,
                content="当前图像模型 dall-e-3 不支持参考图，请改用 gpt-image 系列或 wan 系列",
                error="reference_not_supported",
            )

        reference_paths = [info["path"] for info in reference_images]

        def _do_generate():
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url)
            if not reference_paths:
                return client.images.generate(
                    model=model, prompt=prompt, n=1,
                    size=size, response_format="b64_json",
                )

            # 有参考图时走 images.edit（multipart，image 传文件列表，最多 4 张）
            handles = []
            try:
                for path in reference_paths:
                    handles.append(open(path, "rb"))
                return client.images.edit(
                    model=model, prompt=prompt, image=handles, n=1,
                    size=size, response_format="b64_json",
                )
            finally:
                for handle in handles:
                    try:
                        handle.close()
                    except OSError:
                        pass

        try:
            response = await asyncio.to_thread(_do_generate)
        except Exception as e:
            logger.error(f"[ImageGen] 生成失败: {e}")
            return ToolResult(success=False, content=f"图像生成失败: {str(e)}", error=str(e))

        image_data = response.data[0]
        if not (hasattr(image_data, 'b64_json') and image_data.b64_json):
            return ToolResult(success=False, content="模型未返回图像数据", error="no_image_data")

        output_dir = os.path.join(BASE_DIR, 'output')
        os.makedirs(output_dir, exist_ok=True)
        filename = datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '.png'
        filepath = os.path.join(output_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(base64.b64decode(image_data.b64_json))

        logger.info(f"[ImageGen] 图片已保存: {filepath}")

    return ToolResult(
        success=True,
        content=f"图像已生成并保存: {filepath}",
        data={"file_path": filepath, "prompt": prompt},
    )
