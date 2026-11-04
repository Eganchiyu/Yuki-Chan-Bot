#!/usr/bin/env python3
"""主机侧网络看门狗：mihomo(TUN/IPv4) 出站失效时自动重载，兜底重连 WiFi。

背景（2026-11-04 现场取证）：
  - 机器从未休眠（suspend_stats.success=0），NapCat 正常是因为 QQ 走 IPv6 直连、
    且既有长连接不受影响；而所有经过 mihomo TUN 的 IPv4 新建连接全部 connect timeout。
  - mihomo 后一天多次报 "[TUN] default interface lost by monitor"，WiFi 在 18:46-18:48
    连续漫游 4 个 AP。接口监视失效后 mihomo 不再重建出站链路，只能手工重载——
    19:13:36 的自动重载正是当时网络恢复的原因。
  - 因此：探活失败 -> 重载 mihomo 配置 -> 重连 WiFi，逐级升级。

用法：
  netwatch.py watch                 常驻（systemd: yuki-netwatch.service）
  netwatch.py probe                 单次探活，任一失败 exit 1
  netwatch.py reload [--debounce N] 仅重载 mihomo（NetworkManager dispatcher 调用）
  netwatch.py diag                  打印当前网络/mihomo 诊断快照
  netwatch.py force                 处理 QQ /刷新 请求（systemd path 单元触发）
"""

from __future__ import annotations

import glob
import json
import os
import signal
import socket
import ssl
import subprocess
import sys
import time

ROOT = "/home/asumi/Yuki"
LOG_PATH = f"{ROOT}/logs/netwatch.log"
STATUS_PATH = "/run/yuki-netwatch.json"
RELOAD_STAMP = "/run/yuki-netwatch.last-reload"
# QQ /刷新 指令的交接目录（容器与宿主同一个绝对路径）
FORCE_PENDING_DIR = f"{ROOT}/data/netforce_pending"
FORCE_RESULT_PATH = f"{ROOT}/data/netforce_result.json"

MIHOMO_SOCK_GLOB = "/tmp/mihomo-party-*.sock"
MIHOMO_CONFIG = "/home/asumi/.config/mihomo-party/work/config.yaml"
MIHOMO_LOG_DIR = "/home/asumi/.config/mihomo-party/logs"

# (名称, 域名, 路径, 超时秒) —— 两条路径分别代表 TUN 直连与代理出站
PROBES = [
    ("direct", "api.deepseek.com", "/v1/models", 8.0),
    ("proxy", "www.gstatic.com", "/generate_204", 8.0),
]
INTERVAL = 30          # 探活间隔
BAD_CYCLES_ANY = 3     # 单条路径连续失败多少轮触发修复
BAD_CYCLES_ALL = 2     # 全部路径连续失败多少轮触发修复
MIN_GAP = 90           # 两次修复之间最小间隔
MAX_PER_HOUR = 12      # 每小时最多修复次数
LOG_MAX_BYTES = 5 * 1024 * 1024


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {msg}"
    print(line, flush=True)
    try:
        if os.path.getsize(LOG_PATH) > LOG_MAX_BYTES:
            os.replace(LOG_PATH, LOG_PATH + ".1")
    except OSError:
        pass
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def sh(cmd: list[str], timeout: float = 30.0) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as exc:  # noqa: BLE001
        return 1, f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------- mihomo API
def mihomo_sock() -> str | None:
    socks = sorted(glob.glob(MIHOMO_SOCK_GLOB), key=os.path.getmtime, reverse=True)
    return socks[0] if socks else None


def mihomo_api(method: str, path: str, body: dict | None = None,
               timeout: float = 10.0) -> tuple[int, bytes]:
    sock_path = mihomo_sock()
    if not sock_path:
        return 0, b"mihomo socket not found"
    payload = b"" if body is None else json.dumps(body).encode()
    head = (f"{method} {path} HTTP/1.1\r\nHost: localhost\r\n"
            f"Connection: close\r\n")
    if body is not None:
        head += "Content-Type: application/json\r\n"
    head += f"Content-Length: {len(payload)}\r\n\r\n"
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(sock_path)
        s.sendall(head.encode() + payload)
        buf = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}".encode()
    finally:
        s.close()
    header, _, data = buf.partition(b"\r\n\r\n")
    try:
        status = int(header.split(b" ")[1])
    except (IndexError, ValueError):
        status = 0
    if b"transfer-encoding: chunked" in header.lower():
        out, rest = b"", data
        while rest:
            size_line, _, rest = rest.partition(b"\r\n")
            try:
                size = int(size_line.strip() or b"0", 16)
            except ValueError:
                break
            if size == 0:
                break
            out += rest[:size]
            rest = rest[size + 2:]
        data = out
    return status, data


