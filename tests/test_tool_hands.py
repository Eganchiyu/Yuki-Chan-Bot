"""亲手操作类工具（bash / 手机 ADB）与工具历史折叠的单元测试。"""
import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from core.tool_prune import STUB_PREFIX, ToolHistoryPruner
from core.toolchain import ToolContext, ToolRuntime
from core.tools import TOOL_HANDLERS, TOOL_SPECS
from core.tools.tools_bash import bash_tool
from core.tools.tools_phone import _annotate_screenshot, _compact_tree, _format_tree, phone_action_tool

SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node class="android.widget.FrameLayout" package="com.sankuai.meituan" bounds="[0,0][1080,2400]"
        clickable="false" text="" content-desc="">
    <node class="android.widget.TextView" bounds="[420,400][660,470]" clickable="false" text="外卖" content-desc="">
      <node class="android.widget.TextView" bounds="[430,410][650,460]" clickable="false" text="外卖" content-desc=""/>
    </node>
    <node class="android.widget.EditText" bounds="[100,180][980,260]" clickable="true"
          text="搜索商家" content-desc=""/>
    <node class="android.widget.ImageView" bounds="[900,2180][1020,2300]" clickable="true"
          text="" content-desc="购物车"/>
    <node class="android.view.View" bounds="[0,0][1080,2400]" clickable="true" text="" content-desc=""/>
    <node class="android.widget.TextView" bounds="[0,300][1080,360]" clickable="false"
          text="隐藏节点" content-desc="" visible-to-user="false"/>
  </node>
