# -*- coding: utf-8 -*-
"""R643 常驻牙：R51 判据②的分母必须按「发」算，同题多发谁也不许被平均、被借走、被丢掉。

对着的病（10-04 本席现取，非声明）：凭据件 ``scripts/r631_stage_sum_delta.py`` 把同一题的两发
折成一枚分母 —— run20k 的 ``doc-04`` 实测 27,244.6／27,490.9 ms 两发，旧口径只留后一行，另一发
整个掉在账外，差的 246.3 ms＝最小一发的 0.904%，与 ``<1%`` 判据线同一数量级。⇒ 那条线量的是
「这题平均多久」而不是「这一发多久」：**判据本身不成立**，不是读数差一点。

本文件的刀（每把配正控；全合成，零容器零连库零模型；原料只写 tmp_path 影子端）：
① 抹掉某一发的身份（抹掉 ts 桥／开 ``--fold-legacy`` 退回按题号折叠）⇒ 尺必须红并点名该发；
② 从原料里删掉一枚 trace 行 ⇒ 母集掉一枚，那发被 ``unattributed`` 点名，不许静默通过；
③ 手改阈值线（``<1%``→``<5%``）⇒ 在册牙与判据现读同时不认，且这条线在发级账上确实承重；
④ 两发故意造成相同 ms ⇒ 不许折成一发（折叠病最像「没病」的形态）；
⑤ 折叠能把一枚 FAIL 折成 PASS ⇒ 直接证「判据不成立」，不只是「差 0.9%%」；
⑥ 发级身份与行位无关：原料行序打乱，逐发账与逐题账必须逐枚相等（R638 那把棘轮的同族病）。

真窗那一组只在 ``%TEMP%\\evalrun`` 那三本件在位时跑；不在位即 skip，不改判语。
🔴 本文件的钉一律不看「此刻工作树脏不脏／盘上字节等不等于 HEAD」（在册事故 #96／#107／#113）：
判据全是原料内容与在册算术，两态复跑同数是总控在收席那一刻现取的事。
"""

import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "r631_stage_sum_delta_r643", REPO_ROOT / "scripts" / "r631_stage_sum_delta.py")
ruler = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = ruler  # dataclass 要能从 sys.modules 找回本模块
_SPEC.loader.exec_module(ruler)

_R636_SPEC = importlib.util.spec_from_file_location(
    "r636_stage_coverage_r643", REPO_ROOT / "scripts" / "r636_stage_coverage.py")
coverage = importlib.util.module_from_spec(_R636_SPEC)
sys.modules[_R636_SPEC.name] = coverage
_R636_SPEC.loader.exec_module(coverage)

from app.common import stage_timing  # noqa: E402  纯算术件，零 PG 探针

BASE = datetime(2026, 10, 4, tzinfo=timezone.utc)
WINDOWS = ("run18", "run19", "run20k")
REAL_DIR = Path(os.path.expandvars(r"%TEMP%")) / "evalrun"
real_inputs = pytest.mark.skipif(
    not all((REAL_DIR / ("%s-%s.jsonl" % (window, kind))).exists()
            for window in WINDOWS for kind in ("traces", "sidecar", "sidecar-frames")),
    reason="仓外导出件不在位（%%TEMP%%\\evalrun）⇒ 真窗对账组不参与判语")

#: 合成用的两发跨度：真实读数的量级（run20k doc-04 那 246.3 ms 之差在此缩成 10 ms 同形）。
SHOT_A_MS = 1010.0
SHOT_B_MS = 1000.0
SEGMENT_MS = 995.0


def _iso(offset_ms: float) -> str:
    return (BASE + timedelta(milliseconds=offset_ms)).isoformat()


def _stamp(offset_s: float) -> str:
    """采集器落行的 ``ts``（秒级、本地面）：发级身份桥用的就是这枚内容，不是行号。"""
    return (BASE + timedelta(seconds=offset_s)).strftime("%Y-%m-%d %H:%M:%S")


def _write_jsonl(path: Path, rows) -> None:
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _request_pair(trace_id: str, session: str, window_ms: float) -> list[dict]:
    return [
        {"trace_id": trace_id, "event_type": "request.started", "sequence": 1,
         "timestamp": _iso(0.0), "payload": {"record_id": "%s:started" % trace_id,
                                             "session_id": session}},
        {"trace_id": trace_id, "event_type": "request.completed", "sequence": 2,
         "timestamp": _iso(window_ms), "payload": {"record_id": "%s:completed" % trace_id,
                                                   "session_id": session}},
    ]


