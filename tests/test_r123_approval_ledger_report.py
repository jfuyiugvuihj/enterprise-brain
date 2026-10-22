"""R123 甲案（评分侧）：一份 run6 侧车要同时给出两把尺，报告要多印那一行，分母不许缩。

判据原文：跟进单 §57 + 施工单 R123 判据 ②④。全程离线：夹具与侧车都是 tmp_path 里现写的
合成料（`tests/fixtures/**` 与 `tests/test_evaluation_report.py` 在业主名下，本单一个字没改）。

两把尺的定义（写死在这里，免得口径漂）：
  * 甲案口径 = 主报告的 `answer_correctness`：分母 = 全部题数，卡闸的题拿**批准后的终答**计分。
  * 旧口径 = `pre_approval_ruler.answer_correctness`：分母不变，卡闸的题拿侧车 `pre_answer`
    （批准前那一帧）计分 ⇒ 与 run2..run5 同一把尺，能从同一份 run6 侧车重算出来。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_105 = REPO_ROOT / "tests" / "fixtures" / "business_evaluation_100.jsonl"

PARK_TEXT = "本轮在「生成图表」前等待你确认，确认后才会执行，目前尚未产出回答内容。"
FAILED_PLACEHOLDER = "<approval-failed-no-terminal-answer>"

#: 跟进单 §57 具名的那 18 枚（run3 起两枚报告都是这批；run4/§4BH.11 复算照旧 18 枚）。
RUN4_RUN5_HITL_IDS_18 = (
    "insight-07 chart-01 chart-02 chart-03 chart-04 approval-05 scope-02 scope-05 "
    "tool-01 tool-02 tool-04 report-02 report-05 report-07 report-09 report-10 "
    "report-11 report-12").split()


def write_jsonl(path: Path, rows) -> Path:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                    encoding="utf-8")
    return path


def _fixture_rows(tmp_path):
    return write_jsonl(tmp_path / "fixture.jsonl", [
        {"id": "doc-A", "category": "文档问答", "question": "住宿费标准？",
         "answer": "500元/晚", "must_contain": ["500元/晚"], "requires_evidence": True},
        {"id": "approval-B", "category": "审批判断", "question": "只有支付截图能报吗？",
         "answer": "需补开发票", "must_contain": ["需补开发票"], "requires_evidence": True},
        {"id": "chart-C", "category": "图表生成", "question": "画个柱状图",
         "answer": "柱状图", "must_contain": ["柱状图"], "requires_evidence": True},
    ])


def _answers(tmp_path):
    """甲案后的 answers：B 拿批准后的真终答，C 批准失败 ⇒ 占位串（不是半截 park 文本）。"""
    return write_jsonl(tmp_path / "answers.jsonl", [
        {"id": "doc-A", "answer": "住宿费标准是500元/晚。",
         "evidence": [{"source_name": "差旅制度", "locator": "第3页"}],
         "latency_ms": 100, "first_token_at": 1.0, "thinking_chars": None, "tool_calls": 1},
        {"id": "approval-B", "answer": "只有支付截图不能入账，需补开发票后由财务复核。",
         "evidence": [{"source_name": "口径登记表", "locator": "第9行"}],
         "latency_ms": 200, "first_token_at": 2.0, "thinking_chars": None, "tool_calls": 2},
        {"id": "chart-C", "answer": FAILED_PLACEHOLDER, "evidence": [],
         "latency_ms": 300, "first_token_at": None, "thinking_chars": None, "tool_calls": 1},
    ])


def _ledger(tmp_path, rows=None):
    rows = rows or [
        {"id": "doc-A", "kind": "ok", "attempt": 1, "sentinel": False, "evidence_n": 1,
         "answer_chars": 15, "tool_calls": 1, "wall_ms": 100.0, "ts": "x",
         "pre_kind": "ok", "pre_answer_chars": 15, "pre_evidence_n": 1, "approved": False,
         "approval_rounds": 0, "approval_http_status": None, "approval_error": ""},
        {"id": "approval-B", "kind": "approved_ok", "attempt": 1, "sentinel": False,
         "evidence_n": 1, "answer_chars": 24, "tool_calls": 2, "wall_ms": 200.0, "ts": "x",
         "pre_kind": "hitl", "pre_answer": PARK_TEXT, "pre_answer_chars": len(PARK_TEXT),
         "pre_evidence_n": 0, "approved": True, "approval_rounds": 1,
         "approval_http_status": 200, "approval_error": ""},
        {"id": "chart-C", "kind": "approval_failed", "attempt": 1, "sentinel": True,
         "evidence_n": 0, "answer_chars": len(FAILED_PLACEHOLDER), "tool_calls": 1,
         "wall_ms": 300.0, "ts": "x", "pre_kind": "hitl", "pre_answer": PARK_TEXT,
         "pre_answer_chars": len(PARK_TEXT), "pre_evidence_n": 0, "approved": False,
         "approval_rounds": 1, "approval_http_status": 403, "approval_error": "HTTP 403"},
    ]
    return write_jsonl(tmp_path / "sidecar.jsonl", rows)


def _by_id(path: Path):
    """把一份 JSONL 读成 id -> 行，给 answer_fn 用。"""
    return {str(row["id"]): row
            for row in (json.loads(line) for line in
                        path.read_text(encoding="utf-8").splitlines() if line.strip())}


def test_one_sidecar_gives_both_rulers_with_the_same_denominator(tmp_path):
    fixture = _fixture_rows(tmp_path)
    from app.quality.eval import evaluate_evaluation_set

    answers = _by_id(_answers(tmp_path))
    report = evaluate_evaluation_set(fixture, lambda row: answers[row["id"]],
                                     approval_ledger=_ledger(tmp_path))
    summary = report["approval_ledger"]
    assert summary["hitl_pre_n"] == 2 and summary["hitl_pre_ids"] == ["approval-B", "chart-C"]
    assert summary["approved_final_n"] == 1 and summary["approval_failed_n"] == 1
    assert summary["approval_failed_ids"] == ["chart-C"]
    assert summary["ledger_rows"] == 3 and summary["ledger_rows_not_in_fixture"] == []
    # 甲案口径：doc-A 与批准后的 approval-B 都对，chart-C 占位串判错
    assert report["total"] == 3
    assert report["answer_correctness"] == pytest.approx(2 / 3, abs=1e-4)
    assert report["evidence_coverage"] == pytest.approx(2 / 3, abs=1e-4)
    # 旧口径：分母仍是 3（不是 1），卡闸的两题拿 park 文本与「有没有出处」计分
    ruler = report["pre_approval_ruler"]
    assert ruler["total"] == 3, "旧口径的分母不许缩（判据 4）"
    assert ruler["answer_correctness"] == pytest.approx(1 / 3, abs=1e-4)
    assert ruler["evidence_coverage"] == pytest.approx(1 / 3, abs=1e-4)
    assert ruler["substituted_rows"] == 2


def test_report_prints_the_approval_line_with_both_numbers(tmp_path):
    from app.quality.eval import evaluate_evaluation_set, format_approval_line

    fixture = _fixture_rows(tmp_path)
    answers = _by_id(_answers(tmp_path))
    report = evaluate_evaluation_set(fixture, lambda row: answers[row["id"]],
                                     approval_ledger=_ledger(tmp_path))
    line = format_approval_line(report)
    assert "本轮经审批取得终答的题数 1 / 批准失败 1" in line
    assert "批准前卡在闸上 2 题" in line
    assert report["approval_line"] == line
    assert f"{report['answer_correctness']:.4f}" in line  # 甲案那个数
    assert f"{report['pre_approval_ruler']['answer_correctness']:.4f}" in line  # 旧口径那个数


def test_legacy_sidecar_without_pre_keys_fabricates_no_approvals(tmp_path):
    """run2..run5 那类旧侧车（没有 pre_* / approval_*）喂进来，不得凭空长出批准记录。"""
    from app.quality.eval import evaluate_evaluation_set

    fixture = _fixture_rows(tmp_path)
    legacy = write_jsonl(tmp_path / "sidecar-run5.jsonl", [
        {"id": "doc-A", "kind": "ok", "attempt": 1, "sentinel": False, "evidence_n": 1,
         "answer_chars": 15, "tool_calls": 1, "wall_ms": 100.0, "ts": "x"},
        {"id": "approval-B", "kind": "hitl", "attempt": 1, "sentinel": False,
         "evidence_n": 0, "answer_chars": len(PARK_TEXT), "tool_calls": 2,
         "wall_ms": 200.0, "ts": "x"},
    ])
    answers = _by_id(_answers(tmp_path))
    report = evaluate_evaluation_set(fixture, lambda row: answers[row["id"]],
                                     approval_ledger=legacy)
    summary = report["approval_ledger"]
    assert summary["hitl_pre_n"] == 0 and summary["approved_final_n"] == 0
    assert summary["approval_failed_n"] == 0 and summary["ledger_rows"] == 2
    # 没有可替换的那一帧 ⇒ 旧口径与甲案口径同值（不猜、不补）
    assert report["pre_approval_ruler"]["answer_correctness"] == report["answer_correctness"]
    assert report["pre_approval_ruler"]["substituted_rows"] == 0


def test_explicitly_named_missing_ledger_is_a_hard_error(tmp_path):
    """「没有账本」不许被读成「批准失败 0 题」：显式指定过就必须存在。"""
    from app.quality.eval import evaluate_evaluation_set

    fixture = _fixture_rows(tmp_path)
    with pytest.raises(FileNotFoundError):
        evaluate_evaluation_set(fixture, lambda row: {}, approval_ledger=tmp_path / "nope.jsonl")


def test_no_ledger_at_all_leaves_the_report_shape_untouched(tmp_path, monkeypatch):
    from app.quality.runner import run_recorded_evaluation

    monkeypatch.delenv("EVAL_APPROVAL_LEDGER", raising=False)
    monkeypatch.delenv("EVAL_SIDECAR", raising=False)
    report = run_recorded_evaluation(_fixture_rows(tmp_path), _answers(tmp_path),
                                     tmp_path / "report.json")
    assert "approval_ledger" not in report and "pre_approval_ruler" not in report
    assert "approval_line" not in report


def test_runner_prints_the_line_once_and_still_writes_the_json(tmp_path, monkeypatch, capsys):
    from app.quality.runner import run_recorded_evaluation

    monkeypatch.setenv("EVAL_APPROVAL_LEDGER", str(_ledger(tmp_path)))
    report = run_recorded_evaluation(_fixture_rows(tmp_path), _answers(tmp_path),
                                     tmp_path / "report.json")
    printed = capsys.readouterr().out.strip().splitlines()
    assert len(printed) == 1 and printed[0] == report["approval_line"]
    saved = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert saved["approval_ledger"]["approved_final_n"] == 1
    assert saved["pre_approval_ruler"]["total"] == 3


def test_resolve_approval_ledger_reads_env_in_the_documented_order(monkeypatch):
    from app.quality.runner import resolve_approval_ledger

    monkeypatch.setenv("EVAL_SIDECAR", r"%TEMP%\evalrun\sidecar-run6.jsonl")
    assert resolve_approval_ledger() == r"%TEMP%\evalrun\sidecar-run6.jsonl"
    monkeypatch.setenv("EVAL_APPROVAL_LEDGER", r"%TEMP%\evalrun\archived.jsonl")
    assert resolve_approval_ledger() == r"%TEMP%\evalrun\archived.jsonl"
    monkeypatch.setenv("EVAL_APPROVAL_LEDGER", "   ")
    assert resolve_approval_ledger() == r"%TEMP%\evalrun\sidecar-run6.jsonl"
    monkeypatch.delenv("EVAL_SIDECAR")
    assert resolve_approval_ledger() is None


def test_approval_failed_row_is_a_real_answer_not_a_coverage_gap(tmp_path):
    """批准失败要留在分母里：它不能变成"缺题"，否则覆盖闸一炸，整轮 73 分钟白跑。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "r123_collect_under_test", REPO_ROOT / "scripts" / "collect_evaluation_answers.py")
    collector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(collector)

    rows = [{"id": "chart-C", "question": "画个柱状图"}]
    answers, failures = collector.collect_answers(
        rows,
        lambda row: {"answer": FAILED_PLACEHOLDER, "evidence": [], "first_token_at": None,
                     "thinking_chars": None, "tool_calls": 1},
        answer_source="eval_transport_ask_v2:transport")
    assert failures == [] and len(answers) == 1
    collector.assert_coverage(rows, answers)


