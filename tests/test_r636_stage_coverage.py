# -*- coding: utf-8 -*-
"""R636 常驻牙：覆盖面这把尺真在量东西，而且三把反证刀各咬得住（全合成 + 真窗对账各一组）。

对着的病：G-R51-1 第四格「端到端与分段加总误差 <1%」三窗全 FAIL，缺的是**覆盖面归因**。
这把尺有四种死法，本文件一枚一枚对着：
① 假装对得上 —— 不复算 R631 的读数，只把它的 JSON 抄一遍 → 注入一枚「认不出某段」的假尺它照旧绿；
② 悄悄摘题 —— no_denominator 不进账，母集看着就小了；
③ 型别靠嘴 —— 把「没发事件」写成「被嵌套剔除」也算一条账；
④ 派生尺读空 —— AST 读不到在册形状时静交空表，所有归因都失去凭据。
所以钉的是：注入假尺必红（①）、摘组必红（②）、无凭据的型 C 必拒（③）、影子树能检出调用点（④的反向自证）。

合成件刻意不带 payload.question：带着它 samples_from_span_payload 会去 import app/agents/nodes 问
R42 判别器，离线牙不该把产品路由拖进来（本文件零网络、零模型、零 PG、零容器）。
真窗那一组只在 %TEMP%\\evalrun 那三本件在位时跑；不在位即 skip，不改判语。
"""

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "r636_stage_coverage", REPO_ROOT / "scripts" / "r636_stage_coverage.py")
ruler = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = ruler  # dataclass 要能从 sys.modules 找回本模块，否则当场炸
_SPEC.loader.exec_module(ruler)

BASE = datetime(2026, 10, 4, tzinfo=timezone.utc)
WINDOWS = ("run18", "run19", "run20k")
REAL_DIR = ruler.default_directory()
real_inputs = pytest.mark.skipif(
    not all((REAL_DIR / ("%s-%s.jsonl" % (w, kind))).exists()
            for w in WINDOWS for kind in ("traces", "sidecar", "sidecar-frames")),
    reason="仓外导出件不在位（%%TEMP%%\\evalrun）⇒ 真窗对账组不参与判语")


def _iso(offset_ms: float) -> str:
    return (BASE + timedelta(milliseconds=offset_ms)).isoformat()


def _stamp(offset_ms: float) -> str:
    """created_at 的形状：PG 交回的是无偏移的 UTC 文本（同导出件）。"""
    return (BASE + timedelta(milliseconds=offset_ms)).strftime("%Y-%m-%d %H:%M:%S.%f")


def _write_jsonl(path: Path, rows) -> None:
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _started(trace_id: str, session_id: str, *, lane: str = "qa", tier: str = "chat",
             offset_ms: float = 0.0, lane_source: str = "r42", owner: str = "evalbot") -> dict:
    payload = {"lane": lane, "tier": tier, "may_plan": True, "owner_id": owner,
               "lane_rule": "test", "rules_lane": lane, "session_id": session_id,
               "lane_source": lane_source, "declared_lane": "", "allowed_workers": ["doc"],
               "required_workers": []}
    return {"trace_id": trace_id, "request_id": "req-%s" % trace_id[-6:], "task_id": "task-%s" % trace_id[-6:],
            "sequence": 1, "event_type": "request.started", "status": "running",
            "owner_id": owner, "payload": payload, "created_at": _stamp(offset_ms)}


def _finished(trace_id: str, event_type: str, *, record_id: str, stage: str = "", tool: str = "",
              tier: str = "", worker: str = "", duration_ms: int = 0, start_ms: float = 0.0,
              sequence: int = 2) -> dict:
    payload = {"record_id": record_id, "record_kind": "model_calls" if event_type == "model.finished" else "tool_calls",
               "status": "completed", "duration_ms": int(duration_ms),
               "started_at": _iso(start_ms), "completed_at": _iso(start_ms + int(duration_ms))}
    if stage:
        payload["stage"] = stage
    if tool:
        payload["tool_name"] = tool
    if tier:
        payload["model_tier"] = tier
    if worker:
        payload["worker"] = worker
    return {"trace_id": trace_id, "request_id": "req-%s" % trace_id[-6:], "task_id": "task-%s" % trace_id[-6:],
            "sequence": sequence, "event_type": event_type, "status": "completed", "owner_id": "evalbot",
            "payload": payload, "created_at": _stamp(start_ms + int(duration_ms))}


