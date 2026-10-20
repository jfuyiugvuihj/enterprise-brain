"""R595 常驻钉（三）：诚实跨度只认 sidecar 的 ``wall_ms``，``latency_ms`` 一律拒收当跨度。

对着的病：跟进单 §21 R205a／看板 §4BV——真实适配器故意不自报 ``latency_ms``
（``scripts/eval_transport_ask_v2.py:1407``），采集器旧行为曾把 ``perf_counter`` 的**整调用**跨度顶上去
（重试、重试 sleep、排队轮询观测窗、09-23 那 8 h 6 min 整机待机全在里面），run6 因此印出 average 351 121 ms。
本钉保证：本件的聚合里**一枚 ``latency_ms`` 都不许出现**；它只被读来点名差出容忍带的题。
判据⑤ 反证二把就在这一枚钉上：**把跨度换成 ``latency_ms``，本文件必红**。
"""

import importlib.util
import json
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "r595_latency_readout", REPO_ROOT / "scripts" / "r595_latency_readout.py")
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)


def write_jsonl(path: Path, rows) -> None:
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def rows_from(shape, tier="问答", category="文档问答"):
    """shape = [(题号, answers 那枚 latency_ms, sidecar 那枚 wall_ms)]。"""
    fixture = [{"id": rid, "tier": tier, "category": category, "question": "?"}
               for rid, _inbook, _ledger in shape]
    answers = [{"id": rid, "answer": "略", "evidence": [], "latency_ms": inbook}
               for rid, inbook, _ledger in shape]
    sidecar = [{"id": rid, "kind": "ok", "attempt": 1, "wall_ms": ledger}
               for rid, _inbook, ledger in shape]
    return fixture, answers, sidecar


def case(tmp_path, fixture, answers, sidecar, label="span"):
    paths = {}
    for name, rows in (("fixture", fixture), ("answers", answers), ("sidecar", sidecar)):
        path = Path(tmp_path) / ("%s-%s.jsonl" % (name, label))
        write_jsonl(path, rows)
        paths[name] = path
    return paths, mod.collect(paths["answers"], paths["fixture"], paths["sidecar"],
                              transport_source=mod.DEFAULT_TRANSPORT_SOURCE, label=label)


#: run6 里那三枚被整机待机污染的原件（跟进单 §93.9 逐位复算过）：latency_ms 是 wall_ms 的 6.5~523 倍。
RUN6_SHAPE = [("data-04", 1342781.94, 35064.5), ("data-06", 29265911.25, 55930.8),
              ("data-07", 1206484.047, 186854.4)]


def test_wall_ms_is_the_only_span_that_reaches_the_aggregate(tmp_path):
    """三枚 latency_ms 全是几十倍的假数：纸面逐枚点名，但 avg/p50/p95 只能由 wall_ms 构成。"""
    fixture, answers, sidecar = rows_from(RUN6_SHAPE, tier="分析", category="Excel计算")
    paths, data = case(tmp_path, fixture, answers, sidecar)
    cell = data["cells"][mod.GROUP_ANALYSIS_REPORT]
    assert cell["n_used"] == 3
    assert cell["p95_rank"] == 186854.4                 # 最大那枚 **wall_ms**
    assert cell["p50_rank"] == 55930.8
    assert cell["max"] == 186854.4 and cell["min"] == 35064.5
    assert cell["avg"] == round((35064.5 + 55930.8 + 186854.4) / 3, 1)
    for poisoned in (1342781.94, 29265911.25, 1206484.047, 29265911.2, 1342781.9):
        assert poisoned not in (cell["avg"], cell["p50_rank"], cell["p95_rank"], cell["max"], cell["min"])
    assert sorted(row["id"] for row in data["drift"]) == ["data-04", "data-06", "data-07"]
    assert {row["action"] for row in data["drift"]} == {"repaired_to_frame_ledger"}   # 在册判器现给
    assert {row["latency_ms"] for row in data["drift"]} == {1342781.94, 29265911.25, 1206484.047}
    text = "\n".join(mod.render(data))
    assert "一枚都没拿来聚合" in text and "data-06" in text and "差出容忍带" in text


def test_zero_drift_when_the_two_columns_agree(tmp_path):
    """干净窗（run13/14 的形状）：两列互证 ⇒ 点名零枚，但聚合用的仍然只有 wall_ms。"""
    fixture, answers, sidecar = rows_from([("doc-01", 25640.02, 25636.4), ("doc-02", 9485.768, 9483.7)])
    paths, data = case(tmp_path, fixture, answers, sidecar, label="clean")
    assert data["drift"] == [] and data["rejects"] == []
    assert data["cells"][mod.GROUP_QA]["p95_rank"] == 25636.4     # wall_ms，不是 25640.02
    assert "差出容忍带：零枚" in "\n".join(mod.render(data))


