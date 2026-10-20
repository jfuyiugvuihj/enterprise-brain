# -*- coding: utf-8 -*-
"""R631 常驻牙：端到端 对 分段加总 这把尺真在量东西（全合成，零 run18／run19／run20k 真数）。

对着的病：G-R51-1 欠的是「② 端到端与分段加总误差 <1%（对齐 latency-budget 的 0.03%）」那一次
对照读数。这把尺可以有两种死法，本文件的刀一枚一枚对着它们：
① 永远红 —— 量不到也报 FAIL，把「没货」写成「不合格」，下一班就照着一枚不存在的读数改产品；
② 永远绿 —— 把分段加总自己当端到端，比值恒 0，任何一窗都 PASS。②比①危险得多，因为它长得像证据。
所以钉的是：
* 摘掉一枚分段 ⇒ 误差必须变（不是「还能跑」）；把某段翻倍 ⇒ 比值必须动；
* 端到端与分段塞成同源 ⇒ 必须判「不可信」走 RC_UNTRUSTED —— 声明同源与恒零差两条签名各钉一枚；
* 一窗无货 ⇒ RC_NO_INPUT 且印面上不许出现 PASS／FAIL；
* 判据常量与对齐常量各一枚反证刀：摘掉它原来红的当场变绿 ⇒ 证明它在承重；
* 交叉重叠未决 ⇒ 误差 0.01% 也不许 PASS（不许拿百分比蒙混）；
* 真源不自造：本件用的三枚函数必须就是 app/common/stage_timing 那三枚。

为什么全合成：run18／run19／run20k 的盘上产物一件都没有 duration_ms（现读取证见
docs/perf/r631-stage-sum-delta-2026-10-04.md）；拿真数当钉等于把「今天量不到」这件事本身钉掉，
而合成样本能钉的是**尺子的行为** —— 那才是这一格欠的东西。
合成件刻意不带 payload.question：带着它 samples_from_span_payload 会去 import
app/agents/nodes 问 R42 判别器，离线牙不该把产品路由拖进来（本文件零网络零模型零 PG）。
"""

import importlib.util
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "r631_stage_sum_delta", REPO_ROOT / "scripts" / "r631_stage_sum_delta.py")
ruler = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = ruler  # dataclass 要能从 sys.modules 找回本模块，否则当场炸
_SPEC.loader.exec_module(ruler)

from app.common import stage_timing  # noqa: E402
from app.common.performance import PerformanceStats  # noqa: E402

BASE = datetime(2026, 10, 4, tzinfo=timezone.utc)

#: latency-budget 那十行的毫秒版（合计 160 552 ms，窗 160 600 ms，误差 0.0299%）。
#: 这是**合成样本的骨架**，数字取自纸上那把对照表，不是任何一窗的真读数。
BUDGET_MS = (
    ("classify", 81.0),
    ("classify", 27797.0),
    ("classify", 71.0),
    ("generate", 24046.0),
    ("rewrite", 41581.0),
    ("retrieve", 242.0),
    ("generate", 50448.0),
    ("classify", 15931.0),
    ("reflect", 33.0),
    ("classify", 322.0),
)
WINDOW_MS = 160600.0
BUDGET_ERROR_PCT = (WINDOW_MS - sum(value for _stage, value in BUDGET_MS)) / WINDOW_MS * 100.0


def _iso(offset_ms: float) -> str:
    return (BASE + timedelta(milliseconds=offset_ms)).isoformat()


def _write_jsonl(path: Path, rows) -> None:
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _request_pair(trace_id: str, window_ms: float) -> list[dict]:
    """request.started / request.completed 两枚：在册那把端到端尺（request_windows_from_events）读的就是这对。"""
    return [
        {"trace_id": trace_id, "event_type": "request.started", "sequence": 1,
         "timestamp": _iso(0.0), "payload": {"record_id": "%s:started" % trace_id}},
        {"trace_id": trace_id, "event_type": "request.completed", "sequence": 2,
         "timestamp": _iso(window_ms), "payload": {"record_id": "%s:completed" % trace_id}},
    ]


def _segment(trace_id: str, index: int, stage: str, duration_ms: float, cursor_ms: float) -> dict:
    """一枚已落库的 ``model.finished``：两端齐全、与邻段不重叠，duration 按产品口径 int 地板。"""
    floored = int(duration_ms)
    payload = {
        "record_id": "%s:seg:%d" % (trace_id, index),
        "record_kind": "model_calls",
        "status": "completed",
        "stage": stage,
        "duration_ms": floored,
        "started_at": _iso(cursor_ms),
        "completed_at": _iso(cursor_ms + floored),
    }
    return {"trace_id": trace_id, "event_type": "model.finished", "sequence": 10 + index,
            "timestamp": payload["completed_at"], "payload": payload}