def _event(trace_id: str, event_type: str, payload: dict, offset_ms: float, sequence: int = 3) -> dict:
    return {"trace_id": trace_id, "request_id": "req-%s" % trace_id[-6:], "task_id": "task-%s" % trace_id[-6:],
            "sequence": sequence, "event_type": event_type, "status": "completed", "owner_id": "evalbot",
            "payload": payload, "created_at": _stamp(offset_ms)}


def synth(tmp_path: Path, name: str = "r636demo") -> Path:
    """四枚题 + 一枚孤儿 + 一枚未归名孤儿：把三型与两组明账都在合成窗里凑齐。

    doc-01  正常：supervisor(classify) + search_docs(retrieve) + worker model(generate)
            ＋ 两本未登记时长账（retrieval.completed、step.finished）
    chart-01 只有 supervisor 一发；真工作在孤儿 trace 上（型 A/a3）
    scope-09 generate 一枚嵌在 retrieve 跨度里 ⇒ 整段被剔（型 C）
    doc-04   只有 retrieval.completed，没有 search_docs 跨度 ⇒ retrieve 型 B
    """
    directory = tmp_path / "evalrun"
    directory.mkdir(parents=True, exist_ok=True)
    events: list[dict] = []
    frames: list[dict] = []
    sidecar: list[dict] = []

    # doc-01：三段落账
    events.append(_started("trace-doc01", "sess-doc01", offset_ms=0.0))
    events.append(_finished("trace-doc01", "model.finished", record_id="r:classify", tier="analysis",
                            duration_ms=2000, start_ms=100, sequence=2))
    events.append(_finished("trace-doc01", "tool_call.finished", record_id="r:search", tool="search_docs",
                            worker="doc", duration_ms=6000, start_ms=3000, sequence=3))
    events.append(_finished("trace-doc01", "model.finished", record_id="r:gen", tier="analysis", worker="doc",
                            duration_ms=4000, start_ms=12000, sequence=4))
    events.append(_event("trace-doc01", "retrieval.completed",
                         {"duration_ms": 5200.0, "rewrite_count": 3, "top_k": 5}, 9000))
    events.append(_event("trace-doc01", "step.finished",
                         {"worker": "doc", "step_id": "s", "summary": {"duration_ms": 15000}}, 16000))
    frames.append({"id": "doc-01", "session_id": "sess-doc01", "attempt": 1, "kind": "ok"})
    sidecar.append({"id": "doc-01", "kind": "ok", "attempt": 1, "wall_ms": 30000.0, "ts": "2026-10-04 08:00:30"})

    # chart-01：本题只有 supervisor 一发，工作在孤儿上
    events.append(_started("trace-chart01", "sess-chart01", lane="analysis", tier="analysis", offset_ms=0.0))
    events.append(_finished("trace-chart01", "model.finished", record_id="c:classify", tier="analysis",
                            duration_ms=2632, start_ms=100, sequence=2))
    frames.append({"id": "chart-01", "session_id": "sess-chart01", "attempt": 1, "kind": "approved_ok"})
    sidecar.append({"id": "chart-01", "kind": "approved_ok", "attempt": 1, "wall_ms": 94651.0,
                    "ts": "2026-10-04 08:01:34"})
    # 批准续跑的头：只有 request.started，lane 空，lane_source=resumed
    events.append(_started("trace-resumedhead", "sess-chart01", lane="", tier="", offset_ms=20000.0,
                           lane_source="resumed"))
    # 孤儿：同题号桥不在它身上（无 session_id），但时间紧跟那枚头 300 ms
    events.append(_event("trace-orphanchart", "step.started", {"worker": "chart", "step_id": "s", "sequence": 1},
                         20300.0, sequence=1))
    events.append(_finished("trace-orphanchart", "model.finished", record_id="o:gen", tier="analysis",
                            worker="chart", duration_ms=70000, start_ms=20400.0, sequence=2))
    events.append(_event("trace-orphanchart", "step.finished",
                         {"worker": "chart", "step_id": "s", "summary": {"duration_ms": 71000}}, 91000.0))

    # scope-09：generate 整段嵌在 retrieve 里 ⇒ 被剔（型 C）
    events.append(_started("trace-scope09", "sess-scope09", lane="analysis", tier="analysis", offset_ms=0.0))
    events.append(_finished("trace-scope09", "model.finished", record_id="s:classify", tier="analysis",
                            duration_ms=1000, start_ms=50, sequence=2))
    events.append(_finished("trace-scope09", "tool_call.finished", record_id="s:search", tool="search_docs",
                            worker="doc", duration_ms=5000, start_ms=2000, sequence=3))
    events.append(_finished("trace-scope09", "model.finished", record_id="s:gen", tier="analysis", worker="doc",
                            duration_ms=1000, start_ms=2500, sequence=4))
    frames.append({"id": "scope-09", "session_id": "sess-scope09", "attempt": 1, "kind": "ok"})
    sidecar.append({"id": "scope-09", "kind": "ok", "attempt": 1, "wall_ms": 20000.0, "ts": "2026-10-04 08:00:20"})

    # doc-04：只有未登记的检索账 ⇒ retrieve 型 B
    events.append(_started("trace-doc04", "sess-doc04", offset_ms=0.0))
    events.append(_finished("trace-doc04", "model.finished", record_id="d4:classify", tier="analysis",
                            duration_ms=1000, start_ms=100, sequence=2))
    events.append(_event("trace-doc04", "retrieval.completed",
                         {"duration_ms": 4000.0, "rewrite_count": 1, "top_k": 3}, 4200.0))
    frames.append({"id": "doc-04", "session_id": "sess-doc04", "attempt": 1, "kind": "ok"})
    sidecar.append({"id": "doc-04", "kind": "ok", "attempt": 1, "wall_ms": 9000.0, "ts": "2026-10-04 08:00:09"})

    # 一枚进不了任何题的孤儿（没有头配对，也没有 session）
    events.append(_event("trace-orphanloose", "model.started", {"worker": "export", "record_id": "l:1"}, 99000.0))
    events.append(_finished("trace-orphanloose", "model.finished", record_id="l:1", tier="analysis",
                            worker="export", duration_ms=500, start_ms=99100.0))

    _write_jsonl(directory / ("%s-traces.jsonl" % name), events)
    _write_jsonl(directory / ("%s-sidecar.jsonl" % name), sidecar)
    _write_jsonl(directory / ("%s-sidecar-frames.jsonl" % name), frames)
    return directory
