# core/phone_macro.py
"""手机组合技：操作历史落盘 + 语义定位器 + 宏的清洗与持久化。

设计取舍：
    1. 控件编号每次 dump 都会变，所以记录的是「语义定位器」：
       text(控件文案) + cls(类名) + rel(相对屏幕的比例坐标)；
       回放时先按文案全等匹配、再模糊匹配、最后按比例坐标兜底（偏差超阈值算失败）。
    2. 历史全量保留原始步骤，只在「存成宏」时做清洗（往返折叠 / 相邻重复），
       清洗规则会误判，日志保持原样才方便事后排查。
    3. 每步都带 expect（动作后新增的文案 + package），回放时用它判断这步是否生效。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time

from utils import BASE_DIR
from utils.logger import get_logger

logger = get_logger("phone_macro")

DATA_DIR = os.path.join(BASE_DIR, "data")
DEFAULT_HISTORY_PATH = os.path.join(DATA_DIR, "phone_history.jsonl")
DEFAULT_MACRO_PATH = os.path.join(DATA_DIR, "phone_macros.json")

HISTORY_MAX_LINES = 500
HISTORY_KEEP_LINES = 300
MACRO_VERSION = 1

# 回放时按比例坐标兜底允许的偏差（相对屏幕长边）
COORD_TOLERANCE = 0.08
# 相邻重复点击判定的时间窗（秒）
DUP_TAP_WINDOW = 2.5
# 往返折叠最多回看多少步
ROUND_TRIP_WINDOW = 8

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_\-]+)\s*\}\}")
_PRIVATE_PREFIX = "_"


# ---------------- 定位器 ----------------

def _labels(tree: dict, limit: int = 5) -> list[str]:
    labels = [node["label"] for node in tree.get("nodes", []) if node.get("label")]
    return labels[:limit] if limit else labels


def fingerprint(tree: dict) -> str:
    """界面指纹：package + 前若干个控件文案，用于判断「是否回到了原界面」。"""
    raw = (tree.get("package") or "") + "\x1f" + "\x1f".join(_labels(tree))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def state_of(tree: dict) -> dict:
    return {"package": tree.get("package") or "", "fp": fingerprint(tree), "labels": _labels(tree)}


def build_locator(node: dict, tree: dict) -> dict:
    """把控件节点转成与编号无关的定位器。"""
    width, height = tree.get("size") or (0, 0)
    rel = [
        round(node["cx"] / width, 4) if width else 0.5,
        round(node["cy"] / height, 4) if height else 0.5,
    ]
    return {"kind": "node", "text": (node.get("label") or "")[:40],
            "cls": node.get("cls") or "", "rel": rel}


def locator_at(x: int, y: int, tree: dict) -> dict:
    """坐标点按也存成比例定位器，换分辨率仍可用。"""
    width, height = tree.get("size") or (0, 0)
    return {
        "kind": "point",
        "text": "",
        "cls": "",
        "rel": [
            round(x / width, 4) if width else 0.5,
            round(y / height, 4) if height else 0.5,
        ],
    }


def resolve_locator(tree: dict, locator: dict, tolerance: float = COORD_TOLERANCE):
    """在控件树里落地一个定位器，返回 (x, y, 描述, 匹配方式)；失败返回 None。

    kind=point（模型直接点坐标）就按比例还原成点，不做控件吸附；
    kind=node（记录时对着控件点的）先按文案匹配，再按比例坐标就近吸附，
    偏差超过屏幕长边的 tolerance 视为界面已变，返回 None 让调用方报错。
    """
    nodes = tree.get("nodes") or []
    width, height = tree.get("size") or (0, 0)
    rel = (locator or {}).get("rel") or [0.5, 0.5]
    rel = (list(rel) + [0.5, 0.5])[:2]
    tx, ty = float(rel[0]) * width, float(rel[1]) * height
    text = ((locator or {}).get("text") or "").strip()
    cls = ((locator or {}).get("cls") or "").strip()
    kind = (locator or {}).get("kind") or ("node" if text else "point")

    if kind == "point":
        return int(tx), int(ty), "", "point"

    def distance(node) -> float:
        return ((node["cx"] - tx) ** 2 + (node["cy"] - ty) ** 2) ** 0.5

    if text:
        exact = [n for n in nodes if (n.get("label") or "") == text]
        if exact:
            same_cls = [n for n in exact if cls and n.get("cls") == cls]
            pool = same_cls or exact
            node = min(pool, key=distance)
            return node["cx"], node["cy"], node.get("label") or text, "text"
        fuzzy = [
            n for n in nodes
            if n.get("label")
            and (text in n["label"] or n["label"] in text)
            and min(len(text), len(n["label"])) >= 2
        ]
        if fuzzy:
            node = min(fuzzy, key=distance)
            return node["cx"], node["cy"], node.get("label") or text, "fuzzy"
        # 有文案却找不到：说明界面真的变了，宁可失败也不盲点
        return None

    if nodes:
        node = min(nodes, key=distance)
        if distance(node) <= max(width, height, 1) * tolerance:
            return node["cx"], node["cy"], node.get("label") or "", "coord"
    if 0 < tx < width and 0 < ty < height:
        return int(tx), int(ty), "", "point"
    return None


# ---------------- expect ----------------

# 这类文案是过程提示，出现在 expect 里会让回放永远等不到
TRANSIENT_LABELS = ("加载", "刷新", "请稍候", "Loading", "loading")


def build_expect(before: dict, after: dict, limit: int = 3) -> dict:
    """动作后新出现的文案 + package，作为回放时的校验条件。"""
    old = {label for label in _labels(before, 0)}
    new = [
        label[:40] for label in _labels(after, 0)
        if label not in old and not any(word in label for word in TRANSIENT_LABELS)
    ]
    return {"package": after.get("package") or "", "labels": new[:limit]}


# ---------------- 历史 ----------------

class PhoneHistory:
    """手机操作历史：jsonl 追加，滚动保留最近若干条。"""

    def __init__(self, path: str = DEFAULT_HISTORY_PATH, max_lines: int = HISTORY_MAX_LINES,
                 keep_lines: int = HISTORY_KEEP_LINES):
        self.path = os.path.abspath(path)
        self.max_lines = max_lines
        self.keep_lines = keep_lines
        self._lock = threading.Lock()
        self._count = None
        self._seq = 0

    def _scan(self) -> None:
        """首次使用时数一遍行数并取出最后的序号。"""
        self._count, self._seq = 0, 0
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    self._count += 1
                    try:
                        self._seq = max(self._seq, int(json.loads(line).get("n") or 0))
                    except (ValueError, TypeError, json.JSONDecodeError):
                        continue
        except OSError as exc:
            logger.warning(f"[PhoneHistory] 读取失败: {exc}")

    def record(self, chat_id: str, step: dict, before: dict, after: dict) -> dict:
        with self._lock:
            if self._count is None:
                self._scan()
            self._seq += 1
            entry = {
                "n": self._seq,
                "ts": round(time.time(), 3),
                "chat_id": str(chat_id or ""),
                "step": step,
                "before": state_of(before),
                "after": state_of(after),
                "expect": build_expect(before, after),
            }
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                self._count += 1
                if self._count > self.max_lines:
                    self._rotate()
            except OSError as exc:
                logger.warning(f"[PhoneHistory] 写入失败: {exc}")
            return entry

    def _rotate(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                lines = [line for line in f if line.strip()]
        except OSError:
            return
        kept = lines[-self.keep_lines:]
        temp = f"{self.path}.tmp"
        try:
            with open(temp, "w", encoding="utf-8") as f:
                f.writelines(kept)
            os.replace(temp, self.path)
            self._count = len(kept)
        except OSError as exc:
            logger.warning(f"[PhoneHistory] 轮转失败: {exc}")

    def recent(self, limit: int = 15) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                lines = [line for line in f if line.strip()]
        except OSError as exc:
            logger.warning(f"[PhoneHistory] 读取失败: {exc}")
            return []
        entries = []
        for line in lines[-max(1, limit):]:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries


phone_history = PhoneHistory()


def _same_locator(a: dict | None, b: dict | None, tolerance: float = 0.01) -> bool:
    a, b = a or {}, b or {}
    if (a.get("text") or "") != (b.get("text") or ""):
        return False
    ra, rb = a.get("rel") or [0, 0], b.get("rel") or [0, 0]
    try:
        return abs(float(ra[0]) - float(rb[0])) <= tolerance and abs(float(ra[1]) - float(rb[1])) <= tolerance
    except (TypeError, ValueError, IndexError):
        return False


def _is_back(step: dict) -> bool:
    return step.get("op") == "key" and str(step.get("key") or "").upper().endswith("BACK")


def _strip_private(step: dict) -> dict:
    return {k: v for k, v in step.items() if not str(k).startswith(_PRIVATE_PREFIX)}


def clean_steps(entries: list[dict]) -> tuple[list[dict], dict]:
    """把历史记录清洗成可复用的宏步骤。

    返回 (steps, report)；report 里记着折叠掉了多少步，方便模型一眼确认。
    """
    items = []
    for entry in entries:
        step = entry.get("step")
        before = entry.get("before") or {}
        if not isinstance(step, dict) or not before:
            continue
        step = dict(step)
        step.setdefault("expect", entry.get("expect") or {})
        step["_ts"] = entry.get("ts") or 0
        step["_before_fp"] = before.get("fp") or ""
        step["_after_fp"] = (entry.get("after") or {}).get("fp") or ""
        items.append(step)

    report = {"input": len(items), "round_trip": 0, "duplicate": 0, "noop": 0}

    # 1) 往返折叠：点进某页又 back 回到原界面 → 这段白跑，整段丢弃
    folded: list[dict] = []
    index = 0
    while index < len(items):
        step = items[index]
        if step.get("op") in ("tap", "long_press"):
            back_at = None
            for cursor in range(index + 1, min(index + ROUND_TRIP_WINDOW + 1, len(items))):
                if _is_back(items[cursor]):
                    back_at = cursor
                    break
            if back_at is not None:
                back_fp = items[back_at].get("_after_fp") or ""
                if back_fp and back_fp == step.get("_before_fp"):
                    report["round_trip"] += back_at - index + 1
                    index = back_at + 1
                    continue
        folded.append(step)
        index += 1

    # 2) 按键空转：如输入法把 back 吃掉，界面指纹完全没变，这步等于没做
    effective: list[dict] = []
    for step in folded:
        if (
            step.get("op") == "key"
            and step.get("_before_fp")
            and step.get("_before_fp") == step.get("_after_fp")
        ):
            report["noop"] += 1
            continue
        effective.append(step)

    # 3) 相邻重复点击：两秒内连点同一个控件只留一次
    final: list[dict] = []
    for step in effective:
        if final and step.get("op") == "tap" and final[-1].get("op") == "tap":
            previous = final[-1]
            if (
                _same_locator(previous.get("loc"), step.get("loc"))
                and abs(float(step.get("_ts") or 0) - float(previous.get("_ts") or 0)) <= DUP_TAP_WINDOW
            ):
                report["duplicate"] += 1
                continue
        final.append(step)

    report["steps"] = len(final)
    return [_strip_private(step) for step in final], report


# ---------------- 参数替换 ----------------

def render_value(value, params: dict, missing: set):
    if isinstance(value, str):
        def replacement(match):
            key = match.group(1)
            if key not in params:
                missing.add(key)
                return match.group(0)
            return str(params[key])
        return _PLACEHOLDER_RE.sub(replacement, value)
    if isinstance(value, list):
        return [render_value(item, params, missing) for item in value]
    if isinstance(value, dict):
        return {key: render_value(item, params, missing) for key, item in value.items()}
    return value


def render_steps(steps: list[dict], params: dict) -> tuple[list[dict], list[str]]:
    missing: set[str] = set()
    rendered = [render_value(step, params, missing) for step in steps]
    return rendered, sorted(missing)


def used_placeholders(steps: list[dict]) -> set[str]:
    """扫出步骤里引用到的 {{参数名}}。"""
    found: set[str] = set()

    def walk(value):
        if isinstance(value, str):
            found.update(_PLACEHOLDER_RE.findall(value))
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)

    walk(steps)
    return found


def apply_replacements(value, mapping: dict):
    """把字面量替换成占位符（如 {"炸鸡": "{{food}}"}），用于把录下来的固定文字参数化。"""
    if not mapping:
        return value
    if isinstance(value, str):
        for old, new in mapping.items():
            if old and str(old) in value:
                value = value.replace(str(old), str(new))
        return value
    if isinstance(value, list):
        return [apply_replacements(item, mapping) for item in value]
    if isinstance(value, dict):
        return {key: apply_replacements(item, mapping) for key, item in value.items()}
    return value


def declared_params(params) -> list[dict]:
    """规范化参数声明，支持 ["food"] 或 [{"name": "food", "desc": "..."}]。"""
    result = []
    for item in params or []:
        if isinstance(item, str):
            name = item.strip()
            desc = ""
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            desc = str(item.get("desc") or "")
        else:
            continue
        if not name:
            continue
        result.append({"name": name, "desc": desc, "default": (item.get("default", "") if isinstance(item, dict) else "")})
    return result


# ---------------- 宏存储 ----------------

class MacroStore:
    """组合技持久化（原子写，全局一份）。"""

    def __init__(self, path: str = DEFAULT_MACRO_PATH):
        self.path = os.path.abspath(path)
        self._lock = threading.Lock()

    def _load(self) -> dict:
        if not os.path.exists(self.path):
            return {"version": MACRO_VERSION, "macros": {}}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(f"[PhoneMacro] 读取失败: {exc}")
            return {"version": MACRO_VERSION, "macros": {}}
        if not isinstance(data, dict):
            return {"version": MACRO_VERSION, "macros": {}}
        data.setdefault("version", MACRO_VERSION)
        if not isinstance(data.get("macros"), dict):
            data["macros"] = {}
        return data

    def _write(self, data: dict) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        temp = f"{self.path}.tmp"
        with open(temp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp, self.path)

    def list(self) -> list[dict]:
        with self._lock:
            macros = self._load()["macros"]
        return sorted(
            (
                {
                    "name": name,
                    "desc": (item.get("desc") or ""),
                    "app": (item.get("app") or ""),
                    "params": item.get("params") or [],
                    "steps": len(item.get("steps") or []),
                    "version": item.get("version") or 1,
                    "used": item.get("used") or 0,
                    "ok": item.get("ok") or 0,
                    "fail": item.get("fail") or 0,
                }
                for name, item in macros.items()
            ),
            key=lambda row: row["name"],
        )

    def get(self, name: str) -> dict | None:
        with self._lock:
            return self._load()["macros"].get(str(name or "").strip())

    def save(self, name: str, desc: str, app: str, params: list[dict], steps: list[dict]) -> dict:
        name = str(name or "").strip()
        with self._lock:
            data = self._load()
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            old = data["macros"].get(name) or {}
            macro = {
                "name": name,
                "desc": desc or old.get("desc") or "",
                "app": app or old.get("app") or "",
                "params": params,
                "steps": steps,
                "version": int(old.get("version") or 0) + 1,
                "created_at": old.get("created_at") or now,
                "updated_at": now,
                "used": int(old.get("used") or 0),
                "ok": int(old.get("ok") or 0),
                "fail": int(old.get("fail") or 0),
            }
            data["macros"][name] = macro
            self._write(data)
        return macro

    def delete(self, name: str) -> bool:
        name = str(name or "").strip()
        with self._lock:
            data = self._load()
            if name not in data["macros"]:
                return False
            data["macros"].pop(name)
            self._write(data)
        return True

    def record_result(self, name: str, ok: bool) -> None:
        name = str(name or "").strip()
        with self._lock:
            data = self._load()
            macro = data["macros"].get(name)
            if not macro:
                return
            macro["used"] = int(macro.get("used") or 0) + 1
            macro["ok" if ok else "fail"] = int(macro.get("ok" if ok else "fail") or 0) + 1
            try:
                self._write(data)
            except OSError as exc:
                logger.warning(f"[PhoneMacro] 统计写入失败: {exc}")


macro_store = MacroStore()
