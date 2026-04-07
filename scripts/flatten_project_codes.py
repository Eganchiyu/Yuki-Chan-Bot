from pathlib import Path
import pathspec


def merge_project_files():
    # 1. 定位根目录 (scripts 的上一级)
    script_path = Path(__file__).resolve()
    root_dir = script_path.parent.parent

    output_filename = "project_for_ai.txt"
    output_path = root_dir / output_filename

    extensions = {".py", ".md", ".txt"}

    # 2. 加载 .gitignore
    gitignore_file = root_dir / ".gitignore"
    if gitignore_file.exists():
        with open(gitignore_file, "r", encoding="utf-8", errors="ignore") as f:
            spec = pathspec.PathSpec.from_lines('gitwildmatch', f.readlines())
    else:
        spec = pathspec.PathSpec.from_lines('gitwildmatch', [])

    ignored_patterns = {output_filename, "scripts/", ".git/", ".gitignore", "__pycache__/"}

    print(f"正在扫描: {root_dir}")
    count = 0

    with open(output_path, "w", encoding="utf-8") as outfile:
        for path in root_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in extensions:
                continue

            rel_path_str = str(path.relative_to(root_dir))

            # 排除检查
            if spec.match_file(rel_path_str) or any(p in rel_path_str for p in ignored_patterns):
                continue

            # 3. 尝试多种编码读取（解决 0xff 报错）
            content = None
            # 常见编码尝试序列：utf-8 -> utf-16 -> gbk (Windows常用)
            for encoding in ['utf-8', 'utf-16', 'gbk', 'latin-1']:
                try:
                    with open(path, "r", encoding=encoding) as infile:
                        content = infile.read()
                    break  # 如果成功读取则跳出循环
                except (UnicodeDecodeError, UnicodeError):
                    continue

            if content is not None:
                outfile.write("\n" + "=" * 60 + "\n")
                outfile.write(f"FILE_PATH: {rel_path_str}\n")
                outfile.write("=" * 60 + "\n\n")
                outfile.write(content)
                outfile.write("\n\n")
                print(f"✅ 已合并: {rel_path_str}")
                count += 1
            else:
                print(f"❌ 最终放弃: {rel_path_str} (所有已知编码均无法读取)")

    print(f"\n--- 任务完成 ---")
    print(f"成功合并 {count} 个文件 -> {output_path}")


if __name__ == "__main__":
    merge_project_files()