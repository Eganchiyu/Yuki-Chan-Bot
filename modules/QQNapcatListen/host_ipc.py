# modules/QQNapcatListen/host_ipc.py
"""与宿主机守护进程（supervisor / netwatch）交互的文件 IPC 协议。

包含：
1. `/重启`：通过 staging/ 投递容器重启请求，并通过 data/restart_notice.json 落盘重启完成待发消息；
2. `/刷新`：通过 data/netforce_pending/ 投递网络连通性探测与 mihomo 重载请求。
"""
import asyncio
import json
import os
import time

from config import cfg
from utils.logger import get_logger

logger = get_logger("napcat_listen")

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_STAGING_DIR = os.path.join(_ROOT, "staging")
_SUPERVISOR_STATE = os.path.join(_ROOT, "deploy", "state.json")
_RESTART_NOTICE_FILE = os.path.join(_ROOT, "data", "restart_notice.json")
RESTART_NOTICE_MAX_AGE = 600
MAX_RESTART_PER_HOUR = int(os.environ.get("YUKI_MAX_RESTART_PER_HOUR", 5))

_NETFORCE_PENDING_DIR = os.path.join(_ROOT, "data", "netforce_pending")
_NETFORCE_RESULT_FILE = os.path.join(_ROOT, "data", "netforce_result.json")
NETFORCE_WAIT_SECONDS = 45.0


def _recent_restart_count() -> int:
    """读宿主 supervisor 的历史，统计最近一小时的重启次数。"""
    try:
        with open(_SUPERVISOR_STATE, encoding="utf-8") as f:
            history = (json.load(f) or {}).get("history") or []
    except Exception:
        return 0
    now = time.time()
    return sum(
        1
        for h in history
        if isinstance(h, dict)
        and h.get("result") in {"restarted", "restart_failed"}
        and now - float(h.get("ts") or 0) < 3600
    )