def _segment(trace_id: str, session: str, index: int, stage: str, duration_ms: float,
              cursor_ms: float) -> dict:
    floored = int(duration_ms)
    payload = {"record_id": "%s:seg:%d" % (trace_id, index), "record_kind": "model_calls",
               "status": "completed", "stage": stage, "duration_ms": floored,
               "started_at": _iso(cursor_ms), "completed_at": _iso(cursor_ms + floored),
               "session_id": session}
    return {"trace_id": trace_id, "event_type": "model.finished", "sequence": 10 + index,
            "timestamp": payload["completed_at"], "payload": payload}


def _frames_row(key: str, session: str, ts: str, window_ms: float) -> dict:
    return {"id": key, "session_id": session, "attempt": 1, "kind": "ok", "ts": ts,
            "events": [{"event": "request.started", "elapsed_ms": 0.0},
                       {"event": "request.completed", "elapsed_ms": window_ms}]}


def _sidecar_row(key: str, ts: str, wall_ms: float, attempt: int = 1) -> dict:
    return {"id": key, "kind": "ok", "attempt": attempt, "wall_ms": wall_ms, "ts": ts}


def synth_shots(tmp_path: Path, specs, *, name: str = "r643demo") -> Path:
    """specs = [dict(题号 key, trace_id, session, ts, wall_ms, segments, window_ms, frames_ms)]。

    每一枚＝**一发**：事件写进它自己的 trace_id，sidecar 与帧账各落一行。返回原料目录。
    """
    directory = tmp_path / "evalrun" / name
    directory.mkdir(parents=True, exist_ok=True)
    events: list[dict] = []
    sidecar: list[dict] = []
    frames: list[dict] = []
    for offset, spec in enumerate(specs):
        trace_id = spec["trace_id"]
        session = spec["session"]
        key = spec["key"]
        ts = spec.get("ts", _stamp(10.0 * offset))
        window_ms = float(spec.get("window_ms", 1_000.0))
        events.extend(_request_pair(trace_id, session, window_ms))
        cursor = 5.0
        for index, (stage, duration_ms) in enumerate(spec.get("segments", ())):
            events.append(_segment(trace_id, session, index, stage, duration_ms, cursor))
            cursor += int(duration_ms) + 1.0
        sidecar.append(_sidecar_row(key, ts, float(spec["wall_ms"]), int(spec.get("attempt", 1))))
        frames.append(_frames_row(key, session, ts, float(spec.get("frames_ms", spec["wall_ms"]))))
    _write_jsonl(directory / ("%s-traces.jsonl" % name), events)
    _write_jsonl(directory / ("%s-sidecar.jsonl" % name), sidecar)
    _write_jsonl(directory / ("%s-sidecar-frames.jsonl" % name), frames)
    return directory


def measure(tmp_path: Path, specs, *, name: str = "r643demo", **kwargs) -> dict:
    """默认走跨钟那条腿（sidecar＋载荷 session 派生的桥），kwargs 可覆盖 e2e_from／fold_legacy。"""
    directory = synth_shots(tmp_path, specs, name=name)
    return ruler.collect(
        window=name,
        directory=directory,
        e2e_from=kwargs.pop("e2e_from", ruler.E2E_SIDECAR),
        traces=[directory / ("%s-traces.jsonl" % name)],
        **kwargs,
    )


def two_shot_specs(overrides=None):
    """同一题 doc-04 两发：跨度不同、身份不同（ts／session／trace 各一枚）。

    overrides = {第几发下标: 要改的字段}，按内容寻址，不按行位。
    """
    base = [
        {"key": "doc-04", "trace_id": "trace-shot-a", "session": "sess-shot-a",
         "ts": _stamp(0.0), "wall_ms": SHOT_A_MS, "window_ms": SHOT_A_MS,
         "segments": (("generate", SEGMENT_MS),)},
        {"key": "doc-04", "trace_id": "trace-shot-b", "session": "sess-shot-b",
         "ts": _stamp(30.0), "wall_ms": SHOT_B_MS, "window_ms": SHOT_B_MS,
         "segments": (("generate", SEGMENT_MS),)},
    ]
    for index, patch in (overrides or {}).items():
        base[index].update(patch)
    return base


def rows_by_trace(data: dict) -> dict:
    return {row["trace_id"]: row for row in data["rows"]}


