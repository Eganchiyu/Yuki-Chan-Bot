# tests/test_tool_phone_macro.py
"""手机组合技：定位器、历史清洗、宏存储与回放的离线单元测试。"""
from types import SimpleNamespace

import pytest

from core import phone_macro as pm
from core.toolchain import ToolContext, ToolRuntime
from core.tools import TOOL_HANDLERS, TOOL_SPECS
from core.tools import tools_phone as tp
from core.tools import tools_phone_macro as tpm


def _context():
    runtime = ToolRuntime(sender=None, yuki_state=SimpleNamespace(), image_store=None)
    return ToolContext(chat_id="c1", mode="group", session=[], combined_text="",
                       runtime=runtime, metadata={})


def _tree(package="com.sankuai.meituan", labels=("外卖", "搜索", "购物车")):
    nodes = []
    for index, label in enumerate(labels, 1):
        nodes.append({
            "index": index,
            "label": label,
            "kind": "可点",
            "cls": "android.widget.TextView",
            "bounds": (0, index * 100, 200, index * 100 + 80),
            "cx": 100,
            "cy": index * 100 + 40,
        })
    return {"package": package, "size": (1080, 2400), "nodes": nodes}


def _entry(seq, step, before_tree, after_tree):
    return {
        "n": seq,
        "ts": float(seq),
        "step": step,
        "before": pm.state_of(before_tree),
        "after": pm.state_of(after_tree),
        "expect": pm.build_expect(before_tree, after_tree),
    }


# ---------- 注册 ----------

def test_phone_macro_registered():
    assert "phone_macro" in TOOL_HANDLERS
    spec = next(s for s in TOOL_SPECS if s.name == "phone_macro")
    assert {"save", "play", "history"} <= set(spec.parameters["properties"]["action"]["enum"])


# ---------- 定位器 ----------

def test_locator_by_text_survives_layout_shift():
    tree = _tree()
    node = tree["nodes"][1]
    locator = pm.build_locator(node, tree)
    shifted = _tree(labels=("外卖", "搜索", "购物车"))
    shifted["nodes"][1]["cy"] = 900
    shifted["nodes"][1]["bounds"] = (0, 860, 200, 940)
    matched = pm.resolve_locator(shifted, locator)
    assert matched and matched[0] == 100 and matched[1] == 900 and matched[3] == "text"


def test_locator_fails_when_text_disappeared():
    locator = pm.build_locator(_tree()["nodes"][1], _tree())
    assert pm.resolve_locator(_tree(labels=("外卖", "购物车")), locator) is None


def test_locator_plain_point_ignores_nodes():
    locator = pm.locator_at(540, 1200, _tree())
    matched = pm.resolve_locator(_tree(), locator)
    assert matched and matched[0] == 540 and matched[1] == 1200 and matched[3] == "point"


def test_build_expect_only_new_labels():
    before = _tree(labels=("外卖", "搜索"))
    after = _tree(labels=("外卖", "搜索", "正在加载", "店铺列表"))
    expect = pm.build_expect(before, after)
    assert expect["package"] == "com.sankuai.meituan"
    assert "店铺列表" in expect["labels"]
    assert "正在加载" not in expect["labels"]  # 过程提示不进 expect


# ---------- 清洗 ----------

def test_clean_steps_folds_round_trip():
    home, page = _tree(labels=("外卖", "搜索")), _tree(labels=("店铺", "返回"))
    tap_in = {"op": "tap", "label": "外卖", "loc": pm.build_locator(home["nodes"][0], home)}
    back = {"op": "key", "label": "", "key": "KEYCODE_BACK"}
    tap_search = {"op": "tap", "label": "搜索", "loc": pm.build_locator(home["nodes"][1], home)}
    entries = [
        _entry(1, tap_in, home, page),
        _entry(2, back, page, home),
        _entry(3, tap_search, home, page),
    ]
    steps, report = pm.clean_steps(entries)
    assert report["round_trip"] == 2
    assert len(steps) == 1 and steps[0]["label"] == "搜索"
    assert "expect" in steps[0]


