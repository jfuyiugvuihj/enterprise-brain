# -*- coding: utf-8 -*-
r"""R518 钉①（2026-09-29，执行层）：A② 甲案的「有逐片腿／无逐片腿」必须**机械派生**，
且逐枚复现 ``docs/testing/r506-a2-reading-2026-09-29.md`` §4 那张三堆分诊表。

派工词的判据一枚不落：

1. **逐枚复现 r506 §4**：堆一 8 枚 + 天然短 1 枚 = 9 枚 ``not_applicable`` 并逐枚点名题号；
   ``metric-02``/``scope-02`` 进 ``no_answer`` 格；``chart-01`` 单列（自加格不参红绿）；
   ``tool-04``/``report-02`` 照旧算红；``insight-07``/``chart-04`` 按 R471 不重判。
   ⇒ 下面那枚 ``assert_matches_r506_triage`` 把这一整格钉成**一个**算式，复现不上就点名差在哪一行。
2. **②原文全分母读仍是 94/105**：新增视图不许改动它（``b1``），合格线 ``text_frames > 1`` 也钉着（``b2``）。
3. **只用既有键派生**：``b3`` 钉「本件读到的每一枚键都在在册账里已经存在」，🔴 不许为派生加键。
4. **三态分明**：``c`` 组逐形点名哪一形落 ``undecidable``（无到达坐标 / 无可 join 的 tool_calls /
   腿跑过却只到一枚帧 / 汇总格与逐帧列对质不上），且取值必是**字符串三态**，不许 ``True`` 不许 0。

🔴 本文件只读在册四本账（``docs/testing/*.jsonl``），零写入、零网络、零容器、零模型；
合成账一律落在 ``tmp_path``。
"""

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

_SPEC = importlib.util.spec_from_file_location(
    "r518_a2_lane_attribution", REPO_ROOT / "scripts" / "r518_a2_lane_attribution.py")
reader = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(reader)

#: 在册四本帧账（run9 是 r506 §4 那张表的出处；另三窗是 r506 §3 那三形对照）。
LEDGERS = {
    "run9": "docs/testing/sidecar-run9-frames.jsonl",
    "run7": "docs/testing/sidecar-run7-frames.jsonl",
    "run6": "docs/testing/sidecar-run6-frames.jsonl",
    "run8p2": "docs/testing/sidecar-run8p2-frames.jsonl",
}

_CACHE = {}


def read(run="run9"):
    """把某一窗的三本账（帧账 + sidecar + answers）跑一遍，结果按窗缓存（同一次 pytest 里复用）。"""
    if run not in _CACHE:
        _CACHE[run] = reader.attribute(REPO_ROOT / LEDGERS[run],
                                       REPO_ROOT / ("docs/testing/sidecar-%s.jsonl" % run),
                                       REPO_ROOT / ("docs/testing/answers-%s.jsonl" % run))
    return _CACHE[run]


# ==== r506 §4 那张表的原文（逐枚，不是一段话）====
R506_PILE_ONE = {"doc-07", "chat-03", "chat-06", "chat-09", "chat-10",
                 "metric-16", "approval-06", "scope-01"}
R506_NATURAL_SHORT = {"data-09"}
R506_NO_ANSWER = {"metric-02", "scope-02"}
R506_SELF_ADDED = {"chart-01"}
R506_STILL_RED = {"tool-04", "report-02"}
R506_NOT_REJUDGED = {"insight-07", "chart-04"}
#: run9 当年那两枚在册读数：②原文全分母 94/105、真尺 91/105（r506 §0 表）。
R506_LITERAL = (94, 105)
R506_PLAN_A = {"denominator": 93, "green_strict": 91}


def na_section(result):
    return result["plan_a_read"]["buckets"]["not_applicable"]


def bucket_of(result, row_id):
    for item in result["rows"]:
        if item["id"] == row_id:
            return item
    raise AssertionError("题号 " + row_id + " 在读数里找不到（有行没落格）")


def not_applicable_ids(result):
    """甲案读里 ``not_applicable`` 那一格的题号（这一格不许被折进「过」那一堆）。"""
    return sorted(set(result["plan_a_read"]["buckets"]["not_applicable"]["ids"]))


