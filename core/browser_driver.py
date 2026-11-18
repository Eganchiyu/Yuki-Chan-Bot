# core/browser_driver.py
"""宿主机 Chrome CDP 异步驱动层：标签页管理、跨域 iframe 穿透、三段式稳定等待与输入原语。"""
from __future__ import annotations

import asyncio
import base64
import json
import re
import time
from typing import Any
from urllib.parse import quote, urlparse

import aiohttp
import websockets

from config import cfg
from utils.logger import get_logger

logger = get_logger("tools")

# 串行化浏览器操控与截图，防止并发会话抢焦点或错位点击
BROWSER_LOCK = asyncio.Lock()


class BrowserUnavailableError(RuntimeError):
    """宿主机 Chrome CDP 未就绪或连接断开。"""


class BrowserActionError(RuntimeError):
    """单步浏览器操作失败（目标缺失、导航失败等）。"""


_KEY_DEFINITIONS: dict[str, dict[str, Any]] = {
    "enter": {"key": "Enter", "code": "Enter", "vk": 13, "text": "\r"},
    "return": {"key": "Enter", "code": "Enter", "vk": 13, "text": "\r"},
    "tab": {"key": "Tab", "code": "Tab", "vk": 9},
    "escape": {"key": "Escape", "code": "Escape", "vk": 27},
    "esc": {"key": "Escape", "code": "Escape", "vk": 27},
    "backspace": {"key": "Backspace", "code": "Backspace", "vk": 8},
    "delete": {"key": "Delete", "code": "Delete", "vk": 46},
    "space": {"key": " ", "code": "Space", "vk": 32, "text": " "},
    "up": {"key": "ArrowUp", "code": "ArrowUp", "vk": 38},
    "arrowup": {"key": "ArrowUp", "code": "ArrowUp", "vk": 38},
    "down": {"key": "ArrowDown", "code": "ArrowDown", "vk": 40},
    "arrowdown": {"key": "ArrowDown", "code": "ArrowDown", "vk": 40},
    "left": {"key": "ArrowLeft", "code": "ArrowLeft", "vk": 37},
    "arrowleft": {"key": "ArrowLeft", "code": "ArrowLeft", "vk": 37},
    "right": {"key": "ArrowRight", "code": "ArrowRight", "vk": 39},
    "arrowright": {"key": "ArrowRight", "code": "ArrowRight", "vk": 39},
    "pageup": {"key": "PageUp", "code": "PageUp", "vk": 33},
    "pagedown": {"key": "PageDown", "code": "PageDown", "vk": 34},
    "home": {"key": "Home", "code": "Home", "vk": 36},
    "end": {"key": "End", "code": "End", "vk": 35},
}

_STABILITY_JS_TEMPLATE = """(function(settleMs, maxWaitMs) {
  return new Promise(function(resolve) {
    if ((window.innerWidth || 0) <= 0 || (window.innerHeight || 0) <= 0 || document.hidden) {
      resolve({settled: true, reason: 'hidden', elapsedMs: 0, readyState: document.readyState});
      return;
    }
    var start = performance.now();
    var lastChange = start;
    var timer = null;
    var obs = null;

    function layoutDigest() {
      try {
        var vw = window.innerWidth || 0;
        var vh = window.innerHeight || 0;
        var els = document.querySelectorAll('button, a[href], input, textarea, select, [role="button"], h1, h2, dialog, [role="dialog"]');
        var acc = [document.readyState, vw, vh, els.length];
        var lim = Math.min(els.length, 24);
        for (var i = 0; i < lim; i++) {
          var r = els[i].getBoundingClientRect();
          acc.push(Math.round(r.left) + ',' + Math.round(r.top) + ',' + Math.round(r.width) + ',' + Math.round(r.height));
        }
        return acc.join('|');
      } catch (e) {
        return '';
      }
    }

    var lastDigest = layoutDigest();

    function done(reason) {
      if (timer) clearTimeout(timer);
      if (obs) {
        try { obs.disconnect(); } catch (e) {}
      }
      resolve({
        settled: reason === 'settled',
        reason: reason,
        elapsedMs: Math.round(performance.now() - start),
        readyState: document.readyState
      });
    }

    try {
      obs = new MutationObserver(function() {
        lastChange = performance.now();
      });
      if (document.documentElement) {
        obs.observe(document.documentElement, {
          childList: true,
          subtree: true,
          attributes: true,
          attributeFilter: ['class', 'style', 'hidden', 'disabled', 'aria-hidden', 'open']
        });
      }
    } catch (e) {}

    function tick() {
      var now = performance.now();
      var curDigest = layoutDigest();
      if (curDigest !== lastDigest) {
        lastDigest = curDigest;
        lastChange = now;
      }
      if (document.readyState === 'complete' && (now - lastChange) >= settleMs) {
        if (window.requestAnimationFrame) {
          window.requestAnimationFrame(function() {
            window.requestAnimationFrame(function() { done('settled'); });
          });
        } else {
          done('settled');
        }
        return;
      }
      if ((now - start) >= maxWaitMs) {
        done('timeout');
        return;
      }
      timer = setTimeout(tick, 70);
    }

    timer = setTimeout(tick, Math.min(80, settleMs));
  });
})"""


