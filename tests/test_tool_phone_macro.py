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


# ---------- 扩展定位器 (resource-id 5级优先级) ----------

def test_locator_text_and_id_priority():
    tree = _tree(labels=("结算", "结算"))
    tree["nodes"][0]["id"] = "com.app:id/btn_cancel_settle"
    tree["nodes"][1]["id"] = "com.app:id/btn_confirm_settle"
    tree["nodes"][1]["cy"] = 1800
    loc = pm.build_locator(tree["nodes"][1], tree)
    assert loc["id"] == "com.app:id/btn_confirm_settle"
    matched = pm.resolve_locator(tree, loc)
    assert matched and matched[1] == 1800 and matched[3] == "text_id"


def test_locator_id_fallback_when_dynamic_text_changes():
    """购物车角标等动态数字变化时，靠 resource-id + 距离容差命中。"""
    tree = _tree(labels=("外卖", "去结算(1)"))
    tree["nodes"][1]["id"] = "com.app:id/cart_submit"
    loc = pm.build_locator(tree["nodes"][1], tree)

    changed_tree = _tree(labels=("外卖", "去结算(5)"))
    changed_tree["nodes"][1]["id"] = "com.app:id/cart_submit"
    matched = pm.resolve_locator(changed_tree, loc)
    assert matched and matched[2] == "去结算(5)" and matched[3] == "id"


# ---------- Sub-LLM 提炼、弹窗守护与回放自愈 ----------

async def test_save_auto_distill_with_sub_llm(monkeypatch, tmp_path):
    from core import phone_agent

    history = pm.PhoneHistory(tmp_path / "history.jsonl")
    store = pm.MacroStore(tmp_path / "macros.json")
    monkeypatch.setattr(pm, "phone_history", history)
    monkeypatch.setattr(pm, "macro_store", store)

    home, page = _tree(labels=("搜索框", "搜索")), _tree(labels=("黄焖鸡", "店铺"))
    history.record("c1", {"op": "swipe", "from_rel": [0.5, 0.8], "to_rel": [0.5, 0.2]}, home, home)
    history.record("c1", {"op": "input", "label": "搜索框", "text": "黄焖鸡", "loc": pm.build_locator(home["nodes"][0], home)}, home, page)

    async def fake_sub_llm(sys_prompt, user_prompt):
        return """```json
        {
          "desc": "搜索美食",
          "keep_indices": [1],
          "param_defs": [{"name": "food", "desc": "美食名", "default": "黄焖鸡"}],
          "replace": {"黄焖鸡": "{{food}}"}
        }
        ```"""

    monkeypatch.setattr(phone_agent, "call_sub_llm", fake_sub_llm)

    res = await tpm.phone_macro_tool(_context(), action="save", name="搜美食", from_history=5)
    assert res.success is True
    assert "Sub-LLM 已自动提取业务参数" in res.content
    saved = store.get("搜美食")
    assert len(saved["steps"]) == 1
    assert saved["steps"][0]["text"] == "{{food}}"
    assert saved["params"][0]["name"] == "food"


async def test_play_dismisses_overlay_and_heals_step(monkeypatch, tmp_path):
    from core import phone_agent

    store = pm.MacroStore(tmp_path / "macros.json")
    monkeypatch.setattr(pm, "macro_store", store)

    home = _tree(labels=("外卖", "搜索"))
    # 原宏想点「去下单」，但界面先弹了权限框，之后文案改版成了「立即下单」
    old_node = {"label": "去下单", "cls": "android.widget.TextView", "cx": 100, "cy": 500}
    store.save("下单", "测试自愈", "com.sankuai.meituan", [], [{
        "op": "tap",
        "label": "去下单",
        "loc": pm.build_locator(old_node, home),
        "expect": {"package": "com.sankuai.meituan", "labels": ["提交订单"]},
    }])

    overlay_tree = _tree(package="com.android.permissioncontroller", labels=("位置信息权限", "仅在使用中允许"))
    redesigned_tree = _tree(package="com.sankuai.meituan", labels=("外卖", "立即下单"))
    final_tree = _tree(package="com.sankuai.meituan", labels=("提交订单", "支付"))

    dump_queue = [overlay_tree, redesigned_tree]
    tapped_coords = []

    async def fake_ensure():
        return "device"

    async def fake_dump(max_nodes):
        return dump_queue.pop(0) if dump_queue else final_tree

    async def fake_adb(args, timeout=20.0):
        if args[:3] == ["shell", "input", "tap"]:
            tapped_coords.append((int(args[3]), int(args[4])))
        return 0, b""

    async def fake_wait(expect, max_nodes, timeout):
        return True, final_tree

    async def fake_sub_llm(sys_prompt, user_prompt):
        return '{"index": 2, "reason": "去下单改版为立即下单"}'

    monkeypatch.setattr(tpm, "_ensure_device", fake_ensure)
    monkeypatch.setattr(tpm, "_dump_tree", fake_dump)
    monkeypatch.setattr(tp, "_adb", fake_adb)
    monkeypatch.setattr(tpm, "_wait_expect", fake_wait)
    monkeypatch.setattr(phone_agent, "call_sub_llm", fake_sub_llm)

    res = await tpm.phone_macro_tool(_context(), action="play", name="下单")
    assert res.success is True
    assert res.data["healed_steps"] == [1]
    # 宏定位器已自我进化为「立即下单」且 version 自增为 2
    evolved = store.get("下单")
    assert evolved["version"] == 2
    assert evolved["steps"][0]["loc"]["text"] == "立即下单"


