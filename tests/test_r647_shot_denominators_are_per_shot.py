# -*- coding: utf-8 -*-
r"""R647 常驻牙：R636 覆盖面账的端到端分母按**发**取；把 shots 折回一枚分母必须当场红。

对着的病（10-04 现取）：scripts/r636_stage_coverage.py::read_inputs 原先读
scripts/r631_stage_sum_delta.py::read_sidecar 那本**题号级折叠视图**当分母（同题多发取 attempt 最大、
并列取后一行），而 build_window 的对账基准取自 scripts/r631_stage_sum_delta.py::collect —— R643
（并树 f0c4572）之后那是按 trace_id 索引的**发级真值**。⇒ 同题两发的两枚 trace 都拿到同一枚折叠
分母，逐枚对账当场崩。真窗读数：run20k／doc-04 的 27,490.9 对 27,244.6，error_pct 31.4064 对 30.7863。

本文件钉三件事，各配正控：
① 同题两发各拿各的分母 —— 不平均、不取最大、不折一枚装作对上（合成窗，环境无关）；
② 把两发折回一枚分母（fold_legacy，复现旧形状）⇒ build_window 当场 MismatchError 并点名那一枚 trace；
③ r636 不再读那本折叠视图 —— AST 现读＋影子端正控（防「今天恰好读不到」的假绿）。

牙不吃盘面状态：不判 dirty、不判盘上字节与 HEAD blob 的关系（同族事故 #96／#107／#113）。
事件行与帧账行的形状复用 tests/test_r636_stage_coverage.py 的那套构造器 —— 本单刻意不复制第二套，
抄一遍形状就是这族病（手抄坐标）的另一张脸；那枚件改名本牙会响，不会静默。
真窗那一枚只在 %TEMP%\evalrun 三本导出件在位时跑；不在位即 skip，不改判语。
"""

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclass 要能从 sys.modules 找回本模块
    spec.loader.exec_module(module)
    return module


host = _load(REPO_ROOT / "tests" / "test_r636_stage_coverage.py", "r647_host_r636_tests")
ruler = host.ruler

NAME = "r647demo"
WINDOWS = ("run18", "run19", "run20k")
REAL_DIR = ruler.default_directory()
real_inputs = pytest.mark.skipif(
    not all((REAL_DIR / ("%s-%s.jsonl" % (w, kind))).exists()
            for w in WINDOWS for kind in ("traces", "sidecar", "sidecar-frames")),
    reason="仓外导出件不在位（%%TEMP%%\\evalrun）⇒ 真窗那一枚不参与判语")


def _rows(trace_id: str, session_id: str, classify_ms: int) -> list[dict]:
    """一发题的三段账：classify ／ retrieve（search_docs）／ generate（worker model）。

    形状与 tests/test_r636_stage_coverage.py::synth 里 doc-01 那一格同一套构造器。
    """
    started = host._started(trace_id, session_id)
    classify = host._finished(trace_id, "model.finished", record_id="%s:classify" % trace_id,
                              tier="analysis", duration_ms=classify_ms, start_ms=50.0, sequence=2)
    search = host._finished(trace_id, "tool_call.finished", record_id="%s:search" % trace_id,
                            tool="search_docs", worker="doc", duration_ms=400, start_ms=600.0, sequence=3)
    generate = host._finished(trace_id, "model.finished", record_id="%s:gen" % trace_id,
                              tier="analysis", worker="doc", duration_ms=100, start_ms=1200.0, sequence=4)
    return [started, classify, search, generate]