def normalize_url(raw_url: str) -> str:
    """规范化待打开 URL，无协议头时默认补 https://，仅允许 http/https/about:blank。"""
    text = (raw_url or "").strip()
    if not text:
        raise ValueError("缺少 url 参数")
    if text == "about:blank":
        return text
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:(?!\d+(/|$))", text) and "://" not in text:
        raise ValueError(f"不支持的 URL 协议: {text.split(':', 1)[0]}")
    if "://" not in text:
        text = "https://" + text
    parsed = urlparse(text)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"不支持的 URL 协议: {parsed.scheme}")
    if not parsed.netloc:
        raise ValueError(f"无效的 URL: {raw_url}")
    return text


class CdpSession:
    """轻量级异步 Chrome DevTools Protocol WebSocket 会话（支持扁平化 OOPIF sessionId）。"""

    def __init__(self, ws_url: str) -> None:
        self.ws_url = ws_url
        self._ws: Any = None
        self._reader_task: asyncio.Task | None = None
        self._next_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._inflight_reqs: dict[str, float] = {}
        self._last_net_activity: float = time.monotonic()
        self._nav_seq: int = 0
        self._child_sessions: dict[str, str] = {}  # targetId -> sessionId
        self._session_to_target: dict[str, str] = {}
        self._visible_child_sids: set[str] = set()

    @property
    def connected(self) -> bool:
        return self._ws is not None and not getattr(self._ws, "closed", False)

    async def connect(self) -> None:
        self._ws = await websockets.connect(
            self.ws_url,
            max_size=None,
            open_timeout=5.0,
            ping_interval=20.0,
            ping_timeout=20.0,
        )
        self._reader_task = asyncio.create_task(self._reader_loop())

    async def close(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except BaseException:
                pass
            self._reader_task = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(BrowserUnavailableError("CDP 连接已关闭"))
        self._pending.clear()
        self._inflight_reqs.clear()
        self._child_sessions.clear()
        self._session_to_target.clear()
        self._visible_child_sids.clear()

    async def _reader_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                msg_id = msg.get("id")
                if msg_id is not None:
                    fut = self._pending.pop(msg_id, None)
                    if fut is not None and not fut.done():
                        if "error" in msg:
                            err = msg["error"]
                            fut.set_exception(
                                RuntimeError(f"CDP {err.get('code')}: {err.get('message')}")
                            )
                        else:
                            fut.set_result(msg.get("result") or {})
                    continue
                self._handle_event(msg)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug(f"[BrowserCDP] reader 结束: {exc}")
        finally:
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(BrowserUnavailableError("CDP 连接中断"))
            self._pending.clear()

    def _handle_event(self, msg: dict) -> None:
        method = msg.get("method") or ""
        params = msg.get("params") or {}
        now = time.monotonic()

        if method == "Network.requestWillBeSent":
            rtype = str(params.get("type") or "")
            if rtype in ("Document", "XHR", "Fetch", "Script", "Stylesheet"):
                req_id = str(params.get("requestId") or "")
                if req_id:
                    self._inflight_reqs[req_id] = now
                    self._last_net_activity = now
        elif method in ("Network.loadingFinished", "Network.loadingFailed"):
            req_id = str(params.get("requestId") or "")
            if req_id in self._inflight_reqs:
                self._inflight_reqs.pop(req_id, None)
                self._last_net_activity = now
        elif method in ("Page.frameNavigated", "Page.loadEventFired", "Page.frameStartedLoading"):
            if not msg.get("sessionId"):
                self._nav_seq += 1
        elif method == "Target.attachedToTarget":
            sid = str(params.get("sessionId") or "")
            info = params.get("targetInfo") or {}
            tid = str(info.get("targetId") or "")
            ttype = str(info.get("type") or "")
            if sid and tid and ttype in ("iframe", "page"):
                self._child_sessions[tid] = sid
                self._session_to_target[sid] = tid
        elif method == "Target.detachedFromTarget":
            sid = str(params.get("sessionId") or "")
            self._visible_child_sids.discard(sid)
            tid = self._session_to_target.pop(sid, None)
            if tid:
                self._child_sessions.pop(tid, None)

    def active_inflight_count(self, max_age_sec: float = 2.5) -> int:
        now = time.monotonic()
        stale = [rid for rid, ts in self._inflight_reqs.items() if (now - ts) > max_age_sec]
        for rid in stale:
            self._inflight_reqs.pop(rid, None)
        return len(self._inflight_reqs)

    async def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        session_id: str | None = None,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        if not self.connected:
            raise BrowserUnavailableError("CDP WebSocket 未连接")
        self._next_id += 1
        req_id = self._next_id
        payload: dict[str, Any] = {"id": req_id, "method": method}
        if params:
            payload["params"] = params
        if session_id:
            payload["sessionId"] = session_id

        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[req_id] = fut
        try:
            await self._ws.send(json.dumps(payload))
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError as exc:
            self._pending.pop(req_id, None)
            raise TimeoutError(f"CDP 调用超时: {method}") from exc
        except Exception:
            self._pending.pop(req_id, None)
            raise


class BrowserDriver:
    """宿主机 Chrome CDP 浏览器驱动单例。"""

    def __init__(self) -> None:
        self._cdp: CdpSession | None = None
        self._target_id: str = ""
        self._ws_url: str = ""

    @staticmethod
    def _tools_cfg():
        return getattr(cfg, "tools", None)

    def cdp_base_url(self) -> str:
        raw = str(getattr(self._tools_cfg(), "browser_cdp_url", "") or "http://127.0.0.1:9222").strip()
        return raw.rstrip("/")

    async def _http_request(self, path: str, *, method: str = "GET", timeout: float = 3.0) -> str:
        url = f"{self.cdp_base_url()}{path}"
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as sess:
                async with sess.request(method, url) as resp:
                    if resp.status >= 400:
                        raise BrowserUnavailableError(f"CDP HTTP {resp.status} ({url})")
                    return await resp.text()
        except BrowserUnavailableError:
            raise
        except Exception as exc:
            raise BrowserUnavailableError(
                f"连不上宿主机 Chrome CDP（{self.cdp_base_url()}）：{exc}。"
                "请确认宿主机 Chrome 已开启 --remote-debugging-port=9222（可运行 scripts/start_yuki_chrome.sh）。"
            ) from exc

    async def _http_json(self, path: str, *, method: str = "GET", timeout: float = 3.0) -> Any:
        raw = await self._http_request(path, method=method, timeout=timeout)
        try:
            return json.loads(raw) if raw.strip() else {}
        except Exception as exc:
            raise BrowserUnavailableError(f"CDP HTTP 返回非 JSON ({self.cdp_base_url()}{path}): {exc}") from exc

    async def list_tabs(self) -> list[dict[str, Any]]:
        targets = await self._http_json("/json/list")
        pages: list[dict[str, Any]] = []
        for item in targets or []:
            if not isinstance(item, dict) or item.get("type") != "page":
                continue
            url = str(item.get("url") or "")
            if url.startswith(("devtools://", "chrome-extension://")):
                continue
            pages.append({
                "id": str(item.get("id") or ""),
                "title": str(item.get("title") or ""),
                "url": url,
                "ws_url": str(item.get("webSocketDebuggerUrl") or ""),
                "active": str(item.get("id") or "") == self._target_id,
            })
        for idx, page in enumerate(pages, 1):
            page["index"] = idx
        return pages

    async def _attach_target(self, target_id: str, ws_url: str) -> None:
        if self._cdp is not None:
            await self._cdp.close()
            self._cdp = None
        if not ws_url:
            raise BrowserUnavailableError(f"目标标签页 {target_id} 缺少 webSocketDebuggerUrl")
        cdp = CdpSession(ws_url)
        await cdp.connect()
        self._cdp = cdp
        self._target_id = target_id
        self._ws_url = ws_url

        for domain in ("Page", "DOM", "Runtime", "Network"):
            try:
                await cdp.call(f"{domain}.enable", timeout=5.0)
            except Exception as exc:
                logger.debug(f"[BrowserDriver] {domain}.enable 异常: {exc}")
        try:
            await cdp.call(
                "Target.setAutoAttach",
                {"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True},
                timeout=5.0,
            )
        except Exception as exc:
            logger.debug(f"[BrowserDriver] Target.setAutoAttach 异常: {exc}")
        await self._bring_to_front(cdp)

    async def _bring_to_front(self, cdp: CdpSession | None = None) -> None:
        """把当前标签页置为前台，避免 Chrome 节流后台标签页的 compositor 导致鼠标事件超时。"""
        sess = cdp or self._cdp
        if sess is None or not sess.connected:
            return
        try:
            if self._target_id:
                await self._http_request(f"/json/activate/{self._target_id}", timeout=2.0)
        except Exception:
            pass
        try:
            await sess.call("Page.bringToFront", timeout=2.5)
        except Exception:
            pass

    async def ensure_connected(self) -> CdpSession:
        if self._cdp is not None and self._cdp.connected and self._target_id:
            try:
                tabs = await self.list_tabs()
                if any(t["id"] == self._target_id for t in tabs):
                    return self._cdp
            except Exception:
                pass

        tabs = await self.list_tabs()
        target = None
        if self._target_id:
            target = next((t for t in tabs if t["id"] == self._target_id), None)
        if target is None and tabs:
            # 优先挑非空白、非 chrome:// 的普通标签页
            target = next(
                (t for t in tabs if t["url"] and not t["url"].startswith(("chrome://", "about:blank"))),
                tabs[0],
            )
        if target is None:
            created = await self._http_json(f"/json/new?{quote('about:blank')}", method="PUT")
            target = {
                "id": str(created.get("id") or ""),
                "ws_url": str(created.get("webSocketDebuggerUrl") or ""),
            }
        await self._attach_target(target["id"], target["ws_url"])
        assert self._cdp is not None
        return self._cdp

    async def switch_tab(self, index_or_id: str | int) -> dict[str, Any]:
        tabs = await self.list_tabs()
        if not tabs:
            raise BrowserActionError("当前没有可切换的标签页")
        raw = str(index_or_id).lstrip("#").strip()
        target = None
        if raw.isdigit():
            idx = int(raw)
            target = next((t for t in tabs if t["index"] == idx), None)
        if target is None:
            target = next((t for t in tabs if t["id"] == raw or raw.lower() in t["title"].lower() or raw.lower() in t["url"].lower()), None)
        if target is None:
            raise BrowserActionError(f"找不到标签页: {index_or_id}")
        await self._http_request(f"/json/activate/{target['id']}")
        await self._attach_target(target["id"], target["ws_url"])
        return target

    async def new_tab(self, url: str = "about:blank") -> dict[str, Any]:
        target_url = normalize_url(url) if url and url != "about:blank" else "about:blank"
        created = await self._http_json(f"/json/new?{quote(target_url, safe='')}", method="PUT")
        tid = str(created.get("id") or "")
        ws_url = str(created.get("webSocketDebuggerUrl") or "")
        await self._attach_target(tid, ws_url)
        await self.wait_until_stable()
        return {"id": tid, "url": target_url}

    async def close_tab(self, index_or_id: str | int | None = None) -> str:
        tabs = await self.list_tabs()
        if not tabs:
            raise BrowserActionError("没有可关闭的标签页")
        target = None
        if index_or_id is not None and str(index_or_id).strip():
            raw = str(index_or_id).lstrip("#").strip()
            if raw.isdigit():
                target = next((t for t in tabs if t["index"] == int(raw)), None)
            else:
                target = next((t for t in tabs if t["id"] == raw), None)
        else:
            target = next((t for t in tabs if t["id"] == self._target_id), tabs[0])
        if target is None:
            raise BrowserActionError(f"找不到要关闭的标签页: {index_or_id}")
        tid = target["id"]
        await self._http_request(f"/json/close/{tid}")
        if tid == self._target_id and self._cdp is not None:
            await self._cdp.close()
            self._cdp = None
            self._target_id = ""
        return target.get("title") or target.get("url") or tid

    async def eval_js(
        self,
        expression: str,
        *,
        session_id: str | None = None,
        context_id: int | None = None,
        await_promise: bool = False,
        timeout: float = 8.0,
    ) -> Any:
        cdp = await self.ensure_connected()
        params: dict[str, Any] = {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": await_promise,
        }
        if context_id is not None:
            params["contextId"] = context_id
        res = await cdp.call("Runtime.evaluate", params, session_id=session_id, timeout=timeout)
        if "exceptionDetails" in res:
            details = res["exceptionDetails"]
            desc = (details.get("exception") or {}).get("description") or details.get("text") or "JS异常"
            raise RuntimeError(desc)
        return (res.get("result") or {}).get("value")

    async def wait_until_stable(
        self,
        *,
        timeout: float | None = None,
        settle_ms: int | None = None,
    ) -> dict[str, Any]:
        """三段式稳定等待：文档 readyState === complete -> 网络在途静默 -> DOM 与布局边界静默。"""
        tcfg = self._tools_cfg()
        max_wait = float(timeout or getattr(tcfg, "browser_wait_timeout", 5.0) or 5.0)
        settle = int(settle_ms or getattr(tcfg, "browser_settle_ms", 280) or 280)
        deadline = time.monotonic() + max_wait

        cdp = await self.ensure_connected()
        # 1. 等待文档 readyState === 'complete'
        while time.monotonic() < deadline:
            try:
                state = await self.eval_js("document.readyState", timeout=2.0)
                if state == "complete":
                    break
            except Exception:
                pass
            await asyncio.sleep(0.1)

        # 2. 等待核心网络请求静默（上限占总剩余时间的 60%，避免长轮询饿死后续步骤）
        net_deadline = min(deadline, time.monotonic() + max(0.8, max_wait * 0.6))
        quiet_sec = max(0.12, settle / 1000.0)
        while time.monotonic() < net_deadline:
            inflight = cdp.active_inflight_count(max_age_sec=2.5)
            since_net = time.monotonic() - cdp._last_net_activity
            if inflight == 0 and since_net >= quiet_sec:
                break
            await asyncio.sleep(0.08)

        # 3. 页面内 DOM + 布局坐标静默窗口 + 双帧 rAF（仅等待主帧与已知可见 OOPIF 子帧，跳过 0x0 隐藏 iframe）
        rem_ms = max(200, int((deadline - time.monotonic()) * 1000))
        expr = f"{_STABILITY_JS_TEMPLATE}({int(settle)}, {rem_ms})"
        call_timeout = max(1.0, rem_ms / 1000.0 + 0.6)
        eval_tasks = [
            self.eval_js(expr, await_promise=True, timeout=call_timeout)
        ]
        visible_sids = [sid for sid in cdp._visible_child_sids if sid in set(cdp._child_sessions.values())]
        for sid in visible_sids[:3]:
            eval_tasks.append(
                self.eval_js(
                    expr,
                    session_id=sid,
                    await_promise=True,
                    timeout=call_timeout,
                )
            )
        results = await asyncio.gather(*eval_tasks, return_exceptions=True)
        main_res = results[0] if results else None
        if isinstance(main_res, dict):
            return main_res
        return {"settled": False, "reason": "fallback"}

    async def navigate(self, url: str) -> dict[str, Any]:
        target_url = normalize_url(url)
        cdp = await self.ensure_connected()
        await self._bring_to_front(cdp)
        res = await cdp.call("Page.navigate", {"url": target_url}, timeout=15.0)
        if res.get("errorText"):
            raise BrowserActionError(f"页面加载失败: {res['errorText']} ({target_url})")
        await asyncio.sleep(0.15)
        return await self.wait_until_stable()

    async def go_back(self) -> bool:
        cdp = await self.ensure_connected()
        hist = await cdp.call("Page.getNavigationHistory", timeout=5.0)
        idx = int(hist.get("currentIndex") or 0)
        entries = hist.get("entries") or []
        if idx <= 0 or idx - 1 >= len(entries):
            return False
        await cdp.call("Page.navigateToHistoryEntry", {"entryId": entries[idx - 1]["id"]}, timeout=10.0)
        await asyncio.sleep(0.15)
        await self.wait_until_stable()
        return True

    async def go_forward(self) -> bool:
        cdp = await self.ensure_connected()
        hist = await cdp.call("Page.getNavigationHistory", timeout=5.0)
        idx = int(hist.get("currentIndex") or 0)
        entries = hist.get("entries") or []
        if idx + 1 >= len(entries):
            return False
        await cdp.call("Page.navigateToHistoryEntry", {"entryId": entries[idx + 1]["id"]}, timeout=10.0)
        await asyncio.sleep(0.15)
        await self.wait_until_stable()
        return True

    async def reload(self) -> None:
        cdp = await self.ensure_connected()
        await cdp.call("Page.reload", {"ignoreCache": False}, timeout=10.0)
        await asyncio.sleep(0.15)
        await self.wait_until_stable()

    async def _dispatch_mouse_click(
        self,
        cdp: CdpSession,
        px: float,
        py: float,
        *,
        button: str = "left",
        click_count: int = 1,
    ) -> None:
        await self._bring_to_front(cdp)
        for attempt in range(2):
            try:
                await cdp.call(
                    "Input.dispatchMouseEvent",
                    {"type": "mouseMoved", "x": px, "y": py},
                    timeout=3.0,
                )
                for _ in range(max(1, click_count)):
                    await cdp.call(
                        "Input.dispatchMouseEvent",
                        {"type": "mousePressed", "x": px, "y": py, "button": button, "clickCount": 1},
                        timeout=3.0,
                    )
                    await asyncio.sleep(0.03)
                    await cdp.call(
                        "Input.dispatchMouseEvent",
                        {"type": "mouseReleased", "x": px, "y": py, "button": button, "clickCount": 1},
                        timeout=3.0,
                    )
                return
            except TimeoutError:
                if attempt == 0:
                    await self._bring_to_front(cdp)
                    await asyncio.sleep(0.15)
                    continue
                raise

    async def _maybe_follow_new_tab(self, cdp: CdpSession, before_ids: set[str]) -> bool:
        """若点击链接新开了 target=_blank 标签页，自动切换到新标签页（与真人视角一致）。"""
        try:
            targets_res = await cdp.call("Target.getTargets", timeout=2.0)
            for t in targets_res.get("targetInfos") or []:
                tid = str(t.get("targetId") or "")
                if t.get("type") == "page" and tid and tid not in before_ids:
                    if str(t.get("openerId") or "") == self._target_id:
                        tabs = await self.list_tabs()
                        new_tab = next((tb for tb in tabs if tb["id"] == tid), None)
                        if new_tab and new_tab.get("ws_url"):
                            await self._http_request(f"/json/activate/{tid}", timeout=2.0)
                            await self._attach_target(tid, new_tab["ws_url"])
                            return True
        except Exception as exc:
            logger.debug(f"[BrowserDriver] 检测新标签页失败: {exc}")
        return False

    async def click_at(self, x: float, y: float, *, button: str = "left", click_count: int = 1) -> None:
        cdp = await self.ensure_connected()
        before_nav = cdp._nav_seq
        before_ids: set[str] = set()
        try:
            tg = await cdp.call("Target.getTargets", timeout=2.0)
            before_ids = {
                str(t.get("targetId") or "")
                for t in (tg.get("targetInfos") or [])
                if t.get("type") == "page"
            }
        except Exception:
            pass
        await self._dispatch_mouse_click(cdp, float(x), float(y), button=button, click_count=click_count)
        await asyncio.sleep(0.2 if cdp._nav_seq != before_nav else 0.15)
        await self._maybe_follow_new_tab(cdp, before_ids)
        await self.wait_until_stable()

    async def hover_at(self, x: float, y: float) -> None:
        cdp = await self.ensure_connected()
        await self._bring_to_front(cdp)
        await cdp.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": float(x), "y": float(y)}, timeout=3.0)
        await asyncio.sleep(0.15)
        await self.wait_until_stable()

    async def input_text(
        self,
        text: str,
        *,
        x: float | None = None,
        y: float | None = None,
        clear: bool = False,
    ) -> None:
        cdp = await self.ensure_connected()
        if x is not None and y is not None:
            await self._dispatch_mouse_click(cdp, float(x), float(y), button="left", click_count=1)
            await asyncio.sleep(0.08)
        if clear:
            await cdp.call(
                "Input.dispatchKeyEvent",
                {"type": "rawKeyDown", "modifiers": 2, "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65},
                timeout=5.0,
            )
            await cdp.call(
                "Input.dispatchKeyEvent",
                {"type": "keyUp", "modifiers": 2, "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65},
                timeout=5.0,
            )
            await cdp.call(
                "Input.dispatchKeyEvent",
                {"type": "rawKeyDown", "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8},
                timeout=5.0,
            )
            await cdp.call(
                "Input.dispatchKeyEvent",
                {"type": "keyUp", "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8},
                timeout=5.0,
            )
            await asyncio.sleep(0.05)

        await cdp.call("Input.insertText", {"text": str(text)}, timeout=8.0)
        await asyncio.sleep(0.12)
        await self.wait_until_stable()

    async def press_key(self, key_name: str) -> None:
        cdp = await self.ensure_connected()
        raw = (key_name or "").strip()
        if not raw:
            raise ValueError("press 需要指定 key 参数（如 Enter / Escape / Tab / Space / ArrowDown）")
        spec = _KEY_DEFINITIONS.get(raw.lower())
        if spec:
            down_params: dict[str, Any] = {
                "type": "rawKeyDown",
                "key": spec["key"],
                "code": spec["code"],
                "windowsVirtualKeyCode": spec["vk"],
            }
            await cdp.call("Input.dispatchKeyEvent", down_params, timeout=5.0)
            if spec.get("text"):
                await cdp.call(
                    "Input.dispatchKeyEvent",
                    {"type": "char", "text": spec["text"], "key": spec["key"], "code": spec["code"]},
                    timeout=5.0,
                )
            await cdp.call(
                "Input.dispatchKeyEvent",
                {"type": "keyUp", "key": spec["key"], "code": spec["code"], "windowsVirtualKeyCode": spec["vk"]},
                timeout=5.0,
            )
        elif len(raw) == 1:
            await cdp.call("Input.insertText", {"text": raw}, timeout=5.0)
        else:
            await cdp.call("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": raw}, timeout=5.0)
            await cdp.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": raw}, timeout=5.0)
        await asyncio.sleep(0.12)
        await self.wait_until_stable()

    async def scroll(
        self,
        direction: str = "down",
        *,
        x: float | None = None,
        y: float | None = None,
        amount: int | None = None,
    ) -> None:
        cdp = await self.ensure_connected()
        metrics = await self.eval_js(
            "({w: window.innerWidth || 1280, h: window.innerHeight || 720})",
            timeout=3.0,
        ) or {"w": 1280, "h": 720}
        vw = max(200, int(metrics.get("w") or 1280))
        vh = max(200, int(metrics.get("h") or 720))
        cx = float(x) if x is not None else vw / 2.0
        cy = float(y) if y is not None else vh / 2.0
        step_y = int(amount or max(260, int(vh * 0.65)))
        step_x = int(amount or max(260, int(vw * 0.55)))
        d = (direction or "down").strip().lower()
        dx, dy = 0, 0
        if d == "down":
            dy = step_y
        elif d == "up":
            dy = -step_y
        elif d == "right":
            dx = step_x
        elif d == "left":
            dx = -step_x
        else:
            raise ValueError("direction 只能是 up / down / left / right")

        await self._bring_to_front(cdp)
        try:
            await cdp.call(
                "Input.dispatchMouseEvent",
                {"type": "mouseWheel", "x": cx, "y": cy, "deltaX": dx, "deltaY": dy},
                timeout=1.2,
            )
        except TimeoutError:
            logger.debug("[BrowserDriver] mouseWheel 超时，降级为 DOM scrollBy 滚动")
            await self.eval_js(
                f"""(function(cx, cy, dx, dy) {{
                  var el = document.elementFromPoint(cx, cy);
                  while (el && el !== document.body && el !== document.documentElement) {{
                    var cs = window.getComputedStyle(el);
                    var canY = dy !== 0 && el.scrollHeight > el.clientHeight + 2 && /(auto|scroll)/.test(cs.overflowY);
                    var canX = dx !== 0 && el.scrollWidth > el.clientWidth + 2 && /(auto|scroll)/.test(cs.overflowX);
                    if (canY || canX) {{
                      el.scrollBy({{left: dx, top: dy, behavior: 'instant'}});
                      return true;
                    }}
                    el = el.parentElement;
                  }}
                  window.scrollBy({{left: dx, top: dy, behavior: 'instant'}});
                  return true;
                }})({cx}, {cy}, {dx}, {dy})""",
                timeout=3.0,
            )
        await asyncio.sleep(0.18)
        await self.wait_until_stable()

    async def capture_screenshot(self) -> bytes:
        cdp = await self.ensure_connected()
        res = await cdp.call("Page.captureScreenshot", {"format": "png", "fromSurface": True}, timeout=12.0)
        b64 = res.get("data") or ""
        return base64.b64decode(b64) if b64 else b""

    async def _frame_rect_in_parent(
        self,
        parent_session_id: str | None,
        child_frame_id: str,
    ) -> dict[str, Any] | None:
        cdp = self._cdp
        assert cdp is not None
        try:
            owner = await cdp.call(
                "DOM.getFrameOwner",
                {"frameId": child_frame_id},
                session_id=parent_session_id,
                timeout=3.0,
            )
            backend_id = owner.get("backendNodeId")
            if not backend_id:
                return None
            resolved = await cdp.call(
                "DOM.resolveNode",
                {"backendNodeId": backend_id},
                session_id=parent_session_id,
                timeout=3.0,
            )
            object_id = (resolved.get("object") or {}).get("objectId")
            if not object_id:
                return None
            fn_res = await cdp.call(
                "Runtime.callFunctionOn",
                {
                    "objectId": object_id,
                    "functionDeclaration": (
                        "function() {"
                        "  var r = this.getBoundingClientRect();"
                        "  var cs = window.getComputedStyle(this);"
                        "  var vis = cs.display !== 'none' && cs.visibility !== 'hidden' && cs.opacity !== '0';"
                        "  var bl = parseFloat(cs.borderLeftWidth) || 0;"
                        "  var bt = parseFloat(cs.borderTopWidth) || 0;"
                        "  var pl = parseFloat(cs.paddingLeft) || 0;"
                        "  var pt = parseFloat(cs.paddingTop) || 0;"
                        "  return {x: r.left + bl + pl, y: r.top + bt + pt, w: r.width, h: r.height, visible: vis};"
                        "}"
                    ),
                    "returnByValue": True,
                },
                session_id=parent_session_id,
                timeout=3.0,
            )
            return ((fn_res.get("result") or {}).get("value")) or None
        except Exception as exc:
            logger.debug(f"[BrowserDriver] 获取 iframe({child_frame_id}) 坐标失败: {exc}")
            return None

    async def _collect_frame_recursive(
        self,
        frame_node: dict[str, Any],
        probe_js: str,
        *,
        parent_session_id: str | None,
        offset_x: float,
        offset_y: float,
        is_root: bool,
        out_frames: list[dict[str, Any]],
    ) -> None:
        cdp = self._cdp
        assert cdp is not None
        frame = frame_node.get("frame") or {}
        frame_id = str(frame.get("id") or "")
        frame_url = str(frame.get("url") or "")
        cur_ox, cur_oy = offset_x, offset_y
        cur_session_id = parent_session_id

        if not is_root:
            if not frame_id or frame_url.startswith(("about:blank", "javascript:")):
                # 空白广告/占位 iframe 跳过
                if frame_url == "about:blank":
                    return
            rect = await self._frame_rect_in_parent(parent_session_id, frame_id)
            if not rect or not rect.get("visible") or float(rect.get("w") or 0) < 16 or float(rect.get("h") or 0) < 16:
                return
            cur_ox = offset_x + float(rect.get("x") or 0)
            cur_oy = offset_y + float(rect.get("y") or 0)
            # 若该 child frame 是跨域 OOPIF，会有独立的 child session（在 Chrome CDP 中 targetId == frameId）
            if frame_id in cdp._child_sessions:
                cur_session_id = cdp._child_sessions[frame_id]
                cdp._visible_child_sids.add(cur_session_id)
                for dom in ("Page", "DOM", "Runtime"):
                    try:
                        await cdp.call(f"{dom}.enable", session_id=cur_session_id, timeout=3.0)
                    except Exception:
                        pass
                # OOPIF 自身也可能包含更深层的子帧
                try:
                    sub_tree = await cdp.call("Page.getFrameTree", session_id=cur_session_id, timeout=3.0)
                    sub_children = (sub_tree.get("frameTree") or {}).get("childFrames") or []
                    if sub_children and not frame_node.get("childFrames"):
                        frame_node["childFrames"] = sub_children
                except Exception:
                    pass

        # 执行视口探针
        snap = None
        try:
            if is_root or cur_session_id != parent_session_id:
                snap = await self.eval_js(probe_js, session_id=cur_session_id, timeout=5.0)
            else:
                world = await cdp.call(
                    "Page.createIsolatedWorld",
                    {"frameId": frame_id, "worldName": "yuki_probe", "grantUniveralAccess": False},
                    session_id=cur_session_id,
                    timeout=3.0,
                )
                ctx_id = world.get("executionContextId")
                if ctx_id:
                    snap = await self.eval_js(probe_js, session_id=cur_session_id, context_id=ctx_id, timeout=5.0)
        except Exception as exc:
            logger.debug(f"[BrowserDriver] 探针执行跳过 frame={frame_id} ({frame_url[:50]}): {exc}")

        if isinstance(snap, dict):
            snap["_frame_id"] = frame_id
            snap["_frame_url"] = frame_url
            snap["_offset_x"] = cur_ox
            snap["_offset_y"] = cur_oy
            snap["_is_root"] = is_root
            out_frames.append(snap)

        for child in frame_node.get("childFrames") or []:
            await self._collect_frame_recursive(
                child,
                probe_js,
                parent_session_id=cur_session_id,
                offset_x=cur_ox,
                offset_y=cur_oy,
                is_root=False,
                out_frames=out_frames,
            )

    async def collect_frames_snapshot(self, probe_js: str) -> list[dict[str, Any]]:
        """穿透同源与跨域 iframe，收集所有可见 Frame 的探针结果（含顶层视口偏移）。"""
        cdp = await self.ensure_connected()
        oopif_by_parent: dict[str, list[dict[str, Any]]] = {}
        try:
            targets_res = await cdp.call("Target.getTargets", timeout=3.0)
            for t in targets_res.get("targetInfos") or []:
                tid = str(t.get("targetId") or "")
                ttype = str(t.get("type") or "")
                parent_fid = str(t.get("parentFrameId") or "")
                if ttype != "iframe" or not tid:
                    continue
                if tid not in cdp._child_sessions:
                    try:
                        att = await cdp.call(
                            "Target.attachToTarget",
                            {"targetId": tid, "flatten": True},
                            timeout=3.0,
                        )
                        sid = str(att.get("sessionId") or "")
                        if sid:
                            cdp._child_sessions[tid] = sid
                            cdp._session_to_target[sid] = tid
                    except Exception:
                        pass
                if parent_fid:
                    oopif_by_parent.setdefault(parent_fid, []).append({
                        "frame": {"id": tid, "url": str(t.get("url") or "")},
                        "childFrames": [],
                    })
        except Exception:
            pass

        tree_res = await cdp.call("Page.getFrameTree", timeout=5.0)
        frame_tree = tree_res.get("frameTree") or {}

        def _inject_oopifs(node: dict[str, Any]) -> None:
            fid = str((node.get("frame") or {}).get("id") or "")
            existing = node.setdefault("childFrames", [])
            seen_ids = {str((c.get("frame") or {}).get("id") or "") for c in existing}
            for oopif_node in oopif_by_parent.get(fid, ()):
                oid = str((oopif_node.get("frame") or {}).get("id") or "")
                if oid and oid not in seen_ids:
                    existing.append(oopif_node)
                    seen_ids.add(oid)
            for child in existing:
                _inject_oopifs(child)

        _inject_oopifs(frame_tree)
        cdp._visible_child_sids.clear()
        out: list[dict[str, Any]] = []
        await self._collect_frame_recursive(
            frame_tree,
            probe_js,
            parent_session_id=None,
            offset_x=0.0,
            offset_y=0.0,
            is_root=True,
            out_frames=out,
        )
        return out


driver = BrowserDriver()