# ---------- 手机聚焦模式 (phone_start / phone_finish / 超时退出) ----------

def test_registry_get_tools_switches_between_default_and_phone_focus():
    from core.toolchain import FunctionRegistry

    reg = FunctionRegistry()
    reg.scan_and_register(TOOL_SPECS)

    default_names = {t["function"]["name"] for t in reg.get_tools(phone_focus=False)}
    assert "phone_start" in default_names
    assert "phone_action" not in default_names
    assert "phone_macro" not in default_names
    assert "phone_finish" not in default_names
    assert "search_diary" in default_names

    focus_names = {t["function"]["name"] for t in reg.get_tools(phone_focus=True)}
    assert {"phone_action", "phone_macro", "phone_finish"} <= focus_names
    assert "phone_start" not in focus_names
    assert "search_diary" not in focus_names
    assert "update_notebook" not in focus_names
    assert "skip" in focus_names


async def test_phone_focus_enter_and_finish_overwrites_work_records_preserving_chat(monkeypatch):
    from core.phone_focus import PhoneFocusManager, SUMMARY_PREFIX, phone_finish_tool, phone_start_tool
    import core.phone_focus as pf

    mgr = PhoneFocusManager(max_idle_turns=5)
    monkeypatch.setattr(pf, "phone_focus_manager", mgr)
    monkeypatch.setattr(tp, "phone_focus_manager", mgr)

    async def fake_ensure():
        return "device"

    async def fake_dump(max_nodes):
        return _tree()

    monkeypatch.setattr(tp, "_ensure_device", fake_ensure)
    monkeypatch.setattr(tp, "_dump_tree", fake_dump)
    monkeypatch.setattr(tp, "_screencap", lambda: (_ for _ in ()).throw(RuntimeError("no shot")))

    class _FakeHistory:
        def __init__(self, initial):
            self.session = list(initial)

        def get_session(self, cid):
            return list(self.session)

        def replace_session(self, cid, new_session):
            self.session = list(new_session)
            return self.session

    fake_history = _FakeHistory([
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "阿澄: 帮我点个汉堡"},
        {"role": "assistant", "content": "我拿起手机看看~", "is_tool_thought": True, "phone_focus_work": True},
        {"role": "tool", "name": "phone_start", "content": '{"success":true}', "phone_focus_work": True},
        {"role": "user", "content": "群友B: 顺便看看有没有可乐"},
        {"role": "tool", "name": "phone_action", "content": '{"success":true}', "phone_focus_work": True},
        {"role": "assistant", "content": "好呀，看到可乐了"},
    ])

    ctx = _context()
    ctx.metadata["history_manager"] = fake_history

    start_res = await phone_start_tool(ctx, goal="点汉堡和可乐")
    assert start_res.success is True
    assert mgr.is_focused("c1") is True
    assert "已进入手机聚焦模式" in start_res.content

    finish_res = await phone_finish_tool(ctx, summary="在美团帮阿澄点好了汉堡和可乐")
    assert finish_res.success is True
    assert mgr.is_focused("c1") is False

    # 工作记录被清除，工作期间插入的群友消息和正常回复按序保留，并以 USER 身份注入总结
    roles_and_contents = [(m["role"], m["content"]) for m in fake_history.session]
    assert roles_and_contents == [
        ("system", "sys"),
        ("user", "阿澄: 帮我点个汉堡"),
        ("user", "群友B: 顺便看看有没有可乐"),
        ("assistant", "好呀，看到可乐了"),
        ("user", f"{SUMMARY_PREFIX}在美团帮阿澄点好了汉堡和可乐"),
    ]


def test_phone_focus_auto_exits_after_more_than_five_idle_turns():
    from core.phone_focus import PhoneFocusManager, SUMMARY_PREFIX

    class _FakeHistory:
        def __init__(self):
            self.session = [
                {"role": "user", "content": "帮我看下手机"},
                {"role": "tool", "name": "phone_action", "content": "{}", "phone_focus_work": True},
            ]

        def get_session(self, cid):
            return list(self.session)

        def replace_session(self, cid, new_session):
            self.session = list(new_session)
            return self.session

    history = _FakeHistory()
    mgr = PhoneFocusManager(max_idle_turns=5)
    mgr.enter("c1", goal="查美团订单")
    mgr.record_step("c1", "launch com.sankuai.meituan", "打开美团")

    # 前 5 轮闲置不退出（限制大于 5 轮才退出）
    for _ in range(5):
        assert mgr.after_turn("c1", phone_tools_used=False, history_manager=history) is False
        assert mgr.is_focused("c1") is True

    # 第 6 轮（>5 轮）闲置自动退出并注入 USER 总结
    assert mgr.after_turn("c1", phone_tools_used=False, history_manager=history) is True
    assert mgr.is_focused("c1") is False
    assert all(m.get("role") != "tool" for m in history.session)
    assert history.session[-1]["role"] == "user"
    assert history.session[-1]["content"].startswith(SUMMARY_PREFIX)
    assert "查美团订单" in history.session[-1]["content"]