def assert_matches_r506_triage(result):
    """把 r506 §4 的三堆分诊**整块**对一遍：任何一枚复现不上都点名说差在哪。

    这枚函数是本钉的正文：``a1`` 拿它跑在册 run9，反证刀（见
    ``tests/test_r518_counter_evidence_knives.py``）拿它跑被改过的账 ⇒ 必红。
    """
    plan = result["plan_a_read"]
    na = na_section(result)
    literal = result["literal_read"]

    assert plan["conservation"]["holds"] is True, (
        "五格不守恒：" + json.dumps(plan["conservation"], ensure_ascii=False))
    assert len(plan["buckets"]["in_scope_has_leg"]) == plan["denominator"]
    assert (literal["green"], literal["denominator"]) == R506_LITERAL, (
        "②原文全分母读漂了：本件读到 " + str(literal["green"]) + "/"
        + str(literal["denominator"]) + "，在册 r506 §0 是 " + str(R506_LITERAL))
    assert not_applicable_ids(result) == sorted(R506_PILE_ONE | R506_NATURAL_SHORT), (
        "not_applicable 那一格的题号复现不上：" + ",".join(not_applicable_ids(result)))
    assert set(na[reader.REASON_NO_PIECE_LEG]) == R506_PILE_ONE, (
        "堆一（无逐片腿）复现不上：读到 "
        + ",".join(sorted(na[reader.REASON_NO_PIECE_LEG]))
        + " ｜ r506 §4 是 " + ",".join(sorted(R506_PILE_ONE)))
    assert set(na[reader.REASON_BELOW_SIZE_GATE]) == R506_NATURAL_SHORT, (
        "天然短那一枚复现不上：读到 " + ",".join(sorted(na[reader.REASON_BELOW_SIZE_GATE])))
    assert na["total"] == len(R506_PILE_ONE) + len(R506_NATURAL_SHORT) == 9, (
        "not_applicable 那一格枚数不对：" + str(na["total"]))
    assert set(plan["buckets"]["no_answer"]["ids"]) == R506_NO_ANSWER, (
        "no_answer 格复现不上：" + ",".join(sorted(plan["buckets"]["no_answer"]["ids"])))
    # 反抹格那一枚：两格都不许是空的，也不许被折进绿里（刀二/刀二c 摸的就是这两行）。
    assert na["ids"], "not_applicable 那一格被人抹成空气 ⇒ 9 枚无腿/天然短轮读成已裁绿"
    assert plan["buckets"]["no_answer"]["ids"], (
        "零文本帧那一格整块抹掉＝把两枚真失败读成空气")
    assert not set(na["ids"]) & set(plan["green_strict_ids"]), "not_applicable 不许出现在甲案绿里"
    assert not set(plan["buckets"]["no_answer"]["ids"]) & set(plan["green_strict_ids"]), (
        "no_answer 不许出现在甲案绿里")
    assert (plan["green_strict"] + len(plan["red_strict"]) == plan["denominator"]), (
        "甲案读的算式不闭合：绿 + 红 != 分母")
    assert set(plan["buckets"]["self_added_cell_only"]["ids"]) == R506_SELF_ADDED, (
        "chart-01 那一格复现不上：" + ",".join(sorted(plan["buckets"]["self_added_cell_only"]["ids"])))
    assert set(plan["red_strict"]) == R506_STILL_RED, (
        "「照旧算红」那两枚复现不上：" + ",".join(sorted(plan["red_strict"])))
    assert set(plan["not_rejudged"]["ids"]) == R506_NOT_REJUDGED, (
        "R471 不重判那两枚复现不上：" + ",".join(sorted(plan["not_rejudged"]["ids"])))
    assert plan["denominator"] == R506_PLAN_A["denominator"], (
        "甲案读分母不对：读到 " + str(plan["denominator"]))
    assert plan["green_strict"] == R506_PLAN_A["green_strict"], (
        "甲案读分子不对：读到 " + str(plan["green_strict"]))
    assert plan["buckets"]["undecidable"]["ids"] == [], (
        "run9 这一窗本件应当枚枚可判，读到派生不出："
        + ",".join(plan["buckets"]["undecidable"]["ids"]))
    assert plan["witness_conflict"]["ids"] == [], (
        "在册账的汇总格与逐帧列应当对得上，读到对质不上："
        + ",".join(plan["witness_conflict"]["ids"]))


# ---------------------------------------------------------------- a 组：逐枚复现分诊
def test_a1_run9_reproduces_the_r506_p4_triage_row_by_row():
    """判据 1：三份在册账现跑，必须逐枚复现 r506 §4 那张表（堆一 8 + 天然短 1 + 堆二 2 + 单列 + 两枚红）。"""
    assert_matches_r506_triage(read("run9"))


