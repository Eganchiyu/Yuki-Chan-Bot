import os
import sys

# 魔法代码：动态获取当前文件的上一级（也就是 YukiV6 根目录），并塞进环境变量
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

# 现在 Python 能看到根目录的 config.py 了，再正常导入就没问题啦
from core.maid.maid import search_diary_fast

def run_tests():
    print(f"{' Yuki 记忆检索引擎测试 ':=^40}")
    
    # 测试用例 1：精确日期搜索
    print("\n▶ 测试 1: 仅按日期搜索 (例如: '2026-05-20')")
    res_date = search_diary_fast(date_str="2026-05-20")
    print(res_date)
    
    # 测试用例 2：纯关键词搜索
    print("\n▶ 测试 2: 仅按关键词搜索 (例如: '生日')")
    res_kw = search_diary_fast(keyword="生日")
    print(res_kw)
    
    # 测试用例 3：日期与关键词组合搜索
    print("\n▶ 测试 3: 日期 + 关键词组合搜索 (例如: '2026-05' + '代码')")
    res_combo = search_diary_fast(date_str="2026-05", keyword="代码")
    print(res_combo)

    # 测试用例 4：异常/空值兜底测试
    print("\n▶ 测试 4: 异常输入测试 (空参数)")
    res_empty = search_diary_fast()
    print(res_empty)
    
    print(f"\n{' 测试结束 ':=^40}")

if __name__ == "__main__":
    run_tests()