@pytest.fixture(scope="module")
def facts():
    return ruler.source_facts()


_REAL: dict[str, dict] = {}


def real(window: str) -> dict:
    if window not in _REAL:
        _REAL[window] = ruler.build_window(window, REAL_DIR)
    return _REAL[window]


def demo(tmp_path: Path):
    directory = synth(tmp_path)
    return ruler.build_window("r636demo", directory)


# ==================== 正控：这把尺在量东西 ====================


def test_synthetic_window_is_measured_and_cross_checked(tmp_path: Path) -> None:
    data = demo(tmp_path)
    assert data["schema"] == "r636.stage-coverage/1"
    assert data["criterion"]["threshold_pct"] == 1.0
    assert data["mismatches"] == []
    keys = sorted(row["key"] for row in data["questions"])
    assert keys == ["chart-01", "doc-01", "doc-04", "scope-09"]


def test_per_question_numbers_are_r631_own_readings(tmp_path: Path) -> None:
    data = demo(tmp_path)
    chart = next(row for row in data["questions"] if row["key"] == "chart-01")
    assert chart["end_to_end_ms"] == 94651.0
    assert chart["segment_sum_ms"] == 2632.0
    assert chart["segments"] == 1
    doc = next(row for row in data["questions"] if row["key"] == "doc-01")
    assert doc["segment_sum_ms"] == 12000.0
    assert doc["missing_stages"] == ["rewrite", "reflect"]


