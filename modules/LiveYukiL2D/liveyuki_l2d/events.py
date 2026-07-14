from __future__ import annotations

from typing import Any


def error_event(message: str, task_id: str | None = None) -> dict[str, Any]:
    event: dict[str, Any] = {"type": "error", "message": message}
    if task_id:
        event["task_id"] = task_id
    return event
