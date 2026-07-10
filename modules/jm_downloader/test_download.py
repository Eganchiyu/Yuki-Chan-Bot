"""JM 下载器集成测试

验证模块导入、元数据获取、下载和文件生成功能。
使用本子 350234 测试，不发送消息，只验证本地流程。

用法:
    cd D:\\Projects\\YukiV6
    python -m modules.jm_downloader.test_download
"""
import sys
import os
import logging
import time

# 确保 YukiV6 根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger("jm_test")

TEST_ALBUM_ID = "350234"
TEST_RANGE_START = 1
TEST_RANGE_END = 5  # 只下5章，快速验证


def test_imports():
    """测试模块导入"""
    print("=" * 50)
    print("  测试 1: 模块导入")
    print("=" * 50)
    try:
        from modules.jm_downloader.cache import init_cache, get_jm_cache_path, clear_all_cache
        from modules.jm_downloader.converter import images_to_pdf, images_to_zip, webp_to_jpg_bytes
        from modules.jm_downloader.downloader import fetch_album_info, download_chapter, download_album
        from modules.jm_downloader.handler import handle_jm_command, _parse_jm_command
        print("  ✅ 所有模块导入成功\n")
        return True
    except Exception as exc:
        print(f"  ❌ 导入失败: {exc}\n")
        return False


def test_parse_command():
    """测试指令解析"""
    print("=" * 50)
    print("  测试 2: 指令解析")
    print("=" * 50)
    from modules.jm_downloader.handler import _parse_jm_command

    cases = [
        ("/jm123456", ("123456", None, None)),
        ("/jm 123456", ("123456", None, None)),
        ("/jm 123456 1-30", ("123456", 1, 30)),
        ("/jm123456 5-10", ("123456", 5, 10)),
        ("hello", None),
        ("/jm", None),
        ("/jm abc", None),
    ]

    all_pass = True
    for text, expected in cases:
        result = _parse_jm_command(text)
        status = "✅" if result == expected else "❌"
        if result != expected:
            all_pass = False
        print(f"  {status} '{text}' → {result}")

    print()
    return all_pass


def test_fetch_info():
    """测试元数据获取"""
    print("=" * 50)
    print(f"  测试 3: 获取本子 {TEST_ALBUM_ID} 元数据")
    print("=" * 50)
    from modules.jm_downloader.downloader import fetch_album_info

    try:
        start = time.perf_counter()
        info = fetch_album_info(TEST_ALBUM_ID)
        elapsed = time.perf_counter() - start

        print(f"  📖 标题: {info['title']}")
        print(f"  ✍️  作者: {info['author_str']}")
        print(f"  🏷️  标签: {', '.join(info['tags'][:5])}")
        print(f"  📚 章节数: {info['total_chapters']}")
        print(f"  ⏱️  耗时: {elapsed:.1f}s")
        print(f"  ✅ 元数据获取成功\n")
        return info
    except Exception as exc:
        print(f"  ❌ 获取失败: {exc}\n")
        return None


def test_download():
    """测试下载 + 文件生成"""
    print("=" * 50)
    print(f"  测试 4: 下载本子 {TEST_ALBUM_ID} 第{TEST_RANGE_START}-{TEST_RANGE_END}章")
    print("=" * 50)
    from modules.jm_downloader.downloader import download_album

    try:
        start = time.perf_counter()
        result = download_album(
            album_id=TEST_ALBUM_ID,
            range_start=TEST_RANGE_START,
            range_end=TEST_RANGE_END,
            max_chapters=30,
            output_format="zip",
            zip_password="",
            retention_days=3,
            max_cache_gb=3.0,
        )
        elapsed = time.perf_counter() - start

        if not result["success"]:
            print(f"  ❌ 下载失败: {result['error']}\n")
            return False

        print(f"  📖 {result['title']}")
        print(f"  📚 {result['chapter_range']}")
        print(f"  🖼️  图片: {result['image_count']}张")
        print(f"  ⏱️  耗时: {result['elapsed']:.1f}s")

        if result["zip_path"]:
            size_mb = result["zip_path"].stat().st_size / 1024 / 1024
            print(f"  📦 ZIP: {result['zip_path']} ({size_mb:.1f}MB)")
        if result["pdf_path"]:
            size_mb = result["pdf_path"].stat().st_size / 1024 / 1024
            print(f"  📄 PDF: {result['pdf_path']} ({size_mb:.1f}MB)")

        print(f"  ✅ 下载成功\n")
        return True
    except Exception as exc:
        print(f"  ❌ 下载异常: {exc}\n")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n🧪 JM 下载器集成测试\n")

    results = []

    # 测试 1: 导入
    results.append(("模块导入", test_imports()))
    if not results[-1][1]:
        print("❌ 导入失败，终止测试")
        return

    # 测试 2: 指令解析
    results.append(("指令解析", test_parse_command()))

    # 测试 3: 元数据
    info = test_fetch_info()
    results.append(("元数据获取", info is not None))
    if not info:
        print("❌ 元数据获取失败，终止测试")
        _print_summary(results)
        return

    # 测试 4: 下载
    results.append(("下载+生成", test_download()))

    _print_summary(results)


def _print_summary(results):
    print("=" * 50)
    print("  测试汇总")
    print("=" * 50)
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}  {name}")
    total = len(results)
    passed = sum(1 for _, p in results if p)
    print(f"\n  {passed}/{total} 通过\n")


if __name__ == "__main__":
    main()