def synth(tmp_path: Path) -> Path:
    """doc-04 问两发（各一枚 trace、各一枚分母）＋ doc-01 问一发：把折叠病摆成最小形状。

    两发的跨度刻意差 500 ms（1,000／1,500），且 segment_sum 各 600／800 ms：
    折叠一次必然改动其中一枚的分母，误差错到另一枚头上 ⇒ 对账当场红，红到点名。
    """
    directory = tmp_path / "evalrun"
    directory.mkdir(parents=True, exist_ok=True)
    events: list[dict] = []
    frames: list[dict] = []
    sidecar: list[dict] = []

    events += _rows("t-04-a", "s-04-a", 100)
    frames.append({"id": "doc-04", "session_id": "s-04-a", "attempt": 1, "kind": "ok"})
    sidecar.append({"id": "doc-04", "kind": "ok", "attempt": 1, "wall_ms": 1000.0,
                    "ts": "2026-10-04 08:00:09", "session_id": "s-04-a"})

    events += _rows("t-04-b", "s-04-b", 300)
    frames.append({"id": "doc-04", "session_id": "s-04-b", "attempt": 1, "kind": "ok"})
    sidecar.append({"id": "doc-04", "kind": "ok", "attempt": 1, "wall_ms": 1500.0,
                    "ts": "2026-10-04 08:00:12", "session_id": "s-04-b"})

    events += _rows("t-01", "s-01", 200)
    frames.append({"id": "doc-01", "session_id": "s-01", "attempt": 1, "kind": "ok"})
    sidecar.append({"id": "doc-01", "kind": "ok", "attempt": 1, "wall_ms": 30000.0,
                    "ts": "2026-10-04 08:00:30", "session_id": "s-01"})

    host._write_jsonl(directory / ("%s-traces.jsonl" % NAME), events)
    host._write_jsonl(directory / ("%s-sidecar.jsonl" % NAME), sidecar)
    host._write_jsonl(directory / ("%s-sidecar-frames.jsonl" % NAME), frames)
    return directory


def reference_by_trace(directory: Path) -> dict[str, dict]:
    """对账基准：r631 现跑的 collect()，按 trace_id 索引的发级真值（不是折叠视图）。"""
    collected = ruler.load_r631().collect(window=NAME, directory=directory)
    return {str(row["trace_id"]): row for row in collected["rows"]}


# ==================== ① 逐发各拿各的分母 ====================


def test_two_shots_of_one_question_get_two_denominators(tmp_path: Path) -> None:
    directory = synth(tmp_path)
    data = ruler.build_window(NAME, directory)
    rows = [row for row in data["questions"] if row["key"] == "doc-04"]
    assert len(rows) == 2, rows
    readings = sorted(row["end_to_end_ms"] for row in rows)
    assert readings == [1000.0, 1500.0], readings
    assert len({row["end_to_end_ms"] for row in rows}) == 2, "两发挤成同一枚分母 = 病没收干净"
    assert data["mismatches"] == []


def test_every_denominator_equals_the_r631_shot_reading(tmp_path: Path) -> None:
    directory = synth(tmp_path)
    data = ruler.build_window(NAME, directory)
    reference = reference_by_trace(directory)
    assert data["questions"], "账本是空的：这枚牙没在量任何东西"
    for row in data["questions"]:
        expected = round(float(reference[row["trace_id"]]["end_to_end_ms"]), 1)
        assert row["end_to_end_ms"] == expected, (row["trace_id"], row["end_to_end_ms"], expected)
        assert row["error_pct"] == pytest.approx(float(reference[row["trace_id"]]["error_pct"])), row["trace_id"]


def test_denominators_never_average_or_take_the_max(tmp_path: Path) -> None:
    """折叠的三种死法（平均／取最大／取后一行）里，平均与取最大最容易冒充「对上了」。"""
    directory = synth(tmp_path)
    denominators = ruler.read_inputs(NAME, directory)["denominators"]
    assert denominators["t-04-a"] == 1000.0, denominators
    assert denominators["t-04-b"] == 1500.0, denominators
    assert denominators["t-04-a"] != (1000.0 + 1500.0) / 2.0
    assert set(denominators) == {"t-04-a", "t-04-b", "t-01"}, "分母必须按 trace_id 索引，不许落回题号"


