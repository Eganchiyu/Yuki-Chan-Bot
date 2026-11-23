# tests/test_jargon.py
"""群黑话（Jargon）存储、三步推断与机械匹配单元测试。"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

from modules.memory.jargon_matcher import format_jargon_reference, match_jargons_for_text
from modules.memory.jargon_miner import (
    extract_candidates_from_dialogue,
    infer_jargon_meaning,
    should_infer_jargon,
)
from modules.memory.jargon_store import JargonStore


def test_jargon_store_and_thresholds(tmp_path):
    store = JargonStore(str(tmp_path / "jargon.db"))
    for i in range(3):
        recs = store.record_candidates("10001", [("典中典", f"证据{i}")])
        assert len(recs) == 1
        assert recs[0].count == i + 1
        assert should_infer_jargon(recs[0]) is False

    # 第 4 次命中达到首档阈值 4
    recs = store.record_candidates("10001", [("典中典", "证据3")])
    assert recs[0].count == 4
    assert should_infer_jargon(recs[0]) is True


def test_jargon_three_step_inference_distinguishes_jargon_vs_plain(tmp_path):
    store = JargonStore(str(tmp_path / "jargon.db"))
    for i in range(4):
        store.record_candidates("10001", [("坐牢", f"今天加班写bug真是坐牢 {i}")])
    rec = store.list_jargons()[0]

    # 1) 语境义与字面义不同 -> 判定为真黑话
    responses_jargon = [
        json.dumps({"meaning": "指在工作或游戏中陷入枯燥痛苦的困境", "no_info": False}, ensure_ascii=False),
        json.dumps({"meaning": "被关进监狱服刑"}, ensure_ascii=False),
        json.dumps({"is_similar": False, "reason": "群里指加班痛苦，与监狱字面义不同"}, ensure_ascii=False),
    ]
    with patch("modules.memory.jargon_miner._call_fast_llm", new_callable=AsyncMock, side_effect=responses_jargon):
        is_jargon = asyncio.run(infer_jargon_meaning(rec, store=store))
    assert is_jargon is True

    verified = store.load_verified_jargons("10001")
    assert len(verified) == 1
    assert verified[0].content == "坐牢"

    # 2) 语境义与字面义一致 -> 判定为普通白话，过滤不注入
    for i in range(4):
        store.record_candidates("10001", [("电脑", f"买了个新电脑 {i}")])
    plain_rec = [r for r in store.list_jargons() if r.content == "电脑"][0]
    responses_plain = [
        json.dumps({"meaning": "电子计算机设备", "no_info": False}, ensure_ascii=False),
        json.dumps({"meaning": "电子计算机"}, ensure_ascii=False),
        json.dumps({"is_similar": True, "reason": "完全相同的常见词汇"}, ensure_ascii=False),
    ]
    with patch("modules.memory.jargon_miner._call_fast_llm", new_callable=AsyncMock, side_effect=responses_plain):
        is_plain_jargon = asyncio.run(infer_jargon_meaning(plain_rec, store=store))
    assert is_plain_jargon is False
    assert all(r.content != "电脑" for r in store.load_verified_jargons("10001"))


def test_jargon_extract_only_user_messages_and_match(tmp_path):
    store = JargonStore(str(tmp_path / "jargon.db"))
    dialogue = [
        {"role": "user", "content": "群友A: 今天又爆典了"},
        {"role": "assistant", "content": "哈哈确实"},
        {"role": "user", "content": "群友B: 真的太爆典了"},
        {"role": "user", "content": "群友C: 每日爆典任务完成"},
    ]
    extract_resp = json.dumps([{"content": "爆典", "idx": 0}], ensure_ascii=False)
    with patch("modules.memory.jargon_miner._call_fast_llm", new_callable=AsyncMock, return_value=extract_resp):
        recs = asyncio.run(extract_candidates_from_dialogue("20002", dialogue, store=store))
    assert len(recs) == 1
    assert recs[0].content == "爆典"

    store.update_inference_result("爆典", is_jargon=True, meaning="指某人说出极具代表性的逆天/经典言论", last_inference_count=4)
    matches = match_jargons_for_text("20002", "今天群里怎么又在爆典啊", store=store)
    assert matches == [("爆典", "指某人说出极具代表性的逆天/经典言论")]
    hint = format_jargon_reference(matches)
    assert "爆典" in hint and "群聊黑话/梗参考" in hint
