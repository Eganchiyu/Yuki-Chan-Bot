import asyncio
import aiohttp


async def debug_qwen():
    # 替换成你那个 sk-780c... 的完整 Key
    api_key = "sk-".strip()
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "qwen-vl-plus",
        "messages": [{"role": "user", "content": "你好"}]
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            print(f"状态码: {resp.status}")
            result = await resp.text()
            print(f"响应内容: {result}")


if __name__ == "__main__":
    asyncio.run(debug_qwen())