def ledger_by_label(data: dict) -> dict:
    return {entry["label"]: entry for entry in data["shot_leg"]["ledger"]}

# ==================== 正控：一发一行账，各量各的跨度 ====================


def test_two_shots_of_one_question_get_two_denominators(tmp_path: Path) -> None:
    data = measure(tmp_path, two_shot_specs())

    assert data["status"] == "measured"
    assert data["untrusted_reasons"] == []
    assert len(data["rows"]) == 2
    assert {row["key"] for row in data["rows"]} == {"doc-04"}
    assert {row["end_to_end_ms"] for row in data["rows"]} == {SHOT_A_MS, SHOT_B_MS}
    rows = rows_by_trace(data)
    assert rows["trace-shot-a"]["error_pct"] == pytest.approx(1.4851, abs=1e-3)
    assert rows["trace-shot-b"]["error_pct"] == pytest.approx(0.5, abs=1e-3)
    assert rows["trace-shot-a"]["within_threshold"] is False
    assert rows["trace-shot-b"]["within_threshold"] is True
    assert {row["shot_count"] for row in data["rows"]} == {2}
    assert {row["shot_index"] for row in data["rows"]} == {1, 2}
    assert {row["e2e_identity"] for row in data["rows"]} == {ruler.SHOT_IDENTITY_TS_BRIDGE}
    assert ruler.decide_rc(data) == ruler.RC_GATE  # 一发过线一发不过＝FAIL，不取平均


def test_the_ledger_names_which_shot_each_row_is(tmp_path: Path) -> None:
    data = measure(tmp_path, two_shot_specs())
    text = "\n".join(ruler.render(data))

    assert "同题多发" in text and "doc-04×2 发" in text
    assert "| doc-04 | 1/2 |" in text and "| doc-04 | 2/2 |" in text
    assert "发级分母账（R643）" in text
    assert "折叠一次能从分母上抹掉 %s ms" % (SHOT_A_MS - SHOT_B_MS) in text
    labels = {row["shot_label"] for row in data["rows"]}
    assert labels == {"doc-04 发1/2", "doc-04 发2/2"}
    assert "doc-04 发1/2" in data["verdict"]["failing_1pct_labels"]


def test_no_denominator_is_the_average_of_the_two_shots(tmp_path: Path) -> None:
    """平均／借用／丢弃三条路一起堵死：两枚分母就是采集器落的那两行数，逐枚相等。"""
    data = measure(tmp_path, two_shot_specs())
    readings = sorted(row["end_to_end_ms"] for row in data["rows"])
    average = (SHOT_A_MS + SHOT_B_MS) / 2.0

    assert readings == [SHOT_B_MS, SHOT_A_MS]
    assert average not in readings
    assert data["shot_leg"]["spreads"][0]["shots_ms"] == [SHOT_A_MS, SHOT_B_MS]
    assert data["shot_leg"]["rows_read"] == data["shot_leg"]["shots"] == 2


def test_the_folded_view_would_have_lost_one_shot(tmp_path: Path) -> None:
    """在册旧视图（R636 仍在读它那本）：两行折成一枚题号级分母，另一行整个不在值里。"""
    path = synth_shots(tmp_path, two_shot_specs()) / "r643demo-sidecar.jsonl"
    leg = ruler.read_sidecar(path)

    assert leg.rows_read == 2 and len(leg.values) == 1
    assert leg.duplicates == ("doc-04",)
    assert list(leg.values.values()) == [SHOT_B_MS]  # 同 attempt 取后一行：前一行掉了


def test_the_frames_leg_is_also_counted_per_shot(tmp_path: Path) -> None:
    data = measure(tmp_path, two_shot_specs(), e2e_from=ruler.E2E_FRAMES)

    assert {row["end_to_end_ms"] for row in data["rows"]} == {SHOT_A_MS, SHOT_B_MS}
    assert {row["e2e_identity"] for row in data["rows"]} == {ruler.SHOT_IDENTITY_SESSION}
    assert data["shot_leg"]["unattributed"] == []
    assert ruler.decide_rc(data) == ruler.RC_GATE


# ==================== 刀①：抹掉一发身份 ⇒ 尺必须红并点名 ====================