def test_a2_pile_one_eight_rows_carry_the_no_leg_witness():
    """堆一那 8 枚的证词必须逐枚在纸面上：``tool_calls==0`` ∧ ``events`` 一枚 ``step`` 都没有。"""
    result = read("run9")
    for row_id in sorted(R506_PILE_ONE):
        item = bucket_of(result, row_id)
        assert item["bucket"] == reader.BUCKET_NOT_APPLICABLE, row_id
        assert item["reason"] == reader.REASON_NO_PIECE_LEG, row_id
        assert item["lane_state"] == reader.NO_PIECE_LEG, row_id
        assert item["tool_calls"] == 0, row_id
        joined = " ".join(item["evidence"])
        assert "tool_calls==0" in joined and "step" in joined, (row_id, item["evidence"])
        assert item["criterion_two_literal"] is False, "它今天仍占着②原文那一读的红（读 1 里不许蒸发）"
        assert item["id"] not in result["plan_a_read"]["buckets"]["in_scope_has_leg"], row_id


def test_a3_natural_short_is_its_own_reason_not_a_missing_leg():
    """天然短那一枚的 ``lane_state`` 仍是 ``undecidable``：它说的是「攒不出第二枚帧」，不是「没有腿」。"""
    """``data-09``（15 字 < 尺寸闸 20）不许与「无腿」并脸：它跑过腿，只是结构上攒不出第二片。"""
    result = read("run9")
    item = bucket_of(result, "data-09")
    assert item["reason"] == reader.REASON_BELOW_SIZE_GATE
    assert item["bucket"] == reader.BUCKET_NOT_APPLICABLE
    assert item["lane_state"] == reader.UNDECIDABLE, "腿名派生不出，不许借尺寸闸冒充已证无腿"
    assert item["answer_chars"] == 15
    assert item["answer_chars"] < result["size_gate"]["stream_piece_min_chars"] == 20
    assert item["tool_calls"] == 2, "这一枚的腿跑过工具 —— 它与堆一的病根不是同一件事"
    joined = " ".join(item["evidence"])
    assert "尺寸闸" in joined, item["evidence"]


def test_a4_no_answer_pair_leaves_the_denominator_but_stays_visible():
    """``metric-02``/``scope-02``：离开②分母进 ``no_answer`` 格，且**逐枚点名**（挪而不记＝让真失败变空气）。"""
    result = read("run9")
    plan = result["plan_a_read"]
    assert sorted(plan["buckets"]["no_answer"]["ids"]) == ["metric-02", "scope-02"]
    for row_id in ("metric-02", "scope-02"):
        item = bucket_of(result, row_id)
        assert item["text_frames"] == 0, row_id
        assert item["bucket"] == reader.BUCKET_NO_ANSWER, row_id
        assert item["criterion_two_literal"] is False, "读 1 里它照旧红"
    assert plan["denominator"] == 93, "这两枚不许进甲案分母"
    assert set(plan["buckets"]["no_answer"]["ids"]).isdisjoint(plan["buckets"]["in_scope_has_leg"])


def test_a5_chart01_is_single_listed_and_cannot_declare_red_or_green():
    """``chart-01``：唯一的严读红因是量具自加的 ``max_stream_frames>1`` ⇒ 单列，不参红绿。"""
    result = read("run9")
    plan = result["plan_a_read"]
    item = bucket_of(result, "chart-01")
    assert item["extra_red_conditions"] == [reader.SELF_ADDED_CELL], item["extra_red_conditions"]
    assert item["bucket"] == reader.BUCKET_SELF_ADDED
    assert "chart-01" not in plan["buckets"]["in_scope_has_leg"]
    assert "chart-01" not in plan["red_strict"], "不得据自加格宣布②红"
    assert "chart-01" not in plan["buckets"]["undecidable"]["ids"], "它落单列那一格，不许混进派生不出"


def test_a6_tool04_and_report02_stay_red_after_the_adjudication():
    """``tool-04``/``report-02``：有腿证词在位（各自有一条流逐片累计）⇒ 甲案读里照旧算红。"""
    result = read("run9")
    plan = result["plan_a_read"]
    for row_id in sorted(R506_STILL_RED):
        item = bucket_of(result, row_id)
        assert item["lane_state"] == reader.HAS_PIECE_LEG, row_id
        assert item["bucket"] == reader.BUCKET_IN_SCOPE, row_id
        assert item["criterion_two_holds_archived"] is False, row_id
        assert reader.SELF_ADDED_CELL not in item["extra_red_conditions"], (row_id, item["extra_red_conditions"])
        assert "uncorrected_breaks==0" in item["extra_red_conditions"], (row_id, item["extra_red_conditions"])
    assert sorted(plan["red_strict"]) == ["report-02", "tool-04"]


