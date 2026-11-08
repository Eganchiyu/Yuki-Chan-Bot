
from pathlib import Path
from typing import Iterator
import codecs
import sys

from pathspec import PathSpec


# =========================
# 配置
# =========================

# 合并后的输出文件名
OUTPUT_NAME = "merged_files.txt"

# 文件路径分隔线
SEPARATOR = "================"

# 是否跳过符号链接，避免意外读取项目目录之外的文件
SKIP_SYMLINKS = True

# 根目录：脚本所在文件夹
ROOT = Path(__file__).resolve().parent

# 输出文件绝对路径
OUTPUT_PATH = (ROOT / OUTPUT_NAME).resolve()


# =========================
# .gitignore 处理
# =========================

def load_gitignore(directory: Path):
    """
    读取当前目录下的 .gitignore。
    返回 GitWildMatch 规则集。
    """
    gitignore = directory / ".gitignore"

    if not gitignore.is_file():
        return None

    try:
        lines = gitignore.read_text(
            encoding="utf-8-sig",
            errors="replace"
        ).splitlines()

        return PathSpec.from_lines("gitwildmatch", lines)

    except Exception as exc:
        print(f"[警告] 无法读取 {gitignore}: {exc}", file=sys.stderr)
        return None



def is_ignored(
    path: Path,
    is_directory: bool,
    ignore_rules: list
) -> bool:
    """
    判断文件或文件夹是否被 .gitignore 忽略。
    """
    ignored = False

    for base_dir, spec in ignore_rules:
        try:
            relative_path = path.relative_to(base_dir).as_posix()
        except ValueError:
            continue

        if is_directory:
            relative_path += "/"

        result = spec.check_file(relative_path)

        # True 代表匹配忽略规则
        # False 代表匹配 ! 反向放行规则
        # None 代表没有匹配
        if result.include is not None:
            ignored = result.include

    return ignored



# =========================
# 递归遍历
# =========================

def iter_files(
    directory: Path,
    inherited_rules: list
) -> Iterator[Path]:
    """
    递归遍历目录，按照各级 .gitignore 规则筛选文件。
    """

    # 继承父目录的忽略规则
    current_rules = list(inherited_rules)

    # 加载当前目录的 .gitignore
    local_spec = load_gitignore(directory)

    if local_spec is not None:
        current_rules.append((directory, local_spec))

    try:
        entries = sorted(
            directory.iterdir(),
            key=lambda p: (p.name.casefold(), p.name)
        )
    except PermissionError:
        print(f"[跳过] 无权访问目录：{directory}", file=sys.stderr)
        return
    except OSError as exc:
        print(f"[跳过] 无法访问目录 {directory}: {exc}", file=sys.stderr)
        return

    for entry in entries:

        # 避免读取 .git 内部元数据
        if entry.name == ".git":
            continue

        # 不跟随符号链接
        if SKIP_SYMLINKS and entry.is_symlink():
            continue

        try:
            if entry.is_dir():

                # 被忽略的目录不再向下遍历
                if is_ignored(entry, True, current_rules):
                    continue

                yield from iter_files(entry, current_rules)

            elif entry.is_file():

                # 防止将本次输出文件再次合并进去
                if entry.resolve() == OUTPUT_PATH:
                    continue

                if is_ignored(entry, False, current_rules):
                    continue

                yield entry

        except OSError as exc:
            print(f"[跳过] 无法处理 {entry}: {exc}", file=sys.stderr)


# =========================
# 文件内容读取
# =========================

def read_file(path: Path) -> tuple[str | None, str]:
    """
    读取文件并尽可能识别文本编码。

    支持：
    - UTF-8
    - UTF-8 BOM
    - UTF-16 / UTF-32 BOM
    - GB18030

    二进制文件不读取原始内容。
    """

    raw = path.read_bytes()

    if not raw:
        return "", "utf-8"

    # 优先处理带 BOM 的文本文件
    if raw.startswith(codecs.BOM_UTF32_LE) or \
       raw.startswith(codecs.BOM_UTF32_BE):
        return raw.decode("utf-32"), "utf-32"

    if raw.startswith(codecs.BOM_UTF16_LE) or \
       raw.startswith(codecs.BOM_UTF16_BE):
        return raw.decode("utf-16"), "utf-16"

    if raw.startswith(codecs.BOM_UTF8):
        return raw.decode("utf-8-sig"), "utf-8-sig"

    # 二进制文件通常包含大量 NUL 字节
    if b"\x00" in raw[:8192]:
        return None, "binary"

    # 检查控制字符比例，辅助识别非文本文件
    sample = raw[:8192]

    control_count = sum(
        1 for byte in sample
        if byte < 32 and byte not in (7, 8, 9, 10, 12, 13, 27)
    )

    if control_count / len(sample) > 0.05:
        return None, "binary"

    # 尝试常见文本编码
    for encoding in ("utf-8", "gb18030"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue

    return None, "unknown"


# =========================
# 合并输出
# =========================

def merge_files():

    file_count = 0
    text_count = 0
    binary_count = 0
    error_count = 0

    print(f"项目目录：{ROOT}")
    print(f"输出文件：{OUTPUT_PATH}")
    print("开始扫描并合并...\n")

    with OUTPUT_PATH.open(
        "w",
        encoding="utf-8",
        newline="\n"
    ) as output:

        for file_path in iter_files(ROOT, []):

            relative_path = file_path.relative_to(ROOT).as_posix()

            file_count += 1

            print(f"[{file_count}] {relative_path}")

            output.write(f"{SEPARATOR}\n")
            output.write(f"{relative_path}\n")
            output.write(f"{SEPARATOR}\n")

            try:
                content, encoding = read_file(file_path)

                if content is None:

                    if encoding == "binary":
                        output.write("[二进制文件：内容已跳过]\n")
                        binary_count += 1
                    else:
                        output.write("[无法识别文件编码：内容已跳过]\n")
                        error_count += 1

                else:
                    output.write(content)

                    # 保证下一个分隔符从新的一行开始
                    if content and not content.endswith("\n"):
                        output.write("\n")

                    text_count += 1

            except Exception as exc:
                output.write(f"[文件读取失败：{exc}]\n")
                error_count += 1

            output.write("\n")

    print("\n========== 合并完成 ==========")
    print(f"扫描文件数：{file_count}")
    print(f"文本文件数：{text_count}")
    print(f"二进制文件：{binary_count}")
    print(f"读取异常数：{error_count}")
    print(f"输出位置：{OUTPUT_PATH}")


if __name__ == "__main__":
    merge_files()