def find_wifi_dev() -> str:
    code, out = sh(["nmcli", "-t", "-f", "DEVICE,TYPE", "device", "status"])
    if code == 0:
        for line in out.splitlines():
            dev, _, typ = line.partition(":")
            if typ.strip() == "wifi":
                return dev
    return "wlp0s20f3"


def find_wifi_con(dev: str) -> str:
    code, out = sh(["nmcli", "-t", "-f", "NAME,DEVICE", "connection", "show", "--active"])
    if code == 0:
        for line in out.splitlines():
            name, _, device = line.rpartition(":")
            if device == dev and name:
                return name
    return ""


def reload_mihomo(diag: bool = False, timeout: float = 6.0) -> bool:
    """重载配置。超时（HTTP=0）说明 core 卡住，光靠重载救不回来。"""
    status, body = mihomo_api("PUT", "/configs?force=true", {"path": MIHOMO_CONFIG},
                              timeout=timeout)
    ok = status in (204, 200)
    detail = "" if ok else f" HTTP={status} {body[:120]!r}"
    if ok and diag:
        status2, raw = mihomo_api("GET", "/configs")
        if status2 == 200:
            try:
                cfg = json.loads(raw)
                detail = f" tun={cfg.get('tun', {}).get('enable')} mode={cfg.get('mode')}"
            except json.JSONDecodeError:
                pass
    log(f"[修复] mihomo 重载配置 {'成功' if ok else '失败'}{detail}")
    return ok


def mihomo_api_alive(timeout: float = 3.0) -> bool:
    status, _ = mihomo_api("GET", "/version", timeout=timeout)
    return status == 200


def find_core_pid() -> int | None:
    """mihomo core 是 mihomo-party 的 sidecar 子进程（setuid root）。"""
    # 必须用 -x 精确匹配进程名：-f 会连命令行里带这个字符串的 bash/pgrep 包装进程一起匹配
    code, out = sh(["pgrep", "-x", "mihomo"])
    pids = [int(x) for x in out.split() if x.strip().isdigit()]
    return pids[0] if pids else None


def restart_mihomo_core(wait: float = 24.0) -> bool:
    """硬重启 mihomo core：SIGTERM 后由 mihomo-party 自动拉起（app.asar 里
    `child.on("close")` 有 Try Restart Core 逻辑），再等新进程 + 探活通过。"""
    pid = find_core_pid()
    if not pid:
        log("[修复] 没找到 mihomo core 进程，跳过重启")
        return False
    started = time.time()
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        log(f"[修复] SIGTERM 失败: {exc}")
        return False
    log(f"[修复] 已向 mihomo core(pid={pid}) 发 SIGTERM，等 GUI 自动拉起")
    deadline = started + 8
    while time.time() < deadline:
        time.sleep(0.5)
        if find_core_pid() != pid:
            break
    else:
        try:
            os.kill(pid, signal.SIGKILL)
            log("[修复] core 未在 8s 内退出，已 SIGKILL")
        except OSError:
            pass
    deadline = time.time() + wait
    noted = False
    while time.time() < deadline:
        time.sleep(2)
        new_pid = find_core_pid()
        if not new_pid or new_pid == pid or not mihomo_sock():
            continue
        results = probe_all()
        if all(ok for ok, _ in results.values()):
            log(f"[修复] core 重启成功 pid={new_pid}，探活正常")
            return True
        if not noted:
            log(f"[修复] core 已重启 pid={new_pid}，探活暂未恢复，继续等")
            noted = True
    log("[修复] core 重启后仍未恢复")
    return False


def flush_cache() -> None:
    for path in ("/cache/dns/flush", "/cache/fakeip/flush"):
        status, _ = mihomo_api("POST", path)
        log(f"[修复] {path} HTTP={status}")