def test_knife_one_erasing_a_shots_identity_turns_the_ruler_red(tmp_path: Path) -> None:
    """正控＝两发各有 ts 桥；这里抹掉第一发的 ``ts`` ⇒ 它不能再借用兄弟发的数。"""
    blinded = two_shot_specs({0: {"ts": ""}})
    data = measure(tmp_path, blinded, name="r643knife1")
    trusted = measure(tmp_path, two_shot_specs(), name="r643knife1ok")

    assert trusted["shot_leg"]["unattributed"] == []
    assert ruler.decide_rc(trusted) == ruler.RC_GATE
    assert len(data["rows"]) == 1  # 只留下拿得到身份的那一发，另一发不借分母
    assert data["skipped"][0]["trace_id"] == "trace-shot-a"
    assert data["skipped"][0]["reason"] == "no_denominator"
    assert ruler.decide_rc(data) == ruler.RC_UNTRUSTED
    unattributed = data["shot_leg"]["unattributed"]
    assert len(unattributed) == 1 and unattributed[0]["wall_ms"] == SHOT_A_MS
    assert "发级身份" in unattributed[0]["reason"]
    assert any("分母身份丢失" in reason and "doc-04 发" in reason
               for reason in data["untrusted_reasons"])
    assert "：PASS" not in "\n".join(ruler.render(data))


def test_knife_one_fold_legacy_reproduces_the_disease_and_goes_red(tmp_path: Path) -> None:
    """``--fold-legacy``：分母退回按题号折叠 ⇒ 同一本原料必须当场判不可信并逐枚点名。"""
    folded = measure(tmp_path, two_shot_specs(), name="r643legacy", fold_legacy=True)
    honest = measure(tmp_path, two_shot_specs(), name="r643legacyok")

    assert honest["shot_leg"]["fold_legacy"] is False
    assert {row["end_to_end_ms"] for row in folded["rows"]} == {SHOT_B_MS}  # 两发挤一枚分母
    assert folded["shot_leg"]["fold_legacy"] is True
    assert ruler.decide_rc(folded) == ruler.RC_UNTRUSTED
    assert any("分母按题号折叠" in reason for reason in folded["untrusted_reasons"])
    conflicts = folded["shot_leg"]["legacy_conflicts"]
    assert [item["label"] for item in conflicts] == ["doc-04 发1/2"]
    assert conflicts[0]["shot_wall_ms"] == SHOT_A_MS and conflicts[0]["used_ms"] == SHOT_B_MS
    assert conflicts[0]["delta_ms"] == pytest.approx(-(SHOT_A_MS - SHOT_B_MS), abs=1e-6)
    assert "R643 病形复现" in "\n".join(ruler.render(folded))


def test_knife_five_folding_can_flip_a_fail_into_a_pass(tmp_path: Path) -> None:
    """最硬的一刀：旧口径下那枚 FAIL 的发被借来 1000 ms 分母后当场变 PASS ⇒ 判据会翻车。"""
    folded = measure(tmp_path, two_shot_specs(), name="r643flip", fold_legacy=True)
    honest = measure(tmp_path, two_shot_specs(), name="r643flipok")

    honest_flags = {row["shot_label"]: row["within_threshold"] for row in honest["rows"]}
    assert honest_flags == {"doc-04 发1/2": False, "doc-04 发2/2": True}
    assert honest["verdict"]["gate_pass"] is False  # 逐发算：发1 真的过不了线
    #: 折叠算：同一本原料里那枚 FAIL 会被借来的 1000 ms 分母折成「过线」。
    assert all(row["within_threshold"] for row in folded["rows"])
    assert folded["verdict"]["gate_pass"] is None  # 尺拒绝判绿：不可信优先于 FAIL／PASS
    assert ruler.decide_rc(honest) == ruler.RC_GATE
    assert ruler.decide_rc(folded) == ruler.RC_UNTRUSTED  # 这种绿不需要改一行代码就能拿到
    assert any("折叠" in reason for reason in folded["untrusted_reasons"])


# ==================== 刀②：删一枚 trace 行 ⇒ 母集掉一枚并被点名 ====================