def _trace_events(trace_id: str, rows, window_ms: float = WINDOW_MS) -> list[dict]:
    events = _request_pair(trace_id, window_ms)
    cursor = 12.0  # 整段序列嵌在窗内，留一点未观测残差 —— 恒零差不是这里的形状
    for index, (stage, duration_ms) in enumerate(rows):
        event = _segment(trace_id, index, stage, duration_ms, cursor)
        events.append(event)
        cursor += int(duration_ms) + 1.0  # 段间空 1 ms：合成样本刻意不重叠
    return events


def synth(tmp_path: Path, specs, *, name: str = "synth07") -> dict:
    """specs = [(trace_id, 题号, rows, window_ms)]；写 trace 事件＋sidecar＋join 三本件。"""
    directory = tmp_path / "evalrun"
    directory.mkdir(parents=True, exist_ok=True)
    events: list[dict] = []
    sidecar: list[dict] = []
    join: list[dict] = []
    for trace_id, key, rows, window_ms in specs:
        events.extend(_trace_events(trace_id, rows, window_ms))
        sidecar.append({"id": key, "kind": "ok", "attempt": 1,
                        "wall_ms": round(window_ms + 250.0, 1)})  # 采集器钟：比服务端窗多一段排队
        join.append({"trace_id": trace_id, "id": key})
    traces = directory / ("%s-traces.jsonl" % name)
    sidecar_path = directory / ("%s-sidecar.jsonl" % name)
    join_path = directory / ("join-%s.jsonl" % name)
    _write_jsonl(traces, events)
    _write_jsonl(sidecar_path, sidecar)
    _write_jsonl(join_path, join)
    return {"directory": directory, "traces": traces, "sidecar": sidecar_path, "join": join_path,
            "window": name}


def measure(tmp_path: Path, specs, **kwargs) -> dict:
    """默认走跨钟那条腿（sidecar＋join）；kwargs 可覆盖 e2e_from／join。"""
    layout = synth(tmp_path, specs)
    return ruler.collect(
        window=layout["window"],
        directory=layout["directory"],
        e2e_from=kwargs.pop("e2e_from", ruler.E2E_SIDECAR),
        traces=[layout["traces"]],
        join=kwargs.pop("join", layout["join"]),
        **kwargs,
    )


# ==================== 真源：本件不许另造一把尺 ====================


def test_the_three_sources_are_the_instrumented_ones_not_a_local_copy() -> None:
    assert ruler.samples_from_events is stage_timing.samples_from_events
    assert ruler.aggregate_stage_latency is stage_timing.aggregate_stage_latency
    assert ruler.request_windows_from_events is stage_timing.request_windows_from_events


def test_criterion_line_and_alignment_anchor_are_read_from_the_paper() -> None:
    criterion = ruler.read_criterion_pct()
    assert criterion["line_lf"] == 522
    assert criterion["threshold_pct"] == 1.0
    assert "端到端与分段加总误差 <1%" in criterion["raw"]
    alignment = ruler.read_alignment_pct()
    assert alignment["align_pct"] == 0.03
    assert alignment["computed_pct"] == pytest.approx(0.02989, abs=1e-4)
    assert alignment["end_to_end_s"] == 160.6 and alignment["sum_s"] == 160.552


def test_inbook_knife_and_paper_criterion_still_agree() -> None:
    assert ruler.probe_inbook_gate() == {"r631-knife-pass": True, "r631-knife-fail": False}


# ==================== 正常形状：尺子量得到东西时怎么印 ====================


def test_a_honest_server_internal_reading_passes_both_lines(tmp_path) -> None:
    data = measure(tmp_path, [("t-a", "doc-01", BUDGET_MS, WINDOW_MS)], e2e_from=ruler.E2E_EVENTS)

    row = data["rows"][0]
    assert data["status"] == "measured"
    assert data["untrusted_reasons"] == []
    assert row["error_pct"] == pytest.approx(BUDGET_ERROR_PCT, abs=1e-3)
    assert row["delta_ms"] != 0.0  # 正常测量里不许出现恒零差那种逐位相等
    assert data["verdict"]["gate_pass"] is True and data["verdict"]["align_pass"] is True
    assert ruler.decide_rc(data) == ruler.RC_OK


def test_the_cross_clock_leg_carries_the_queue_the_segments_cannot_see(tmp_path) -> None:
    """采集器钟比服务端窗多 250 ms（排队＋传输）：跨钟对得上 <1%，对不上 0.03% —— 这是口径事实不是缺陷。"""
    data = measure(tmp_path, [("t-a", "doc-01", BUDGET_MS, WINDOW_MS)])

    row = data["rows"][0]
    assert row["error_pct"] > 0.1
    assert data["verdict"]["gate_pass"] is True
    assert data["verdict"]["align_pass"] is False
    assert ruler.decide_rc(data) == ruler.RC_ALIGN


