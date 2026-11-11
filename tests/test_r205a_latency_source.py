"""R205a 源头件（跟进单 §93.9 ①）：采集器不许再拿整调用跨度冒充「这一发的时延」。

病灶在 scripts/collect_evaluation_answers.py 的「_latency_ms」：载荷不自报时它直接回「measured_ms」，
而那格是 collect_answers 里 perf_counter 的**整调用**跨度——含被打回的重试、重试 sleep、排队轮询观测窗，
run6 的 data-06 里还含 09-23 23:34 → 09-24 07:40 那段 8 h 6 min 整机待机（事故 #40）。
诚实的那一发在帧账 sidecar 的 wall_ms 里（适配器每次尝试开头重取时间、重试不记账）。

🔴 反证钉（源头侧）＝ test_a_span_that_cannot_be_one_attempt_is_not_written_as_latency：
把那道量级守卫摘掉，这一枚必红（latency_ms 会重新等于 29 265 911.2）。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "collect_evaluation_answers.py"

#: run6 现场：data-06 那一发的整调用跨度（8 h 7 m）与帧账 wall_ms（55.9 s，解冻之后那一路）
FROZEN_COLLECTION_SPAN_MS = 29265911.2
FROZEN_FRAME_LEDGER_MS = 55930.8


@pytest.fixture(scope="module")
def collector():
    spec = importlib.util.spec_from_file_location("r205a_collector", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _row(row_id):
    return {"id": row_id, "tier": "问答", "category": "数据分析",
            "question": f"问题 {row_id}？", "answer": "500元/晚",
            "must_contain": ["500元/晚"], "requires_evidence": False}


def _collect_rows(collector, specs):
    """按 (题号, 载荷, 整调用跨度) 跑一遍采集器；时钟每发从 0 起、按给定跨度落表。"""
    ticks = iter([tick for _id, _payload, span in specs for tick in (0.0, span / 1000.0)])
    payload_by_id = {row_id: payload for row_id, payload, _span in specs}
    rows = [_row(row_id) for row_id, _payload, _span in specs]
    answers, failures = collector.collect_answers(
        rows, lambda row: payload_by_id[str(row["id"])],
        answer_source="r205a_synthetic", clock=lambda: next(ticks))
    assert failures == [], failures
    return rows, answers


def _collect_one(collector, payload, *, span_ms, row_id="data-06"):
    _rows, answers = _collect_rows(collector, [(row_id, payload, span_ms)])
    return answers[0]


def test_the_collector_and_the_scorer_read_one_envelope(collector):
    """一把尺：量级上限由评分端定义、采集器只读——两把尺就是账对不上的起手式。"""
    from app.quality.eval import latency_envelope_ms

    assert collector.latency_envelope_ms is latency_envelope_ms
    assert not hasattr(collector, "LATENCY_ENVELOPE_TIMEOUT_MULTIPLES"), "采集器另存了一把尺"
    assert latency_envelope_ms() > FROZEN_FRAME_LEDGER_MS


def test_a_span_that_cannot_be_one_attempt_is_not_written_as_latency(collector):
    """🔴 反证钉（源头侧）：越出一发量级的整调用跨度不再冒充时延，且逐题留下它自己的名字。"""
    answer = _collect_one(collector, {"answer": "住宿费标准是500元/晚。"},
                          span_ms=FROZEN_COLLECTION_SPAN_MS)

    assert answer["latency_ms"] is None, (
        f"latency_ms={answer['latency_ms']!r}：采集器又把整调用跨度冒充成一发的时延"
        " ⇒ 摘掉 _latency_ms 的量级守卫就会这样（run6 的假形状）")
    suspect = answer["latency_suspect"]
    assert suspect["id"] == "data-06"
    assert suspect["collection_span_ms"] == round(FROZEN_COLLECTION_SPAN_MS, 3), "原始观测被丢了"
    assert suspect["one_attempt_envelope_ms"] > FROZEN_FRAME_LEDGER_MS
    assert "wall_ms" in suspect["reason"], "没说清诚实跨度在哪儿"
    # 这一行仍是 runner 读得懂的字节：拒记不许多造形状，也不许少造形状
    assert json.loads(json.dumps(answer, ensure_ascii=False))["latency_ms"] is None


def test_a_span_that_fits_one_attempt_is_still_the_reading(collector):
    """没重试、没被冻的常规那一发：数不许因为新守卫而变没（既往断言零放宽的另一半）。"""
    from app.quality.eval import latency_envelope_ms

    inside = _collect_one(collector, {"answer": "x"}, span_ms=latency_envelope_ms() - 1000.0)
    assert inside["latency_ms"] == pytest.approx(latency_envelope_ms() - 1000.0)
    assert "latency_suspect" not in inside, "干净轮的 answers 行不许长出新键"

    typical = _collect_one(collector, {"answer": "x"}, span_ms=1500.0)
    assert typical["latency_ms"] == 1500.0


def test_a_self_reported_span_is_never_replaced_by_the_collectors_clock(collector):
    """守卫只管「没自报时能不能冒充」，不许反过来盖掉载荷自报的那一发。"""
    answer = _collect_one(collector, {"answer": "x", "latency_ms": 5000.0},
                          span_ms=FROZEN_COLLECTION_SPAN_MS)
    assert answer["latency_ms"] == 5000.0
    assert "latency_suspect" not in answer


def test_the_refused_row_still_satisfies_the_line_contract(collector):
    """拒记不许顺手改行契约：那四键三 trace 键由采集器当场校验，runner 与评分端都靠它。"""
    answer = _collect_one(collector, {"answer": "x"}, span_ms=FROZEN_COLLECTION_SPAN_MS)
    row = _row("data-06")

    collector.assert_line_contract(answer)
    collector.assert_coverage([row], [answer])
    assert set(collector.RUNNER_REQUIRED_KEYS) == {"id", "answer", "evidence", "latency_ms"}
    assert all(answer[key] is None for key in collector.TRACE_KEYS)


def test_a_refused_row_reaches_the_report_through_the_frame_ledger(collector, tmp_path):
    """两道闸咬合：源头拒记 ⇒ 评分端拿帧账那一发的 wall_ms 顶上，格子不撒谎也不缺题。"""
    from app.quality.eval import LATENCY_ACTION_RECOVERED, evaluate_evaluation_set

    def write(path, payload_rows):
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n"
                                for row in payload_rows), encoding="utf-8")
        return path

    specs = [("data-06", {"answer": "500元/晚"}, FROZEN_COLLECTION_SPAN_MS),
             ("doc-08", {"answer": "500元/晚"}, 20378.7)]
    rows, answers = _collect_rows(collector, specs)
    ledger = {"data-06": FROZEN_FRAME_LEDGER_MS, "doc-08": 20375.2}

    write(tmp_path / "fixture.jsonl", rows)
    write(tmp_path / "answers-run7.jsonl", answers)
    sidecar = write(tmp_path / "sidecar-run7.jsonl", [
        {"id": row_id, "kind": "ok", "attempt": 2, "sentinel": False, "evidence_n": 1,
         "answer_chars": 8, "tool_calls": 1, "wall_ms": wall, "ts": "x"}
        for row_id, wall in ledger.items()])

    by_id = {str(answer["id"]): answer for answer in answers}
    report = evaluate_evaluation_set(tmp_path / "fixture.jsonl",
                                     lambda row: by_id[str(row["id"])],
                                     approval_ledger=sidecar)
    cell = report["latency_ms"]

    assert cell["count"] == len(rows), "被拒的那一发应当由帧账顶上，而不是从格子里消失"
    assert cell["average"] <= cell["max"] <= FROZEN_FRAME_LEDGER_MS, (
        f"average={cell['average']} max={cell['max']}：格子里仍有不是一发的跨度")
    listed = {row["id"]: row for row in cell["suspect"]}
    assert listed["data-06"]["action"] == LATENCY_ACTION_RECOVERED
    assert listed["data-06"]["used_ms"] == FROZEN_FRAME_LEDGER_MS
    assert listed["data-06"]["reported_ms"] is None, "源头已拒记，报告不许凭空长出实测"
    assert [row["id"] for row in cell["suspect"]] == ["data-06"], "无重试那题不该被牵连"
    assert report["answer_correctness"] == 1.0, "记账不许动分数"