def test_knife_two_deleting_a_trace_row_names_the_orphan_shot(tmp_path: Path) -> None:
    name = "r643knife2"
    directory = synth_shots(tmp_path, two_shot_specs(), name=name)
    traces = directory / ("%s-traces.jsonl" % name)
    original = [json.loads(line) for line in traces.read_text(encoding="utf-8").splitlines()
                if line.strip()]
    full = ruler.collect(window=name, directory=directory, e2e_from=ruler.E2E_SIDECAR,
                         traces=[traces])
    kept = [row for row in original if row["trace_id"] != "trace-shot-b"]
    _write_jsonl(traces, kept)
    trimmed = ruler.collect(window=name, directory=directory, e2e_from=ruler.E2E_SIDECAR,
                            traces=[traces])

    assert len({row["trace_id"] for row in original}) == 2
    assert len({row["trace_id"] for row in kept}) == 1  # 母集当场少一枚
    assert len(full["rows"]) == 2 and len(trimmed["rows"]) == 1
    assert ruler.decide_rc(full) == ruler.RC_GATE
    assert ruler.decide_rc(trimmed) == ruler.RC_UNTRUSTED
    unattributed = trimmed["shot_leg"]["unattributed"]
    assert len(unattributed) == 1 and unattributed[0]["wall_ms"] == SHOT_B_MS
    assert any("doc-04" in reason for reason in trimmed["untrusted_reasons"])


def test_knife_two_orphan_question_row_is_named_not_dropped(tmp_path: Path) -> None:
    """单发也一样：题号在 trace 侧一枚都连不上 ⇒ 记 unattributed，不许从母集里悄悄摘掉。"""
    spec = [{"key": "doc-07", "trace_id": "trace-shot-c", "session": "sess-shot-c",
             "ts": _stamp(0.0), "wall_ms": 900.0, "segments": (("classify", 880.0),)}]
    name = "r643orphan"
    directory = synth_shots(tmp_path, spec, name=name)
    sidecar = directory / ("%s-sidecar.jsonl" % name)
    _write_jsonl(sidecar, [_sidecar_row("doc-07", _stamp(0.0), 900.0),
                          _sidecar_row("doc-99", _stamp(99.0), 1234.5)])
    data = ruler.collect(window=name, directory=directory, e2e_from=ruler.E2E_SIDECAR,
                         traces=[directory / ("%s-traces.jsonl" % name)])

    assert len(data["rows"]) == 1
    assert data["shot_leg"]["rows_read"] == 2 and data["shot_leg"]["shots"] == 2
    assert [item["key"] for item in data["shot_leg"]["unattributed"]] == ["doc-99"]
    assert ruler.decide_rc(data) == ruler.RC_UNTRUSTED


# ==================== 刀③：阈值线承重；手改纸面不许本件自取 ====================


def test_knife_three_the_one_percent_line_governs_the_shot_rows(tmp_path: Path) -> None:
    """承重证明：同一本原料，线留在 1.0% 是 FAIL，手抬到 5.0% 才绿 —— 线不是装饰。"""
    events = _request_pair("trace-shot-a", "sess-shot-a", SHOT_A_MS) + [
        _segment("trace-shot-a", "sess-shot-a", 0, "generate", SEGMENT_MS, 5.0)]
    samples_by_trace = {"trace-shot-a": stage_timing.samples_from_events(events)}
    leg = ruler.Leg(ruler.E2E_SIDECAR, "client", {"trace-shot-a": SHOT_A_MS}, (), "", "trace")

    strict, _skipped, _reports = ruler.build_rows(samples_by_trace, leg, {}, 1.0, 0.03)
    loose, _skipped, _reports = ruler.build_rows(samples_by_trace, leg, {}, 5.0, 0.03)

    assert strict[0].error_pct == pytest.approx(1.4851, abs=1e-3)
    assert strict[0].within_threshold is False
    assert loose[0].within_threshold is True
    assert ruler.read_criterion_pct()["threshold_pct"] == 1.0  # 与在册牙同一枚命题


def test_knife_three_hand_moving_the_paper_to_five_percent_is_refused(tmp_path, monkeypatch) -> None:
    """把跟进单那一行手抄成 ``<5%`` 的影子纸：现读读到 5.0，但本件拒绝自取口径。"""
    lines = ruler._read_lines(ruler.CRITERION_DOC)
    moved = list(lines)
    moved[ruler.CRITERION_LINE_LF - 1] = moved[ruler.CRITERION_LINE_LF - 1].replace("<1%", "<5%")
    assert "<5%" in moved[ruler.CRITERION_LINE_LF - 1]
    doc = tmp_path / "followup-moved.md"
    doc.write_text("\n".join(moved), encoding="utf-8", newline="\n")

    assert ruler.read_criterion_pct()["threshold_pct"] == 1.0  # 正控：真纸照旧读得到
    assert ruler.read_criterion_pct(doc=doc)["threshold_pct"] == 5.0
    monkeypatch.setattr(ruler, "read_criterion_pct", lambda *a, **k: {
        "threshold_pct": 5.0, "doc": str(doc), "line_lf": ruler.CRITERION_LINE_LF,
        "raw": lines[ruler.CRITERION_LINE_LF - 1]})

    with pytest.raises(ruler.CaliberError) as excinfo:
        ruler.collect(window="shadow", directory=tmp_path, traces=[])
    assert "落不进在册刀刃" in str(excinfo.value)

