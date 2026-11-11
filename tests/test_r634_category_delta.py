# -*- coding: utf-8 -*-
"""R634 的离线牙：全部用合成窗，一枚真窗读数都不当钉。

钉的是一条条判据，不是一串数：
① 跨代次掉了题必须判退化并点名到题号；
② 同一窗喂两遍必须判零摆动；
③ 类目只剩 3 题必须落「样本不足，不许判」，不许落绿；
④ 尺子读的件缺一枚必须 rc=3 并明写「取不到」，不许拿 0 冒充；
⑤ 底没量出来之前，跨代次那一组也不许宣布退化（undecidable，不是绿）；
⑥ 与落盘报告对不上账必须 rc=3（不许挑一把能对上的尺报数）；
⑦ 判分必须长在在册尺上：把 _is_correct 换成常真，本件的数必须跟着变；
⑧ 只读数不改数：跑完之后输入件逐字节不变；--out 指进仓内直接拒。
"""
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
for _path in (str(SCRIPTS), str(REPO_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import r634_category_delta as r634  # noqa: E402
from app.quality import eval as quality_eval  # noqa: E402
from app.quality import runner  # noqa: E402

def row(row_id, category, terms, requires_evidence=True):
    return {"id": row_id, "tier": "问答", "category": category, "question": "问 " + row_id,
            "answer": terms[0], "must_contain": list(terms), "requires_evidence": requires_evidence}


def answer(row_id, terms, evidence_n=1, latency_ms=1000.0, tool_calls=1):
    return {"id": row_id, "answer": "".join(terms), "evidence": [{"source": "a" + str(index) + ".txt"}
            for index in range(evidence_n)], "latency_ms": latency_ms, "tool_calls": tool_calls}


def sidecar(row_id, **overrides):
    record = {"id": row_id, "kind": "ok", "attempt": 1, "sentinel": False, "evidence_n": 1,
              "answer_chars": 1, "tool_calls": 1, "wall_ms": 1000.0, "ts": "2026-01-01 00:00:00",
              "pre_kind": "ok", "pre_answer_chars": 1, "pre_evidence_n": 1, "approved": False,
              "approval_rounds": 0, "approval_http_status": None, "approval_error": ""}
    record.update(overrides)
    return record


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in rows), encoding="utf-8")


def write_window(root, label, fixture_path, answers, sidecars, *, revision, started_at,
                 index_backend="pgvector", transport="spec", shard_size=1):
    """落一扇窗的四枚件：answers／侧车／窗记／报告——报告由在册尺自己产出，不手抄。"""
    write_jsonl(root / (label + "-answers.jsonl"), answers)
    write_jsonl(root / (label + "-sidecar.jsonl"), sidecars)
    (root / (label + ".window.json")).write_text(json.dumps({
        "revision": revision, "index_backend": index_backend,
        "fixture_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
        "transport": transport, "shard_size": shard_size, "container": "x", "probe_ok": True,
        "probe_errors": [], "dry_run": False, "probed_at": started_at, "started_at": started_at,
    }, ensure_ascii=False), encoding="utf-8")
    report_path = root / (label + "-report.json")
    runner.run_recorded_evaluation(str(fixture_path), str(root / (label + "-answers.jsonl")),
                                   str(report_path))
    return report_path


def run_tool(tmp_path, labels, *, out_name="out.json", extra=()):
    argv = ["--dir", str(tmp_path), "--fixture", str(tmp_path / "fixture.jsonl"),
            "--format", "json", "--out", str(tmp_path / out_name)]
    for label in labels:
        argv += ["--window", label]
    argv += list(extra)
    code = r634.main(argv)
    payload = json.loads((tmp_path / out_name).read_text(encoding="utf-8"))
    return code, payload


def cross_cell(payload, category, metric="correctness"):
    for pair in payload["pairs"]:
        if pair["class"] != "cross_generation":
            continue
        cell = (pair.get("cells") or {}).get(category, {}).get(metric)
        if cell:
            return pair, cell
    return None, None