</hierarchy>"""


def _context(mode="group"):
    runtime = ToolRuntime(
        sender=None, yuki_state=SimpleNamespace(), image_store=None
    )
    return ToolContext(
        chat_id="c1", mode=mode, session=[], combined_text="", runtime=runtime, metadata={}
    )


# ---------- 注册表 ----------

def test_hands_on_tools_registered():
    names = {spec.name for spec in TOOL_SPECS}
    assert {"bash", "phone_action"} <= names
    assert "bash" in TOOL_HANDLERS and "phone_action" in TOOL_HANDLERS


def test_phone_schema_has_action_enum():
    spec = next(s for s in TOOL_SPECS if s.name == "phone_action")
    assert "inspect" in spec.parameters["properties"]["action"]["enum"]


# ---------- bash ----------

async def test_bash_runs_command():
    result = await bash_tool(_context(), "echo hello-hands")
    assert result.success is True
    assert "hello-hands" in result.content
    assert result.data["no_persist"] is False


async def test_bash_remember_false_marks_no_persist():
    result = await bash_tool(_context(), "echo temp", remember=False)
    assert result.data["no_persist"] is True


async def test_bash_rejects_destructive_command():
    result = await bash_tool(_context(), "rm -rf /")
    assert result.success is False
    assert result.error == "command_rejected"


async def test_bash_rejects_credential_read():
    result = await bash_tool(_context(), "cat ~/.dsh/.credentials.yaml")
    assert result.success is False
    assert result.error == "command_rejected"


async def test_bash_redacts_secret_output():
    result = await bash_tool(_context(), "echo sk-abcdef1234567890ab")
    assert "sk-abcdef1234567890ab" not in result.content
    assert "sk-***" in result.content


async def test_bash_timeout_kills_command():
    result = await bash_tool(_context(), "sleep 5", timeout=1)
    assert result.success is False
    assert result.error == "timeout"


async def test_bash_missing_command():
    result = await bash_tool(_context(), "   ")
    assert result.error == "missing_command"


# ---------- 控件树 ----------

def test_compact_tree_numbers_nodes_and_dedupes():
    tree = _compact_tree(SAMPLE_XML, max_nodes=60)
    assert tree["package"] == "com.sankuai.meituan"
    assert tree["size"] == (1080, 2400)
    labels = [node["label"] for node in tree["nodes"]]
    # 同文案的子节点被父节点吸收，隐藏节点不出现
    assert labels.count("外卖") == 1
    assert "隐藏节点" not in labels
    assert [node["index"] for node in tree["nodes"]] == list(range(1, len(tree["nodes"]) + 1))
    # 编号带中心坐标，模型可以直接 target=编号
    first = tree["nodes"][0]
    assert (first["cx"], first["cy"]) == (540, 435)


def test_compact_tree_respects_max_nodes():
    tree = _compact_tree(SAMPLE_XML, max_nodes=2)
    assert len(tree["nodes"]) == 2


def test_format_tree_contains_index_and_coords():
    text = _format_tree(_compact_tree(SAMPLE_XML, 60))
    assert "[#1]" in text and "@(" in text and "com.sankuai.meituan" in text


def test_annotate_screenshot_draws_and_shrinks():
    buf = io.BytesIO()
    Image.new("RGB", (1080, 2400), (20, 20, 30)).save(buf, "PNG")
    jpeg = _annotate_screenshot(buf.getvalue(), _compact_tree(SAMPLE_XML, 60))
    assert jpeg and jpeg.startswith(b"\xff\xd8")
    image = Image.open(io.BytesIO(jpeg))
    assert image.width <= 720


async def test_phone_reports_missing_adb(monkeypatch):
    async def _boom(*args, **kwargs):
        raise FileNotFoundError("adb")

    monkeypatch.setattr("core.tools.tools_phone._adb", _boom)
    result = await phone_action_tool(_context(), action="inspect")
    assert result.success is False
    assert result.error == "device_unavailable"
    assert "adb" in result.content


# ---------- 历史折叠 ----------

class _FakeHistory:
    def __init__(self, session):
        self.session = session

    def get_session(self, chat_id):
        return json.loads(json.dumps(self.session))

    def replace_session(self, chat_id, session):
        self.session = json.loads(json.dumps(session))
        return self.session


def _tool_message():
    return {
        "role": "tool",
        "name": "phone_action",
        "tool_call_id": "call_1",
        "content": json.dumps({
            "success": True,
            "content": "[#1] 很长的控件树" * 100,
            "data": {"action": "tap", "steps": ["tap #1(外卖)"], "note": "已打开外卖页"},
            "error": "",
        }, ensure_ascii=False),
    }


def test_pruner_folds_after_idle_turns():
    history = _FakeHistory([{"role": "user", "content": "看一下手机"}, _tool_message()])
    pruner = ToolHistoryPruner(history, idle_turns=2)

    assert pruner.after_turn("c1", True) == 0
    assert pruner.after_turn("c1", False) == 0  # 第 1 轮没工具：还留着
    assert pruner.after_turn("c1", False) == 1  # 第 2 轮没工具：折叠

    content = history.session[1]["content"]
    assert content.startswith(STUB_PREFIX)
    assert "已打开外卖页" in content
    assert len(content) < 260
    assert history.session[1].get("pruned") is True


def test_pruner_keeps_history_while_tools_running():
    history = _FakeHistory([_tool_message()])
    pruner = ToolHistoryPruner(history, idle_turns=2)
    for _ in range(5):
        assert pruner.after_turn("c1", True) == 0
    assert not history.session[0].get("pruned")


def test_pruner_skips_other_roles():
    history = _FakeHistory([{"role": "user", "content": "hi"}])
    pruner = ToolHistoryPruner(history, idle_turns=1)
    assert pruner.prune("c1") == 0
    assert history.session[0]["content"] == "hi"


# ---------- 文字输入 ----------

async def test_input_text_ascii_uses_input_command(monkeypatch):
    from core.tools import tools_phone

    calls = []

    async def fake_adb(args, timeout=20.0):
        calls.append(args)
        return 0, b""

    monkeypatch.setattr(tools_phone, "_adb", fake_adb)
    ok, method = await tools_phone._input_text("hello world")
    assert ok and method == "input text"
    assert calls == [["shell", "input", "text", "hello%sworld"]]


async def test_input_text_percent_s_avoids_space_corruption(monkeypatch):
    """含 %s 的 ASCII 文本不走 input text（防止被 Android 当成空格），转走广播/剪贴板。"""
    from core.phone_driver import driver
    from core.tools import tools_phone

    calls = []

    async def fake_adb(args, timeout=20.0):
        calls.append(args)
        return 0, b""

    async def fake_adb_text(args, timeout=20.0):
        calls.append(args)
        return "Broadcast completed: result=0"

    monkeypatch.setattr(tools_phone, "_adb", fake_adb)
    monkeypatch.setattr(tools_phone, "_adb_text", fake_adb_text)
    monkeypatch.setattr(driver, "_has_adb_keyboard", True)
    ok, method = await tools_phone._input_text("100%s sure")
    assert ok and "ADBKeyboard" in method
    assert not any(args[:3] == ["shell", "input", "text"] for args in calls)


async def test_input_text_skips_adbkeyboard_when_precheck_false(monkeypatch):
    """预检确认未安装 ADBKeyboard 时，直接跳过广播分支走剪贴板粘贴。"""
    from core.phone_driver import driver
    from core.tools import tools_phone

    calls = []

    async def fake_adb(args, timeout=20.0):
        calls.append(args)
        return 0, b""

    monkeypatch.setattr(tools_phone, "_adb", fake_adb)
    monkeypatch.setattr(driver, "_has_adb_keyboard", False)
    ok, method = await tools_phone._input_text("中文测试")
    assert ok and "剪贴板" in method
    flat = [" ".join(args) for args in calls]
    assert not any("ime enable" in c for c in flat)
    assert any("clipboard set-text" in c for c in flat)


def test_compact_tree_keeps_fullscreen_scrollable_and_smaller_overlap():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <hierarchy rotation="0">
      <node class="android.widget.FrameLayout" package="com.autonavi.minimap" bounds="[0,0][1080,2400]">
        <node class="android.webkit.WebView" bounds="[0,0][1080,2400]" scrollable="true" clickable="false" text="" content-desc=""/>
        <node class="android.widget.FrameLayout" bounds="[100,100][500,500]" clickable="true" text="" content-desc=""/>
        <node class="android.widget.ImageButton" resource-id="com.app:id/inner_btn" bounds="[200,200][400,400]" clickable="true" text="" content-desc=""/>
      </node>
    </hierarchy>"""
    tree = _compact_tree(xml, max_nodes=60)
    kinds = [n["kind"] for n in tree["nodes"]]
    assert "滚动" in kinds
    # 中心都在 (300, 300) 的两个无文字可点节点，保留面积更小的 ImageButton
    click_nodes = [n for n in tree["nodes"] if n["kind"] == "可点"]
    assert len(click_nodes) == 1
    assert click_nodes[0]["cls"] == "android.widget.ImageButton"
    assert click_nodes[0]["id"] == "com.app:id/inner_btn"


