# -*- coding: utf-8 -*-
r"""R518 钉②（2026-09-29，执行层）：反证刀 —— 甲案读必须**当场**拒绝被伪造。

派工词点名的三把，逐枚在这里落码（强度只升不降，🔴 既有断言一枚没改弱）：

* **刀一（无腿轮伪造成有腿，改的都是账里今天就有的键）**
  ``d1a`` 改 sidecar 的 ``tool_calls``、``d1c`` 往帧账 ``events`` 里塞一枚 ``step``、
  ``d2a`` 直接改汇总格 ``max_stream_frames``。三枚都必须让 ``assert_matches_r506_triage`` 当场红，
  且伪造者**一枚绿都买不到**：那几行只会从 ``not_applicable`` 掉进「派生不出」，不会进甲案分母。
* **刀二（``not_applicable`` 那一格整块抹成绿）**
  ``d2b`` 连逐帧列一起改（改证据，不是改口径 —— 本件离线证不了账没被人重造，但分诊必对不上）；
  ``d2c`` 直接把落码里那道「NA 归 NA」的闸摸掉（＝有人改代码把不适用折进过），
  分母从 93 涨到 102、红从 2 涨到 11，钉当场红。
* **刀三（②原文合格线从 ``>1`` 手改宽成 ``>=1``）**
  ``d3`` 拿 monkeypatch 摸 ``audit.event_count_gt_1``：读 1 那枚 94/105 立刻变 103/105、钉当场红；
  同时钉住「甲案读的分母不跟合格线走」——改宽合格线也买不到甲案读的绿。
  ``d3b`` 再从源码钉一遍合格线本体今天就是 ``> 1``。

另附本单自己的两枚假零防线：``d4`` 「派生不出」不许折成 ``False``/``0``/``None``；
``d5``/``d6`` 在册账在整轮反证里 sha256 逐字不变（改的全是 ``tmp_path`` 上的副本）。
"""

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

_SPEC = importlib.util.spec_from_file_location(
    "r518_a2_lane_attribution_nails",
    REPO_ROOT / "tests" / "test_r518_a2_lane_attribution.py")
nails = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(nails)

reader = nails.reader
assert_matches_r506_triage = nails.assert_matches_r506_triage
not_applicable_ids = nails.not_applicable_ids

FRAMES9 = REPO_ROOT / "docs" / "testing" / "sidecar-run9-frames.jsonl"
SIDECAR9 = REPO_ROOT / "docs" / "testing" / "sidecar-run9.jsonl"
ANSWERS9 = REPO_ROOT / "docs" / "testing" / "answers-run9.jsonl"
FRAMES9_SHA = "016e9525121c2c6af41da52c199ef843a1425fe853664324137440599823ec18"

#: r506 §4 堆一 8 枚 + 天然短 1 枚 —— 刀一、刀二的靶子。
ALL_PILE = nails.R506_PILE_ONE | nails.R506_NATURAL_SHORT


def _rewrite(source, target, row_ids, mutator):
    """把一本在册账的**副本**里指定题号那几行按 ``mutator`` 改掉；在册原件一枚字节不动。"""
    kept = []
    touched = 0
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if str(row.get("id")) in row_ids:
            row = mutator(row)
            touched += 1
        kept.append(json.dumps(row, ensure_ascii=False))
    assert touched == len(row_ids), (str(source), touched, sorted(row_ids))
    target.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return target


@pytest.fixture()
def ledgers(tmp_path):
    """三本在册账的临时副本（默认一字未改），供各把刀按需篡改。"""
    return {"frames": _rewrite(FRAMES9, tmp_path / "frames.jsonl", set(), lambda row: row),
            "sidecar": _rewrite(SIDECAR9, tmp_path / "sidecar.jsonl", set(), lambda row: row),
            "answers": _rewrite(ANSWERS9, tmp_path / "answers.jsonl", set(), lambda row: row)}


def run(ledgers):
    return reader.attribute(ledgers["frames"], ledgers["sidecar"], ledgers["answers"])