# ------------------------------------------------------------------ ①

def test_cross_generation_drop_is_flagged_and_named(tmp_path):
    rows = [row("a" + str(index), "甲类", ["t" + str(index)]) for index in range(1, 7)]
    fixture = tmp_path / "fixture.jsonl"
    write_jsonl(fixture, rows)
    good = [answer(item["id"], [item["must_contain"][0]]) for item in rows]
    write_window(tmp_path, "genA1", fixture, good, [sidecar(item["id"]) for item in rows],
                 revision="revA", started_at="2026-01-01 00:00:00")
    write_window(tmp_path, "genA2", fixture, good, [sidecar(item["id"]) for item in rows],
                 revision="revA", started_at="2026-01-02 00:00:00")
    worse = [dict(item) for item in good]
    worse[2] = {"id": "a3", "answer": "跑偏了", "evidence": [{"source": "a0.txt"}],
                "latency_ms": 1000.0, "tool_calls": 1}
    write_window(tmp_path, "genB1", fixture, worse, [sidecar(item["id"]) for item in rows],
                 revision="revB", started_at="2026-01-03 00:00:00")

    code, payload = run_tool(tmp_path, ["genA1", "genA2", "genB1"])
    assert code == r634.EXIT_REGRESSION, payload["why"]
    regressions = payload["summary"]["regressions"]
    assert {item["category"] for item in regressions} == {"甲类"}
    assert len(regressions) == 2, "genA1 与 genA2 各自对 genB1 都是一次跨代次对照"
    assert {tuple(item["worsened_ids"]) for item in regressions} == {("a3",)}, regressions
    floor = regressions[0]["floor"]
    assert floor == 0.0 and regressions[0]["worsening"] > floor
    pair, cell = cross_cell(payload, "甲类")
    named = [item for item in pair["flips"] if item["id"] == "a3"]
    assert len(named) == 1 and named[0]["direction"] == "drop"
    assert named[0]["class"] == "answered_differently"
    assert "跑偏" not in "".join(named[0]["hits_compare"])
    assert named[0]["missed_baseline"] == ["t3"] or named[0]["hits_baseline"] == ["t3"]


# ------------------------------------------------------------------ ②

def test_same_window_fed_twice_reads_zero_swing(tmp_path):
    rows = [row("b" + str(index), "乙类", ["u" + str(index)]) for index in range(1, 6)]
    fixture = tmp_path / "fixture.jsonl"
    write_jsonl(fixture, rows)
    answers = [answer(item["id"], [item["must_contain"][0]]) for item in rows]
    write_window(tmp_path, "same1", fixture, answers, [sidecar(item["id"]) for item in rows],
                 revision="revS", started_at="2026-01-01 00:00:00")
    write_window(tmp_path, "same2", fixture, answers, [sidecar(item["id"]) for item in rows],
                 revision="revS", started_at="2026-01-02 00:00:00")

    code, payload = run_tool(tmp_path, ["same1", "same2"])
    pair = payload["pairs"][0]
    assert pair["class"] == "same_fingerprint"
    assert pair["flips"] == []
    for metric, cell in pair["cells"]["乙类"].items():
        assert cell["swing"] == 0.0, (metric, cell)
        assert cell["worsening"] <= 0.0, (metric, cell)
        assert cell["verdict"] == r634.VERDICT_FLOOR_INPUT
    assert payload["summary"]["regressions"] == []
    assert code == r634.EXIT_NOT_JUDGED, "没有跨代次对子时不许报绿灯"


# ------------------------------------------------------------------ ③