def test_quantiles_come_from_the_inbook_nearest_rank(tmp_path) -> None:
    specs = [
        ("t-1", "doc-01", BUDGET_MS, WINDOW_MS),
        ("t-2", "doc-02", BUDGET_MS[:5], 90_000.0),
        ("t-3", "doc-03", (("generate", 1000.0),), 400.0),
    ]
    data = measure(tmp_path, specs, e2e_from=ruler.E2E_EVENTS)

    stats = PerformanceStats()
    for row in data["rows"]:
        stats.observe(row["error_pct"])
    assert data["quantiles"]["count"] == 3
    assert data["quantiles"]["error_p50_pct"] == pytest.approx(stats.percentile(0.50), abs=1e-4)
    assert data["quantiles"]["error_p95_pct"] == pytest.approx(stats.percentile(0.95), abs=1e-4)
    assert data["quantiles"]["error_max_pct"] == pytest.approx(stats.percentile(1.00), abs=1e-4)


def test_the_worst_question_is_named_one_by_one(tmp_path, capsys) -> None:
    specs = [
        ("t-1", "doc-01", BUDGET_MS, WINDOW_MS),
        ("t-2", "doc-02", (("generate", 500.0),), 400.0),  # 25% 过段
        ("t-3", "doc-03", (("generate", 100.0),), 4_000.0),  # 97.5% 没吃满
    ]
    data = measure(tmp_path, specs, e2e_from=ruler.E2E_EVENTS)

    assert [row["key"] for row in data["rows"]] == ["doc-03", "doc-02", "doc-01"]
    assert data["quantiles"]["error_max_pct"] == pytest.approx(97.5, abs=0.01)
    text = "\n".join(ruler.render(data))
    assert "最大一枚 = doc-03" in text
    assert "doc-03=97.5%" in text
    assert "doc-03" in data["verdict"]["failing_1pct"] and "doc-02" in data["verdict"]["failing_1pct"]
    assert ruler.decide_rc(data) == ruler.RC_GATE


def test_two_wrong_requests_cannot_cancel_each_other_out(tmp_path) -> None:
    specs = [("t-short", "doc-01", (("generate", 200.0),), 900.0),
             ("t-long", "doc-02", (("generate", 800.0),), 100.0)]
    data = measure(tmp_path, specs, e2e_from=ruler.E2E_EVENTS)

    errors = {row["key"]: row["error_pct"] for row in data["rows"]}
    assert errors["doc-01"] == pytest.approx(77.7778, abs=0.01)
    assert errors["doc-02"] == pytest.approx(700.0, abs=0.01)
    assert data["verdict"]["gate_pass"] is False
    assert sorted(data["verdict"]["failing_1pct"]) == ["doc-01", "doc-02"]
    assert "整窗加总" not in json.dumps(data)  # 本件只逐题，从不把两题揉成一枚数


def test_truncation_bound_is_derived_from_the_segment_count(tmp_path) -> None:
    specs = [("t-one", "doc-01", (("generate", 900.0),), 1_000.0),
             ("t-two", "doc-02", (("classify", 400.0), ("generate", 400.0)), 1_000.0)]
    data = measure(tmp_path, specs, e2e_from=ruler.E2E_EVENTS)

    bounds = {row["key"]: (row["segments"], row["truncation_bound_ms"]) for row in data["rows"]}
    assert bounds["doc-01"] == (1, 1.0)
    assert bounds["doc-02"] == (2, 2.0)


# ==================== 刀一：分段动一下，误差必须动 ====================


def _samples_and_leg(rows, window_ms: float = WINDOW_MS, trace_id: str = "t"):
    events = _trace_events(trace_id, rows, window_ms)
    samples_by_trace = {trace_id: stage_timing.samples_from_events(events)}
    leg = ruler.Leg(ruler.E2E_EVENTS, "server", {trace_id: window_ms}, (), "", "trace")
    return samples_by_trace, leg


def test_dropping_one_segment_changes_the_error(tmp_path) -> None:
    full, _skipped, _reports = ruler.build_rows(*_samples_and_leg(BUDGET_MS), {}, 1.0, 0.03)
    lean_rows = tuple(row for row in BUDGET_MS if row[0] != "rewrite")
    lean, _skipped, _reports = ruler.build_rows(*_samples_and_leg(lean_rows), {}, 1.0, 0.03)

    assert full[0].error_pct == pytest.approx(BUDGET_ERROR_PCT, abs=1e-3)
    assert lean[0].error_pct > full[0].error_pct + 20.0
    assert "rewrite" in lean[0].missing_stages and "rewrite" not in full[0].missing_stages


