from __future__ import annotations

from typing import Any


def set_model_message(
    model_info: dict[str, Any],
    conf_name: str = "default",
    conf_uid: str = "default",
) -> dict[str, Any]:
    return {
        "type": "set-model-and-conf",
        "model_info": model_info,
        "conf_name": conf_name,
        "conf_uid": conf_uid,
    }