def test_clean_steps_keeps_back_when_landing_differs():
    home, page = _tree(labels=("外卖", "搜索")), _tree(labels=("店铺", "返回"))
    other = _tree(labels=("店铺", "广告"))
    entries = [
        _entry(1, {"op": "tap", "label": "外卖", "loc": pm.build_locator(home["nodes"][0], home)}, home, page),
        _entry(2, {"op": "key", "label": "", "key": "KEYCODE_BACK"}, page, other),
    ]
    steps, report = pm.clean_steps(entries)
    assert report["round_trip"] == 0
    assert len(steps) == 2


def test_clean_steps_drops_noop_key():
    home = _tree()
    entries = [_entry(1, {"op": "key", "label": "", "key": "KEYCODE_BACK"}, home, home)]
    steps, report = pm.clean_steps(entries)
    assert report["noop"] == 1
    assert steps == []


def test_clean_steps_drops_duplicate_taps():
    home = _tree()
    loc = pm.build_locator(home["nodes"][0], home)
    step = {"op": "tap", "label": "外卖", "loc": loc}
    steps, report = pm.clean_steps([_entry(1, step, home, _tree()), _entry(2, step, home, _tree())])
    assert report["duplicate"] == 1
    assert len(steps) == 1


# ---------- 历史存储 ----------

def test_history_records_and_rotates(tmp_path):
    history = pm.PhoneHistory(tmp_path / "history.jsonl", max_lines=3, keep_lines=2)
    before, after = _tree(), _tree(labels=("外卖", "搜索", "购物车", "新页面"))
    for _ in range(6):
        history.record("c1", {"op": "tap", "label": "搜索"}, before, after)
    entries = history.recent(10)
    assert len(entries) == 2  # 超出上限后只留最近 keep_lines 条
    assert entries[-1]["n"] == 6
    assert entries[-1]["expect"]["labels"] == ["新页面"]


# ---------- 参数 ----------

def test_render_steps_reports_missing_params():
    steps = [{"op": "input", "text": "{{food}}", "label": "{{shop}}"}]
    rendered, missing = pm.render_steps(steps, {"food": "炸鸡"})
    assert rendered[0]["text"] == "炸鸡"
    assert missing == ["shop"]


def test_apply_replacements_and_used_placeholders():
    steps = [{"op": "input", "text": "炸鸡", "label": "炸鸡"}]
    steps = pm.apply_replacements(steps, {"炸鸡": "{{food}}"})
    assert pm.used_placeholders(steps) == {"food"}
    assert steps[0]["text"] == "{{food}}"


# ---------- 宏存储 ----------

def test_macro_store_versions_and_stats(tmp_path):
    store = pm.MacroStore(tmp_path / "macros.json")
    first = store.save("点外卖", "搜吃的", "com.sankuai.meituan", [], [{"op": "tap"}])
    assert first["version"] == 1
    second = store.save("点外卖", "", "com.sankuai.meituan", [{"name": "food"}], [{"op": "tap"}])
    assert second["version"] == 2
    store.record_result("点外卖", True)
    store.record_result("点外卖", False)
    row = store.get("点外卖")
    assert row["used"] == 2 and row["ok"] == 1 and row["fail"] == 1
    assert store.list()[0]["steps"] == 1
    assert store.delete("点外卖") is True


# ---------- phone_action 落历史 ----------