def test_the_18_named_rows_keep_105_as_denominator_in_both_rulers(tmp_path):
    """拿真 105 题夹具验判据 4：甲案不改分母，只把 18 枚的答案换成终答。"""
    from app.quality.eval import evaluate_evaluation_set

    rows = [json.loads(line) for line in
            FIXTURE_105.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    assert len(rows) == 105
    parked = set(RUN4_RUN5_HITL_IDS_18)
    assert len(parked) == 18 and parked <= {row["id"] for row in rows}
    terminal = {row["id"]: " ".join([str(row["answer"])] +
                                    [str(item) for item in row["must_contain"]])
                for row in rows}
    ledger_rows = []
    for row in rows:
        hit = row["id"] in parked
        ledger_rows.append({"id": row["id"], "kind": "approved_ok" if hit else "ok",
                            "attempt": 1, "sentinel": False, "evidence_n": 1,
                            "answer_chars": len(terminal[row["id"]]), "tool_calls": 1,
                            "wall_ms": 1.0, "ts": "x",
                            "pre_kind": "hitl" if hit else "ok",
                            **({"pre_answer": PARK_TEXT} if hit else {}),
                            "approved": hit, "approval_rounds": 1 if hit else 0,
                            "approval_http_status": 200 if hit else None,
                            "approval_error": ""})
    fixture = write_jsonl(tmp_path / "evaluation-105.jsonl", rows)
    answers = {row["id"]: {"answer": terminal[row["id"]],
                           "evidence": [{"source_name": "口径登记表", "locator": "第1行"}],
                           "latency_ms": 1000} for row in rows}
    report = evaluate_evaluation_set(
        fixture, lambda row: answers[row["id"]],
        approval_ledger=write_jsonl(tmp_path / "sidecar-run6.jsonl", ledger_rows))
    assert report["total"] == 105
    assert report["approval_ledger"]["hitl_pre_n"] == 18
    assert report["approval_ledger"]["approved_final_n"] == 18
    assert report["approval_ledger"]["approval_failed_n"] == 0
    assert report["answer_correctness"] == 1.0, "甲案口径：18 枚拿到终答后全部答对"
    ruler = report["pre_approval_ruler"]
    assert ruler["total"] == 105 and ruler["substituted_rows"] == 18
    # 🔴 旧口径的第二个毛病（本案顺带量出来，写进交付说明）：那 18 枚里有三枚的 must_contain
    # 恰好被「等待确认」那句话本身满足（chart-01 / chart-02 要「图」，tool-04 要「图表」，
    # 而 park 文本写着「生成图表」）⇒ 旧口径不仅分母撒谎，还会白送假阳性。90/105 = 0.8571。
    assert ruler["answer_correctness"] == pytest.approx(90 / 105, abs=1e-4)
    park_hits = sorted(row["id"] for row in rows
                       if row["id"] in parked
                       and all(str(item) in PARK_TEXT for item in row["must_contain"]))
    assert park_hits == ["chart-01", "chart-02", "tool-04"]