def test_doubling_one_segment_moves_the_ratio(tmp_path) -> None:
    doubled = tuple(
        (stage, value * 2.0) if value == 24046.0 else (stage, value) for stage, value in BUDGET_MS
    )
    base, _skipped, _reports = ruler.build_rows(*_samples_and_leg(BUDGET_MS), {}, 1.0, 0.03)
    over, _skipped, _reports = ruler.build_rows(*_samples_and_leg(doubled), {}, 1.0, 0.03)

    assert over[0].error_pct > base[0].error_pct + 10.0
    assert over[0].delta_ms > 0.0 > over[0].gap_ms  # 分段超出端到端 = 同一秒被算了两遍
    assert over[0].within_threshold is False


def test_a_crossing_overlap_cannot_pass_even_at_a_hundredth_of_a_percent(tmp_path) -> None:
    """和得上的加总照样不算数：两枚交叉段（未决重叠）谁也没被剔除，百分比蒙混不得。"""
    events = _request_pair("t-cross", 20_000.0)
    for index, (start_ms, end_ms) in enumerate(((0.0, 10_000.0), (5_000.0, 15_000.0))):
        payload = {"record_id": "t-cross:seg:%d" % index, "record_kind": "model_calls",
                   "status": "completed", "stage": "generate", "duration_ms": 9_999,
                   "started_at": _iso(start_ms), "completed_at": _iso(end_ms)}
        events.append({"trace_id": "t-cross", "event_type": "model.finished",
                       "sequence": 10 + index, "timestamp": payload["completed_at"], "payload": payload})
    samples_by_trace = {"t-cross": stage_timing.samples_from_events(events)}
    leg = ruler.Leg(ruler.E2E_EVENTS, "server", {"t-cross": 20_000.0}, (), "", "trace")

    rows, _skipped, _reports = ruler.build_rows(samples_by_trace, leg, {}, 1.0, 0.03)

    assert rows[0].error_pct < 0.03  # 百分比本身漂亮得很
    assert rows[0].unresolved_pairs == 1
    assert rows[0].within_threshold is False and rows[0].within_align is False


# ==================== 刀二：同源塞进来必须判不可信（两条签名各一枚） ====================


def test_declaring_the_segment_sum_as_end_to_end_is_judged_untrusted(tmp_path) -> None:
    layout = synth(tmp_path, [("t-a", "doc-01", BUDGET_MS, WINDOW_MS)])
    data = ruler.collect(window=layout["window"], directory=layout["directory"],
                         e2e_from=ruler.E2E_SEGMENTS, traces=[layout["traces"]])

    assert data["status"] == "untrusted"
    assert any("声明同源" in reason for reason in data["untrusted_reasons"])
    assert any("恒零差" in reason for reason in data["untrusted_reasons"])
    assert data["verdict"]["gate_pass"] is None and data["verdict"]["align_pass"] is None
    assert ruler.decide_rc(data) == ruler.RC_UNTRUSTED
    text = "\n".join(ruler.render(data))
    assert "：PASS" not in text and "：FAIL" not in text  # 不可信就不许印判语


def test_a_tautological_sidecar_is_caught_although_it_claims_a_client_clock(tmp_path) -> None:
    """塞成同源的隐蔽路：wall_ms 写成与该题分段加总逐位相等。声明是跨钟，数字是自我复述 ⇒ 恒零差那一刀接住。"""
    layout = synth(tmp_path, [("t-a", "doc-01", BUDGET_MS, WINDOW_MS)])
    _write_jsonl(layout["sidecar"], [{"id": "doc-01", "kind": "ok", "attempt": 1,
                                      "wall_ms": float(sum(int(value) for _stage, value in BUDGET_MS))}])
    data = ruler.collect(window=layout["window"], directory=layout["directory"],
                         e2e_from=ruler.E2E_SIDECAR, traces=[layout["traces"]], join=layout["join"])

    assert data["e2e_leg"]["name"] == ruler.E2E_SIDECAR
    assert not any("声明同源" in reason for reason in data["untrusted_reasons"])
    assert any("恒零差" in reason for reason in data["untrusted_reasons"])
    assert all(row["delta_ms"] == 0.0 for row in data["rows"])
    assert ruler.decide_rc(data) == ruler.RC_UNTRUSTED


def test_cli_returns_the_untrusted_code_for_the_self_sum_leg(tmp_path, capsys) -> None:
    layout = synth(tmp_path, [("t-a", "doc-01", BUDGET_MS, WINDOW_MS)])
    rc = ruler.main(["--window", layout["window"], "--dir", str(layout["directory"]),
                     "--traces", str(layout["traces"]), "--e2e-from", ruler.E2E_SEGMENTS])

    assert rc == ruler.RC_UNTRUSTED
    assert "不可信" in capsys.readouterr().out