def test_read_inputs_names_the_multi_shot_question(tmp_path: Path) -> None:
    """发级账抬头要摆出「这题问了两发、各多少毫秒、谁也没归名失败」。"""
    directory = synth(tmp_path)
    ledger = ruler.read_inputs(NAME, directory)["shot_ledger"]
    assert ledger["keyed"] == "trace", ledger
    assert ledger["rows_read"] == 3 and ledger["shots"] == 3 and ledger["attributed"] == 3, ledger
    assert ledger["traces_with_denominator"] == 3, ledger
    assert ledger["multi_shot_questions"] == {"doc-04": 2}, ledger
    assert ledger["unattributed_labels"] == [] and ledger["no_positive_span_labels"] == []
    assert ledger["fold_legacy"] is False and ledger["legacy_conflicts"] == []
    spread = next(item for item in ledger["spreads"] if item["key"] == "doc-04")
    assert spread["shots_ms"] == [1000.0, 1500.0] and spread["spread_ms"] == 500.0, spread
    assert spread["labels"] == ["doc-04 发1/2", "doc-04 发2/2"], spread


def test_universe_split_is_still_the_four_groups(tmp_path: Path) -> None:
    """本单不动母集四格：三枚 trace 全落 asked，另三格一枚不多一枚不少。"""
    data = ruler.build_window(NAME, synth(tmp_path))
    assert data["universe"]["counts"] == {"asked": 3, "no_denominator": 0, "resumed_head": 0, "bare_trace": 0}
    assert data["universe"]["named_items"] == data["universe"]["declared_distinct_traces"] == 3


# ==================== ② 折回一枚分母 ⇒ 当场红（本单的反证牙）====================


def test_folding_shots_back_to_one_denominator_goes_red(tmp_path: Path) -> None:
    directory = synth(tmp_path)
    with pytest.raises(ruler.MismatchError) as caught:
        ruler.build_window(NAME, directory, fold_legacy=True)
    text = str(caught.value)
    assert "t-04-a" in text, text
    assert "end_to_end_ms" in text and "error_pct" in text, text
    assert "1500.0" in text and "1000.0" in text, text
    # 正控：同一本原料，不折叠就一枚都对得上
    assert ruler.build_window(NAME, directory)["mismatches"] == []


def test_the_fold_knife_really_folds(tmp_path: Path) -> None:
    """反控：fold_legacy 必须真把两发折成一枚分母，否则上面那枚红就不是「折叠」咬的。"""
    directory = synth(tmp_path)
    folded = ruler.read_inputs(NAME, directory, fold_legacy=True)["denominators"]
    honest = ruler.read_inputs(NAME, directory)["denominators"]
    assert folded["t-04-a"] == folded["t-04-b"] == 1500.0, folded
    assert honest["t-04-a"] == 1500.0 or honest["t-04-a"] != folded["t-04-a"], honest
    assert honest["t-04-a"] == 1000.0 and honest["t-04-b"] == 1500.0, honest
    ledger = ruler.read_inputs(NAME, directory, fold_legacy=True)["shot_ledger"]
    assert ledger["fold_legacy"] is True and ledger["legacy_conflicts"], ledger


def test_render_prints_the_shot_leg(tmp_path: Path) -> None:
    """印面要说清分母是按发取的，并且继续 declare 自己不判绿。"""
    directory = synth(tmp_path)
    lines = "\n".join(ruler.render(ruler.build_window(NAME, directory)))
    assert "端到端腿按发取：sidecar_wall_ms 读了 3 行 sidecar ⇒ 3 发连上 3 枚 trace" in lines, lines
    assert "题号级折叠视图已停用" in lines and "复现中" not in lines, lines
    assert "同题多发的题号" in lines and "doc-04" in lines, lines
    assert "不判 G-R51-1 绿不绿" in lines
    assert "：PASS" not in lines and "：FAIL" not in lines


def test_render_flags_the_folded_view(tmp_path: Path) -> None:
    """折叠复现要在印面上留名：那把刀咬出来的账，纸得说清它在复现病形，不是在读真值。"""
    directory = synth(tmp_path)
    data = ruler.build_window(NAME, directory)
    folded_ledger = ruler.read_inputs(NAME, directory, fold_legacy=True)["shot_ledger"]
    with pytest.raises(ruler.MismatchError):
        ruler.build_window(NAME, directory, fold_legacy=True)
    assert "折叠视图复现中" in "\n".join(ruler.render({**data, "shot_ledger": folded_ledger}))
    assert "未归名 无" in "\n".join(ruler.render(data))


# ==================== ③ 折叠视图不再被读（AST 现读＋影子端正控）====================