def test_compact_tree_smart_truncation_prioritizes_interactive_nodes():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <hierarchy rotation="0">
      <node class="android.widget.FrameLayout" package="com.app" bounds="[0,0][1080,2400]">
        <node class="android.view.View" bounds="[10,10][100,100]" clickable="true" text="" content-desc=""/>
        <node class="android.view.View" bounds="[10,120][100,200]" clickable="true" text="" content-desc=""/>
        <node class="android.widget.TextView" bounds="[10,2200][300,2350]" clickable="true" text="底部导航" content-desc=""/>
        <node class="android.widget.EditText" bounds="[10,500][800,600]" clickable="true" text="输入框" content-desc=""/>
      </node>
    </hierarchy>"""
    tree = _compact_tree(xml, max_nodes=2)
    labels = [n["label"] for n in tree["nodes"]]
    # 智能截断不会盲目 break 丢掉底部的输入框和带文字按钮，且截断后按从上到下排序
    assert labels == ["输入框", "底部导航"]


async def test_driver_timeout_heals_after_two_consecutive_failures(monkeypatch):
    import asyncio
    from core.phone_driver import AndroidDriver

    drv = AndroidDriver()
    restarted = []

    async def fake_restart():
        restarted.append(True)

    class _HungProc:
        returncode = None
        def kill(self):
            pass
        async def wait(self):
            pass
        async def communicate(self):
            await asyncio.sleep(10)

    async def fake_exec(*args, **kwargs):
        return _HungProc()

    monkeypatch.setattr(drv, "_restart_adb_server", fake_restart)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    with pytest.raises(TimeoutError):
        await drv.adb(["devices"], timeout=0.01)
    assert len(restarted) == 0

    with pytest.raises(TimeoutError):
        await drv.adb(["devices"], timeout=0.01)
    assert len(restarted) == 1


async def test_scroll_to_find_stops_when_found(monkeypatch):
    from core.tools import tools_phone as tp

    page1 = _compact_tree(SAMPLE_XML, 60)
    page2 = _compact_tree(SAMPLE_XML.replace("外卖", "目标店铺"), 60)
    dumps = [page1, page1, page2]

    async def fake_ensure():
        return "device"

    async def fake_dump(max_nodes):
        return dumps.pop(0) if dumps else page2

    async def fake_adb(args, timeout=20.0):
        return 0, b""

    monkeypatch.setattr(tp, "_ensure_device", fake_ensure)
    monkeypatch.setattr(tp, "_dump_tree", fake_dump)
    monkeypatch.setattr(tp, "_adb", fake_adb)

    res = await phone_action_tool(_context(), action="scroll_to_find", text="目标店铺", remember=False)
    assert res.success is True
    assert "找到" in res.content and "目标店铺" in res.content


async def test_input_text_chinese_switches_ime_and_restores(monkeypatch):
    from core.tools import tools_phone

    calls = []

    async def fake_adb(args, timeout=20.0):
        calls.append(args)
        return 0, b""

    async def fake_adb_text(args, timeout=20.0):
        calls.append(args)
        if args[:2] == ["shell", "am"]:
            return "Broadcasting: Intent { ... }\nBroadcast completed: result=0"
        return ""

    async def fake_current_ime():
        return "com.huawei.ohos.inputmethod/com.android.inputmethod.latin.LatinIME"

    monkeypatch.setattr(tools_phone, "_adb", fake_adb)
    monkeypatch.setattr(tools_phone, "_adb_text", fake_adb_text)
    monkeypatch.setattr(tools_phone, "_current_ime", fake_current_ime)

    ok, method = await tools_phone._input_text("电池测试")
    assert ok and "ADBKeyboard" in method

    flat = [" ".join(args) for args in calls]
    assert any("ime enable com.android.adbkeyboard/.AdbIME" in c for c in flat)
    assert any("ime set com.android.adbkeyboard/.AdbIME" in c for c in flat)
    # 用完后必须还原成用户原本的输入法
    assert any("ime set com.huawei.ohos.inputmethod" in c for c in flat)
    assert not any("input text" in c for c in flat)
