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


async def generate_image_tool(context, prompt, size="1024*1024"):
    """调用图像生成模型生成图片，保存到 output 目录并返回路径。"""
    if not prompt:
        return ToolResult(success=False, content="缺少图像描述", error="missing_prompt")

    api_key = cfg.IMAGE_GEN_API_KEY
    if not api_key:
        return ToolResult(success=False, content="未配置 image_gen_api_key", error="missing_api_key")

    base_url = cfg.IMAGE_GEN_URL
    model = cfg.IMAGE_GEN_MODEL
    # 兼容 "1024x1024" → "1024*1024"
    size = size.replace("x", "*").replace("X", "*")

    # wan 系列走 DashScope 原生 API，其他走 OpenAI 兼容接口
    use_native = model.startswith("wan")

    if use_native:
        host_match = re.match(r'(https://[^/]+)/compatible-mode/v1', base_url)
        if host_match:
            api_endpoint = f"{host_match.group(1)}/api/v1/services/aigc/multimodal-generation/generation"
        else:
            api_endpoint = f"{base_url.rstrip('/')}/api/v1/services/aigc/multimodal-generation/generation"

        payload = {
            "model": model,
            "input": {
                "messages": [
                    {"role": "user", "content": [{"text": prompt}]}
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
        def _do_generate():
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url)
            return client.images.generate(
                model=model, prompt=prompt, n=1,
                size=size, response_format="b64_json",
            )

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