def row_of(result, row_id):
    return nails.bucket_of(result, row_id)


def na_total(result):
    return result["plan_a_read"]["buckets"]["not_applicable"]["total"]


# ------------------------------------------------------------------ 基线
def test_d0_the_untouched_copies_reproduce_the_triage_too(ledgers):
    """副本本身不引入漂移：一字未改的三本副本仍然逐枚复现 r506 §4。"""
    result = run(ledgers)
    assert_matches_r506_triage(result)
    assert result["inputs"]["rows"] == 105
    assert not_applicable_ids(result) == sorted(ALL_PILE)


# ------------------------------------------------------------------ 刀一
def test_d1a_forging_sidecar_tool_calls_on_a_no_leg_round_turns_the_nail_red(ledgers):
    """刀一（改 sidecar 既有键 ``tool_calls`` 0→2）：``doc-07`` 掉出 not_applicable ⇒ 甲案读当场红。"""
    _rewrite(SIDECAR9, ledgers["sidecar"], {"doc-07"}, lambda row: dict(row, tool_calls=2))
    result = run(ledgers)

    item = row_of(result, "doc-07")
    assert item["bucket"] == reader.BUCKET_UNDECIDABLE, item
    assert item["reason"] == reader.REASON_DROP_OR_ZERO_PIECE, item
    assert item["id"] not in result["plan_a_read"]["buckets"]["in_scope_has_leg"]
    assert item["criterion_two_literal"] is False, "🔴 伪造只买到「派生不出」，一枚绿都没买到"
    assert na_total(result) == 8, "少了一枚 not_applicable，那一格就不再是 r506 §4 那一格"
    with pytest.raises(AssertionError, match="题号复现不上|堆一"):
        assert_matches_r506_triage(result)


def test_d1c_forging_a_step_event_into_the_frame_ledger_turns_the_nail_red(ledgers):
    """刀一的分身（往帧账 ``events`` 里塞一枚 ``step``）：另一枚证词同样不许单独撑起「无腿」。"""
    def stuff(row):
        events = list(row.get("events") or [])
        events.append({"stream": 0, "at": 0, "event": "step", "class": "note"})
        return dict(row, events=events)

    _rewrite(FRAMES9, ledgers["frames"], {"chat-09"}, stuff)
    result = run(ledgers)

    item = row_of(result, "chat-09")
    assert item["bucket"] == reader.BUCKET_UNDECIDABLE, item
    assert item["reason"] == reader.REASON_DROP_OR_ZERO_PIECE, item
    assert item["criterion_two_literal"] is False
    with pytest.raises(AssertionError, match="题号复现不上|堆一"):
        assert_matches_r506_triage(result)


# ------------------------------------------------------------------ 刀二
def test_d2a_summary_cell_forgery_is_caught_by_the_frame_column(ledgers):
    """刀二前奏（只改汇总格）：逐帧列对质拦下 —— 甲案分母一枚不许涨，九枚全落「派生不出」。"""
    def forge(row):
        # 把「无腿」伪成「有一条流攒了 3 枚帧」，逐帧列一个字都没敢改（他改不起）。
        return dict(row, max_stream_frames=3, per_stream=[{"frames": 3, "breaks": 0}])

    _rewrite(FRAMES9, ledgers["frames"], ALL_PILE, forge)
    result = run(ledgers)

    plan = result["plan_a_read"]
    assert sorted(plan["witness_conflict"]["ids"]) == sorted(ALL_PILE), plan["witness_conflict"]
    assert plan["denominator"] == 93, "一枚对不上账的汇总格不许把分母撑宽"
    assert na_total(result) == 0
    assert sorted(plan["buckets"]["undecidable"]["ids"]) == sorted(ALL_PILE)
    for row_id in sorted(ALL_PILE):
        item = row_of(result, row_id)
        assert item["bucket"] == reader.BUCKET_UNDECIDABLE, item
        assert item["reason"] == reader.REASON_WITNESS_CONFLICT, item
    with pytest.raises(AssertionError, match="not_applicable 那一格"):
        assert_matches_r506_triage(result)