def test_universe_names_every_trace_once(tmp_path: Path) -> None:
    data = demo(tmp_path)
    universe = data["universe"]
    assert universe["declared_distinct_traces"] == 7
    assert universe["counts"] == {"asked": 4, "no_denominator": 2, "resumed_head": 1, "bare_trace": 0}
    assert universe["named_items"] == universe["declared_distinct_traces"]
    named = [item["trace_id"] for group in data["named"].values() for item in group]
    assert len(named) == len(set(named)) == 7


def test_missing_stages_split_into_three_types_with_evidence(tmp_path: Path) -> None:
    data = demo(tmp_path)
    claims = {(row["key"], row["stage"]): row for row in data["claims"]}
    sibling = claims[("chart-01", "generate")]
    assert sibling["type"] == ruler.TYPE_NO_EVENT and sibling["shape"] == ruler.SHAPE_SIBLING_TRACE
    assert sibling["evidence"][0]["kind"] == "sibling_trace"
    assert claims[("doc-04", "retrieve")]["type"] == ruler.TYPE_UNRECOGNIZED
    assert claims[("doc-04", "rewrite")]["type"] == ruler.TYPE_NO_EVENT
    assert claims[("doc-04", "rewrite")]["shape"] == ruler.SHAPE_NO_SPAN
    nested = claims[("scope-09", "generate")]
    assert nested["type"] == ruler.TYPE_NESTED_OUT
    assert "excluded_count=1" in nested["evidence"][0]["reading"]
    for claim in data["claims"]:
        assert claim["evidence"], claim
        assert all(item["symbol"] and item["reading"] for item in claim["evidence"])


def test_orphan_pairing_uses_the_resumed_head_bridge(tmp_path: Path) -> None:
    data = demo(tmp_path)
    paired = {row["trace_id"]: row for row in data["orphans"]["paired"]}
    assert paired["trace-orphanchart"]["paired"]["key"] == "chart-01"
    assert paired["trace-orphanchart"]["paired"]["lag_ms"] == 300.0
    assert data["orphans"]["unpaired"] == [] or all(
        row["trace_id"] != "trace-orphanchart" for row in data["orphans"]["unpaired"])
    loose = next(row for row in data["named"][ruler.GROUP_NO_DENOM] if row["trace_id"] == "trace-orphanloose")
    assert loose["paired_to"] is None
    assert loose["reason"] == "no_request_started"
    chart = next(row for row in data["questions"] if row["key"] == "chart-01")
    assert chart["orphan_ms"] == 70000.0


def test_no_denominator_items_are_named_not_dropped(tmp_path: Path) -> None:
    data = demo(tmp_path)
    named = data["named"][ruler.GROUP_NO_DENOM]
    assert len(named) == data["universe"]["counts"][ruler.GROUP_NO_DENOM] == 2
    assert {row["trace_id"] for row in named} == {"trace-orphanchart", "trace-orphanloose"}


def test_render_declares_it_does_not_judge_the_gate(tmp_path: Path) -> None:
    lines = "\n".join(ruler.render(demo(tmp_path)))
    assert "不判 G-R51-1 绿不绿" in lines
    assert "：PASS" not in lines and "：FAIL" not in lines


# ==================== 反证刀（判据④：三把，每把配正控） ====================


def test_knife_a_recognizer_losing_a_stage_goes_red(tmp_path: Path) -> None:
    """把 retrieve 段的识别摘掉 ⇒ 本件复算的分段加总必与 R631 现跑数对不上。"""
    directory = synth(tmp_path)

    def blind(events):
        return [sample for sample in ruler.samples_from_events(events) if sample.stage != "retrieve"]

    with pytest.raises(ruler.MismatchError) as caught:
        ruler.build_window("r636demo", directory, recognizer=blind)
    assert "segment_sum_ms" in str(caught.value) or "对不上" in str(caught.value)
    # 正控：同一本原料，不注入假尺就一切相等
    assert ruler.build_window("r636demo", directory)["mismatches"] == []


