"""R205a 记账件（跟进单 §93.9 ①）：报告那一格「平均值大于逐题最大值」今后必须当场拦下。

数字取自 run6 现场与 §93.0 的帧账核对：报告 latency_ms = {count 105, average 351 121.76,
p95 163 262.073}，而逐题帧账 wall_ms 全表 max 272.2 s / avg 50.8 s ⇒ 那个平均值大过了逐题最大值，
一眼假。这里钉三件事：① 那种形状进不了报告（guard 直接炸），② 每一格都只由「一发尝试自己的跨度」
构成（越界者被替换或被排除，且逐题列出），③ 规则写在数上、不写在题号上。

🔴 反证钉（记账侧）＝ test_a_retry_inflated_span_is_repaired_to_the_frame_ledger：
把「实测 vs 帧账容忍带」那条规则摘掉，这一枚必红——600 s 量级那一发仍在量级上限之内，
只有帧账这把尺拦得住它。
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

import pytest

from app.quality.eval import (
    LATENCY_ACTION_ABSENT,
    LATENCY_ACTION_EXCLUDED,
    LATENCY_ACTION_KEPT,
    LATENCY_ACTION_RECOVERED,
    LATENCY_ACTION_REPAIRED,
    LATENCY_LEDGER_RATIO_TOLERANCE,
    LATENCY_LEDGER_SLACK_MS,
    LatencyAccountingError,
    aggregate_latency_ms,
    build_latency_cell,
    classify_latency_span,
    guard_latency_cell,
    latency_envelope_ms,
)

#: run6 报告那一格与帧账逐题最大值（§93.0：全表 max 272.2 s）——「一眼假」的原样
RUN6_CELL = {"count": 105, "average": 351121.76, "p95": 163262.073, "max": 272200.0}
#: run6 data-06：整调用跨度 8 h 7 m，帧账那一发 55.9 s
FROZEN_MEASURED_MS = 29265911.2
FROZEN_WALL_MS = 55930.8


def _envelope():
    return latency_envelope_ms()


def write_jsonl(path: Path, rows) -> Path:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                    encoding="utf-8")
    return path


def _report(tmp_path, readings, ledger_rows):
    """readings：{题号: latency_ms 或 None}；ledger_rows：{题号: wall_ms 或 None（缺行）}。"""
    from app.quality.eval import evaluate_evaluation_set

    fixture = write_jsonl(tmp_path / "fixture.jsonl", [
        {"id": row_id, "category": "数据分析", "tier": "问答", "question": f"问题 {row_id}？",
         "answer": "500元/晚", "must_contain": ["500元/晚"], "requires_evidence": True}
        for row_id in readings])
    sidecar = write_jsonl(tmp_path / "sidecar.jsonl", [
        {"id": row_id, "kind": "ok", "attempt": 1, "sentinel": False, "evidence_n": 1,
         "answer_chars": 8, "tool_calls": 1, "wall_ms": wall, "ts": "x"}
        for row_id, wall in ledger_rows.items() if wall is not None])
    answers = {row_id: {"id": row_id, "answer": "住宿费标准是500元/晚。",
                        "evidence": [{"source_name": "差旅制度", "locator": "第3页"}],
                        "first_token_at": None, "thinking_chars": None, "tool_calls": 1,
                        "latency_ms": latency}
               for row_id, latency in readings.items()}
    return evaluate_evaluation_set(fixture, lambda row: answers[str(row["id"])],
                                   approval_ledger=sidecar)


# ===== 判据 ①：那种形状出不了报告 ======================================================

def test_the_run6_cell_shape_is_rejected_on_the_spot():
    """「平均值大于逐题最大值」这一眼假的形状，从现在起是异常，不是一份能看的报告。"""
    with pytest.raises(LatencyAccountingError) as raised:
        guard_latency_cell(dict(RUN6_CELL))
    message = str(raised.value)
    assert "平均值" in message and "大于逐题最大值" in message
    assert str(RUN6_CELL["average"]) in message and str(RUN6_CELL["max"]) in message


def test_the_honest_ledger_bounds_the_cell_itself():
    """帧账说逐题最大 272.2 s，格子里却出现 400 s 的跨度 ⇒ 不必逐题回头看，闸当场炸。"""
    honest_max = 272200.0  # run6 帧账全表 max（§93.0）
    with pytest.raises(LatencyAccountingError) as raised:
        build_latency_cell([40000.0, 400000.0], honest_max_ms=honest_max)
    assert "诚实上界" in str(raised.value)
    # 同批数落在诚实上界之内就出得来：这道闸不是「不许有慢题」，是「不许有解释不了的跨度」
    assert build_latency_cell([40000.0, 272200.0], honest_max_ms=honest_max)["max"] == 272200.0


def test_the_report_is_not_produced_when_one_span_cannot_be_explained(tmp_path):
    """活的路径：没有帧账可对的那一发越出诚实上界 ⇒ evaluate_evaluation_set 当场炸，不出报告。"""
    readings = {"a-01": 30000.0, "a-02": 30000.0, "a-03": _envelope() / 2}
    with pytest.raises(LatencyAccountingError):
        _report(tmp_path, readings, {"a-01": 30000.0, "a-02": 30000.0, "a-03": None})


def test_an_empty_cell_never_trips_the_guard():
    """一格时延都没有（全部未测）是既有出口，不是撒谎：count 0 不炸。"""
    guard_latency_cell({"count": 0, "average": 0, "p95": 0, "max": 0})
    assert aggregate_latency_ms([])["count"] == 0


# ===== 判据 ①：格子里只许有「一发尝试自己的跨度」 ======================================

def test_a_span_beyond_one_attempt_magnitude_cannot_enter_the_cell():
    """量级这一把尺：run6 那发 8 h 就算没有帧账可对，也不许进聚合，且要被逐题列出。"""
    verdict = classify_latency_span("data-06", FROZEN_MEASURED_MS, None,
                                    envelope_ms=_envelope())
    assert verdict["action"] == LATENCY_ACTION_EXCLUDED
    assert verdict["used_ms"] is None
    assert "没有帧账可对" in verdict["row"]["reason"]


def test_a_retry_inflated_span_is_repaired_to_the_frame_ledger():
    """🔴 反证钉（记账侧）：在一发量级之内、但不是这一发的跨度 ⇒ 只能由帧账容忍带拦下。"""
    reported = _envelope() / 2  # 一定在量级上限之内：量级这把尺管不到它
    verdict = classify_latency_span("data-04", reported, 30000.0, envelope_ms=_envelope())

    assert verdict["action"] == LATENCY_ACTION_REPAIRED, "容忍带那道规则被摘掉了"
    assert verdict["used_ms"] == 30000.0
    assert verdict["corroborated"] is True
    row = verdict["row"]
    assert row["reported_ms"] == reported and row["frame_ledger_ms"] == 30000.0
    assert "容忍带" in row["reason"]
    # 容忍带本身就是尺：恰好落在带上沿的读数仍算这一发，越出去才换帧账
    limit = round(30000.0 * LATENCY_LEDGER_RATIO_TOLERANCE + LATENCY_LEDGER_SLACK_MS, 2)
    assert classify_latency_span("data-04", limit, 30000.0,
                                 envelope_ms=_envelope())["action"] == LATENCY_ACTION_KEPT
    assert classify_latency_span("data-04", limit + 0.1, 30000.0,
                                 envelope_ms=_envelope())["action"] == LATENCY_ACTION_REPAIRED


def test_a_span_inside_the_tolerance_band_stays_the_reading():
    """run6 里 102/105 题是这个形状：两数本就同一发，谁也不许被动过。"""
    verdict = classify_latency_span("doc-08", 20378.7, 20375.2, envelope_ms=_envelope())
    assert verdict["action"] == LATENCY_ACTION_KEPT
    assert verdict["used_ms"] == 20378.7
    assert verdict["row"] is None, "干净的题不许出现在逐题清单里"


def test_the_frame_ledger_itself_must_fit_one_attempt_to_replace_anything():
    """帧账越出一发量级 ⇒ 它自己也不是诚实跨度，不能拿它替换别人，两边一起排除。"""
    verdict = classify_latency_span("odd-01", _envelope() * 3, _envelope() * 2,
                                    envelope_ms=_envelope())
    assert verdict["action"] == LATENCY_ACTION_EXCLUDED
    assert verdict["used_ms"] is None
    assert verdict["corroborated"] is False


def test_a_missing_reading_is_recovered_from_the_ledger_and_listed():
    """源头拒记（latency_ms 为 null）那一发：帧账顶上，并逐题写清它是「补」不是「测」。"""
    verdict = classify_latency_span("data-06", None, FROZEN_WALL_MS, envelope_ms=_envelope())
    assert verdict["action"] == LATENCY_ACTION_RECOVERED
    assert verdict["used_ms"] == FROZEN_WALL_MS
    assert verdict["row"]["reported_ms"] is None
    assert "latency_suspect" in verdict["row"]["reason"] or "wall_ms" in verdict["row"]["reason"]


def test_an_unreadable_reading_is_never_swallowed():
    """读不成毫秒的实测：有帧账就换帧账并列出，没帧账就排除并列出——两条路都不许静默消失。"""
    recovered = classify_latency_span("bad-01", "fast", 30000.0, envelope_ms=_envelope())
    assert recovered["action"] == LATENCY_ACTION_RECOVERED
    assert "读不成毫秒" in recovered["row"]["reason"]

    excluded = classify_latency_span("bad-02", "fast", None, envelope_ms=_envelope())
    assert excluded["action"] == LATENCY_ACTION_EXCLUDED
    assert excluded["row"] is not None and "fast" in excluded["row"]["reason"]

    absent = classify_latency_span("bad-03", None, None, envelope_ms=_envelope())
    assert absent["action"] == LATENCY_ACTION_ABSENT
    assert absent["row"] is None, "没测到不等于测得假，不该被列成可疑"


def test_the_rules_read_numbers_not_question_ids():
    """规则写在数上：换一套题号，处置结果逐字相同（不许题号白名单）。"""
    def cell_for(row_id):
        return aggregate_latency_ms([
            {"id": row_id, "reported_ms": FROZEN_MEASURED_MS, "frame_ledger_ms": FROZEN_WALL_MS},
            {"id": f"clean-{row_id}", "reported_ms": 20378.7, "frame_ledger_ms": 20375.2},
        ])

    named, renamed = cell_for("data-06"), cell_for("zzz-99")
    for key in ("count", "average", "p95", "max", "frame_ledger_rows", "suspect_n",
                "one_attempt_envelope_ms", "basis"):
        assert named[key] == renamed[key], key
    used_named = [row["used_ms"] for row in named["suspect"]]
    used_renamed = [row["used_ms"] for row in renamed["suspect"]]
    assert used_named == used_renamed == [FROZEN_WALL_MS]
    assert named["suspect"][0]["used_ms"] == FROZEN_WALL_MS


# ===== 聚合那一格自身的形状 ==============================================================

def _mixed_spans():
    return [
        {"id": "clean-01", "reported_ms": 20378.7, "frame_ledger_ms": 20375.2},
        {"id": "frozen-02", "reported_ms": FROZEN_MEASURED_MS, "frame_ledger_ms": FROZEN_WALL_MS},
        {"id": "retry-03", "reported_ms": _envelope() / 2, "frame_ledger_ms": 30000.0},
        {"id": "refused-04", "reported_ms": None, "frame_ledger_ms": 40000.0},
        {"id": "ghost-05", "reported_ms": _envelope() * 3, "frame_ledger_ms": None},
        {"id": "unmeasured-06", "reported_ms": None, "frame_ledger_ms": None},
    ]


def test_the_aggregate_lists_every_handled_row_in_input_order():
    cell = aggregate_latency_ms(_mixed_spans())
    used = [20378.7, FROZEN_WALL_MS, 30000.0, 40000.0]

    assert cell["count"] == len(used), "格子里只许有那一发自己的跨度"
    assert cell["average"] == pytest.approx(round(statistics.mean(used), 2))
    assert cell["max"] == max(used) and cell["p95"] == max(used)
    assert cell["average"] <= cell["max"] <= FROZEN_MEASURED_MS / 2
    assert [row["id"] for row in cell["suspect"]] == [
        "frozen-02", "retry-03", "refused-04", "ghost-05"]
    assert [row["action"] for row in cell["suspect"]] == [
        LATENCY_ACTION_REPAIRED, LATENCY_ACTION_REPAIRED,
        LATENCY_ACTION_RECOVERED, LATENCY_ACTION_EXCLUDED]
    assert all(row["reason"] for row in cell["suspect"]), "被处置过的题必须说清为什么"
    assert cell["suspect_n"] == len(cell["suspect"]) == 4
    assert cell["frame_ledger_rows"] == 4, "对过帧账的题数要单独可见"
    assert cell["one_attempt_envelope_ms"] == _envelope()
    assert "每发尝试" in cell["basis"]


def test_the_three_score_cells_do_not_move_for_a_clean_run(tmp_path):
    """帧账在场也不许扰动干净轮的数：count/average/p95 与逐题实测的直接聚合同值。"""
    readings = {f"row-{index}": 20000.0 + index for index in range(10)}
    ledger = {row_id: wall - 3.5 for row_id, wall in readings.items()}

    cell = _report(tmp_path, readings, ledger)["latency_ms"]
    values = sorted(readings.values())

    assert cell["suspect"] == [] and cell["suspect_n"] == 0
    assert cell["count"] == 10 == len(values)
    assert cell["average"] == round(statistics.mean(values), 2)
    assert cell["p95"] == values[-1] and cell["max"] == values[-1]


def test_the_run6_numbers_land_on_the_honest_ledger_scale(tmp_path):
    """run6 那一发被帧账顶上之后，整格回到诚实量级：average ≤ max ≤ 逐题帧账最大跨度。"""
    readings = {"data-06": FROZEN_MEASURED_MS, "doc-08": 20378.7,
                "doc-13": 18080.3, "metric-18": 24016.6}
    ledger = {"data-06": FROZEN_WALL_MS, "doc-08": 20375.2,
              "doc-13": 18077.3, "metric-18": 24013.5}

    cell = _report(tmp_path, readings, ledger)["latency_ms"]

    assert cell["average"] <= cell["max"] == FROZEN_WALL_MS
    assert cell["count"] == 4 and cell["suspect_n"] == 1
    assert cell["suspect"][0]["id"] == "data-06"
    assert cell["suspect"][0]["used_ms"] == FROZEN_WALL_MS
    # 被替换的那一发恰好贡献帧账那一发的跨度，其余各发仍拿自己的实测（规则①不换干净的数）
    assert cell["average"] == round(statistics.mean(
        [FROZEN_WALL_MS, 20378.7, 18080.3, 24016.6]), 2)
