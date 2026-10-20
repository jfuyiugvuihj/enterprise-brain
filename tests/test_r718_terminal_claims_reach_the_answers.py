# -*- coding: utf-8 -*-
"""R718 · 终态帧里那两格断言分母必须一路走到答案件。

钉什么（工单 R718 判据\u2462\u2463）：
  \u2460 legacy ``done`` 帧带两枚 claim 走采集器 ⇒ 答案件那一行的 ``claims`` 枚数＝2、逐枚可指认；
  \u2461 只带 ``claims_error`` 稳定码那一枚 ⇒ 分母格仍缺席，但原因码原样落账（「没有分母」与
     「一枚不被支撑的断言都没有」是两句话，混成一格就是把零分母洗成零幻觉）；
  \u2462 什么也没交出的 ``done`` 帧 ⇒ payload 与今天逐字节相同（旧窗那种缺键形状不许被事后补齐）；
  \u2463 队列道：终态载荷里的两格折进取回账 ``terminal`` 那一格，只从那里取；
  \u2464 牙：第四枚键名不许混过具名子集判（反证刀，标 ``counter_evidence``）。

\U0001F534 全程离线：零服务／零模型／零连库。把手一律复用 ``tests/test_r181_text_frame_ruler.py``
   的公共把手 ``build_adapter``（R601 立的规矩：不许再抄一份 adapter 构造）。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, str(REPO / rel))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: R181 那本尺的把手：合成 SSE、脚本化 opener、payload 名单、真 transport。
R181 = _load("r181_harness_for_r718", "tests/test_r181_text_frame_ruler.py")
#: C\u2463 的在册尺：分母在位与否由它判，本件只喂行、不改它。
R704 = _load("r704_for_r718", "scripts/r704_claims_coverage_readout.py")

CLAIM_ONE = {"text": "Q3 营收 1200 万元", "supported": True, "evidence_ids": ["chunk-01"]}
CLAIM_TWO = {"text": "环比增长 8%", "supported": True, "evidence_ids": ["chunk-02", "chunk-03"]}

ANSWER_EVENTS = [("text", {"type": "text", "content": R181.FULL[:8]}),
                 ("text", {"type": "text", "content": R181.FULL})]


def drive_with_done(tmp_path, done_data):
    """真 transport 走一题：正文两帧 + 一帧终态，payload 交回采集器再折成答案行。"""
    module = R181.build_adapter(tmp_path)
    row = R181.fixture_row("doc-01")
    script = {"/api/v1/ask": ANSWER_EVENTS + [("done", done_data)]}
    payload, _opener, sidecar, frames = R181.drive(module, script, row)
    answer = R181.COLLECTOR.build_answer(row, payload, measured_ms=1234.5,
                                         answer_source="r718-under-test")
    return module, payload, sidecar, frames, answer


def test_two_claims_in_the_done_frame_reach_the_answers_line(tmp_path):
    done = {"type": "done", "claims": [CLAIM_ONE, CLAIM_TWO], "claims_error": ""}
    _module, payload, _sidecar, _frames, answer = drive_with_done(tmp_path, done)
    assert payload["claims"] == [CLAIM_ONE, CLAIM_TWO]          # 只搬不改，枚数与顺序都在
    assert answer["claims"] == [CLAIM_ONE, CLAIM_TWO]           # 落进答案件那一行
    assert len(R704.claims_of(answer)) == 2
    for claim in R704.claims_of(answer):                        # 逐枚可指认，不许折成一个数
        assert set(claim) == {"text", "supported", "evidence_ids"}
    tally = R704.tally([answer])
    assert tally["rows_with_claims_key"] == 1 and tally["rows_with_claims_items"] == 1
    assert tally["denominator"] == "MEASURED", tally            # C\u2463 从今天起有分母
    assert "claims_error" not in answer                         # 空原因码不许发键


def test_only_the_error_code_lands_and_the_denominator_stays_absent(tmp_path):
    done = {"type": "done", "claims": [], "claims_error": "claims_denominator_zero"}
    _module, payload, _sidecar, _frames, answer = drive_with_done(tmp_path, done)
    assert "claims" not in payload and "claims" not in answer
    assert payload["claims_error"] == "claims_denominator_zero"
    assert answer["claims_error"] == "claims_denominator_zero"  # 稳定码原样落账
    tally = R704.tally([answer])
    assert tally["denominator"] == "NOT_MEASURED", tally        # 零分母不许被读成零幻觉


def test_a_done_frame_that_carries_nothing_changes_not_a_byte(tmp_path):
    _module, payload, _sidecar, _frames, answer = drive_with_done(tmp_path, {"type": "done"})
    assert set(payload) == R181.PAYLOAD_KEYS                    # 今天那五键，一字节不多
    assert "claims" not in answer and "claims_error" not in answer
    assert R181.COLLECTOR.assert_line_contract(answer) is None  # 契约照旧过


def test_the_queue_leg_folds_claims_out_of_the_terminal_payload(tmp_path):
    module = R181.build_adapter(tmp_path)
    body = {"status": "done", "terminal_schema": "v1", "terminal_state": "answered",
            "answer_present": True, "sources_present": True, "sources": [],
            "claims": [CLAIM_ONE, CLAIM_TWO]}
    readout = module._terminal_readout(body)
    assert readout["claims"] == [CLAIM_ONE, CLAIM_TWO]
    assert module._terminal_claims_cells({"terminal": readout}) == {"claims": [CLAIM_ONE, CLAIM_TWO]}
    empty = module._terminal_readout({"status": "done", "terminal_state": "answered",
                                      "answer_present": True, "sources": []})
    assert "claims" not in empty                               # 交不出就整格缺席
    assert module._terminal_claims_cells({"terminal": empty}) == {}
    assert module._terminal_claims_cells(None) == {}


@pytest.mark.counter_evidence
def test_counter_evidence_a_fourth_key_cannot_slip_past_the_named_subset(tmp_path, monkeypatch):
    """反证刀：把 ``claims_confidence`` 这种第四枚键名放进终态帧，具名子集判必须当场红。"""
    done = {"type": "done", "claims": [CLAIM_ONE], "claims_error": "",
            "claims_confidence": 0.9}
    module, payload, _sidecar, _frames, _answer = drive_with_done(tmp_path, done)
    smuggled = set(payload) - R181.PAYLOAD_KEYS - R181.R718_CARRY_KEYS
    assert smuggled == set()                                   # 真采集器不许替第四枚键名开门
    assert set(payload) <= R181.PAYLOAD_KEYS | R181.R718_CARRY_KEYS
    assert "claims_confidence" not in payload                  # 名单外一枚都进不来
