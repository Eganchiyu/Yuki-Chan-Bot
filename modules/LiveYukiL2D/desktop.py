from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Any

try:
    from .server import start_background_server
except ImportError:
    from server import start_background_server

ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "frontend" / "minimal"


def ensure_server(
    session_pipeline: Any | None = None,
    pipeline_loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    start_background_server(session_pipeline, pipeline_loop)


# ======== 桌宠窗口启动与桌面 API 逻辑主函数 ========

def main(
    session_pipeline: Any | None = None,
    pipeline_loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    ensure_server(session_pipeline, pipeline_loop)
    npm = "npm.cmd" if os.name == "nt" else "npm"
    subprocess.Popen([npm, "run", "desktop"], cwd=FRONTEND_DIR)


if __name__ == "__main__":
    main()