async def test_phone_action_records_semantic_step(monkeypatch, tmp_path):
    history = pm.PhoneHistory(tmp_path / "history.jsonl")
    monkeypatch.setattr(pm, "phone_history", history)
    before, after = _tree(), _tree(labels=("外卖", "搜索", "购物车", "新页面"))

    async def fake_ensure():
        return "device"

    async def fake_adb(args, timeout=20.0):
        return 0, b""

    async def fake_dump(max_nodes):
        return before if not tapped else after

    tapped = False

    original_exec = tp._exec_step

    async def fake_exec(step, tree):
        nonlocal tapped
        tapped = True
        return await original_exec(step, tree)

    monkeypatch.setattr(tp, "_ensure_device", fake_ensure)
    monkeypatch.setattr(tp, "_adb", fake_adb)
    monkeypatch.setattr(tp, "_dump_tree", fake_dump)
    monkeypatch.setattr(tp, "_exec_step", fake_exec)
    monkeypatch.setattr(tp, "_screencap", lambda: (_ for _ in ()).throw(RuntimeError("no shot")))

    result = await tp.phone_action_tool(_context(), action="tap", target="1")
    assert result.success is True
    entries = history.recent(5)
    assert len(entries) == 1
    assert entries[0]["step"]["op"] == "tap"
    assert entries[0]["step"]["loc"]["text"] == "外卖"
    assert entries[0]["expect"]["labels"] == ["新页面"]


async def test_phone_action_remember_false_skips_history(monkeypatch, tmp_path):
    history = pm.PhoneHistory(tmp_path / "history.jsonl")
    monkeypatch.setattr(pm, "phone_history", history)
    tree = _tree()

    async def fake_ensure():
        return "device"

    async def fake_adb(args, timeout=20.0):
        return 0, b""

    async def fake_dump(max_nodes):
        return tree

    monkeypatch.setattr(tp, "_ensure_device", fake_ensure)
    monkeypatch.setattr(tp, "_adb", fake_adb)
    monkeypatch.setattr(tp, "_dump_tree", fake_dump)
    monkeypatch.setattr(tp, "_screencap", lambda: (_ for _ in ()).throw(RuntimeError("no shot")))

    result = await tp.phone_action_tool(_context(), action="tap", target="1", remember=False)
    assert result.success is True
    assert history.recent(5) == []


# ---------- 宏工具 ----------

async def test_save_from_history_and_play(monkeypatch, tmp_path):
    history = pm.PhoneHistory(tmp_path / "history.jsonl")
    store = pm.MacroStore(tmp_path / "macros.json")
    monkeypatch.setattr(pm, "phone_history", history)
    monkeypatch.setattr(pm, "macro_store", store)

    home, page = _tree(labels=("外卖", "搜索")), _tree(labels=("店铺", "返回"))
    tap_step = {"op": "tap", "label": "外卖", "loc": pm.build_locator(home["nodes"][0], home)}
    history.record("c1", tap_step, home, page)

    saved = await tpm.phone_macro_tool(_context(), action="save", name="进店", from_history=5,
                                       param_defs=["shop"], replace={"外卖": "{{shop}}"})
    assert saved.success is True
    macro = store.get("进店")
    assert macro["steps"][0]["loc"]["text"] == "{{shop}}"

    async def fake_ensure():
        return "device"

    async def fake_dump(max_nodes):
        return page

    async def fake_exec(step, tree):
        return "tap 店铺"

    async def fake_wait(expect, max_nodes, timeout):
        return True, page

    monkeypatch.setattr(tpm, "_ensure_device", fake_ensure)
    monkeypatch.setattr(tpm, "_dump_tree", fake_dump)
    monkeypatch.setattr(tpm, "_exec_step", fake_exec)
    monkeypatch.setattr(tpm, "_wait_expect", fake_wait)

    played = await tpm.phone_macro_tool(_context(), action="play", name="进店", params={"shop": "奶茶"})
    assert played.success is True
    assert played.data["steps"] == 1
    assert store.get("进店")["ok"] == 1