# ---------------------------------------------------------------------- 探活
def probe(name: str, host: str, path: str, timeout: float) -> tuple[bool, str]:
    t0 = time.time()
    try:
        infos = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)
        ip = infos[0][4][0]
    except Exception as exc:  # noqa: BLE001
        return False, f"dns 失败: {type(exc).__name__}: {exc}"
    ctx = ssl.create_default_context()
    raw = None
    try:
        raw = socket.create_connection((ip, 443), timeout=timeout)
        with ctx.wrap_socket(raw, server_hostname=host) as tls:
            tls.settimeout(timeout)
            tls.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}\r\n"
                         f"User-Agent: yuki-netwatch\r\nConnection: close\r\n\r\n").encode())
            data = tls.recv(128)
        if data.startswith(b"HTTP/"):
            return True, f"ip={ip} {data.split(b'\r\n')[0].decode(errors='replace')} {time.time()-t0:.2f}s"
        return False, f"ip={ip} 非 HTTP 响应 {data[:40]!r} {time.time()-t0:.2f}s"
    except Exception as exc:  # noqa: BLE001
        return False, f"ip={ip} {type(exc).__name__}: {exc} {time.time()-t0:.2f}s"
    finally:
        if raw is not None:
            try:
                raw.close()
            except OSError:
                pass


def probe_all() -> dict[str, tuple[bool, str]]:
    return {name: probe(name, host, path, timeout) for name, host, path, timeout in PROBES}


# -------------------------------------------------------------------- 诊断快照
def active_wifi() -> str:
    code, out = sh(["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL,FREQ", "device", "wifi"])
    active = [line for line in out.splitlines() if line.startswith("yes:")]
    return " ; ".join(active) if active else "(无活动 AP)"


def diagnostics() -> dict:
    dev = find_wifi_dev()
    snap = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ip4_route": sh(["ip", "-4", "route", "show", "default"])[1],
        "ip4_addr": sh(["ip", "-4", "-o", "addr", "show", dev])[1],
        "ip6_route": sh(["ip", "-6", "route", "show", "default"])[1],
        "resolv": sh(["cat", "/etc/resolv.conf"])[1],
        "wifi": active_wifi(),
        "conntrack": sh(["cat", "/proc/sys/net/netfilter/nf_conntrack_count"])[1],
        "mihomo_log_tail": sh(
            ["bash", "-c",
             f"tail -n 15 $(ls -t {MIHOMO_LOG_DIR}/core-*.log 2>/dev/null | head -1) 2>/dev/null"]
        )[1],
    }
    status, raw = mihomo_api("GET", "/configs")
    if status == 200:
        try:
            cfg = json.loads(raw)
            snap["mihomo"] = {"mode": cfg.get("mode"), "tun": cfg.get("tun", {}).get("enable")}
        except json.JSONDecodeError:
            snap["mihomo"] = "parse error"
    else:
        snap["mihomo"] = f"api HTTP={status}"
    return snap


# ---------------------------------------------------------------------- 修复
def link_layer_broken(dev: str) -> tuple[bool, str]:
    """链路层是否真的断了：无默认路由 / 无 IPv4 地址 / NM 认为未连接。

    校园网真断网时只重载 mihomo（避免反复重置 WiFi 连接），
    只有链路层异常才升级到 nmcli 重连。
    """
    code, route = sh(["ip", "-4", "route", "show", "default"])
    if code != 0 or "default" not in route:
        return True, "无 IPv4 默认路由"
    code, addr = sh(["ip", "-4", "-o", "addr", "show", dev])
    if "inet " not in addr:
        return True, f"{dev} 无 IPv4 地址"
    code, state = sh(["nmcli", "-t", "-f", "GENERAL.STATE", "device", "show", dev])
    if "connected" not in state:
        return True, f"NM 状态 {state.strip()}"
    return False, "链路层正常"


def wifi_recovery_steps() -> list[tuple[str, object]]:
    """最后手段：链路层异常或 mihomo 侧全部救不回来时才动 WiFi。"""
    dev = find_wifi_dev()
    con = find_wifi_con(dev)
    return [
        (f"nmcli device reapply {dev}",
         lambda: sh(["nmcli", "device", "reapply", dev], timeout=60)),
        (f"重连 WiFi {con or dev}",
         lambda: sh(["nmcli", "connection", "up", con or dev], timeout=90)),
    ]


_gap_state = {"last": 0.0, "hist": []}