def test_d2b_forging_the_frame_column_too_still_breaks_the_triage(ledgers):
    """刀二（同一格整块抹绿·连 ``frames`` 一起伪造）：本件离线证不了账没被重造，但**钉必红**。

    照实写自己的边界：逐帧列也在账上，改它就不是改口径而是改证据。本件的防线是「两列必须自洽」
    加 sha256 把账钉死在纸面上（``d6``）；「账被人整本重造」不在一枚离线只读件的能力内，
    这条边界写进读数件，不假称已封。
    """
    def forge(row):
        records = list(row.get("frames") or [])
        base = records[0] if records else {"stream": 0, "chars": 0}
        extra = [dict(base, at=100 + at, chars=int(base.get("chars") or 0) + at)
                 for at in (1, 2, 3)]
        return dict(row, text_frames=4, max_stream_frames=4, streams=1,
                    per_stream=[{"frames": 4, "breaks": 0}],
                    frames=records + extra, criterion_two_holds=True)

    _rewrite(FRAMES9, ledgers["frames"], ALL_PILE, forge)
    result = run(ledgers)

    plan = result["plan_a_read"]
    assert plan["witness_conflict"]["ids"] == [], "两列被一起改自洽了，对质这一道拦不住（本件的边界）"
    assert plan["denominator"] == 102, "分母确实涨了：这就是改证据的代价"
    assert na_total(result) == 0
    with pytest.raises(AssertionError, match="②原文全分母读漂了"):
        assert_matches_r506_triage(result)
    assert result["literal_read"]["green"] != 94, result["literal_read"]["green"]


def test_d2c_folding_the_na_cell_into_green_via_code_breaks_every_count(ledgers, monkeypatch):
    """刀二本体（有人改落码，把 ``not_applicable`` 折进「过」那一堆）：绿与红与分母三处同时报乱。"""
    honest = reader._bucket_of

    def tampered(row, lane, judged, min_chars):
        bucket = honest(row, lane, judged, min_chars)
        return reader.BUCKET_IN_SCOPE if bucket == reader.BUCKET_NOT_APPLICABLE else bucket

    monkeypatch.setattr(reader, "_bucket_of", tampered)
    result = run(ledgers)
    monkeypatch.setattr(reader, "_bucket_of", honest)

    plan = result["plan_a_read"]
    assert na_total(result) == 0, "格子被抹平了"
    assert set(na_section_ids(result)) == set()
    assert plan["denominator"] == 102, plan["denominator"]
    assert plan["green_strict"] == 91, "抹格一枚绿也没多买：那 9 行在②原文上本来就红"
    assert len(plan["red_strict"]) == 11, plan["red_strict"]
    assert set(ALL_PILE) <= set(plan["red_strict"]), plan["red_strict"]
    assert "report-02" in plan["red_strict"] and "tool-04" in plan["red_strict"]
    with pytest.raises(AssertionError):
        assert_matches_r506_triage(result)
    # 摘掉闸之后，那 9 枚不会安静地变成「不适用＝过」：它们带着②原文的红挤进分母。
    for row_id in sorted(ALL_PILE):
        item = row_of(result, row_id)
        assert item["criterion_two_literal"] is False, row_id
        assert row_id in plan["red_strict"], row_id


def na_section_ids(result):
    return result["plan_a_read"]["buckets"]["not_applicable"]["ids"]