async def test_play_launch_checks_package_only(monkeypatch, tmp_path):
    store = pm.MacroStore(tmp_path / "macros.json")
    monkeypatch.setattr(pm, "macro_store", store)
    # launch 的 expect 里带着当时的主页文案，但 App 会恢复上次页面，只校验包名
    store.save("开设置", "", "", [], [{
        "op": "launch", "label": "设置", "package": "com.android.settings",
        "expect": {"package": "com.android.settings", "labels": ["应用和服务"]},
    }])

    tree = _tree(package="com.android.settings", labels=("向上导航", "搜索设置项"))

    async def fake_ensure():
        return "device"

    async def fake_dump(max_nodes):
        return tree

    async def fake_exec(step, tree):
        return "launch com.android.settings"

    async def fake_wait(expect, max_nodes, timeout):
        assert expect["labels"] == []
        return True, tree

    monkeypatch.setattr(tpm, "_ensure_device", fake_ensure)
    monkeypatch.setattr(tpm, "_dump_tree", fake_dump)
    monkeypatch.setattr(tpm, "_exec_step", fake_exec)
    monkeypatch.setattr(tpm, "_wait_expect", fake_wait)

    result = await tpm.phone_macro_tool(_context(), action="play", name="开设置")
    assert result.success is True


async def test_play_stops_when_expect_fails(monkeypatch, tmp_path):
    store = pm.MacroStore(tmp_path / "macros.json")
    monkeypatch.setattr(pm, "macro_store", store)
    store.save("进店", "", "", [], [{"op": "tap", "label": "外卖", "loc": {"kind": "point", "rel": [0.5, 0.5]},
                                     "expect": {"package": "com.sankuai.meituan", "labels": ["店铺"]}}])

    tree = _tree()

    async def fake_ensure():
        return "device"

    async def fake_dump(max_nodes):
        return tree

    async def fake_exec(step, tree):
        return "tap 外卖"

    async def fake_wait(expect, max_nodes, timeout):
        return False, tree

    async def fake_screenshot(context, tree):
        return ""

    monkeypatch.setattr(tpm, "_ensure_device", fake_ensure)
    monkeypatch.setattr(tpm, "_dump_tree", fake_dump)
    monkeypatch.setattr(tpm, "_exec_step", fake_exec)
    monkeypatch.setattr(tpm, "_wait_expect", fake_wait)
    monkeypatch.setattr(tpm, "_screenshot_hint", fake_screenshot)

    result = await tpm.phone_macro_tool(_context(), action="play", name="进店")
    assert result.success is False
    assert result.error == "macro_failed"
    assert result.data["failed_step"] == 1
    assert store.get("进店")["fail"] == 1


async def test_play_dry_run_does_not_touch_device(monkeypatch, tmp_path):
    store = pm.MacroStore(tmp_path / "macros.json")
    monkeypatch.setattr(pm, "macro_store", store)
    store.save("看看", "", "", [], [{"op": "tap", "label": "外卖"}])

    result = await tpm.phone_macro_tool(_context(), action="play", name="看看", dry_run=True)
    assert result.success is True
    assert "dry_run" in result.content


async def test_play_missing_param(monkeypatch, tmp_path):
    store = pm.MacroStore(tmp_path / "macros.json")
    monkeypatch.setattr(pm, "macro_store", store)
    store.save("搜", "", "", [{"name": "food"}], [{"op": "input", "text": "{{food}}"}])

    result = await tpm.phone_macro_tool(_context(), action="play", name="搜")
    assert result.error == "missing_params"


async def test_history_and_list_output(tmp_path, monkeypatch):
    history = pm.PhoneHistory(tmp_path / "history.jsonl")
    store = pm.MacroStore(tmp_path / "macros.json")
    monkeypatch.setattr(pm, "phone_history", history)
    monkeypatch.setattr(pm, "macro_store", store)
    history.record("c1", {"op": "tap", "label": "搜索"}, _tree(), _tree())

    listed = await tpm.phone_macro_tool(_context(), action="history")
    assert "#1" in listed.content and "tap" in listed.content
    empty = await tpm.phone_macro_tool(_context(), action="list")
    assert empty.success is True and "还没有保存" in empty.content
