# utils/paths.py
# 跨平台路径兼容工具：处理数据库/配置里残留的 Windows 绝对路径（D:\Projects\YukiV6\...）
import os
import re

from utils import BASE_DIR

# 匹配 Windows 盘符路径：D:\...、D:/...、/D:\...、\D:\... 四种形态
_WIN_ABS_RE = re.compile(r'^(?P<prefix>[/\\]?[A-Za-z]:)[\\/]+(?P<rest>.*)$')


def _existing_suffix_path(rest: str) -> str:
    """把“存储路径的尾部”接到项目根目录上，返回第一个真实存在的路径。

    例：D:\\Projects\\YukiV6\\scripts\\04_meme_cache_tools\\data\\stickers\\x.jpg
        → Projects/YukiV6/scripts/.../x.jpg   （不存在）
        → YukiV6/scripts/.../x.jpg            （不存在）
        → scripts/04_meme_cache_tools/data/stickers/x.jpg （存在 ✓）

    这样就不依赖“项目文件夹必须叫 YukiV6”这个脆弱前提：
    文件夹改名成 Yuki（或换成别的父目录结构）后，只要图片还在项目里就能找到。
    """
    parts = [p for p in rest.split('/') if p]
    for i in range(len(parts)):
        candidate = os.path.join(BASE_DIR, *parts[i:])
        if os.path.exists(candidate):
            return candidate
    return ""


def normalize_stored_path(path: str) -> str:
    """把数据库/配置中存储的图片路径转换为当前系统可用的路径。

    - Windows 上：原样返回（数据库里的路径本来就是本机路径）。
    - Linux/macOS 上：若路径是 Windows 盘符路径（D:\\...、D:/...、/D:\\...），
      剥掉盘符、反斜杠转正斜杠，再映射回项目根目录：
      先按项目目录名锚点，锚点对不上（文件夹被改名）时改为
      「存储路径尾部 + 项目根目录」的存在性探测，两者都找不到才退回拼接结果。
      已是 Linux 绝对路径或相对路径的，基本原样返回（相对路径会先按项目根试一次）。
    - 存在性探测：多个候选路径中优先返回真实存在的那个，都找不到则返回第一个候选
      （保证报错信息可读，而不是拼出一个奇怪的 // 路径）。
    """
    if not path or os.name == 'nt':
        return path

    raw = path.strip()
    # 剥掉 file:// 前缀（兼容入库时的不同形态）
    # 注意只剥 7 个字符：file:///home/x → /home/x（保留开头的斜杠），
    # 若剥 8 个字符会把 Linux 绝对路径变成一个找不到的相对路径。
    if raw.startswith('file://'):
        raw = raw[7:]

    # 已是 Linux 绝对路径（注意别误伤 /D:/ 这种 Windows 形态）
    if raw.startswith('/') and not re.match(r'^/[A-Za-z]:', raw):
        return raw
    # 相对路径：先尝试按项目根目录解析（数据库里的相对路径多以项目根为基准），
    #           解析不到则原样返回，由调用方按 cwd 处理
    if not raw.startswith('/') and not re.match(r'^[A-Za-z]:', raw):
        candidate = os.path.join(BASE_DIR, raw)
        return candidate if os.path.exists(candidate) else raw

    m = _WIN_ABS_RE.match(raw)
    if not m:
        return raw

    rest = m.group('rest').replace('\\', '/').strip('/')
    if not rest:
        return raw

    candidates = []

    # 候选1：以项目目录名为锚点，只保留它之后的部分（兼容 D:/Projects/YukiV6/ 与 D:/YukiV6/ 两种形态）
    project_name = os.path.basename(BASE_DIR.rstrip('/'))
    parts = rest.split('/')
    if project_name in parts:
        anchor = len(parts) - 1 - parts[::-1].index(project_name)
        tail = '/'.join(parts[anchor + 1:])
        if tail:
            candidates.append(os.path.join(BASE_DIR, tail))

    # 候选2：项目目录名对不上时（例如文件夹已从 YukiV6 改名为 Yuki），
    #        退化为「存储路径尾部 + 项目根目录」的存在性探测
    suffix = _existing_suffix_path(rest)
    if suffix:
        candidates.append(suffix)

    # 候选3：整段接在项目根后面
    candidates.append(os.path.join(BASE_DIR, rest))

    # 候选4：兜底——盘符剥掉后的原始形态
    candidates.append(os.path.join(BASE_DIR, raw.replace('\\', '/').lstrip('/')))

    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]