# ==================== 刀三：量不到要说不到，不许冒充不合格 ====================


def test_a_window_without_the_segment_leg_says_no_measurement(tmp_path) -> None:
    """换一枚没有 trace 导出的窗名：有分母没分子 ⇒ 必须说“量不到”，不许报 FAIL。"""
    layout = synth(tmp_path, [("t-a", "doc-01", BUDGET_MS, WINDOW_MS)])
    data = ruler.collect(window="run-empty", directory=layout["directory"],
                         e2e_from=ruler.E2E_SIDECAR, traces=[], sidecar=layout["sidecar"])
    text = "\n".join(ruler.render(data))

    assert data["status"] == "no_segments"
    assert data["quantiles"] is None
    assert data["verdict"]["gate_pass"] is None
    assert ruler.decide_rc(data) == ruler.RC_NO_INPUT
    assert "量不到" in text and "：PASS" not in text and "：FAIL" not in text


def test_the_printed_exit_code_never_disagrees_with_the_real_one(tmp_path) -> None:
    """run18 现跑踩到的形状：分段腿无货 + 声明同源同时命中 ⇒ 真码 4，小标题不许硬写 3。

    印面一旦写着「退出码 3」而末行是 4，下一班照纸追债就追错那一格（同源判死与缺导出
    是两件不同的事）。钉的是 render 里不许再出现任何硬写死的码数。
    """
    layout = synth(tmp_path, [("t-a", "doc-01", BUDGET_MS, WINDOW_MS)])
    data = ruler.collect(window="run-empty", directory=layout["directory"],
                         e2e_from=ruler.E2E_SEGMENTS, traces=[], sidecar=layout["sidecar"])
    text = "\n".join(ruler.render(data))
    rc = ruler.decide_rc(data)

    assert rc == ruler.RC_UNTRUSTED, "这枚组合的真实优先级就是不可信 > 无货"
    assert data["status"] == "no_segments"
    codes = {int(hit) for hit in re.findall(r"退出码[^0-9]{0,3}(\d)", text)}
    assert codes == {rc}, "印面里每一枚退出码都必须等于真码：%s" % sorted(codes)
    assert "：PASS" not in text and "：FAIL" not in text

def test_an_empty_directory_is_no_measurement(tmp_path) -> None:
    (tmp_path / "nothing").mkdir()
    rc = ruler.main(["--window", "run99", "--dir", str(tmp_path / "nothing")])

    assert rc == ruler.RC_NO_INPUT


def test_the_cross_clock_leg_refuses_to_guess_the_join(tmp_path, capsys) -> None:
    layout = synth(tmp_path, [("t-a", "doc-01", BUDGET_MS, WINDOW_MS)])
    rc = ruler.main(["--window", layout["window"], "--dir", str(layout["directory"]),
                     "--traces", str(layout["traces"]), "--e2e-from", ruler.E2E_SIDECAR])

    assert rc == ruler.RC_NO_INPUT
    out = capsys.readouterr().out
    assert "--join" in out and "SLO_BLOCKERS" in out  # 点名为什么连不上，不静默降级


# ==================== 刀四：两枚常量各自在承重（反证） ====================


def test_refutation_removing_the_criterion_constant_turns_red_into_green(tmp_path) -> None:
    """摘掉 <1% 那枚常量：同一本分段账、同一个误差，红的当场变绿 ⇒ 常量不是装饰。"""
    lean_rows = tuple(row for row in BUDGET_MS if row[0] != "rewrite")
    samples_by_trace, leg = _samples_and_leg(lean_rows)

    real, _skipped, _reports = ruler.build_rows(samples_by_trace, leg, {}, 1.0, 0.03)
    neutralised, _skipped, _reports = ruler.build_rows(samples_by_trace, leg, {}, 1e9, 0.03)

    assert real[0].within_threshold is False
    assert neutralised[0].within_threshold is True
    assert real[0].error_pct == neutralised[0].error_pct  # 一个数都没动，只摘了判据


def test_refutation_removing_the_alignment_constant_turns_red_into_green(tmp_path) -> None:
    """摘掉 0.03% 那枚对齐常量：一枚 33 ms 的段丢了照样绿 —— <1% 一格对这种丢段是无力 的。"""
    lean_rows = tuple(row for row in BUDGET_MS if row[1] != 33.0)
    samples_by_trace, leg = _samples_and_leg(lean_rows)

    real, _skipped, _reports = ruler.build_rows(samples_by_trace, leg, {}, 1.0, 0.03)
    neutralised, _skipped, _reports = ruler.build_rows(samples_by_trace, leg, {}, 1.0, 1e9)

    assert real[0].error_pct == pytest.approx(0.0504, abs=1e-3)
    assert real[0].within_threshold is True
    assert real[0].within_align is False
    assert neutralised[0].within_align is True