# ==================== 刀④：两发故意同 ms ⇒ 不许折成一发 ====================


def test_knife_four_two_shots_with_identical_ms_are_not_folded(tmp_path: Path) -> None:
    """折叠病最像「没病」的形态：两发跨度逐位相等，旧口径折起来不留任何痕迹。"""
    same_ms = [
        {"key": "doc-08", "trace_id": "trace-same-a", "session": "sess-same-a",
         "ts": _stamp(0.0), "wall_ms": 27490.9, "segments": (("generate", 9_000.0),)},
        {"key": "doc-08", "trace_id": "trace-same-b", "session": "sess-same-b",
         "ts": _stamp(30.0), "wall_ms": 27490.9, "segments": (("generate", 9_500.0),)},
    ]
    data = measure(tmp_path, same_ms, name="r643knife4")
    leg = data["shot_leg"]

    assert leg["rows_read"] == leg["shots"] == 2
    assert len(data["rows"]) == 2 and len({row["trace_id"] for row in data["rows"]}) == 2
    assert {row["end_to_end_ms"] for row in data["rows"]} == {27490.9}
    assert {row["segment_sum_ms"] for row in data["rows"]} == {9_000.0, 9_500.0}
    assert {row["shot_label"] for row in data["rows"]} == {"doc-08 发1/2", "doc-08 发2/2"}
    assert leg["spreads"][0]["spread_ms"] == 0.0 and leg["spreads"][0]["shots"] == 2
    assert leg["unattributed"] == []
    assert ruler.decide_rc(data) is not ruler.RC_UNTRUSTED


def test_knife_four_identical_content_shots_refuse_to_pick_one(tmp_path: Path) -> None:
    """内容逐位相同（同 ts 同 ms）＝真的分不清哪发对哪枚 trace ⇒ 两发一起点名，不挑一枚装作看见。"""
    twin = [
        {"key": "doc-09", "trace_id": "trace-twin-a", "session": "sess-twin-a",
         "ts": _stamp(0.0), "wall_ms": 800.0, "segments": (("classify", 700.0),)},
        {"key": "doc-09", "trace_id": "trace-twin-b", "session": "sess-twin-b",
         "ts": _stamp(0.0), "wall_ms": 800.0, "segments": (("classify", 720.0),)},
    ]
    data = measure(tmp_path, twin, name="r643twin")

    assert len(data["rows"]) == 0
    assert len(data["shot_leg"]["unattributed"]) == 2
    assert "同一 (题号, ts)" in data["shot_leg"]["unattributed"][0]["reason"]
    assert ruler.decide_rc(data) == ruler.RC_UNTRUSTED
    assert "：PASS" not in "\n".join(ruler.render(data))


def test_attribute_shots_never_overwrite_one_another(tmp_path: Path) -> None:
    """两发抢同一枚 trace（清单只交一身份）⇒ 都退回未归属：折叠与借用都不许发生。"""
    shots = [ruler.Shot(key="doc-10", wall_ms=100.0, ts="2026-10-04 08:00:00"),
             ruler.Shot(key="doc-10", wall_ms=200.0, ts="2026-10-04 08:00:10")]
    frames = [ruler.Shot(key="doc-10", wall_ms=100.0, ts="2026-10-04 08:00:00",
                         session_id="sess-x"),
              ruler.Shot(key="doc-10", wall_ms=200.0, ts="2026-10-04 08:00:10",
                         session_id="sess-x")]  # 两发被塞成同一枚 session ⇒ 同一枚 trace
    values, ledger = ruler.attribute_shots(
        shots, frames_shots=frames, sessions_by_trace={"trace-x": "sess-x"},
        trace_to_key={"trace-x": "doc-10"})

    assert values == {}
    assert [entry["identity"] for entry in ledger] == [ruler.SHOT_IDENTITY_NONE] * 2
    assert "抢同一枚 trace" in ledger[0]["reason"]


# ==================== 刀⑥：发级身份与行位无关 ====================