def test_knife_b_dropping_no_denominator_goes_red(tmp_path: Path) -> None:
    """把 no_denominator 从母集摘掉 ⇒ 母集与账本枚数当场不相等。"""
    directory = synth(tmp_path)
    with pytest.raises(ruler.UniverseError):
        ruler.build_window("r636demo", directory, omit_groups=(ruler.GROUP_NO_DENOM,))
    # 正控：不摘组即一枚不丢
    data = ruler.build_window("r636demo", directory)
    assert data["universe"]["named_items"] == 7


def test_knife_c_type_c_without_exclusion_reading_goes_red(tmp_path: Path) -> None:
    """把一道「没发事件」的缺失手写成型 C（无剔除凭据）⇒ validate_claims 必拒。"""
    data = demo(tmp_path)
    rows = {row["trace_id"]: row for row in data["questions"]}
    doc = next(row for row in data["questions"] if row["key"] == "doc-01")
    forged = [{
        "key": "doc-01", "trace_id": doc["trace_id"], "stage": "rewrite",
        "type": ruler.TYPE_NESTED_OUT, "shape": "",
        "evidence": [{"kind": "source_shape", "symbol": "app/common/stage_timing.py::aggregate_stage_latency",
                      "reading": "总被剔了一点"}],
    }]
    with pytest.raises(ruler.EvidenceError):
        ruler.validate_claims(forged, rows, ruler.CANONICAL_STAGES)
    # 正控：真有剔除读数的那一枚（scope-09 的 generate）过检
    nested = [claim for claim in data["claims"] if claim["type"] == ruler.TYPE_NESTED_OUT]
    assert nested
    assert ruler.validate_claims(nested, rows, ruler.CANONICAL_STAGES)[ruler.TYPE_NESTED_OUT] == len(nested)


def test_claim_without_evidence_is_rejected(tmp_path: Path) -> None:
    data = demo(tmp_path)
    rows = {row["trace_id"]: row for row in data["questions"]}
    bare = [{"key": "doc-01", "trace_id": list(rows)[0], "stage": "reflect",
             "type": ruler.TYPE_NO_EVENT, "shape": ruler.SHAPE_NO_SPAN, "evidence": []}]
    with pytest.raises(ruler.EvidenceError):
        ruler.validate_claims(bare, rows, ruler.CANONICAL_STAGES)
    wrong_type = [{**data["claims"][0], "type": "guess"}]
    with pytest.raises(ruler.EvidenceError):
        ruler.validate_claims(wrong_type, rows, ruler.CANONICAL_STAGES)


def test_derived_ruler_detects_a_planted_call_site(tmp_path: Path) -> None:
    """影子端正控：派生尺读的不是「今天恰好零枚」，而是真能检出调用点。"""
    shadow = tmp_path / "app" / "pkg"
    shadow.mkdir(parents=True)
    (shadow / "mod.py").write_text(
        "def adopt():\n    from app.trace.spans import record_stage_event\n"
        "    return record_stage_event(None, stage='reflect', duration_ms=33)\n",
        encoding="utf-8")
    hits = ruler.call_sites_of("record_stage_event", tmp_path / "app")
    assert hits == ["app/pkg/mod.py::adopt"]
    # 反控：真实的 app/** 今天仍是零枚（这条形状一变，覆盖面账就得改口径）
    assert ruler.call_sites_of("record_stage_event", REPO_ROOT / "app") == []