def test_a_dropped_reflect_row_reddens_only_the_alignment_line(tmp_path) -> None:
    lean_rows = tuple(row for row in BUDGET_MS if row[1] != 33.0)
    data = measure(tmp_path, [("t-a", "doc-01", lean_rows, WINDOW_MS)], e2e_from=ruler.E2E_EVENTS)

    assert data["verdict"]["gate_pass"] is True and data["verdict"]["align_pass"] is False
    assert ruler.decide_rc(data) == ruler.RC_ALIGN


# ==================== 刀五：判据现读；纸改了不许本件自取 ====================


def _followup_like(tmp_path: Path, criterion: str) -> Path:
    doc = tmp_path / "followup-doctored.md"
    body = ["filler %d\r\n" % index for index in range(1, CRITERION_FILLER_LINES)]
    body.append(criterion)
    doc.write_bytes("".join(body).encode("utf-8"))
    return doc


CRITERION_FILLER_LINES = 522


def test_the_criterion_is_read_from_the_paper_not_from_a_literal(tmp_path) -> None:
    doc = _followup_like(tmp_path, "| **R51** | x | ② 端到端与分段加总误差 <5%（对齐 y 的 0.03%） |\r\r\n")

    assert ruler.read_criterion_pct(doc, 522)["threshold_pct"] == 5.0


def test_a_criterion_line_that_moved_is_a_caliber_error(tmp_path) -> None:
    doc = _followup_like(tmp_path, "| **R51** | 阶段化 P95 观测 | ① 各段 P50/P95 可查 |\r\r\n")

    with pytest.raises(ruler.CaliberError):
        ruler.read_criterion_pct(doc, 522)
    with pytest.raises(ruler.CaliberError):
        ruler.read_criterion_pct(doc, 900)  # 行数不够同样不许猜


def test_a_diverging_paper_reddens_the_caliber_instead_of_the_reading(tmp_path, monkeypatch) -> None:
    """纸面若改成 5%：跟进单与 app 的门分家 ⇒ 本件拒出数，不自取任何一枚口径。"""
    monkeypatch.setattr(ruler, "read_criterion_pct", lambda *a, **k: {
        "threshold_pct": 5.0, "doc": "doctored.md", "line_lf": 522, "raw": "x"})
    layout = synth(tmp_path, [("t-a", "doc-01", BUDGET_MS, WINDOW_MS)])

    with pytest.raises(ruler.CaliberError):
        ruler.collect(window=layout["window"], directory=layout["directory"],
                      e2e_from=ruler.E2E_EVENTS, traces=[layout["traces"]])


def test_the_alignment_anchor_is_read_and_self_checked(tmp_path) -> None:
    consistent = tmp_path / "budget-ok.md"
    consistent.write_bytes("# x\n\n日志自报 `200.0s`，我按毫秒时间戳拆出 **199.9s**，误差 0.05%\n".encode("utf-8"))
    self_contradicting = tmp_path / "budget-bad.md"
    self_contradicting.write_bytes("# x\n\n日志自报 `160.6s`，我按毫秒时间戳拆出 **100.000 s**，误差 0.03%\n".encode("utf-8"))

    assert ruler.read_alignment_pct(consistent)["align_pct"] == 0.05
    with pytest.raises(ruler.CaliberError):
        ruler.read_alignment_pct(self_contradicting)
    with pytest.raises(ruler.CaliberError):
        ruler.read_alignment_pct(tmp_path / "absent.md")


# ==================== 刀六：跨度与件名按在册口径，不接受自我申报 ====================


def test_the_ruler_reads_wall_ms_not_the_self_reported_latency_ms(tmp_path) -> None:
    """R205a／R595 那条口径：诚实跨度只认 sidecar 的 wall_ms，latency_ms 不收当跨度。"""
    path = tmp_path / "run-synth-sidecar.jsonl"
    _write_jsonl(path, [{"id": "doc-01", "kind": "ok", "latency_ms": 160552.0, "wall_ms": 0}])

    with pytest.raises(ruler.InputMissing):
        ruler.read_sidecar(path)


def test_the_frames_leg_needs_the_real_request_pair(tmp_path) -> None:
    path = tmp_path / "run-synth-sidecar-frames.jsonl"
    _write_jsonl(path, [{"id": "doc-01", "events": [
        {"event": "text", "elapsed_ms": 100.0}, {"event": "done", "elapsed_ms": 900.0}]}])

    with pytest.raises(ruler.InputMissing):
        ruler.read_frames(path)