def test_three_question_category_is_refused_not_green(tmp_path):
    rows = [row("c" + str(index), "丙类", ["v" + str(index)]) for index in range(1, 4)]
    fixture = tmp_path / "fixture.jsonl"
    write_jsonl(fixture, rows)
    good = [answer(item["id"], [item["must_contain"][0]]) for item in rows]
    write_window(tmp_path, "tinyA1", fixture, good, [sidecar(item["id"]) for item in rows],
                 revision="revA", started_at="2026-01-01 00:00:00")
    write_window(tmp_path, "tinyA2", fixture, good, [sidecar(item["id"]) for item in rows],
                 revision="revA", started_at="2026-01-02 00:00:00")
    worse = [dict(item) for item in good]
    worse[0] = {"id": "c1", "answer": "没含锚词", "evidence": [], "latency_ms": 1000.0, "tool_calls": 0}
    write_window(tmp_path, "tinyB1", fixture, worse, [sidecar(item["id"]) for item in rows],
                 revision="revB", started_at="2026-01-03 00:00:00")

    code, payload = run_tool(tmp_path, ["tinyA1", "tinyA2", "tinyB1"])
    _, cell = cross_cell(payload, "丙类")
    assert cell["verdict"] == r634.VERDICT_INSUFFICIENT
    assert "样本不足" in cell["verdict_reason"]
    assert payload["summary"]["regressions"] == []
    assert code == r634.EXIT_NOT_JUDGED, "全部格都不可判时不是干净"


# ------------------------------------------------------------------ ④

def test_missing_artifact_is_reported_as_unreadable_not_zero(tmp_path, capsys):
    rows = [row("d" + str(index), "丁类", ["w" + str(index)]) for index in range(1, 6)]
    fixture = tmp_path / "fixture.jsonl"
    write_jsonl(fixture, rows)
    answers = [answer(item["id"], [item["must_contain"][0]]) for item in rows]
    write_window(tmp_path, "half1", fixture, answers, [sidecar(item["id"]) for item in rows],
                 revision="revA", started_at="2026-01-01 00:00:00")
    write_window(tmp_path, "half2", fixture, answers, [sidecar(item["id"]) for item in rows],
                 revision="revA", started_at="2026-01-02 00:00:00")
    (tmp_path / "half2-answers.jsonl").unlink()

    code = r634.main(["--dir", str(tmp_path), "--fixture", str(fixture),
                      "--window", "half1", "--window", "half2"])
    captured = capsys.readouterr()
    assert code == r634.EXIT_UNREADABLE
    assert "取不到" in captured.err, captured.err
    assert "answers" in captured.err, captured.err
    assert code != r634.EXIT_CLEAN, "缺件绝不能落到 0"


def test_missing_window_label_is_unreadable(tmp_path, capsys):
    rows = [row("d1", "丁类", ["w1"])]
    fixture = tmp_path / "fixture.jsonl"
    write_jsonl(fixture, rows)
    code = r634.main(["--dir", str(tmp_path), "--fixture", str(fixture), "--window", "ghost"])
    assert code == r634.EXIT_UNREADABLE
    assert "取不到" in capsys.readouterr().err


# ------------------------------------------------------------------ ⑤

def test_cross_generation_without_a_floor_pair_cannot_declare_regression(tmp_path):
    rows = [row("e" + str(index), "戊类", ["x" + str(index)]) for index in range(1, 7)]
    fixture = tmp_path / "fixture.jsonl"
    write_jsonl(fixture, rows)
    good = [answer(item["id"], [item["must_contain"][0]]) for item in rows]
    write_window(tmp_path, "soloA", fixture, good, [sidecar(item["id"]) for item in rows],
                 revision="revA", started_at="2026-01-01 00:00:00")
    worse = [dict(item) for item in good]
    worse[1] = {"id": "e2", "answer": "跑偏", "evidence": [{"source": "a0.txt"}],
                "latency_ms": 1000.0, "tool_calls": 1}
    write_window(tmp_path, "soloB", fixture, worse, [sidecar(item["id"]) for item in rows],
                 revision="revB", started_at="2026-01-02 00:00:00")

    code, payload = run_tool(tmp_path, ["soloA", "soloB"])
    pair, cell = cross_cell(payload, "戊类")
    assert cell["verdict"] == r634.VERDICT_NO_FLOOR
    assert "不许宣布任何一格退化" in cell["verdict_reason"]
    assert payload["summary"]["regressions"] == []
    assert payload["summary"]["noise_floor"]["measured"] is False
    assert code == r634.EXIT_NOT_JUDGED