def test_identityless_detector_reads_the_two_real_sites(facts) -> None:
    symbols = {row["file_symbol"] for row in facts["identityless_model_sites"]}
    assert "app/agents/nodes.py::respond" in symbols
    assert "app/agents/nodes.py::plan" in symbols
    tiers = {row["tier"] for row in facts["identityless_model_sites"]}
    assert {"ModelTier.CHAT", "ModelTier.PLAN"} <= tiers
    assert all(row["passes_config"] == "False" for row in facts["identityless_model_sites"])


def test_identityless_detector_ignores_a_site_that_passes_config(tmp_path: Path) -> None:
    shadow = tmp_path / "app" / "pkg"
    shadow.mkdir(parents=True)
    (shadow / "mod.py").write_text(
        "def bad():\n    return _make_model(ModelTier.CHAT, prompt=q).invoke([m], config=config)\n"
        "def good():\n    return _make_model(ModelTier.PLAN, prompt=p).invoke([m])\n",
        encoding="utf-8")
    rows = ruler.identityless_model_sites(tmp_path / "app")
    assert [row["file_symbol"] for row in rows] == ["app/pkg/mod.py::good"]


def test_derived_ruler_goes_red_when_the_tables_split(tmp_path: Path) -> None:
    """AST 与在册常量分家 ⇒ 派生尺拒绝出数（不许拿一套自造的表去归因）。"""
    shadow_app = tmp_path / "app"
    (shadow_app / "common").mkdir(parents=True)
    source = (REPO_ROOT / "app" / "common" / "stage_timing.py").read_text(encoding="utf-8")
    mutated = source.replace('"model.finished": "model",', '"model.finished": "model", "step.finished": "step",', 1)
    assert mutated != source
    timing = shadow_app / "common" / "stage_timing.py"
    timing.write_text(mutated, encoding="utf-8")
    with pytest.raises(ruler.DerivedError):
        ruler.source_facts(app_root=REPO_ROOT / "app", stage_timing_file=timing)
    # 正控：真件不炸
    assert ruler.source_facts()["finished_events"]["model.finished"] == "model"


def test_unregistered_stage_of_refuses_to_invent_a_stage(facts) -> None:
    assert ruler.unregistered_stage_of({"event_type": "step.progress", "payload": {"worker_count": 0}}, facts) == ("", None)
    assert ruler.unregistered_stage_of({"event_type": "request.completed", "payload": {}}, facts) == ("", None)
    row = {"event_type": "retrieval.completed", "payload": {"duration_ms": 100.0}}
    assert ruler.unregistered_stage_of(row, facts) == ("retrieve", 100.0)


def test_main_exit_codes(tmp_path: Path) -> None:
    directory = synth(tmp_path)
    assert ruler.main(["--window", "r636demo", "--dir", str(directory), "--json"]) == ruler.EXIT_OK
    assert ruler.main(["--window", "nosuchwindow", "--dir", str(directory)]) == ruler.EXIT_NO_INPUT

# ==================== 真窗对账（判据①②③：仓外导出件在位才跑） ====================


@real_inputs
@pytest.mark.parametrize("window,母集,无分母", [("run18", 105, 20), ("run19", 105, 19), ("run20k", 106, 19)])
def test_real_window_ledger_matches_r631_row_by_row(window: str, 母集: int, 无分母: int) -> None:
    data = real(window)
    assert data["criterion"]["r631_status"] == "measured"
    assert data["mismatches"] == []
    assert len(data["questions"]) == 母集
    assert data["reference_gap"]["asked_minus_rows"] == 0
    assert data["reference_gap"]["no_denom_minus_skipped"] == 0
    assert data["universe"]["counts"][ruler.GROUP_NO_DENOM] == 无分母
    assert data["universe"]["counts"][ruler.GROUP_RESUMED_HEAD] == 19
    assert data["universe"]["named_items"] == data["universe"]["declared_distinct_traces"]
    named = {item["trace_id"] for group in data["named"].values() for item in group}
    assert len(named) == data["universe"]["declared_distinct_traces"]