def test_a7_insight07_and_chart04_are_flagged_not_rejudged():
    """``insight-07``/``chart-04``：账与尺不同代 ⇒ 明记「不重判」，既不追加定罪也不裁绿。"""
    result = read("run9")
    plan = result["plan_a_read"]
    assert sorted(plan["not_rejudged"]["ids"]) == ["chart-04", "insight-07"]
    for row_id in ("insight-07", "chart-04"):
        item = bucket_of(result, row_id)
        assert item["ledger_drift"] is True, row_id
        assert item["criterion_two_holds_archived"] is True, row_id
        assert item["recomputed_ledger"] is False, row_id
        assert row_id not in plan["red_strict"], "不重判＝不许拿现尺复算去追加定罪"


def test_a8_buckets_are_mutually_exclusive_and_conserve_every_row():
    """五格互斥且守恒：105 = 93 + 9 + 2 + 1 + 0，一枚不许丢、一枚不许落两格。"""
    result = read("run9")
    plan = result["plan_a_read"]
    cons = plan["conservation"]
    assert (cons["rows"], cons["in_scope_has_leg"], cons["not_applicable"], cons["no_answer"],
            cons["self_added_cell_only"], cons["undecidable"]) == (105, 93, 9, 2, 1, 0)
    seen = [item["id"] for item in result["rows"]]
    assert len(seen) == len(set(seen)) == 105, "有行重复或掉队"
    allowed = set(reader.ALL_BUCKETS)
    assert {item["bucket"] for item in result["rows"]} <= allowed
    for item in result["rows"]:
        assert item["lane_state"] in reader.LANE_STATES, item
        assert item["reason"] == "" or item["reason"] in reader.ALL_REASONS, item


# ---------------------------------------------------------------- b 组：两读并列与「不加键」
def test_b1_literal_read_is_untouched_by_the_new_view():
    """判据 2：甲案视图是**另加的一格**，②原文全分母那枚数一枚不许漂（94/105）。"""
    result = read("run9")
    rows = [reader.audit.judge_row(row)
            for row in reader.audit.read_rows(REPO_ROOT / LEDGERS["run9"])]
    summary = reader.audit.summarize(rows)
    assert summary["criterion_two_holds_literal"] == 94
    assert result["literal_read"]["green"] == summary["criterion_two_holds_literal"], (
        "本件那枚 94 不是从判器来的 ⇒ 两把尺不同代")
    assert result["literal_read"]["denominator"] == summary["rows"] == 105
    assert sorted(result["literal_read"]["red"]) == sorted(
        R506_PILE_ONE | R506_NATURAL_SHORT | R506_NO_ANSWER)


def test_b2_the_pass_line_is_strictly_greater_than_one():
    """合格线钉死在 ``text_frames > 1``：一枚帧就是红，本件不许把它读宽（反证刀三摸的就是这一行）。"""
    assert reader.audit.event_count_gt_1({"text_frames": 1}) is False
    assert reader.audit.event_count_gt_1({"text_frames": 2}) is True
    assert _literal_read_is_gate_dependent(), "读 1 的绿数与 text_frames==1 的行数必须互相咬住"
    single = [item for item in read("run9")["rows"] if item["text_frames"] == 1]
    assert len(single) == 9, [item["id"] for item in single]
    assert all(item["criterion_two_literal"] is False for item in single)


def _literal_read_is_gate_dependent():
    """``text_frames == 1`` 的行数 + 全绿行 + 零帧行 == 分母 —— 拿账自证，不抄纸上的数。"""
    rows = read("run9")["rows"]
    ones = sum(1 for item in rows if item["text_frames"] == 1)
    zeros = sum(1 for item in rows if item["text_frames"] == 0)
    greens = sum(1 for item in rows if item["criterion_two_literal"])
    return ones == 9 and zeros == 2 and greens == 105 - ones - zeros


