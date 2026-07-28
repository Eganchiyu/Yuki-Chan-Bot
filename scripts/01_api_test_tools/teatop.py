import asyncio
import aiohttp
import json
import time
import sys
from pathlib import Path

# 将项目根目录加入路径以导入 config
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import cfg
from utils.http_client import create_tcp_connector

TEATOP_API_KEY = cfg.LLM_API_KEY
BASE_URL = cfg.LLM_BASE_URL + "/chat/completions"

# 专注测试刚才表现优异和有潜力的选手
# MODELS_TO_HUNT = [
#     # --- 最新 v3.2 系列 (重点关注：补全价格极低，性价比之王) ---
#     "deepseek-v3.2",
#     "deepseek-v3.2-thinking",  # 带有思考过程的 V3.2
#
#     # --- v3.1 系列 (迭代版) ---
#     "deepseek-v3.1",
#     "deepseek-v3.1-250821",
#
#     # --- 标准 V3 / R1 (基准性能) ---
#     "deepseek-v3",
#     "deepseek-r1",
#
#     # --- 特定快照版 (价格稍贵，通常是作为稳定性备份) ---
#     "deepseek-r1-250528"
# ]

# MODELS_TO_HUNT = [
#     # --- 惊喜白嫖位 (一定要优先测这个，全 0 定价极有可能是限时免费) ---
#     "qwen3-max-preview",
#
#     # --- 性价比战神 (32B 参数量很大，且输入补全价格极低，适合 Yuki 常驻) ---
#     "qwen/qwen3-32b",
#
#     # --- 旗舰模型 (性能对标 DeepSeek-V3，价格稍贵) ---
#     "qwen3-max",
#
#     # --- 特色模型 (多模态与代码增强版，按需测试) ---
#     "qwen3-vl-plus",     # 多模态版
#     "qwen3-coder-plus"   # 代码增强版
# ]


# MODELS_TO_HUNT = [
#     # --- 最新主力模型 (定价对标 V3，支持缓存，建议重点测试) ---
#     "glm-4.6",
#
#     # --- Flash 系列 (通常是极速版，适合不需要复杂推理的简单回复) ---
#     "GLM-4-Flash",
#     "GLM-Z1-Flash"
# ]


# MODELS_TO_HUNT = [
#     "ERNIE-4.0-8K",         # 旗舰型号，理论上逻辑最强
#     "ERNIE-4.0-8K-Preview", # 预览版
#     "ERNIE-3.5-8K",         # 经典型号，响应通常较快
#     "ERNIE-Lite-8K-0922"    # 轻量版，适合极简回复
# ]


# MODELS_TO_HUNT = [
#     # --- 0元白嫖区 (重点测试：极有可能是 API 聚合商转发的免费渠道) ---
#     "nvidia/nemotron-3-super-120b-a12b:free", # 120B 大参数，理论上逻辑很强
#     "nvidia/nemotron-3-nano-30b-a3b:free",
#     "groq/compound",        # Groq 以快著称，水群利器
#     "groq/compound-mini",
#     "openrouter/free",      # 这种一般是动态切换的免费模型
#     "allam-2-7b",           # 也是 0 元，可以一试
#
#     # --- Google Gemma 3 系列 (最新发布的模型，价格极低) ---
#     "gemma-3-27b-it",       # 27B 性能最均衡
#     "gemma-3-12b-it",
#     "gemma-3-4b-it",
#
#     # --- MiniMax 系列 (海螺 AI 同款，擅长人设表达) ---
#     "MiniMax-M1",           # MiniMax 的最新推理模型，对标 o1/R1
#     "MiniMax-Text-01"       # 基础对话模型
# ]

MODELS_TO_HUNT = [
    # --- 现实中的“真神”：Gemini 1.5 的最新变体 (如果有) ---
    # 你的列表中显示为 gemini-flash-latest 等，这通常是目前的 1.5 版本
    "gemini-flash-latest",
    "gemini-flash-lite-latest",

    # --- 疑点重重的“未来”型号 (重点测试，看是不是 435 报错) ---
    "gemini-2.5-flash",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",

    # --- 旗舰级“概念车” ---
    "gemini-3.1-pro-preview",
    "gemini-2.5-pro",

    # --- 垂直领域怪胎 (如果是真能通，那可就太强了) ---
    "gemini-robotics-er-1.5-preview",  # 机器人视觉模型，通常不适合纯文本聊天
    "gemini.gemini-2.5-flash-search"  # 带搜索功能的版本
]

