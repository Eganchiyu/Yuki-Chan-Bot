# test_vision_models_local.py
import aiohttp
import asyncio
import base64
import cv2
import numpy as np
import os
import json
from datetime import datetime

OPENAI_API_KEY = "sk-X1BZhjc24oeZfH9dSinRn8UVQnV4kUvLHEhCCyJbWYTCcbQG"
OPENAI_API_URL = "https://api.ytea.top/v1"

# 使用本地图片
LOCAL_IMAGE_PATH = "1.jpg"  # 根目录下的1.jpg

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def load_local_image(image_path):
    """从本地加载图片"""
    try:
        with open(image_path, 'rb') as f:
            return f.read()
    except Exception as e:
        log(f"读取本地图片失败: {e}")
        return None

def compress_image(image_data, max_size=640, quality=70):
    """压缩图片为base64"""
    try:
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            log("无法读取图片")
            return None
        h, w = img.shape[:2]
        if max(h, w) > max_size:
            scale = max_size / max(h, w)
            new_w, new_h = int(w * scale), int(h * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            log(f"尺寸从 {w}x{h} 压缩到 {new_w}x{new_h}")
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        _, buffer = cv2.imencode('.jpg', img, encode_param)
        return base64.b64encode(buffer).decode('utf-8')
    except Exception as e:
        log(f"压缩失败: {e}")
        return None

async def test_model(model_name, b64_data):
    """测试单个模型"""
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    full_url = f"{OPENAI_API_URL.rstrip('/')}/chat/completions"
    
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"}},
                    {"type": "text", "text": "用一句话描述这个表情包，不超过12个字"}
                ]
            }
        ],
        "max_tokens": 50,
        "temperature": 0.75
    }
    
    log(f"测试模型: {model_name}")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(full_url, json=payload, headers=headers) as resp:
                log(f"状态码: {resp.status}")
                if resp.status == 200:
                    result = await resp.json()
                    content = result["choices"][0]["message"]["content"]
                    log(f"✅ 识别结果: {content}")
                    return True, content
                else:
                    text = await resp.text()
                    log(f"❌ 错误: {text[:200]}")
                    return False, text
        except Exception as e:
            log(f"❌ 异常: {e}")
            return False, str(e)

async def main():
    print("="*60)
    print("精选视觉模型测试（本地图片）")
    print("="*60)
    
    # 检查本地图片
    if not os.path.exists(LOCAL_IMAGE_PATH):
        print(f"❌ 图片不存在: {LOCAL_IMAGE_PATH}")
        return
    
    print(f"📸 使用本地图片: {LOCAL_IMAGE_PATH}")
    
    # 加载图片
    img_data = load_local_image(LOCAL_IMAGE_PATH)
    if not img_data:
        return
    
    # 压缩图片
    print("🔄 压缩图片...")
    b64_data = compress_image(img_data)
    if not b64_data:
        return
    
    # 精选测试模型
    test_models = [
        "qwen3-vl-flash",        # Qwen最新视觉快版（便宜）
        "glm-4.6v",              # 智谱视觉（国内优化）
        "yi-vision-v2",          # 零一万物视觉（中文好）
        "qwen-vl-plus-latest",   # 通义增强版（平衡）
        "gpt-4o-mini-ca",        # 贵的但试试
    ]
    
    print(f"\n📋 共 {len(test_models)} 个精选模型")
    print("="*60)
    
    results = []
    for i, model in enumerate(test_models, 1):
        print(f"\n[{i}/{len(test_models)}] ", end="")
        success, result = await test_model(model, b64_data)
        results.append((model, success, result))
        await asyncio.sleep(1)  # 避免请求太快
    
    # 汇总
    print("\n" + "="*60)
    print("📊 测试结果汇总")
    print("="*60)
    for model, success, result in results:
        if success:
            print(f"✅ {model}: {result}")
        else:
            print(f"❌ {model}: 失败")
    
    # 推荐
    print("\n" + "="*60)
    print("💡 推荐模型")
    print("="*60)
    successful = [(m, r) for m, s, r in results if s]
    if successful:
        for model, result in successful:
            print(f"👉 {model} -> {result}")
        print("\n选一个效果最好的缝合进Yuki！")
    else:
        print("❌ 没有可用的视觉模型")

if __name__ == "__main__":
    asyncio.run(main())