import asyncio
import aiohttp
import time
import json
import sys
from pathlib import Path

# 将项目根目录加入路径以导入 config
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import cfg
from utils.http_client import create_tcp_connector

# --- 配置区 ---
# 1. 官方 DeepSeek 配置
OFFICIAL_KEY = cfg.BACKUP_API_KEY
OFFICIAL_URL = cfg.BACKUP_BASE_URL + "/chat/completions"

# 2. TeaTop 站配置 (刚才表现最好的 v3.2)
TEATOP_KEY = cfg.LLM_API_KEY
TEATOP_URL = cfg.LLM_BASE_URL + "/chat/completions"

TEST_PROMPT = "你是 Yuki，一个亲昵黏人的电子妹妹，称呼我为哥哥大人。现在请用一句话简短地向我问好，要体现出你很想我的样子。"


# --- 实验逻辑 ---
async def fetch_test(session, url, key, model_name, provider_name):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": TEST_PROMPT}],
        "max_tokens": 100,
        "temperature": 0.7,
        "stream": False  # 设为 False 方便计算总耗时
    }

    start = time.time()
    try:
        async with session.post(url, json=payload, headers=headers, timeout=30) as resp:
            elapsed = time.time() - start
            if resp.status == 200:
                data = await resp.json()
                content = data["choices"][0]["message"]["content"].replace("\n", " ")
                return {"ok": True, "time": elapsed, "content": content}
            else:
                return {"ok": False, "err": f"HTTP {resp.status}"}
    except Exception as e:
        return {"ok": False, "err": str(e)}


async def run_benchmark(provider, url, key, model, rounds=5):
    print(f"🚀 开始测试 {provider} ({model})...")
    async with aiohttp.ClientSession(connector=create_tcp_connector()) as session:
        results = []
        for i in range(rounds):
            res = await fetch_test(session, url, key, model, provider)
            results.append(res)
            print(f"  - Round {i + 1}: {'✅' if res['ok'] else '❌'} ({res.get('time', 0):.2f}s)")
            await asyncio.sleep(1)  # 避免 QPS 过载

        successes = [r for r in results if r["ok"]]
        avg_time = sum(r["time"] for r in successes) / len(successes) if successes else 0
        return {
            "name": provider,
            "success_rate": f"{len(successes)}/{rounds}",
            "avg_time": round(avg_time, 2),
            "sample_content": successes[0]["content"] if successes else "N/A"
        }


async def main():
    # 实验 A: 官方
    official_report = await run_benchmark("DeepSeek官方", OFFICIAL_URL, OFFICIAL_KEY, "deepseek-chat")
    # 实验 B: TeaTop
    teatop_report = await run_benchmark("TeaTop站", TEATOP_URL, TEATOP_KEY, "deepseek-v3.2")

    print("\n" + "=" * 80)
    print(f"{'服务提供方':<15} | {'稳定性':<10} | {'平均耗时':<8} | {'回复样板'}")
    print("-" * 80)
    for r in [official_report, teatop_report]:
        icon = "👑" if r['name'] == "DeepSeek官方" else "🔋"
        print(f"{icon} {r['name']:<12} | {r['success_rate']:<10} | {r['avg_time']:<6}s | {r['sample_content']}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())