def test_shot_identities_do_not_depend_on_row_order(tmp_path: Path) -> None:
    """把三本原料的行序整个倒过来写：逐发账与逐题账必须逐枚相等（R638 同族病的钉）。"""
    forward = measure(tmp_path, two_shot_specs(), name="r643order1")
    reversed_specs = list(reversed(two_shot_specs()))
    reversed_data = measure(tmp_path, reversed_specs, name="r643order2")

    def normalize(data: dict) -> list:
        return sorted([[entry["label"], entry["wall_ms"], entry["identity"], entry["traces"]]
                       for entry in data["shot_leg"]["ledger"]])

    assert normalize(forward) == normalize(reversed_data)
    assert sorted((row["shot_label"], row["end_to_end_ms"], row["error_pct"])
                  for row in forward["rows"]) == sorted(
                      (row["shot_label"], row["end_to_end_ms"], row["error_pct"])
                      for row in reversed_data["rows"])


def test_knife_one_manifest_bridged_shots_beat_the_missing_frames(tmp_path) -> None:
    """没有帧账时，``--join`` 清单交来的发级身份（ts）就是唯一的桥：各发仍各算各的。"""
    name = "r643manifest"
    directory = synth_shots(tmp_path, two_shot_specs(), name=name)
    (directory / ("%s-sidecar-frames.jsonl" % name)).unlink()  # 把帧账那本件摘掉：桥只剩清单
    manifest = directory / "manifest.jsonl"
    _write_jsonl(manifest, [
        {"trace_id": "trace-shot-a", "id": "doc-04", "ts": _stamp(0.0)},
        {"trace_id": "trace-shot-b", "id": "doc-04", "ts": _stamp(30.0)},
    ])

    data = ruler.collect(window=name, directory=directory, e2e_from=ruler.E2E_SIDECAR,
                         traces=[directory / ("%s-traces.jsonl" % name)], join=manifest)

    assert {row["end_to_end_ms"] for row in data["rows"]} == {SHOT_A_MS, SHOT_B_MS}
    assert {row["e2e_identity"] for row in data["rows"]} == {ruler.SHOT_IDENTITY_MANIFEST}
    assert data["shot_leg"]["unattributed"] == []
    assert ruler.decide_rc(data) == ruler.RC_GATE


def test_knife_one_manifest_without_shot_identity_refuses_to_fold(tmp_path) -> None:
    """同一枚清单只交题号（旧那本形状）而原料有两发 ⇒ 一枚都认不出来：不许折，只许点名。"""
    name = "r643manifestbare"
    directory = synth_shots(tmp_path, two_shot_specs(), name=name)
    (directory / ("%s-sidecar-frames.jsonl" % name)).unlink()
    manifest = directory / "manifest-bare.jsonl"
    _write_jsonl(manifest, [
        {"trace_id": "trace-shot-a", "id": "doc-04"},
        {"trace_id": "trace-shot-b", "id": "doc-04"},
    ])

    data = ruler.collect(window=name, directory=directory, e2e_from=ruler.E2E_SIDECAR,
                         traces=[directory / ("%s-traces.jsonl" % name)], join=manifest)

    assert data["rows"] == []
    assert len(data["shot_leg"]["unattributed"]) == 2
    assert any("分母身份丢失" in reason for reason in data["untrusted_reasons"])
    assert ruler.decide_rc(data) == ruler.RC_UNTRUSTED


def test_exit_code_contract_is_unchanged() -> None:
    """本单不许新增退出码：折叠走「不可信」那一格，与在册优先级同一条路。"""
    assert sorted(ruler.EXIT_CODE_MEANING) == [0, 1, 2, 3, 4, 5]
    assert "发级身份丢失" in ruler.EXIT_CODE_MEANING[ruler.RC_UNTRUSTED]
    assert "不可信" in ruler.EXIT_CODE_MEANING[ruler.RC_UNTRUSTED]


# ==================== 真窗对账（原料在位才跑；不在位即 skip）====================


@real_inputs
@pytest.mark.parametrize("window,母集,无分母", [("run18", 105, 20), ("run19", 105, 19),
                                               ("run20k", 106, 19)])
