# utils/paths.py
# 跨平台路径兼容工具：处理数据库/配置里残留的 Windows 绝对路径（D:\Projects\YukiV6\...）
import os
import re

from utils import BASE_DIR

# 匹配 Windows 盘符路径：D:\...、D:/...、/D:\...、\D:\... 四种形态
_WIN_ABS_RE = re.compile(r'^(?P<prefix>[/\\]?[A-Za-z]:)[\\/]+(?P<rest>.*)$')


def normalize_stored_path(path: str) -> str:
    """把数据库/配置中存储的图片路径转换为当前系统可用的路径。

    - Windows 上：原样返回（数据库里的路径本来就是本机路径）。
    - Linux/macOS 上：若路径是 Windows 盘符路径（D:\\...、D:/...、/D:\\...），
      剥掉盘符、反斜杠转正斜杠，再以项目目录名为锚点映射回项目根目录；
      已是 Linux 绝对路径或相对路径的，原样返回。
    - 存在性探测：多个候选路径中优先返回真实存在的那个，都找不到则返回第一个候选
      （保证报错信息可读，而不是拼出一个奇怪的 // 路径）。
    """
    if not path or os.name == 'nt':
        return path

    raw = path.strip()
    # 剥掉 file:// 前缀（兼容入库时的不同形态）
    if raw.startswith('file:///'):
        raw = raw[8:]
    elif raw.startswith('file://'):
        raw = raw[7:]

    # 已是 Linux 绝对路径（注意别误伤 /D:/ 这种 Windows 形态）
    if raw.startswith('/') and not re.match(r'^/[A-Za-z]:', raw):
        return raw
    # 相对路径：保持原样，由调用方按 cwd 解析
    if not raw.startswith('/'):
        # 但若相对路径其实以盘符开头（如 D:xxx），仍按 Windows 路径处理
        if not re.match(r'^[A-Za-z]:', raw):
            return raw

    m = _WIN_ABS_RE.match(raw)
    if not m:
        return raw

    rest = m.group('rest').replace('\\', '/').strip('/')
    if not rest:
        return raw

    project_name = os.path.basename(BASE_DIR.rstrip('/'))
    candidates = []

    # 候选1：以项目目录名为锚点，只保留它之后的部分（兼容 D:/Projects/YukiV6/ 与 D:/YukiV6/ 两种形态）
    parts = rest.split('/')
    if project_name in parts:
        anchor = len(parts) - 1 - parts[::-1].index(project_name)
        tail = '/'.join(parts[anchor + 1:])
        if tail:
            candidates.append(os.path.join(BASE_DIR, tail))

    # 候选2：整段接在项目根后面
    candidates.append(os.path.join(BASE_DIR, rest))

    # 候选3：兜底——盘符剥掉后的原始形态
    candidates.append(os.path.join(BASE_DIR, raw.replace('\\', '/').lstrip('/')))

    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]