@real_inputs
@pytest.mark.parametrize("window", list(WINDOWS))
def test_real_window_every_missing_stage_is_type_named_and_evidenced(window: str) -> None:
    data = real(window)
    questions = {row["key"]: row for row in data["questions"]}
    assert questions
    for row in data["questions"]:
        for stage in row["missing_stages"]:
            claim = row["stages"][stage]["claim"]
            assert claim["type"] in ruler.MISSING_TYPES, (row["key"], stage, claim)
            assert claim["evidence"], (row["key"], stage)
    rollup = data["stage_rollup"]
    assert rollup["rewrite"]["producing_questions"] == 0
    assert rollup["reflect"]["producing_questions"] == 0
    assert rollup["classify"]["missing_questions"] == 0


@real_inputs
@pytest.mark.parametrize("window", list(WINDOWS))
def test_real_window_approved_resume_is_the_paired_orphan_lane(window: str) -> None:
    data = real(window)
    paired = {row["paired"]["key"] for row in data["orphans"]["paired"] if row["paired"]}
    heads = {item["key"] for item in data["named"][ruler.GROUP_RESUMED_HEAD]}
    assert paired == heads and len(heads) == 19
    for row in data["orphans"]["paired"]:
        assert row["paired"]["lag_ms"] >= 0
    resume_lane = next(entry for entry in data["nonproducing_lanes"]
                       if "批准续跑的头" in entry["scope"])
    assert resume_lane["questions"] == 19
    assert all(row["lane_source"] == "resumed" and row["lane"] == ""
               for row in data["named"][ruler.GROUP_RESUMED_HEAD])


@real_inputs
def test_real_windows_do_not_silently_drop_the_unpaired_orphan() -> None:
    """run18 的那枚「有 request.started 但 session 不在本窗帧账」的孤儿必须留在未归名，不许归题。"""
    data = real("run18")
    loose = [row for row in data["orphans"]["unpaired"]]
    assert len(loose) == 1
    assert loose[0]["reason"] == "session_absent_from_frames"
    assert loose[0]["sample_count"] == 6
    assert real("run19")["orphans"]["unpaired"] == []
    assert real("run20k")["orphans"]["unpaired"] == []


# ==================== 车道名字不许说过头话（今日在册病：把 a3 叫成「直答」）====================

def test_lane_names_cannot_overreach(tmp_path: Path) -> None:
    """合成窗：chart-01 的 generate 缺账在同胞 trace 上，绝不能被列进「闲聊直答」。"""
    data = demo(tmp_path)
    direct = next(e for e in data["nonproducing_lanes"] if "闲聊直答" in e["scope"])
    sibling = next(e for e in data["nonproducing_lanes"] if "同胞 trace" in e["scope"])
    assert "chart-01" in sibling["keys"] and "chart-01" not in direct["keys"]
    # 反控：把谓词里 orphan_traces 那一格摘掉，chart-01 就会混进直答（所以这一枚必须钉住）
    assert direct["predicate"].endswith("orphan_traces 为空")


@real_inputs
@pytest.mark.parametrize("window", WINDOWS)
def test_real_window_direct_lane_is_disjoint_from_sibling_traces(window: str) -> None:
    """真窗：直答题集与 a3 题集互斥，两集之和恰等于 generate 缺账题集（谁也不许替谁背名）。"""
    data = real(window)
    direct = next(e for e in data["nonproducing_lanes"] if "闲聊直答" in e["scope"])
    sibling = next(e for e in data["nonproducing_lanes"] if "同胞 trace" in e["scope"])
    a1 = {q["key"] for q in data["questions"]
          if (q["stages"]["generate"]["claim"] or {}).get("shape") == ruler.SHAPE_NO_IDENTITY}
    a3 = {q["key"] for q in data["questions"]
          if (q["stages"]["generate"]["claim"] or {}).get("shape") == ruler.SHAPE_SIBLING_TRACE}
    gmiss = {q["key"] for q in data["questions"] if q["stages"]["generate"]["missing"]}
    assert set(sibling["keys"]) == a3
    assert set(direct["keys"]) == a1
    assert set(direct["keys"]) & a3 == set()
    assert set(direct["keys"]) | set(sibling["keys"]) == gmiss
