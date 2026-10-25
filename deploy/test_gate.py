#!/usr/bin/env python3
"""测试门：与基线对比，只对「本次改动新增的失败」报警。

为什么需要基线：项目里有 20+ 个依赖环境/网络的既有失败（缺 NapCat、缺模型、
Windows 专用路径等）。如果门要求全绿，自进化会被永久卡死；如果完全不看，
回归又会漏过去。所以只比较差集。

用法：
    python deploy/test_gate.py                    # 对比基线，有新增失败则退出 1
    python deploy/test_gate.py --print-fails      # 只打印当前失败清单（用于生成基线）
    python deploy/test_gate.py --update-baseline   # 写基线（需要在可写环境执行）
"""
import json
import os
import subprocess
import sys

ROOT = os.environ.get("YUKI_ROOT") or os.getcwd()
TESTS = os.path.join(ROOT, "tests")
BASELINE = os.environ.get("YUKI_TEST_BASELINE", os.path.join(ROOT, "deploy", "test_baseline.json"))


def run_tests():
    proc = subprocess.run(
        [sys.executable, "run_tests.py"],
        cwd=TESTS, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=900,
    )
    out = proc.stdout or ""
    fails = sorted(
        line.split(" ", 1)[1].strip()
        for line in out.splitlines()
        if line.startswith("FAIL ") and "::" in line
    )
    summary = next((l for l in out.splitlines() if l.startswith("=== passed=")), "")
    return fails, summary, out


def main():
    fails, summary, raw = run_tests()

    if "--print-fails" in sys.argv:
        print(json.dumps({"fails": fails, "summary": summary}, ensure_ascii=False, indent=2))
        return 0

    baseline = []
    if os.path.exists(BASELINE):
        try:
            with open(BASELINE, encoding="utf-8") as f:
                baseline = json.load(f).get("fails", [])
        except Exception as e:
            print(f"基线读取失败（按空基线处理）: {e}")

    if "--update-baseline" in sys.argv:
        os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump({"fails": fails, "summary": summary}, f, ensure_ascii=False, indent=2)
        print(f"基线已更新: {len(fails)} 个已知失败 -> {BASELINE}")
        return 0

    new_fails = [f for f in fails if f not in baseline]
    fixed = [f for f in baseline if f not in fails]

    print(summary or "(无测试摘要)")
    print(f"已知失败 {len(baseline)} 个，当前失败 {len(fails)} 个，新增 {len(new_fails)} 个")
    if fixed:
        print(f"本次修好了 {len(fixed)} 个：{', '.join(fixed[:5])}")

    if new_fails:
        print("GATE_FAILED: 新增失败用例（疑似本次改动引入回归）")
        for f in new_fails[:20]:
            print(f"  ✗ {f}")
        # 把 traceback 尾巴也带上，方便回灌给小女仆
        print("\n--- 测试输出尾部 ---")
        print("\n".join((raw or "").splitlines()[-40:]))
        return 1

    print("测试门通过：无新增失败")
    return 0


if __name__ == "__main__":
    sys.exit(main())
