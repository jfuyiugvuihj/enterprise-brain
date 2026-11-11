"""R205a 复现件（判据⑤）：run6 的真实形状 —— 一发实测跨度 8 h、帧账 wall_ms 55.9 s。

数字取自 run6 现场（evalrun 目录里的 answers-run6.jsonl 与 sidecar-run6.jsonl 逐字抄来），
夹具题面是 tmp_path 里现写的合成料，评测集一个字没动。

未改代码上这一件必须红：采集器拿整调用跨度冒充「这一发的时延」，平均值就被那一发抬到
逐题最大值之上（run6 报告 latency_ms.average = 351 121 ms，而诚实的逐题最大是 272.2 s）。
"""
from __future__ import annotations

import json
from pathlib import Path

#: run6 实测：09-23 23:34 → 09-24 07:40 宿主整机待机，那一发的采集器跨度被冻进 8 h 6 min
FROZEN_ID = "data-06"
FROZEN_MEASURED_MS = 29265911.2
FROZEN_WALL_MS = 55930.8

#: 同窗三枚无重试题：实测与帧账逐位对齐（run6 里 105 题有 102 题是这个形状，差 <0.1%）
CLEAN_ROWS = [
    ("doc-08", 20378.7, 20375.2),
    ("doc-13", 18080.3, 18077.3),
    ("metric-18", 24016.6, 24013.5),
]

ALL_ROWS = [(FROZEN_ID, FROZEN_MEASURED_MS, FROZEN_WALL_MS)] + CLEAN_ROWS


def write_jsonl(path: Path, rows) -> Path:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                    encoding="utf-8")
    return path


def _fixture(tmp_path: Path) -> Path:
    return write_jsonl(tmp_path / "fixture.jsonl", [
        {"id": row_id, "category": "文档问答", "tier": "问答", "question": f"问题 {row_id}？",
         "answer": "500元/晚", "must_contain": ["500元/晚"], "requires_evidence": True}
        for row_id, _measured, _wall in ALL_ROWS
    ])


def _answers(tmp_path: Path) -> dict:
    """采集器写出来的那份逐题答案：latency_ms 就是它当时的整调用跨度。"""
    return {row_id: {"id": row_id, "answer": "住宿费标准是500元/晚。",
                     "evidence": [{"source_name": "差旅制度", "locator": "第3页"}],
                     "first_token_at": None, "thinking_chars": None, "tool_calls": 1,
                     "latency_ms": measured}
            for row_id, measured, _wall in ALL_ROWS}


def _ledger(tmp_path: Path) -> Path:
    """帧账 sidecar：每发尝试自己的真实跨度，被打回的重试不记账。"""
    return write_jsonl(tmp_path / "sidecar-run6.jsonl", [
        {"id": row_id, "kind": "ok", "attempt": 3 if row_id == FROZEN_ID else 1,
         "sentinel": False, "evidence_n": 1, "answer_chars": 14, "tool_calls": 1,
         "wall_ms": wall, "ts": "x"}
        for row_id, _measured, wall in ALL_ROWS
    ])


def _honest_answers(tmp_path: Path) -> dict:
    """同一批题，把那一发的实测值换成诚实跨度 —— 只有时延来源不同。"""
    return {row_id: {**_answers(tmp_path)[row_id],
                     "latency_ms": wall if row_id == FROZEN_ID else measured}
            for row_id, measured, wall in ALL_ROWS}


def _report(tmp_path: Path, answers: dict):
    from app.quality.eval import evaluate_evaluation_set

    return evaluate_evaluation_set(_fixture(tmp_path), lambda row: answers[row["id"]],
                                   approval_ledger=_ledger(tmp_path))


def test_the_frozen_attempt_must_not_be_averaged_into_the_latency_cell(tmp_path):
    """判据①：报告那一格今后只能由「每发尝试自己的真实跨度」构成。"""
    cell = _report(tmp_path, _answers(tmp_path))["latency_ms"]

    # ⓪ 拿帧账里诚实的逐题最大值当尺：平均值一旦越过它，格子里就混进了非单发跨度
    honest_max = max(wall for _row_id, _measured, wall in ALL_ROWS)
    assert cell["average"] <= honest_max, (
        f"average={cell['average']} 大于逐题诚实跨度最大值 {honest_max}"
        " ⇒ 8 h 那一发仍被算进平均（run6 的假形状）")

    # ① 平均值大于逐题最大值 —— 这种一眼假的形状必须当场不存在
    assert cell["average"] <= cell["max"], (
        f"average={cell['average']} 大于逐题最大值 {cell.get('max')}：时延格里混进了"
        "非单发跨度（run6 的那一发 8 h 待机）")
    # ② 越界那一发要被逐题列出来，并说清拿什么替代了它
    listed = {row["id"]: row for row in cell["suspect"]}
    assert FROZEN_ID in listed, "被冻的那一发必须逐题列出，不许静默进平均"
    assert listed[FROZEN_ID]["reported_ms"] == FROZEN_MEASURED_MS
    assert listed[FROZEN_ID]["used_ms"] == FROZEN_WALL_MS
    # ③ 逐题列全 ⇒ 无重试的三枚不许被牵连
    assert [row["id"] for row in cell["suspect"]] == [FROZEN_ID]
    # ④ 平均值与逐题最大值都落回诚实量级（帧账全表 max 272.2 s / avg 50.8 s 同量级）
    assert cell["max"] == FROZEN_WALL_MS
    assert cell["average"] < 360000.0, "平均值仍被 8 h 那一发抬起 ⇒ 记账没修好"


def test_the_three_score_cells_do_not_move_when_only_latency_bookkeeping_changes(tmp_path):
    """判据③：时延记账可以修，correctness / evidence / unsupported_claim_rate 逐位不变。"""
    frozen = _report(tmp_path, _answers(tmp_path))
    honest = _report(tmp_path, _honest_answers(tmp_path))

    for key in ("answer_correctness", "evidence_coverage", "unsupported_claim_rate",
                "category_metrics"):
        assert frozen[key] == honest[key], f"{key} 被时延记账改动影响到了"