# ------------------------------------------------------------------ ⑥

def test_report_numbers_that_disagree_with_the_ruler_are_refused(tmp_path, capsys):
    rows = [row("f" + str(index), "己类", ["y" + str(index)]) for index in range(1, 6)]
    fixture = tmp_path / "fixture.jsonl"
    write_jsonl(fixture, rows)
    answers = [answer(item["id"], [item["must_contain"][0]]) for item in rows]
    report = write_window(tmp_path, "tamper1", fixture, answers, [sidecar(item["id"]) for item in rows],
                          revision="revA", started_at="2026-01-01 00:00:00")
    write_window(tmp_path, "tamper2", fixture, answers, [sidecar(item["id"]) for item in rows],
                 revision="revA", started_at="2026-01-02 00:00:00")
    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["answer_correctness"] = round(payload["answer_correctness"] + 0.2, 4)
    report.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    code = r634.main(["--dir", str(tmp_path), "--fixture", str(fixture),
                      "--window", "tamper1", "--window", "tamper2"])
    captured = capsys.readouterr()
    assert code == r634.EXIT_UNREADABLE
    assert "对账破" in captured.err, captured.err


# ------------------------------------------------------------------ ⑦

def test_correctness_grows_out_of_the_live_ruler(tmp_path, monkeypatch):
    """反证刀：把在册尺的 _is_correct 换成常真，本件的逐类目数必须跟着变。

    本件若自己另写一套「算不算对」，这一刀就砍不动它——换尺之后它照样报 0.0。
    """
    rows = [row("g" + str(index), "庚类", ["z" + str(index)]) for index in range(1, 6)]
    fixture = tmp_path / "fixture.jsonl"
    write_jsonl(fixture, rows)
    wrong = [{"id": item["id"], "answer": "一个锚词都不含", "evidence": [{"source": "a0.txt"}],
              "latency_ms": 1000.0, "tool_calls": 1} for item in rows]
    assert all("z" + str(index) not in wrong[index - 1]["answer"] for index in range(1, 6))

    monkeypatch.setattr(quality_eval, "_is_correct", lambda row_, result_: True)
    write_window(tmp_path, "ruler1", fixture, wrong, [sidecar(item["id"]) for item in rows],
                 revision="revA", started_at="2026-01-01 00:00:00")
    write_window(tmp_path, "ruler2", fixture, wrong, [sidecar(item["id"]) for item in rows],
                 revision="revA", started_at="2026-01-02 00:00:00")
    code, payload = run_tool(tmp_path, ["ruler1", "ruler2"])

    assert code == r634.EXIT_NOT_JUDGED, payload["why"]
    for window in payload["windows"]:
        assert window["reconcile"]["status"].startswith("全格对上"), window["reconcile"]
        assert window["global"]["answer_correctness"] == 1.0
        assert all(cell["correctness"] == 1.0 for cell in window["categories"].values())
    assert payload["windows"][0]["global"]["answer_correctness"] == 1.0, "本件得跟着在册尺走"


# ------------------------------------------------------------------ ⑧