def test_the_join_manifest_is_the_only_bridge_between_the_two_keyspaces(tmp_path) -> None:
    layout = synth(tmp_path, [("t-a", "doc-01", BUDGET_MS, WINDOW_MS)])
    _write_jsonl(layout["join"], [{"trace_id": "t-other", "id": "doc-99"}])

    with pytest.raises(ruler.InputMissing):
        ruler.collect(window=layout["window"], directory=layout["directory"],
                      e2e_from=ruler.E2E_SIDECAR, traces=[layout["traces"]], join=layout["join"])


def test_rows_are_named_by_question_when_a_join_exists_and_by_trace_when_not(tmp_path) -> None:
    layout = synth(tmp_path, [("t-a", "doc-01", BUDGET_MS, WINDOW_MS)])
    joined = ruler.collect(window=layout["window"], directory=layout["directory"],
                           e2e_from=ruler.E2E_EVENTS, traces=[layout["traces"]], join=layout["join"])
    bare = ruler.collect(window=layout["window"], directory=layout["directory"],
                         e2e_from=ruler.E2E_EVENTS, traces=[layout["traces"]])

    assert joined["rows"][0]["key"] == "doc-01"
    assert bare["rows"][0]["key"] == "t-a"
    assert bare["verdict"]["gate_pass"] is True  # 没 join 只是少了题号，不拆腿


# ==================== 退出码契约 ====================


def test_exit_codes_are_the_documented_set_and_are_mutually_exclusive() -> None:
    assert ruler.RC_OK == 0 and ruler.RC_GATE == 1 and ruler.RC_ALIGN == 2
    assert ruler.RC_NO_INPUT == 3 and ruler.RC_UNTRUSTED == 4 and ruler.RC_CALIBER == 5
    assert sorted(ruler.EXIT_CODE_MEANING) == [0, 1, 2, 3, 4, 5]
    assert "不是 PASS" in ruler.EXIT_CODE_MEANING[ruler.RC_NO_INPUT]
    assert "不可信" in ruler.EXIT_CODE_MEANING[ruler.RC_UNTRUSTED]


def test_untrusted_beats_a_would_be_pass_and_no_input_beats_a_would_be_fail(tmp_path) -> None:
    specs = [("t-a", "doc-01", BUDGET_MS, WINDOW_MS)]
    layout = synth(tmp_path, specs)
    trusted = ruler.collect(window=layout["window"], directory=layout["directory"],
                            e2e_from=ruler.E2E_EVENTS, traces=[layout["traces"]])
    self_sum = ruler.collect(window=layout["window"], directory=layout["directory"],
                             e2e_from=ruler.E2E_SEGMENTS, traces=[layout["traces"]])
    empty = ruler.collect(window="run42", directory=layout["directory"], e2e_from=ruler.E2E_EVENTS, traces=[])

    assert ruler.decide_rc(trusted) == ruler.RC_OK
    assert ruler.decide_rc(self_sum) == ruler.RC_UNTRUSTED  # 同一枚输入，绿被收回
    assert ruler.decide_rc(empty) == ruler.RC_NO_INPUT
def test_concurrent_traces_do_not_lose_segments_to_each_other(tmp_path) -> None:
    """合成件三题共用同一枚起点＝并发请求：整窗台账必须由逐题报告相加。

    在册 aggregate_stage_latency 比的是区间，把一窗的题全倒进同一次调用，并发请求的两枚跨度
    会因墙上时钟重叠被当成「嵌套」剔出加总（10-04 实测 pooled：pairs=13／未决=9／生成段被剔
    2 980 ms）。判据②本来就是逐题主张 ⇒ 相加只认逐题报告，一枚都不许多剔或漏剔。
    """
    specs = [("t-a", "doc-01", BUDGET_MS, WINDOW_MS),
             ("t-b", "doc-02", (("classify", 120.0), ("generate", 2980.0)), 4200.0),
             ("t-c", "doc-03", (("retrieve", 300.0),), 900.0)]
    data = measure(tmp_path, specs, e2e_from=ruler.E2E_EVENTS)
    ledger = data["ledger_view"]

    assert ledger["overlap"]["pairs"] == 0
    assert ledger["overlap"]["unresolved_pairs"] == 0
    assert sum(cell["ledger_count"] for cell in ledger["stages"].values()) == sum(
        row["segments"] for row in data["rows"])
    assert round(sum(cell["total_ms"] for cell in ledger["stages"].values()), 6) == round(
        sum(row["segment_sum_ms"] for row in data["rows"]), 6)
    assert ledger["stages"]["generate"]["excluded_ms"] == 0.0

def _session_stamped_events(trace_id: str, rows, window_ms: float, session: str) -> list[dict]:
    """同一本合成件，只在每枚载荷上补一枚 session_id —— 在册载荷真带它（orchestrator.py:1502）。"""
    events = _trace_events(trace_id, rows, window_ms)
    for event in events:
        event["payload"]["session_id"] = session
    return events