def test_a_row_without_a_sidecar_line_is_refused_not_backfilled(tmp_path):
    fixture, answers, sidecar = rows_from([("doc-01", 30000.0, 30000.0), ("doc-02", 99999999.0, 40000.0)])
    sidecar = [row for row in sidecar if row["id"] != "doc-02"]
    paths, data = case(tmp_path, fixture, answers, sidecar, label="nosidecar")
    assert data["cells"][mod.GROUP_QA]["n"] == 2 and data["cells"][mod.GROUP_QA]["n_measured"] == 1
    assert [row["id"] for row in data["rejects"]] == ["doc-02"]
    assert "latency_ms 不许顶替" in data["rejects"][0]["reason"]
    assert data["cells"][mod.GROUP_QA]["p95_rank"] == 30000.0     # 那枚 99 999 999 没混进聚合


def test_wall_ms_over_the_one_attempt_envelope_is_not_honest(tmp_path, monkeypatch):
    """帧账自己也得过量级这一关（用在册 latency_envelope_ms 那把尺）：越界就明写不可信、不计入聚合。"""
    monkeypatch.setenv("MODEL_REQUEST_TIMEOUT", "1")             # envelope = 1 s × 8 = 8000 ms
    fixture, answers, sidecar = rows_from([("doc-01", 1000.0, 2000.0), ("doc-02", 1000.0, 99999.0)])
    paths, data = case(tmp_path, fixture, answers, sidecar, label="envelope")
    assert data["envelope_ms"] == 8000.0
    assert [row["id"] for row in data["rejects"]] == ["doc-02"]
    assert "越出一发量级上限" in data["rejects"][0]["reason"]
    assert data["cells"][mod.GROUP_QA]["n_measured"] == 1


def test_unreadable_wall_ms_is_none_not_zero(tmp_path):
    fixture, answers, sidecar = rows_from([("doc-01", 1000.0, 2000.0)])
    sidecar[0]["wall_ms"] = "30 秒"
    paths, data = case(tmp_path, fixture, answers, sidecar, label="junk")
    assert [row["id"] for row in data["rejects"]] == ["doc-01"]
    assert "读不成非负毫秒" in data["rejects"][0]["reason"]
    assert data["cells"][mod.GROUP_QA]["n_used"] == 0


def test_same_question_multiple_attempts_takes_the_largest_attempt(tmp_path):
    """同题多轮取 attempt 最大那一行（与在册 eval_lane_readout.py:47 同规则），不另起一本折叠账。"""
    fixture, answers, sidecar = rows_from([("doc-01", 1000.0, 2000.0)])
    sidecar = [{"id": "doc-01", "kind": "ok", "attempt": 1, "wall_ms": 2000.0},
               {"id": "doc-01", "kind": "error_event", "attempt": 2, "wall_ms": 4000.0}]
    paths, data = case(tmp_path, fixture, answers, sidecar, label="attempts")
    assert data["counts"]["sidecar_raw"] == 2 and data["counts"]["sidecar"] == 1
    assert data["counts"]["s_collisions"] == 1
    assert data["cells"][mod.GROUP_QA]["p95_rank"] == 4000.0


def test_missing_sidecar_file_refuses_instead_of_guessing(tmp_path, capsys):
    fixture, answers, sidecar = rows_from([("doc-01", 1000.0, 2000.0)])
    paths, data = case(tmp_path, fixture, answers, sidecar, label="derive")
    assert Path(paths["sidecar"]).name == "sidecar-derive.jsonl"      # 件名同规律推得出
    with pytest.raises(mod.ReadoutError):
        mod.default_sidecar_for(Path(tmp_path) / "no-match.jsonl")    # 认不出就不猜
    rc = mod.main(["--answers", str(paths["answers"]), "--fixture", str(paths["fixture"]),
                   "--sidecar", str(Path(tmp_path) / "does-not-exist.jsonl")])
    assert rc == mod.RC_INPUT
    assert "取不到件" in capsys.readouterr().out


def test_inputs_are_never_written_to(tmp_path, capsys):
    """只读纪律：三本件跑前跑后 sha256 与 mtime 一字不动，也不许在旁边落新件。"""
    fixture, answers, sidecar = rows_from(RUN6_SHAPE, tier="分析", category="Excel计算")
    paths, data = case(tmp_path, fixture, answers, sidecar, label="readonly")
    before = {key: (mod.sha12(value), os.path.getmtime(str(value))) for key, value in paths.items()}
    snapshot = set(os.listdir(str(tmp_path)))
    mod.render(data)
    rc = mod.main(["--answers", str(paths["answers"]), "--fixture", str(paths["fixture"]),
                   "--sidecar", str(paths["sidecar"]), "--label", "readonly"])
    after = {key: (mod.sha12(value), os.path.getmtime(str(value))) for key, value in paths.items()}
    assert before == after and rc == mod.RC_OK
    assert set(os.listdir(str(tmp_path))) == snapshot
