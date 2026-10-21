"""无 pytest 环境下的最小测试 runner：收集 test_*.py 里的 test_* 函数逐个执行。

用法: python run_tests.py [模块名...]   （默认跑 tests/ 下全部）
"""
import asyncio
import importlib.util
import inspect
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TESTS = os.path.join(ROOT, "tests")


def load(path):
    name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main(targets):
    if not targets:
        targets = sorted(
            os.path.join(TESTS, f) for f in os.listdir(TESTS)
            if f.startswith("test_") and f.endswith(".py")
        )
    passed = failed = 0
    for path in targets:
        try:
            mod = load(path)
        except Exception:
            print(f"[LOAD ERROR] {path}")
            traceback.print_exc()
            failed += 1
            continue
        for name, fn in sorted(vars(mod).items()):
            if not (name.startswith("test_") and callable(fn)):
                continue
            try:
                result = fn()
                if inspect.iscoroutine(result):
                    asyncio.run(result)
                passed += 1
                print(f"PASS {os.path.basename(path)}::{name}")
            except Exception:
                failed += 1
                print(f"FAIL {os.path.basename(path)}::{name}")
                traceback.print_exc()
    print(f"\n=== passed={passed} failed={failed} ===")
    return 1 if failed else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    paths = [a if os.path.isabs(a) else os.path.join(TESTS, a if a.endswith(".py") else a + ".py")
             for a in args]
    sys.exit(main(paths))