def test_the_payload_session_is_the_bridge_when_no_manifest_is_fed(tmp_path) -> None:
    """跨钟那条腿的桥不一定非要人交清单：采集器一题一枚 session，事件载荷也带 session。"""
    directory = tmp_path / "evalrun"
    directory.mkdir()
    traces = directory / "synth08-traces.jsonl"
    _write_jsonl(traces, _session_stamped_events("t-a", BUDGET_MS, WINDOW_MS, "761c24c2e7de4084aea00accde3bef39"))
    sidecar = directory / "synth08-sidecar.jsonl"
    _write_jsonl(sidecar, [{"id": "doc-01", "kind": "ok", "wall_ms": WINDOW_MS + 250.0}])
    _write_jsonl(directory / "synth08-sidecar-frames.jsonl",
                 [{"id": "doc-01", "session_id": "761c24c2e7de4084aea00accde3bef39", "events": []}])

    data = ruler.collect(window="synth08", directory=directory, e2e_from=ruler.E2E_SIDECAR, traces=[traces])

    assert data["join_source"] == "payload.session_id"
    assert data["join_size"] == 1
    assert data["rows"][0]["key"] == "doc-01"
    assert data["rows"][0]["trace_id"] == "t-a"
    assert data["verdict"]["gate_pass"] is True  # 0.185% —— 跨钟对得上 1%，对不上 0.03%
    assert data["verdict"]["align_pass"] is False
    assert ruler.decide_rc(data) == ruler.RC_ALIGN


def test_an_explicit_manifest_wins_over_the_payload_derived_bridge(tmp_path) -> None:
    directory = tmp_path / "evalrun"
    directory.mkdir()
    traces = directory / "synth09-traces.jsonl"
    _write_jsonl(traces, _session_stamped_events("t-a", BUDGET_MS, WINDOW_MS, "sess-aaa"))
    #: sidecar 只认清单那枚题号；载荷派生那枚（doc-01）故意不在 sidecar 里 ——
    #: 谁赢不是嘴上说的，是看哪枚连得上、哪枚的读数进得了分母。
    sidecar = directory / "synth09-sidecar.jsonl"
    _write_jsonl(sidecar, [{"id": "doc-99", "kind": "ok", "wall_ms": WINDOW_MS + 250.0}])
    _write_jsonl(directory / "synth09-sidecar-frames.jsonl", [{"id": "doc-01", "session_id": "sess-aaa"}])
    manifest = directory / "manifest.jsonl"
    _write_jsonl(manifest, [{"trace_id": "t-a", "id": "doc-99"}])

    data = ruler.collect(window="synth09", directory=directory, e2e_from=ruler.E2E_SIDECAR,
                         traces=[traces], join=manifest)

    assert data["join_source"] == "manifest"
    assert data["rows"][0]["key"] == "doc-99"
    assert data["join_size"] == 1

def test_the_same_question_twice_is_named_not_folded(tmp_path) -> None:
    """run20k 实测：106 行 105 枚题号（doc-04 两行、attempt 都是 1）。静默取最后一行就是把重试擦掉。"""
    path = tmp_path / "synth10-sidecar.jsonl"
    _write_jsonl(path, [
        {"id": "doc-04", "kind": "ok", "attempt": 1, "wall_ms": 27244.6},
        {"id": "doc-04", "kind": "ok", "attempt": 1, "wall_ms": 27490.9},
        {"id": "doc-05", "kind": "ok", "attempt": 2, "wall_ms": 512.0},
        {"id": "doc-05", "kind": "ok", "attempt": 3, "wall_ms": 611.0},
    ])

    leg = ruler.read_sidecar(path)

    assert leg.rows_read == 4  # 读进分母的行数，不是连出的题号数
    assert len(leg.values) == 2
    assert leg.duplicates == ("doc-04", "doc-05")
    assert leg.values["doc-04"] == 27490.9  # 同 attempt 取后一行；attempt 不同取 attempt 最大那枚
    assert leg.values["doc-05"] == 611.0


def test_the_honest_span_is_still_the_only_span_accepted(tmp_path) -> None:
    """补一枚：wall_ms 缺失／为 0 的行不进分母，也不能把整件判空——有别的正数就照连。"""
    path = tmp_path / "synth11-sidecar.jsonl"
    _write_jsonl(path, [
        {"id": "doc-01", "kind": "ok", "attempt": 1, "wall_ms": 0},
        {"id": "doc-02", "kind": "ok", "attempt": 1, "wall_ms": 1234.5},
    ])

    leg = ruler.read_sidecar(path)

    assert leg.values == {"doc-02": 1234.5}
    assert leg.rows_read == 1