# ------------------------------------------------------------------ 刀三
def test_d3_loosening_the_pass_line_from_gt1_to_ge1_turns_read_one_red(ledgers, monkeypatch):
    """刀三（合格线 ``>1`` 改宽成 ``>=1``）：94/105 立刻变 103/105，甲案分母却纹丝不动。"""
    original = reader.audit.event_count_gt_1
    monkeypatch.setattr(reader.audit, "event_count_gt_1",
                        lambda row: int(row["text_frames"]) >= 1)
    try:
        result = run(ledgers)
    finally:
        monkeypatch.setattr(reader.audit, "event_count_gt_1", original)

    # 105 行里 2 枚零帧行永远过不了②-b（无末帧可比），9 枚单帧行被放宽的②-a 放行成绿。
    assert result["literal_read"]["green"] == 94 + 9, result["literal_read"]
    assert result["literal_read"]["red"] == ["metric-02", "scope-02"]
    for row_id in ALL_PILE:
        assert row_of(result, row_id)["criterion_two_literal"] is True, "改宽合格线＝把单帧轮直接判绿"
    assert result["plan_a_read"]["denominator"] == 93, "甲案分母只认腿的证词，不跟合格线走"
    with pytest.raises(AssertionError, match="②原文全分母读漂了"):
        assert_matches_r506_triage(result)


def test_d3b_the_loosened_line_is_not_the_shipped_caliber():
    """钉在册那一枚合格线本体：``audit.event_count_gt_1`` 今天就是 ``> 1``，🔴 不许被顺手改宽。"""
    source = (REPO_ROOT / "scripts" / "r239_stream_gap_offline_audit.py").read_text(encoding="utf-8")
    body = source.split('def event_count_gt_1(row):', 1)[1].split("\ndef ", 1)[0]
    assert 'int(row["text_frames"]) > 1' in body, body
    assert ">= 1" not in body and ">=1" not in body, "合格线被改宽了"


# ------------------------------------------------------------------ 假零防线
def test_d4_undecidable_never_collapses_into_a_boolean_or_a_zero(tmp_path):
    """派生不出那一态必须是字符串 ``"undecidable"``，不许折成 ``False``/``0``/``None``。"""
    row = {"id": "shape-01", "kind": "ok", "text_frames": 1, "max_stream_frames": 1,
           "streams": 1, "per_stream": [{"frames": 1}], "answer_chars": 400,
           "missing_chars": 0, "extra_chars": 0, "last_frame_covers_answer": True,
           "uncorrected_breaks": 0, "criterion_two_holds": False}
    path = tmp_path / "frames.jsonl"
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    result = reader.attribute(path)
    item = row_of(result, "shape-01")

    assert item["lane_state"] == reader.UNDECIDABLE
    assert item["lane_state"] not in (True, False, 0, 1, None)
    assert item["reason"] == reader.REASON_NO_ARRIVAL
    assert item["bucket"] == reader.BUCKET_UNDECIDABLE
    assert result["plan_a_read"]["buckets"]["undecidable"]["literal_red"] == ["shape-01"], (
        "派生不出这一枚在②原文上仍红：它不许因为「量不到」从红账里蒸发")
    assert result["plan_a_read"]["conservation"]["holds"] is True


def test_d5_missing_required_key_is_rejected_not_zero_filled(tmp_path):
    """帧账缺判② 必读键 ⇒ 拒判（``LedgerSchemaError``），🔴 不许补零继续出数（与 r506 钉② 同一条纪律）。"""
    path = tmp_path / "frames.jsonl"
    path.write_text(json.dumps({"id": "x", "text_frames": 3}, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    with pytest.raises(reader.audit.LedgerSchemaError):
        reader.attribute(path)
    assert reader.main(["--frames", str(path)]) == 2, "出不了数就明写取不到，不编数"


def test_d6_the_in_book_ledgers_are_byte_identical_after_all_knives():
    """整轮反证跑完，在册三本账的 sha256 与读数件记下的那枚全值逐字相同（改的都是副本）。"""
    assert reader.audit.sha256_of(FRAMES9) == FRAMES9_SHA
    result = reader.attribute(FRAMES9, SIDECAR9, ANSWERS9)
    assert result["inputs"]["inputs_unchanged"] is True
    assert result["inputs"]["sha256_before"][str(FRAMES9)] == FRAMES9_SHA
    assert reader.audit.sha256_of(FRAMES9) == FRAMES9_SHA