def test_b3_no_key_that_is_not_already_in_the_ledgers_is_consumed():
    """判据 3：本件读的每一枚键都在在册账里已经存在 —— 🔴 没有一枚是为了派生新加的。"""
    frames = reader.audit.read_rows(REPO_ROOT / LEDGERS["run9"])
    on_disk = set()
    for row in frames:
        on_disk.update(row.keys())
    sidecar, _ = reader.rows_by_id(REPO_ROOT / "docs/testing/sidecar-run9.jsonl")
    answers, _ = reader.rows_by_id(REPO_ROOT / "docs/testing/answers-run9.jsonl")
    for row in list(sidecar.values()) + list(answers.values()):
        on_disk.update(row.keys())
    needed = set(reader.FRAME_KEYS_USED) | set(reader.SIDECAR_KEYS_USED)
    assert needed - on_disk == set(), "本件要用了账里没有的键：" + ",".join(sorted(needed - on_disk))
    # 帧账那一行的键集自 R215/R471 起就是这些：本件一格都没添。
    assert "worker" not in on_disk and "leg" not in on_disk and "lane" not in on_disk


def test_b4_leg_names_are_not_derivable_and_the_reader_says_so():
    """判据 4：腿名（哪条腿交付的）今天**派生不出**，本件必须明写 0 行可派生，不许含糊。"""
    plan = read("run9")["plan_a_read"]
    assert plan["leg_names"]["derivable_rows"] == 0
    assert plan["leg_names"]["rows"] == 105
    assert "腿名列" in plan["leg_names"]["note"]
    for item in read("run9")["rows"]:
        assert not any(key.startswith("worker") or key == "leg" for key in item["keys_used"]), item


def test_b5_reading_the_ledgers_writes_nothing():
    """三本在册账读完 sha256 逐枚不变（只读取证件的自证）。"""
    result = read("run9")
    inputs = result["inputs"]
    assert inputs["inputs_unchanged"] is True
    assert inputs["sha256_before"] == inputs["sha256_after"]
    assert inputs["sha256_before"][str(REPO_ROOT / LEDGERS["run9"])].startswith("016e9525")


def test_b6_main_exits_zero_on_all_four_in_book_ledgers():
    """四扇窗都能出数且退出码 0（含守恒与未改动两道自证）。"""
    for run, frames in LEDGERS.items():
        code = reader.main(["--frames", str(REPO_ROOT / frames),
                            "--sidecar", str(REPO_ROOT / ("docs/testing/sidecar-%s.jsonl" % run)),
                            "--answers", str(REPO_ROOT / ("docs/testing/answers-%s.jsonl" % run))])
        assert code == 0, run


# ---------------------------------------------------------------- c 组：三态与另外三扇窗
def test_c1_run7_has_no_arrival_coordinates_so_no_leg_cannot_be_derived():
    """run7（R223 之前的账）：``events`` 列根本不存在 ⇒ 那同名九枚只能交「派生不出」，🔴 不许交 not_applicable。"""
    result = read("run7")
    plan = result["plan_a_read"]
    assert plan["buckets"]["not_applicable"]["total"] == 0
    und = plan["buckets"]["undecidable"]
    assert set(und["ids"]) == {"approval-06", "chat-03", "chat-06", "chat-09", "chat-10",
                              "data-09", "doc-07", "metric-17", "scope-01"}, und["ids"]
    assert all(bucket_of(result, row_id)["reason"] == reader.REASON_NO_ARRIVAL
               for row_id in und["ids"])
    assert set(und["literal_red"]) == set(und["ids"]), "②原文红的行不许因为「派生不出」就被裁绿"
    assert plan["conservation"]["holds"] is True


def test_c2_run8p2_queue_window_is_not_applicable_whole_window():
    """run8p2 整窗走队列道：``queue`` 格非空 / ``kind`` 以 queued 起 ⇒ 20/20 not_applicable（无腿）。"""
    result = read("run8p2")
    plan = result["plan_a_read"]
    na = na_section(result)
    assert len(na[reader.REASON_QUEUE_PATH]) == 20
    assert plan["denominator"] == 0
    assert plan["buckets"]["no_answer"]["ids"] == []
    assert result["literal_read"]["green"] == 0
    assert plan["conservation"]["holds"] is True


def test_c3_run6_window_has_no_positive_witness_at_all():
    """run6（逐片腿还没接上那一窗）：``max_stream_frames > 1`` 零枚 ⇒ 甲案分母 0，85 枚落派生不出。"""
    result = read("run6")
    plan = result["plan_a_read"]
    assert plan["buckets"]["in_scope_has_leg"] == []
    assert plan["conservation"]["undecidable"] == 85
    assert plan["conservation"]["self_added_cell_only"] == 19
    assert plan["conservation"]["no_answer"] == 1
    assert result["literal_read"]["green"] == 19
    assert plan["conservation"]["holds"] is True