def test_real_window_attributes_every_shot_on_the_books(window: str, 母集: int, 无分母: int) -> None:
    data = ruler.collect(window=window, directory=REAL_DIR)
    leg = data["shot_leg"]

    assert data["status"] == "measured" and data["untrusted_reasons"] == []
    assert len(data["rows"]) == 母集 and len(data["skipped"]) == 无分母
    assert leg["rows_read"] == leg["shots"] == leg["attributed"]
    assert leg["unattributed"] == [] and leg["no_positive_span"] == []
    assert {row["e2e_identity"] for row in data["rows"]} == {ruler.SHOT_IDENTITY_TS_BRIDGE}
    assert ruler.decide_rc(data) == ruler.RC_GATE


@real_inputs
def test_real_run20k_doc04_shots_are_each_measured_against_their_own_span() -> None:
    honest = ruler.collect(window="run20k", directory=REAL_DIR)
    folded = ruler.collect(window="run20k", directory=REAL_DIR, fold_legacy=True)
    spread = [item for item in honest["shot_leg"]["spreads"] if item["key"] == "doc-04"]

    assert len(spread) == 1 and spread[0]["shots_ms"] == [27244.6, 27490.9]
    assert spread[0]["spread_ms"] == 246.3
    assert spread[0]["spread_pct_of_min"] == pytest.approx(0.904, abs=1e-3)
    rows = [row for row in honest["rows"] if row["key"] == "doc-04"]
    assert {row["end_to_end_ms"] for row in rows} == {27244.6, 27490.9}
    assert {row["end_to_end_ms"] for row in folded["rows"] if row["key"] == "doc-04"} == {27490.9}
    #: 改前／改后那枚 p50 与 §11 账面逐枚相等（31.4064 是折叠读数，31.0382 是逐发读数）
    assert folded["quantiles"]["error_p50_pct"] == pytest.approx(31.4064, abs=1e-3)
    assert honest["quantiles"]["error_p50_pct"] == pytest.approx(31.0382, abs=1e-3)
    assert ruler.decide_rc(folded) == ruler.RC_UNTRUSTED
    assert ruler.decide_rc(honest) == ruler.RC_GATE


@real_inputs
@pytest.mark.parametrize("window,p50", [("run18", 32.9612), ("run19", 29.7976)])
def test_real_single_shot_windows_are_byte_for_byte_unchanged(window: str, p50: float) -> None:
    data = ruler.collect(window=window, directory=REAL_DIR)

    assert data["quantiles"]["error_p50_pct"] == pytest.approx(p50, abs=1e-3)
    assert data["shot_leg"]["spreads"] == [] and data["shot_leg"]["multi_shot_questions"] == {}
    assert data["shot_leg"]["unattributed"] == []


@real_inputs
def test_real_no_denominator_family_is_still_named_item_by_item() -> None:
    for window, count in (("run18", 20), ("run19", 19), ("run20k", 19)):
        data = ruler.collect(window=window, directory=REAL_DIR)

        assert len(data["skipped"]) == count, window
        assert {item["reason"] for item in data["skipped"]} == {"no_denominator"}, window
        assert all(item["trace_id"] for item in data["skipped"]), window


@real_inputs
@pytest.mark.parametrize("window,母集,无分母", [("run18", 105, 20), ("run19", 105, 19)])
def test_real_universe_reconciles_with_the_coverage_ledger(window: str, 母集: int,
                                                           无分母: int) -> None:
    built = coverage.build_window(window, REAL_DIR)
    data = ruler.collect(window=window, directory=REAL_DIR)
    gap = built["reference_gap"]

    assert gap["asked_minus_rows"] == 0 and gap["no_denom_minus_skipped"] == 0
    assert gap["rows"] == 母集 and gap["skipped"] == 无分母
    assert len(data["rows"]) == gap["rows"] and len(data["skipped"]) == gap["skipped"]
    assert built["mismatches"] == []


@real_inputs
def test_real_run20k_only_diverges_from_the_coverage_ledger_on_the_folded_denominator() -> None:
    """母集枚数照旧对得上；分歧只在同题多发的分母上 —— 覆盖面那把尺自己也折了一枚。"""
    data = ruler.collect(window="run20k", directory=REAL_DIR)
    multi = {entry["key"] for entry in data["shot_leg"]["ledger"] if entry["shot_count"] > 1}

    with pytest.raises(coverage.MismatchError) as excinfo:
        coverage.build_window("run20k", REAL_DIR)

    hits = json.loads(str(excinfo.value).split("前若干枚：", 1)[1])
    assert {item["field"] for item in hits} <= {"end_to_end_ms", "error_pct"}
    assert {item["key"] for item in hits} <= multi
    assert {item["key"] for item in hits} == {"doc-04"}