def remediation_allowed() -> tuple[bool, str]:
    now = time.time()
    if now - _gap_state["last"] < MIN_GAP:
        return False, f"距上次修复不足 {MIN_GAP}s"
    _gap_state["hist"] = [t for t in _gap_state["hist"] if now - t < 3600]
    if len(_gap_state["hist"]) >= MAX_PER_HOUR:
        return False, f"近 1 小时已修复 {len(_gap_state['hist'])} 次，限流"
    return True, ""


def dump_diagnostics() -> str:
    """把完整现场快照写成单独文件，返回一行摘要（避免日志被快照刷屏）。"""
    snap = diagnostics()
    path = f"{ROOT}/logs/netwatch_diag_{time.strftime('%Y%m%d_%H%M%S')}.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=2)
    except OSError:
        path = "(快照写入失败)"
    summary = (f"route=[{snap.get('ip4_route', '')}] wifi=[{snap.get('wifi', '')}] "
               f"conntrack={snap.get('conntrack', '?')} mihomo={snap.get('mihomo')} "
               f"快照={path}")
    return summary


def _run_step(label: str, action, actions: list[str],
              results: dict[str, tuple[bool, str]]) -> tuple[bool, dict]:
    """执行一步修复，并在几秒内复验；返回 (是否恢复, 最新探活结果)。"""
    log(f"[修复] 执行：{label}")
    actions.append(label)
    try:
        action()
    except Exception as exc:  # noqa: BLE001
        log(f"[修复] 执行异常 {label}: {type(exc).__name__}: {exc}")
    for wait in (2, 3, 4):
        time.sleep(wait)
        results = probe_all()
        if all(ok for ok, _ in results.values()):
            log(f"[修复] 恢复：{label} 后探活全部正常 " +
                json.dumps({k: v[1] for k, v in results.items()}, ensure_ascii=False))
            return True, results
    return False, results


def remediate(results: dict[str, tuple[bool, str]]) -> tuple[bool, list[str], dict]:
    """修复阶梯，返回 (是否恢复, 已执行步骤, 最后一次探活结果)。

    顺序：重载配置 → （接口还活着时）清缓存再重载 → 重启 mihomo core → 动 WiFi。
    2026-11-04 20:10 现场：WiFi 漫游触发重载，重载本身卡死（控制接口 10s 超时），
    core 卡住期间所有新连接被瞬间 EOF —— 这种只能靠重启 core，重载多少次都没用。
    """
    actions: list[str] = []
    allowed, why = remediation_allowed()
    if not allowed:
        log(f"[修复] 跳过：{why}")
        return False, [f"跳过（{why}）"], results
    _gap_state["last"] = time.time()
    _gap_state["hist"].append(_gap_state["last"])
    log("[修复] 触发：" + dump_diagnostics())

    ok, results = _run_step("重载 mihomo 配置", lambda: reload_mihomo(diag=True, timeout=6.0),
                            actions, results)
    if ok:
        return True, actions, results

    if mihomo_api_alive():
        ok, results = _run_step(
            "清 DNS/fake-ip 缓存并重载",
            lambda: (flush_cache(), reload_mihomo(timeout=6.0))[1], actions, results)
        if ok:
            return True, actions, results
    else:
        log("[修复] 控制接口无响应，跳过清缓存，直接重启 core")

    ok, results = _run_step("重启 mihomo core", restart_mihomo_core, actions, results)
    if ok:
        return True, actions, results

    dev = find_wifi_dev()
    broken, why = link_layer_broken(dev)
    log(f"[修复] mihomo 侧已救不回来，转 WiFi 兜底（{why}）")
    for label, action in wifi_recovery_steps():
        ok, results = _run_step(label, action, actions, results)
        if ok:
            return True, actions, results

    log("[修复] 所有步骤均未恢复，等待下一轮：" +
        json.dumps({k: v[1] for k, v in results.items()}, ensure_ascii=False))
    return False, actions, results


def _take_force_requests() -> list[dict]:
    """取走容器投递的手动刷新请求（处理完即删，避免重复触发）。"""
    try:
        names = sorted(os.listdir(FORCE_PENDING_DIR))
    except OSError:
        return []
    reqs = []
    for name in names:
        if not name.endswith(".json"):
            continue
        path = os.path.join(FORCE_PENDING_DIR, name)
        req = {"id": name[:-5]}
        try:
            with open(path, encoding="utf-8") as f:
                req.update(json.load(f))
        except Exception:  # noqa: BLE001
            pass
        try:
            os.remove(path)
        except OSError:
            pass
        reqs.append(req)
    return reqs