def test_c4_no_witness_never_becomes_a_boolean_or_a_zero():
    """三态取值必须是字符串：``undecidable`` 不许折成 ``True``/``0``（R507/R515 刚治过的那族假零病）。"""
    row = {"id": "x", "kind": "ok", "text_frames": 1, "max_stream_frames": 1, "streams": 1,
           "per_stream": [{"frames": 1}], "answer_chars": 400,
           "events": [{"event": "status"}, {"event": "text"}]}
    lane = reader.derive_lane_state(row, None, 20)
    assert lane["lane_state"] == reader.UNDECIDABLE
    assert lane["lane_state"] is not True and lane["lane_state"] is not False
    assert lane["reason"] == reader.REASON_NO_TOOL_CALLS
    assert str(lane["lane_state"]) in reader.LANE_STATES


def test_c5_forged_summary_cell_without_frames_trips_the_cross_check(tmp_path):
    """有腿证词必须过对质：只把 ``max_stream_frames`` 改成 5、逐帧列不动 ⇒ 落 ``witness_conflict``。"""
    row = {"id": "forge-01", "kind": "ok", "text_frames": 1, "max_stream_frames": 5, "streams": 1,
           "per_stream": [{"frames": 5}], "answer_chars": 400,
           "frames": [{"stream": 0, "at": 1, "chars": 400, "sha": "aaaa"}],
           "missing_chars": 0, "extra_chars": 0, "last_frame_covers_answer": True,
           "uncorrected_breaks": 0, "criterion_two_holds": True}
    lane = reader.derive_lane_state(row, 2, 20)
    assert lane["lane_state"] == reader.UNDECIDABLE, lane
    assert lane["reason"] == reader.REASON_WITNESS_CONFLICT, lane
    conflict = reader.witness_conflict(row)
    assert conflict and "max_stream_frames" in conflict, conflict


def test_c6_consistent_frames_column_is_what_buys_the_has_leg_witness(tmp_path):
    """逐帧列与汇总格对得上，正面证词才成立 —— 对质不是摆设。"""
    row = {"id": "ok-01", "kind": "ok", "text_frames": 4, "max_stream_frames": 4, "streams": 1,
           "per_stream": [{"frames": 4}], "answer_chars": 400,
           "frames": [{"stream": 0, "at": at, "chars": 100 * at, "sha": "s%d" % at}
                      for at in (1, 2, 3, 4)],
           "missing_chars": 0, "extra_chars": 0, "last_frame_covers_answer": True,
           "uncorrected_breaks": 0, "criterion_two_holds": True}
    assert reader.witness_conflict(row) is None
    assert reader.derive_lane_state(row, 2, 20)["lane_state"] == reader.HAS_PIECE_LEG


def test_c7_size_gate_comes_from_the_source_not_from_a_hand_copy():
    """尺寸闸的数值从 ``app/agents/nodes.py`` 现取；真源改了本件跟着改，取不到就拒判。"""
    assert reader.piece_size_gate() == 20
    missing = reader.REPO_ROOT / "docs" / "testing" / "no-such-file-here.py"
    with pytest.raises(reader.SizeGateError):
        reader.piece_size_gate(missing)


def test_c8_rows_without_tool_calls_join_degrade_to_undecidable(tmp_path):
    """把 sidecar/answers 摘掉：那 8 枚「无腿」立刻降级成派生不出 —— 证词缺一枚就不许断言。"""
    frames = reader.audit.read_rows(REPO_ROOT / LEDGERS["run9"])
    path = tmp_path / "frames.jsonl"
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in frames) + "\n",
                    encoding="utf-8")
    result = reader.attribute(path)
    na = na_section(result)
    assert na["total"] == 0, "无腿与天然短两格都缺一枚 tool_calls ⇒ 一枚都不许断言"
    assert na[reader.REASON_NO_PIECE_LEG] == []
    und = result["plan_a_read"]["buckets"]["undecidable"]
    assert len(und["ids"]) == 9, und["ids"]
    assert set(und["ids"]) == R506_PILE_ONE | R506_NATURAL_SHORT
    assert all(bucket_of(result, i)["reason"] == reader.REASON_NO_TOOL_CALLS for i in und["ids"])
    assert set(und["literal_red"]) == set(und["ids"]), "降级成派生不出之后，②原文那 9 枚红一枚不许被裁绿"
    assert result["plan_a_read"]["denominator"] == 93, "分母不许因为摘掉 sidecar 而变宽"