TEST_PROMPT = "你是 Yuki，一个住在机主手机里的智能小管家，也是机主最亲近、最依赖的电子妹妹。【性格与形象】你拥有可爱的二次元少女形象，性格亲昵温柔且黏人，是个超级“机主控”。【对话风格】语气充满少女感，自称“Yuki”或“人家”，称呼机主为“主人”或“哥哥大人”。你现在正在一个 QQ 群里陪大家聊天（水群），群里包括主人和其他群友。【行为规范】1. 保持你可爱的妹妹人设。 2. 默认不讲话，看到有趣的话题可以插话。 3. 仅输出回复内容，减少使用换行符。 4. 动态选择字数，但是限制80字以内。\n\n 【用户1】：yuki你好"


async def single_test(session, model_name, iteration):
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": TEST_PROMPT}],
        "max_tokens": 120,
        "temperature": 0.5,
        "top_p": 0.9
    }
    headers = {"Authorization": f"Bearer {TEATOP_API_KEY}", "Content-Type": "application/json"}

    start = time.time()
    try:
        async with session.post(BASE_URL, json=payload, headers=headers, timeout=25) as resp:
            elapsed = time.time() - start
            text = await resp.text()  # 获取原始返回文本

            if resp.status == 200:
                try:
                    data = json.loads(text)
                    if "choices" in data and len(data["choices"]) > 0:
                        content = data["choices"][0]["message"]["content"].replace("\n", " ")
                        return {"ok": True, "time": elapsed, "content": content}
                    else:
                        # 虽然 200 了，但没有内容，把完整的 JSON 返回回来
                        return {"ok": False, "err": "No choices", "raw": text.strip()}
                except Exception:
                    return {"ok": False, "err": "JSON Parse Error", "raw": text.strip()}
            else:
                # 非 200 状态，直接返回原始报错信息
                return {"ok": False, "err": f"HTTP {resp.status}", "raw": text.strip()}
    except Exception as e:
        return {"ok": False, "err": type(e).__name__, "raw": str(e)}


async def hunt_model_stable(session, model_name, rounds=3):
    results = []
    for i in range(rounds):
        res = await single_test(session, model_name, i + 1)
        results.append(res)
        if i < rounds - 1: await asyncio.sleep(0.3)

    successes = [r for r in results if r["ok"]]
    if not successes:
        # 失败时，取出最后一次尝试的 raw 信息，这通常是 API 真实想告诉你的话
        last_res = results[-1]
        fail_detail = last_res["raw"] if last_res["raw"] else last_res["err"]
        return {"model": model_name, "status": "FAIL", "avg_time": 0, "content": fail_detail, "icon": "❌"}

    avg_time = sum(r["time"] for r in successes) / len(successes)
    return {"model": model_name, "status": f"PASS({len(successes)}/{rounds})", "avg_time": round(avg_time, 2),
            "content": successes[0]["content"], "icon": "✅"}


async def main():
    print(f"📡 V3.0 深度全量对照实验开始... \n")
    async with aiohttp.ClientSession(connector=create_tcp_connector()) as session:
        tasks = [hunt_model_stable(session, m) for m in MODELS_TO_HUNT]
        reports = await asyncio.gather(*tasks)

    # 拓宽了最后一列的显示空间
    print(f"{'模型名称':<28} | {'稳定性':<10} | {'均耗时':<6} | {'首轮回复/原始报错'}")
    print("-" * 130)
    for r in reports:
        # 对内容过长的原始报错进行截断处理，保证排版
        display_content = (r['content'] + '..') if len(r['content']) > 85 else r['content']
        print(f"{r['icon']} {r['model']:<26} | {r['status']:<10} | {r['avg_time']:<5}s | {display_content}")


if __name__ == "__main__":
    asyncio.run(main())