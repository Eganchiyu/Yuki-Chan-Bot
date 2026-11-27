#!/usr/bin/env python3
"""宿主机 → 容器 data/inbox/ 的文件同步（定时任务用，stdlib only）。

宿主机侧来源目录（任选存在者）：
    $YUKI_INBOX_SOURCES（冒号分隔，可覆盖）
    默认：$HOME/Yuki/host_inbox、/tmp/yuki_outbox
落点：$ROOT/data/inbox/（data/ 是容器 rw 挂载，容器内外同路径）。
文件在同一挂载上，容器内可直接用 /home/asumi/Yuki/data/inbox/<name> 发送。
"""
import os
import shutil
import sys
import time

ROOT = os.environ.get("YUKI_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOME = os.path.expanduser("~")
DEST = os.path.join(ROOT, "data", "inbox")
MAX_BYTES = int(os.environ.get("YUKI_INBOX_MAX_BYTES", 200 * 1024 * 1024))
MIN_AGE = float(os.environ.get("YUKI_INBOX_MIN_AGE", 3.0))


def sources():
    raw = os.environ.get("YUKI_INBOX_SOURCES", "")
    dirs = [p for p in raw.split(":") if p.strip()]
    return dirs or [os.path.join(HOME, "Yuki", "host_inbox"), "/tmp/yuki_outbox"]


def sync(log=print):
    os.makedirs(DEST, exist_ok=True)
    copied = 0
    for src_dir in sources():
        if not os.path.isdir(src_dir):
            continue
        for name in sorted(os.listdir(src_dir)):
            if name.startswith("."):
                continue
            src = os.path.join(src_dir, name)
            if not os.path.isfile(src):
                continue
            try:
                st = os.stat(src)
            except OSError:
                continue
            if st.st_size > MAX_BYTES or (time.time() - st.st_mtime) < MIN_AGE:
                continue
            dst = os.path.join(DEST, name)
            try:
                if os.path.isfile(dst) and os.path.getsize(dst) == st.st_size and os.path.getmtime(dst) >= st.st_mtime:
                    continue
                shutil.copy2(src, dst)
                copied += 1
                log(f"inbox: {src} -> {dst}")
            except OSError as e:
                log(f"inbox 复制失败 {src}: {e}")
    return copied


if __name__ == "__main__":
    n = sync()
    if "--verbose" in sys.argv:
        print(f"synced {n} file(s) -> {DEST}")