def request_container_restart(reason: str = "") -> str:
    """把重启请求投递给宿主 supervisor（它负责跑 deploy/run.sh 重建容器）。"""
    task_dir = os.path.join(_STAGING_DIR, f"restart_{time.strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(task_dir, exist_ok=True)
    payload = {
        "type": "restart",
        "summary": reason or "群聊 /重启 指令",
        "requested_by": "master",
        "requested_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(os.path.join(task_dir, "request.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return task_dir


def _write_netforce_request() -> str:
    """投递「刷新网络」请求给宿主看门狗，返回请求 id。"""
    os.makedirs(_NETFORCE_PENDING_DIR, exist_ok=True)
    req_id = f"{int(time.time() * 1000)}-{os.getpid()}"
    path = os.path.join(_NETFORCE_PENDING_DIR, f"{req_id}.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"id": req_id, "ts": time.time(), "source": "qq-/刷新"}, f, ensure_ascii=False)
    os.replace(tmp, path)
    return req_id


def _read_netforce_result(req_id: str) -> dict | None:
    """读取宿主回写的刷新结果，id 不匹配视为还没轮到本次请求。"""
    try:
        with open(_NETFORCE_RESULT_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.warning(f"[NetForce] 读取刷新结果失败: {e}")
        return None
    return data if str(data.get("id")) == req_id else None


async def _wait_netforce_result(req_id: str, timeout: float = NETFORCE_WAIT_SECONDS):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = _read_netforce_result(req_id)
        if data:
            return data
        await asyncio.sleep(1.0)
    return None


def _format_netforce_reply(result: dict) -> str:
    probes = result.get("probes") or {}

    def state(name: str) -> str:
        item = probes.get(name) or {}
        return f"{name} {'通' if item.get('ok') else '不通'}"

    detail = "，".join(state(name) for name in ("direct", "proxy") if probes.get(name))
    if result.get("ok"):
        return f"测试已连通（{detail}）"
    actions = result.get("actions") or []
    tail = f"，已尝试：{'、'.join(actions)}" if actions else ""
    return f"没连通（{detail}）{tail}"


async def _refresh_flow(gateway, chat_id, mode: str = "group") -> None:
    """手动刷新网络：交给宿主看门狗真实探活（必要时重载 mihomo），结果回原会话。"""
    from modules.QQNapcatListen import listen_main as lm

    try:
        await gateway.send(chat_id, "正在测试网络连通性…", mode=mode)
    except Exception as e:
        logger.error(f"[NetForce] 刷新前通知失败: {e}")

    try:
        req_id = lm._write_netforce_request()
    except Exception as e:
        logger.error(f"[NetForce] 投递刷新请求失败: {e}")
        await gateway.send(chat_id, "刷新请求没投递出去…等下一次自动巡检吧", mode=mode)
        return

    result = await lm._wait_netforce_result(req_id)
    if result is None:
        logger.warning(f"[NetForce] 请求 {req_id} 等待超时（宿主看门狗未响应）")
        text = "宿主看门狗没有响应，刷新超时了…等下一次自动巡检吧"
    else:
        text = lm._format_netforce_reply(result)
        logger.info(f"[NetForce] 请求 {req_id} 结果: {json.dumps(result, ensure_ascii=False)}")
    try:
        await gateway.send(chat_id, text, mode=mode)
    except Exception as e:
        logger.error(f"[NetForce] 刷新结果发送失败: {e}")


def _write_restart_notice(chat_id, text: str, mode: str = "group") -> None:
    """落盘「重启完成」待发消息，供新进程启动后补发到原会话。"""
    payload = {
        "chat_id": int(chat_id),
        "mode": mode,
        "text": text,
        "ts": time.time(),
    }
    os.makedirs(os.path.dirname(_RESTART_NOTICE_FILE), exist_ok=True)
    tmp = _RESTART_NOTICE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, _RESTART_NOTICE_FILE)


def _pop_restart_notice() -> dict | None:
    """取出并删除待发的重启通知。"""
    try:
        with open(_RESTART_NOTICE_FILE, encoding="utf-8") as f:
            notice = json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.warning(f"[Restart] 读取重启通知失败: {e}")
        notice = None
    try:
        os.remove(_RESTART_NOTICE_FILE)
    except Exception:
        pass
    return notice


async def send_pending_restart_notice(gateway, retries: int = 20, delay: float = 3.0):
    """启动后补发「重启完成」到重启前所在的会话。"""
    notice = _pop_restart_notice()
    if not notice:
        return
    if time.time() - float(notice.get("ts") or 0) > RESTART_NOTICE_MAX_AGE:
        logger.warning("[Restart] 重启完成通知已过期，丢弃")
        return

    chat_id = notice.get("chat_id")
    text = notice.get("text") or f"{cfg.ROBOT_NAME.title()} 重启完成，我回来啦~"
    mode = notice.get("mode") or "group"
    for attempt in range(1, retries + 1):
        try:
            await gateway.send(chat_id, text, mode=mode)
            logger.info(f"[Restart] 已向 {chat_id} 补发重启完成通知")
            return
        except Exception as e:
            logger.warning(f"[Restart] 重启完成通知发送失败（第 {attempt}/{retries} 次）: {e}")
            await asyncio.sleep(delay)
    logger.error("[Restart] 重启完成通知多次发送失败，已放弃")


async def _restart_flow(gateway, group_id):
    """先在本群喊一声“正在重启”，确认发出去了再投递重启请求。"""
    recent = _recent_restart_count()
    if recent >= MAX_RESTART_PER_HOUR:
        logger.warning(f"[Restart] 一小时内已重启 {recent} 次，拒绝本次请求")
        await gateway.send(
            group_id, f"一个小时内人家已经重启 {recent} 次啦，先歇一会儿吧~", mode="group"
        )
        return

    try:
        await gateway.send(group_id, f"{cfg.ROBOT_NAME.title()} 正在重启，稍等一下下~", mode="group")
    except Exception as e:
        logger.error(f"[Restart] 重启前通知失败: {e}")

    try:
        _write_restart_notice(
            group_id, f"{cfg.ROBOT_NAME.title()} 重启完成，我回来啦~", mode="group"
        )
    except Exception as e:
        logger.error(f"[Restart] 记录重启完成通知失败: {e}")

    try:
        task_dir = request_container_restart(f"{cfg.ROBOT_NAME} 群聊 /重启 指令")
        logger.warning(f"[Restart] 已投递重启请求: {task_dir}")
    except Exception as e:
        logger.error(f"[Restart] 投递重启请求失败: {e}")
