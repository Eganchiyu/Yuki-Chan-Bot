from __future__ import annotations

import os
import asyncio
import subprocess
from pathlib import Path
from typing import Any

try:
    from .server import HOST, PORT, is_server_running, start_background_server
except ImportError:
    from server import HOST, PORT, is_server_running, start_background_server

ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "frontend" / "minimal"


def ensure_server(
    session_pipeline: Any | None = None,
    pipeline_loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    start_background_server(session_pipeline, pipeline_loop)


def main(
    session_pipeline: Any | None = None,
    pipeline_loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    ensure_server(session_pipeline, pipeline_loop)
    npm = "npm.cmd" if os.name == "nt" else "npm"
    subprocess.Popen([npm, "run", "desktop"], cwd=FRONTEND_DIR)


if __name__ == "__main__":
    main()