def test_tool_reads_only_and_refuses_to_write_into_the_repo(tmp_path, capsys):
    rows = [row("h" + str(index), "辛亥类", ["q" + str(index)]) for index in range(1, 6)]
    fixture = tmp_path / "fixture.jsonl"
    write_jsonl(fixture, rows)
    answers = [answer(item["id"], [item["must_contain"][0]]) for item in rows]
    write_window(tmp_path, "quiet1", fixture, answers, [sidecar(item["id"]) for item in rows],
                 revision="revA", started_at="2026-01-01 00:00:00")
    write_window(tmp_path, "quiet2", fixture, answers, [sidecar(item["id"]) for item in rows],
                 revision="revA", started_at="2026-01-02 00:00:00")
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(tmp_path.glob("quiet1-*"))}

    code, payload = run_tool(tmp_path, ["quiet1", "quiet2"], out_name="product.json")
    after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted(tmp_path.glob("quiet1-*"))}
    assert before == after, "本件只许读数，输入件一个字节都不许变"
    assert code == r634.EXIT_NOT_JUDGED

    forbidden = REPO_ROOT / "docs" / "perf" / "r634-should-never-be-written-by-the-tool.json"
    code = r634.main(["--dir", str(tmp_path), "--fixture", str(fixture),
                      "--window", "quiet1", "--window", "quiet2",
                      "--format", "json", "--out", str(forbidden)])
    assert code == r634.EXIT_UNREADABLE
    assert not forbidden.exists(), "--out 指进仓内必须直接拒"
    assert "仓外" in capsys.readouterr().err or "仓内" in capsys.readouterr().err


# ------------------------------------------------------------------ ⑨

def test_the_four_ways_a_question_can_lose_a_point_are_named(tmp_path):
    """本单要的那一句「逐格给得出答得不同还是没答／哨兵／批准失败」：四型各一枚，逐枚点名。"""
    rows = [row("i" + str(index), "壬类", ["s" + str(index)]) for index in range(1, 7)]
    fixture = tmp_path / "fixture.jsonl"
    write_jsonl(fixture, rows)
    good = [answer(item["id"], [item["must_contain"][0]]) for item in rows]
    write_window(tmp_path, "kindA1", fixture, good, [sidecar(item["id"]) for item in rows],
                 revision="revA", started_at="2026-01-01 00:00:00")
    write_window(tmp_path, "kindA2", fixture, good, [sidecar(item["id"]) for item in rows],
                 revision="revA", started_at="2026-01-02 00:00:00")

    worse = {item["id"]: dict(item) for item in good}
    worse["i1"]["answer"] = ""                                    # 没答
    worse["i2"]["answer"] = "哨兵顶回来的那一发"                    # 哨兵
    worse["i3"]["answer"] = "批准失败后没有终答"                    # 批准失败
    worse["i4"]["answer"] = "有字但这一发未答完"                    # 未答完（kind 不是 ok）
    sidecars = []
    for index, item in enumerate(rows, 1):
        overrides = {}
        if item["id"] == "i2":
            overrides = {"sentinel": True, "kind": "sentinel"}
        elif item["id"] == "i3":
            overrides = {"kind": quality_eval.APPROVAL_FAILED_KIND, "approval_error": "批准通道炸了",
                         "evidence_n": 0, "tool_calls": 0, "answer_chars": 0}
        elif item["id"] == "i4":
            overrides = {"kind": "error_event"}
        sidecars.append(sidecar(item["id"], **overrides))
    write_window(tmp_path, "kindB1", fixture, [worse[item["id"]] for item in rows], sidecars,
                 revision="revB", started_at="2026-01-03 00:00:00")

    code, payload = run_tool(tmp_path, ["kindA1", "kindA2", "kindB1"])
    assert code == r634.EXIT_REGRESSION, payload["why"]
    pair, cell = cross_cell(payload, "壬类")
    named = {item["id"]: item for item in pair["flips"] if item["direction"] == "drop"}
    assert set(named) == {"i1", "i2", "i3", "i4"}, sorted(named)
    assert named["i1"]["class"] == "no_answer"
    assert named["i2"]["class"] == "sentinel"
    assert named["i3"]["class"] == "approval_failed"
    assert named["i4"]["class"] == "not_answered"
    assert named["i3"]["signals"]["evidence_zeroed"] is True
    assert named["i3"]["signals"]["tool_calls_zeroed"] is True
    assert named["i1"]["signals"]["evidence_zeroed"] is False, "答案空但引证没塌：形状信号不许替归类做主"
    assert named["i2"]["class_reason"].startswith("侧车 sentinel")
    assert cell["verdict"] == r634.VERDICT_REGRESSION