def called_attributes(source: str) -> set[str]:
    return {node.attr for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Attribute)}


def test_r636_no_longer_reads_the_folded_view() -> None:
    source = (REPO_ROOT / "scripts" / "r636_stage_coverage.py").read_text(encoding="utf-8")
    attrs = called_attributes(source)
    assert "read_sidecar" not in attrs, "又去读题号级折叠视图了 = R647 的病复发"
    assert {"read_sidecar_shots", "read_frames_shots", "trace_sessions_from_events",
            "_build_shot_leg"} <= attrs, attrs
    # 影子端正控：同一把检测器读到老形状必须认出来（不许是「今天恰好读不到」）
    assert "read_sidecar" in called_attributes("values = r631.read_sidecar(path)\n")
    assert "read_sidecar" not in called_attributes("values = r631.read_sidecar_shots(path)[0]\n")


def test_r631_still_owns_the_folded_view(tmp_path: Path) -> None:
    """r636 一字未动 r631：折叠视图还在那件里当对照与病形复现（本单禁区）。"""
    r631 = ruler.load_r631()
    sidecar = synth(tmp_path) / ("%s-sidecar.jsonl" % NAME)
    folded = r631.read_sidecar(sidecar)
    assert folded.keyed == "question" and sorted(folded.values) == ["doc-01", "doc-04"], folded
    assert folded.duplicates == ("doc-04",), folded
    assert set(folded.values) == {"doc-01", "doc-04"} and folded.values["doc-04"] == 1500.0


# ==================== 真窗（事故原形状：run20k／doc-04 的两发）====================


@real_inputs
def test_real_run20k_doc04_keeps_both_shot_denominators() -> None:
    """事故原形状：run20k／doc-04 的两枚 trace 必须同时摆出 27,244.6 与 27,490.9。

    刻意不抄 trace_id 字面（这族病就是手抄坐标）：只按题号取那两行，逐枚与 r631 现跑对。
    """
    data = ruler.build_window("run20k", REAL_DIR)
    rows = [row for row in data["questions"] if row["key"] == "doc-04"]
    assert len(rows) == 2, rows
    assert sorted(row["end_to_end_ms"] for row in rows) == [27244.6, 27490.9], rows
    assert len({row["trace_id"] for row in rows}) == 2 and len({row["error_pct"] for row in rows}) == 2, rows
    by_trace = {row["trace_id"]: round(float(row["end_to_end_ms"]), 1) for row in rows}
    reference = {str(row["trace_id"]): round(float(row["end_to_end_ms"]), 1)
                 for row in ruler.load_r631().collect(window="run20k", directory=REAL_DIR)["rows"]}
    assert all(by_trace[trace] == reference[trace] for trace in by_trace), (by_trace, reference)
    assert data["mismatches"] == []


@real_inputs
def test_real_run20k_goes_red_when_the_shots_are_folded() -> None:
    """把真窗折回旧形状 ⇒ 必须复现事故 #R647 那两枚数：27,490.9 对 27,244.6。"""
    with pytest.raises(ruler.MismatchError) as caught:
        ruler.build_window("run20k", REAL_DIR, fold_legacy=True)
    text = str(caught.value)
    assert "doc-04" in text and "27490.9" in text and "27244.6" in text, text


@real_inputs
def test_real_windows_still_do_not_pass_the_gate(tmp_path: Path) -> None:
    """判据④：本单不推绿。三窗账全（rc 语义那句），两条阈值线仍归 R631 判 FAIL。"""
    for window in WINDOWS:
        data = ruler.build_window(window, REAL_DIR)
        assert data["mismatches"] == [], window
        assert data["criterion"]["r631_status"] == "measured", window
        assert ruler.main(["--window", window, "--dir", str(REAL_DIR)]) == ruler.EXIT_OK, window
        r631 = ruler.load_r631()
        collected = r631.collect(window=window, directory=REAL_DIR)
        failing = [row["key"] for row in collected["rows"] if not row["within_threshold"]]
        assert len(failing) == len(collected["rows"]), (window, len(failing), len(collected["rows"]))
        assert r631.decide_rc(collected) != r631.RC_OK, window