def write_force_result(req_id: str, ok: bool, results: dict, actions: list[str]) -> None:
    payload = {
        "id": req_id,
        "ok": ok,
        "probes": {k: {"ok": v[0], "detail": v[1]} for k, v in results.items()},
        "actions": actions,
        "ts": time.time(),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    tmp = FORCE_RESULT_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, FORCE_RESULT_PATH)
    except OSError as exc:
        log(f"[刷新] 结果写入失败: {exc}")


def cmd_force() -> int:
    """手动刷新（QQ /刷新）：先探活，正常就直接回报；不正常走修复阶梯。"""
    reqs = _take_force_requests()
    if not reqs:
        return 0
    req_id = str(reqs[-1].get("id"))
    log(f"[刷新] 收到手动刷新请求 {req_id}（待处理 {len(reqs)} 条）")
    results = probe_all()
    ok = all(v[0] for v in results.values())
    actions: list[str] = []
    if ok:
        log("[刷新] 探活已正常，不重载 mihomo")
    else:
        log("[刷新] 探活失败：" +
            json.dumps({k: v[1] for k, v in results.items()}, ensure_ascii=False))
        ok, actions, results = remediate(results)
    write_force_result(req_id, ok, results, actions)
    log(f"[刷新] 回写结果 id={req_id} ok={ok} actions={actions}")
    return 0


def write_status(payload: dict) -> None:
    try:
        with open(STATUS_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except OSError:
        pass


# ------------------------------------------------------------------------ 入口
def cmd_watch() -> int:
    log(f"看门狗启动：探活 {[p[0] for p in PROBES]}，间隔 {INTERVAL}s")
    bad = {name: 0 for name, *_ in PROBES}
    last_ok_ts = 0.0
    while True:
        results = probe_all()
        ok_all = all(ok for ok, _ in results.values())
        for name, (ok, detail) in results.items():
            if ok:
                if bad[name] >= BAD_CYCLES_ANY:
                    log(f"[恢复] {name} 自行恢复：{detail}")
                bad[name] = 0
            else:
                bad[name] += 1
                if bad[name] <= 3 or bad[name] % 10 == 0:
                    log(f"[异常] {name} 第 {bad[name]} 次失败：{detail}")
        if ok_all:
            last_ok_ts = time.time()
        else:
            if any(v >= BAD_CYCLES_ALL for v in bad.values()):
                remediate(results)
                bad = {name: 0 for name, *_ in PROBES}
        write_status({
            "ts": time.time(),
            "ok": ok_all,
            "last_ok": last_ok_ts,
            "probes": {k: {"ok": v[0], "detail": v[1]} for k, v in results.items()},
            "bad_streak": bad,
        })
        time.sleep(INTERVAL)


def cmd_probe() -> int:
    results = probe_all()
    bad = 0
    for name, (ok, detail) in results.items():
        print(f"{'OK  ' if ok else 'FAIL'} {name}: {detail}")
        bad += 0 if ok else 1
    return 1 if bad else 0


def cmd_reload(debounce: int) -> int:
    now = time.time()
    try:
        last = os.path.getmtime(RELOAD_STAMP)
    except OSError:
        last = 0.0
    if debounce and now - last < debounce:
        return 0
    open(RELOAD_STAMP, "w").close()
    ok = reload_mihomo(diag=True, timeout=6.0)
    if not ok:
        log("[修复] 重载失败（core 可能被卡住），转重启 core")
        ok = restart_mihomo_core()
    return 0 if ok else 1


def cmd_diag() -> int:
    print(json.dumps(diagnostics(), ensure_ascii=False, indent=2))
    for name, (ok, detail) in probe_all().items():
        print(f"{'OK  ' if ok else 'FAIL'} {name}: {detail}")
    return 0


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "probe"
    if cmd == "watch":
        return cmd_watch()
    if cmd == "probe":
        return cmd_probe()
    if cmd == "reload":
        debounce = 0
        if "--debounce" in argv:
            debounce = int(argv[argv.index("--debounce") + 1])
        return cmd_reload(debounce)
    if cmd == "diag":
        return cmd_diag()
    if cmd == "force":
        return cmd_force()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
