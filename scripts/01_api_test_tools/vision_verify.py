import asyncio
import aiohttp
import time
import os
import sys
from pathlib import Path

# 将项目根目录加入路径以导入 config
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import cfg
from utils.http_client import create_tcp_connector

# --- 配置区 ---
API_KEY = cfg.LLM_API_KEY
BASE_URL = cfg.LLM_BASE_URL + "/chat/completions"  # 从配置中读取
# 待验证的模型列表
MODELS_TO_CHECK = [
    "qwen3-vl-plus",
    "gemini-2.5-flash",
    "gpt-4o-mini-ca",
    "GLM-4-Flash"
]

import base64

def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        # 读取图片二进制数据
        binary_data = image_file.read()
        # 转换为 base64 编码
        base64_encoded = base64.b64encode(binary_data).decode('utf-8')
        return base64_encoded

# 使用示例
image_path = "test_image.jpg"
TEST_B64 = image_to_base64(image_path)


# 用于测试的图片（1x1 像素的红色图片 Base64，防止网络下载干扰，确保只测试接口通路）
# 如果你想测试真实识别能力，可以把下面的字符串换成你程序里生成的真实 Base64


async def verify_b64_model(session, model_name):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    # 构造标准的 OpenAI 格式 Payload
    # 注意：data:image/png;base64, 这一段前缀非常关键
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请告诉我你在这张图里看到了什么颜色？"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{TEST_B64}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 50
    }

    start_time = time.time()
    try:
        async with session.post(BASE_URL, json=payload, headers=headers, timeout=30) as resp:
            elapsed = time.time() - start_time
            if resp.status == 200:
                data = await resp.json()
                content = data['choices'][0]['message']['content']
                # 检查回复内容，判断模型是否真的“看”到了图
                return True, elapsed, content
            else:
                err_text = await resp.text()
                return False, elapsed, f"HTTP {resp.status}: {err_text}"
    except Exception as e:
        return False, 0, str(e)


async def main():
    print(f"🧪 开始 Base64 模式下视觉模型通路验证...\n")
    async with aiohttp.ClientSession(connector=create_tcp_connector()) as session:
        for model in MODELS_TO_CHECK:
            print(f"正在验证 [{model}] ...", end="", flush=True)
            success, cost, result = await verify_b64_model(session, model)

            if success:
                print(f" ✅ 响应成功!")
                print(f"    - 耗时: {cost:.2f}s")
                print(f"    - 模型回复: {result}")
                # 逻辑判断：如果模型说“我看不到图”或者回复极其简短无关，可能依然没通
                if "红" in result or "Red" in result.lower() or "color" in result.lower():
                    print(f"    - 验证结论: 视觉理解【真实有效】")
                else:
                    print(f"    - 验证结论: ⚠️ 接口通了但模型可能没看图（睁眼瞎）")
            else:
                print(f" ❌ 失败")
                print(f"    - 错误原因: {result}")
            print("-" * 50)


if __name__ == "__main__":
    asyncio.run(main())