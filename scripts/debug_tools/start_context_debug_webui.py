# scripts/debug_tools/start_context_debug_webui.py
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.debug.webui_server import main


if __name__ == "__main__":
    main()
