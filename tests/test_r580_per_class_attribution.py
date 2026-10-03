# -*- coding: utf-8 -*-
"""R580 常驻钉 —— 钉住「A④ 逐类归因」这把量具的**形状**与四类归因的落点，不钉任何一枚真机的数。

🔴 全离线：两窗四本账与 parity 一律在 ``tmp_path`` 里当场合成；一枚读数都不从真机目录里读
（那批件是凭据纸 §1 的活，落到本件就成了"在有期限的临时件上钉常驻判据"）。这件事由
``test_counter_evidence_k_the_pins_are_offline`` 逐字钉住。

===== 五格判据在本件里的落点 =====
① 两维分桶守恒：``category`` 全族 Σn 与 ``tier`` 三档 Σn 都等于题数，破了 rc≠0
   （``test_both_dims_conserve_the_whole_window``）。
② 每一处下降都有题级归因，四类之外不许新类；归因成"检索腿"的题必须交出两窗 evidence 的
   文件名#chunk 级差异并与读后端同向（``test_every_flip_lands_in_one_of_the_four_classes`` /
   ``test_a_leg_attribution_names_the_chunk_level_delta``）。
③ 甲案扣除集合现读，两窗不同就点名差哪几枚（``test_denominator_account_is_read_live``）。
④ 反证 ≥3 把：这里给了 a..k 共十一把，一枚都不分层出门。
⑤ 本格只交数：三档只有 达／不达／不可判，不许出现宣布翻绿的那句话
   （``test_the_tool_never_declares_green``）。

===== 在册尺不许被绕过 =====
判分只走 ``app/quality/eval.py::_is_correct``：把那枚函数换掉，本件的数必须跟着动（刀 e）；
拿在册 ``evaluate_evaluation_set`` 现生成的报告交进去，两本读数必须逐枚相等
（``test_the_in_book_report_is_an_independent_witness``）；报告被动过一枚 ⇒ rc=2（刀 d）。
"""

import hashlib
import importlib.util
import io
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "r580_per_class_attribution", REPO_ROOT / "scripts" / "r580_per_class_attribution.py")
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)

quality_eval = mod.quality_eval

#: 迷你题集：七枚，覆盖四个族、三档，每族都留了一枚可失败的下降。
FIXTURE_ROWS = [
    {"id": "doc-01", "tier": "问答", "category": "文档问答", "question": "住宿费标准？",
     "answer": "一线城市 500 元/晚", "must_contain": ["500元"], "requires_evidence": True},
    {"id": "doc-02", "tier": "问答", "category": "文档问答", "question": "怎么报销？",
     "answer": "凭发票据实报销", "must_contain": ["据实报销"], "requires_evidence": True},
    {"id": "metric-01", "tier": "分析", "category": "口径冲突", "question": "费用算哪个月？",
     "answer": "以发生月归属", "must_contain": ["发生月"], "requires_evidence": True},
    {"id": "metric-02", "tier": "分析", "category": "口径冲突", "question": "跨月怎么处理？",
     "answer": "拆两笔挂账", "must_contain": ["跨月"], "requires_evidence": False},
    {"id": "metric-03", "tier": "分析", "category": "口径冲突", "question": "次月冲销行不行？",
     "answer": "可以冲销", "must_contain": ["冲销"], "requires_evidence": True},
    {"id": "chat-01", "tier": "问答", "category": "多轮对话", "question": "接上文：谁的额度？",
     "answer": "部门负责人审批", "must_contain": ["部门负责人"], "requires_evidence": True},
    {"id": "report-01", "tier": "报告", "category": "报告生成", "question": "出个结论",
     "answer": "本期收入增长", "must_contain": ["结论"], "requires_evidence": True,
     "r401": {"disposition": "丙", "missing_term": "结论", "reason": "语料互斥未裁：两处口径相反",
              "pool": "交付阶段按客户真实密级做"}},
]
TITLES = [str(row["id"]) for row in FIXTURE_ROWS]
TOTAL = len(TITLES)

#: 两窗的答案与引证：形状就是真机那两窗的形状（evidence 枚数、空引证、预制占位串都在）。
EVIDENCE = {
    "w13": {
        "doc-01": [("差旅细则.txt", 2, "住宿按城市等级限额")],
        "doc-02": [("差旅细则.txt", 2, "凭发票据实报销，超出部分自理")],
        "metric-01": [("制度登记表.txt", 5, "费用以发生月归属，跨月拆两笔挂账")],
        "metric-02": [],
        "metric-03": [],
        "chat-01": [("管理制度手册.txt", 3, "部门负责人在额度内审批")],
        "report-01": [("经营报告.txt", 11, "本期结论：收入增长")],
    },
    "w14": {
        "doc-01": [("制度登记表.txt", 4, "一线城市住宿标准 500元/晚"),
                   ("差旅细则.txt", 2, "住宿按城市等级限额")],
        "doc-02": [("差旅细则.txt", 2, "凭发票据实报销，超出部分自理")],
        "metric-01": [("员工手册.txt", 1, "费用报销需提前审批")],
        "metric-02": [("制度登记表.txt", 6, "跨月费用按发生月拆分")],
        "metric-03": [("管理制度手册.txt", 3, "跨月单据在次月第一周处理")],
        "chat-01": [("管理制度手册.txt", 3, "部门负责人在额度内审批")],
        "report-01": [("经营报告.txt", 11, "本期结论：收入增长")],
    },
}
ANSWERS = {
    "w13": {
        "doc-01": "住宿按城市等级限额，凭发票报销。",
        "doc-02": "凭发票据实报销，超出部分自理。",
        "metric-01": "费用归属见第五条：以发生月为准。",
        "metric-02": "本轮未产出任何结论，请重试或补充数据范围。",
        "metric-03": "本轮未产出任何结论，请重试或补充数据范围。",
        "chat-01": "接上文：部门负责人在额度内审批。",
        "report-01": "报告结论：本期收入增长，成本口径不变。",
    },
    "w14": {
        "doc-01": "一线城市 500元/晚，二线 400 元。",
        "doc-02": "凭发票在限额内报销，超出自理。",
        "metric-01": "费用按审批月归属。",
        "metric-02": "跨月要拆两笔挂账。",
        "metric-03": "次月可以冲销，需在备案期内。",
        "chat-01": "接上文：由上级签字后走款。",
        "report-01": "本期收入增长，成本不变，结论见第五条。",
    },
}
#: 七枚迷你题的 parity 读数（在册量具的形状：每题两腿各 top-k、本腿独有、本腿行数）。
PARITY_ROWS = {
    "doc-01": {"chroma": ["差旅细则.txt_2", "员工手册.txt_1", "管理制度手册.txt_3",
                          "经营报告.txt_11", "制度登记表.txt_1"],
               "pg": ["制度登记表.txt_4", "差旅细则.txt_2", "员工手册.txt_1",
                      "管理制度手册.txt_3", "经营报告.txt_11"]},
    "doc-02": {"chroma": ["差旅细则.txt_2", "员工手册.txt_1"], "pg": ["差旅细则.txt_2",
                                                                      "员工手册.txt_1"]},
    "metric-01": {"chroma": ["差旅细则.txt_2", "员工手册.txt_1"],
                  "pg": ["差旅细则.txt_2", "员工手册.txt_1"]},
    "metric-02": {"chroma": ["制度登记表.txt_6"], "pg": ["制度登记表.txt_6"]},
    "metric-03": {"chroma": [], "pg": ["管理制度手册.txt_3", "制度登记表.txt_6"]},
    "chat-01": {"chroma": ["管理制度手册.txt_3"], "pg": ["管理制度手册.txt_3"]},
    "report-01": {"chroma": ["经营报告.txt_11"], "pg": ["经营报告.txt_11"]},
}
#: 侧车 kind：未答完那一族只出现在 w13 的 metric-02／metric-03 两枚上。
KINDS = {"w13": {"metric-02": "error_event"}, "w14": {"report-01": "approved_ok"}}
BACKENDS = {"w13": "", "w14": "pgvector"}
REVISION = "0" * 40
TRANSPORT = "eval_transport_ask_v2:transport"


def _write_jsonl(path, rows):
    with io.open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _answers_rows(label, answers, evidence):
    rows = []
    for row in FIXTURE_ROWS:
        row_id = str(row["id"])
        rows.append({"id": row_id, "answer": answers[row_id],
                     "evidence": [{"worker": "doc", "source": source,
                                   "source_id": source + "#chunk=" + str(chunk),
                                   "chunk_index": chunk, "excerpt": excerpt}
                                  for source, chunk, excerpt in evidence[row_id]],
                     "latency_ms": 1000.0 + len(row_id),
                     "answer_source": TRANSPORT})
    return rows


def _sidecar_rows(label, answers, evidence, kinds):
    rows = []
    for row in FIXTURE_ROWS:
        row_id = str(row["id"])
        rows.append({"id": row_id, "kind": kinds.get(row_id, "ok"), "attempt": 1,
                     "sentinel": False, "evidence_n": len(evidence[row_id]),
                     "answer_chars": len(answers[row_id]), "tool_calls": 0,
                     "wall_ms": 1000.0 + len(row_id), "pre_kind": None,
                     "approved": kinds.get(row_id) == "approved_ok", "approval_rounds": 0})
    return rows


def _parity_rows(parity_map):
    questions = []
    for row in FIXTURE_ROWS:
        row_id = str(row["id"])
        chroma = list(parity_map[row_id]["chroma"])
        pg = list(parity_map[row_id]["pg"])
        questions.append({"id": row_id, "k": 5, "chroma_ids": chroma, "pg_ids": pg,
                          "chroma_only_ids": sorted(set(chroma) - set(pg)),
                          "pg_only_ids": sorted(set(pg) - set(chroma)),
                          "chroma_rows": len(chroma), "pg_rows": len(pg),
                          "overlap": len(set(chroma) & set(pg)),
                          "same_set": set(chroma) == set(pg)})
    return {"meta": {"tool": "scripts/r59_recall_compare.py", "k": 5,
                     "generated_at": "2026-10-03T00:27:01+08:00"},
            "questions": questions,
            "summary": {"questions": len(questions), "chroma_zero_rows": sum(
                1 for item in questions if item["chroma_rows"] == 0),
                "pg_zero_rows": sum(1 for item in questions if item["pg_rows"] == 0),
                "same_set": sum(1 for item in questions if item["same_set"]),
                "differing_set": sum(1 for item in questions if not item["same_set"]),
                "questions_zero_overlap": 0, "mean_overlap_ratio": 0.7}}


def write_pair(tmp_path, answers=None, evidence=None, kinds=None, parity_map=None,
               backends=None, reports=True, rename_b=None, drop_ids=()):
    """在 tmp_path 里落一整套「题集＋两窗四本账＋parity」，返回 read_pair 的关键字与 CLI 参数。"""
    tmp_path = Path(str(tmp_path))
    tmp_path.mkdir(parents=True, exist_ok=True)
    answers = answers or {label: dict(ANSWERS[label]) for label in BACKENDS}
    evidence = evidence or {label: dict(EVIDENCE[label]) for label in BACKENDS}
    kinds = kinds or KINDS
    parity_map = parity_map or PARITY_ROWS
    backends = backends or BACKENDS
    label_a, label_b = "w13", rename_b or "w14"
    ids = [row_id for row_id in TITLES if row_id not in drop_ids]

    fixture = tmp_path / "mini-fixture.jsonl"
    _write_jsonl(fixture, FIXTURE_ROWS)
    fixture_sha = hashlib.sha256(fixture.read_bytes()).hexdigest()

    paths = {"fixture": str(fixture)}
    for slot, label in (("a", label_a), ("b", label_b)):
        answers_rows = [row for row in _answers_rows(label, answers[label], evidence[label])
                        if row["id"] in ids]
        sidecar_rows = [row for row in _sidecar_rows(label, answers[label], evidence[label],
                                                     kinds.get(label, {}))
                        if row["id"] in ids]
        answers_path = tmp_path / (label + "-answers.jsonl")
        sidecar_path = tmp_path / (label + "-sidecar.jsonl")
        window_path = tmp_path / (label + ".window.json")
        _write_jsonl(answers_path, answers_rows)
        _write_jsonl(sidecar_path, sidecar_rows)
        window_path.write_text(json.dumps(
            {"revision": REVISION, "index_backend": backends[label],
             "fixture_sha256": fixture_sha, "transport": TRANSPORT, "shard_size": 1,
             "container": "probe-container", "probe_ok": True, "probe_errors": [],
             "dry_run": False, "started_at": "2026-10-03 00:00:00"},
            ensure_ascii=False, indent=1), encoding="utf-8")
        paths["answers_" + slot] = str(answers_path)
        paths["sidecar_" + slot] = str(sidecar_path)
        paths["window_" + slot] = str(window_path)
        if reports:
            table = {row["id"]: row["answer"] for row in answers_rows}
            ev = {row["id"]: row["evidence"] for row in answers_rows}

            def answer_fn(row, table=table, ev=ev):
                return {"answer": table[row["id"]], "evidence": ev[row["id"]],
                        "latency_ms": 1000.0}

            report = quality_eval.evaluate_evaluation_set(
                str(fixture), answer_fn, approval_ledger=str(sidecar_path))
            report_path = tmp_path / (label + "-report.json")
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
            paths["report_" + slot] = str(report_path)
        else:
            paths["report_" + slot] = str(tmp_path / (label + "-report.absent.json"))
    parity_path = tmp_path / "p3-parity.json"
    parity_path.write_text(json.dumps(_parity_rows(parity_map), ensure_ascii=False, indent=1),
                           encoding="utf-8")
    paths["parity"] = str(parity_path)
    paths["expect_total"] = TOTAL
    return paths


def argv_for(paths, expect_total=None, parity=None):
    argv = ["--answers-a", paths["answers_a"], "--answers-b", paths["answers_b"],
            "--fixture", paths["fixture"], "--report-a", paths["report_a"],
            "--report-b", paths["report_b"], "--expect-total", str(expect_total or TOTAL)]
    if parity is not None:
        argv += ["--parity", parity]
    return argv


def bucket(result, dim, name):
    return next(item for item in result["buckets"][dim] if item["name"] == name)


def flip(result, row_id):
    return next(item for item in result["flips"] if item["id"] == row_id)


def edited(label, row_id, text):
    """把某一窗某一题的终答换掉（只动答案文本，引证一枚都不动），返回整套两窗答案。"""
    table = {name: dict(ANSWERS[name]) for name in BACKENDS}
    table[label][row_id] = text
    return table


def test_both_dims_conserve_the_whole_window(tmp_path):
    result = mod.read_pair(**write_pair(tmp_path))
    for dim in mod.DIMS:
        assert result["conservation"][dim]["ok"] is True
        assert sum(item["n"] for item in result["buckets"][dim]) == TOTAL
        members = [row_id for item in result["buckets"][dim]
                   for row_id in result["bucket_membership"][dim][item["name"]]]
        assert sorted(members) == sorted(TITLES)          # 每枚恰好落进这一维的一桶
    assert result["conservation"][mod.DIM_CATEGORY]["expect_total"] == TOTAL


def test_bucket_table_carries_both_rulers_and_the_deducted_count(tmp_path):
    result = mod.read_pair(**write_pair(tmp_path))
    label_a, label_b = result["labels"]["a"], result["labels"]["b"]
    reporting = bucket(result, mod.DIM_CATEGORY, "报告生成")
    assert reporting["n"] == 1 and reporting["deducted_n"] == 1
    assert reporting[label_a]["scorable_denom"] == 0
    assert reporting[label_a]["scorable_score"] is None    # 空子集报 None，不报 0.0
    assert reporting[label_a]["denom"] == reporting["n"]
    docs = bucket(result, mod.DIM_CATEGORY, "文档问答")
    assert docs[label_a]["correct_n"] == docs[label_b]["correct_n"] == 1
    assert docs[label_a]["score"] == docs[label_b]["score"] == 0.5
    for item in result["buckets"][mod.DIM_TIER]:
        assert item[label_a]["denom"] == item["n"] > 0
        assert 0.0 <= item[label_a]["score"] <= 1.0


def test_every_flip_lands_in_one_of_the_four_classes(tmp_path):
    result = mod.read_pair(**write_pair(tmp_path))
    assert {item["class"] for item in result["flips"]} == set(mod.CLASS_ORDER)
    headline = result["headline"]
    assert (headline["flips_n"], headline["down_n"], headline["up_n"]) == (6, 3, 3)
    assert headline["down_ids"] == ["chat-01", "doc-02", "metric-01"]
    assert headline["up_ids"] == ["doc-01", "metric-02", "metric-03"]
    assert headline["class_totals"] == {"检索腿": 2, "生成措辞": 2, "分母口径": 1, "量具取不到": 1}
    assert headline["down_class_totals"] == {"检索腿": 0, "生成措辞": 2, "分母口径": 0,
                                             "量具取不到": 1}
    assert set(headline["down_by_category"]) == {"文档问答", "口径冲突", "多轮对话"}
    assert set(headline["flips_by_category"]) == {"文档问答", "口径冲突", "多轮对话"}
    for item in result["flips"]:
        assert item["code"] and item["class"] in mod.CLASS_ORDER
        evidence = item["evidence"]
        assert evidence["anchors"] and evidence["hi_label"] != evidence["lo_label"]
        assert sorted(evidence["hi_citations"]) != sorted(evidence["lo_citations"]) \
            or item["code"] == mod.CODE_WORD_CHUNK_SAME


def test_the_dropping_buckets_are_flagged_and_the_three_rungs_are_used(tmp_path):
    result = mod.read_pair(**write_pair(tmp_path))
    categories = {item["name"]: item for item in result["buckets"][mod.DIM_CATEGORY]}
    assert categories["多轮对话"]["direction"] == "down"
    assert categories["多轮对话"]["verdict"] == "不达"
    assert categories["口径冲突"]["direction"] == "up"
    assert categories["口径冲突"]["verdict"] == "不可判"          # 分数没降，但 metric-01 没证清
    assert categories["文档问答"]["direction"] == "flat"
    assert categories["文档问答"]["verdict"] == "达"              # 退步全在措辞，被进步抵住
    assert categories["报告生成"]["verdict"] == "达"
    assert categories["报告生成"]["down_flip_ids"] == []
    tiers = {item["name"]: item for item in result["buckets"][mod.DIM_TIER]}
    assert (tiers["问答"]["direction"], tiers["问答"]["verdict"]) == ("down", "不达")
    assert (tiers["分析"]["direction"], tiers["分析"]["verdict"]) == ("up", "不可判")
    assert (tiers["报告"]["direction"], tiers["报告"]["verdict"]) == ("flat", "达")
    assert {"达", "不达", "不可判"} == {item["verdict"] for item in result["verdicts"][mod.DIM_CATEGORY]}
    for item in result["verdicts"][mod.DIM_CATEGORY]:
        assert "=" in item["basis"] and "Δ" in item["basis"]      # 每一档都带凭据


def test_a_leg_attribution_names_the_chunk_level_delta(tmp_path):
    result = mod.read_pair(**write_pair(tmp_path))
    t1 = flip(result, "doc-01")
    assert t1["class"] == mod.CLASS_LEG and t1["code"] == mod.CODE_LEG_T1
    assert "制度登记表.txt#chunk=4" in t1["evidence"]["diff_b_only"]
    assert "制度登记表.txt_4" in t1["evidence"]["hi_leg"]["only_ids"]
    assert "制度登记表.txt_4" not in t1["evidence"]["lo_leg"]["topk_ids"]
    t2 = flip(result, "metric-03")
    assert t2["class"] == mod.CLASS_LEG and t2["code"] == mod.CODE_LEG_T2
    assert t2["evidence"]["lo_citations"] == []
    assert t2["evidence"]["lo_leg"]["rows"] == 0 and t2["evidence"]["hi_leg"]["rows"] > 0
    assert "metric-03" in result["leg_zero_rows"]["chroma"]        # 与 Chroma 空返回那一族同向
    outside = flip(result, "metric-01")
    assert outside["code"] == mod.CODE_UNMEASURED_OUTSIDE
    assert outside["evidence"]["carrier_delta_hi_only"] == ["制度登记表.txt_5"]
    assert "制度登记表.txt_5" not in outside["evidence"]["hi_leg"]["topk_ids"]
    assert "制度登记表.txt_5" not in outside["evidence"]["lo_leg"]["topk_ids"]


def test_denominator_account_is_read_live(tmp_path):
    result = mod.read_pair(**write_pair(tmp_path))
    account = result["denominator_account"]
    unscorable = sorted(quality_eval.unscorable_row_ids(FIXTURE_ROWS))
    assert account["fixture_derived"]["deducted_ids"] == unscorable == ["report-01"]
    assert account["fixture_derived"]["deducted_n"] == 1
    assert account["fixture_derived"]["denominator_rows"] == TOTAL - 1
    assert [cell["deducted_ids"] for cell in account["per_report"].values()] == [unscorable, unscorable]
    assert account["identical_across_windows_by_fixture"] is True
    run_sets = account["per_window_run_sets"]
    assert run_sets["w13"]["error_event_ids"] == ["metric-02"]
    assert run_sets["w14"]["error_event_ids"] == []
    assert account["run_set_window_diffs"]["error_event_ids"] == {
        "only_in_w13": ["metric-02"], "only_in_w14": []}
    assert account["run_set_window_diffs"]["uncompleted_or_failed_ids"]["only_in_w13"] == ["metric-02"]
    assert run_sets["w14"]["approved_final_ids"] == ["report-01"]


def test_the_in_book_report_is_an_independent_witness(tmp_path):
    paths = write_pair(tmp_path)
    result = mod.read_pair(**paths)
    label_a, label_b = result["labels"]["a"], result["labels"]["b"]
    for label, key in ((label_a, "report_a"), (label_b, "report_b")):
        report = json.loads(Path(paths[key]).read_text(encoding="utf-8"))
        checked = result["report_crosscheck"][label]
        assert checked["state"] == "matched"
        assert checked["answer_correctness"] == report["answer_correctness"]
        assert checked["scorable_subset"] == report["answer_correctness_scorable_subset"]
        assert checked["categories_checked"] == len({row["category"] for row in FIXTURE_ROWS})


def test_the_tool_never_declares_green(tmp_path, capsys):
    rc = mod.main(argv_for(write_pair(tmp_path)))
    out = capsys.readouterr().out
    assert rc == mod.EXIT_OK
    assert "翻绿" not in out and "A④ 通过" not in out
    assert "本格只交数" in out
    result = mod.read_pair(**write_pair(tmp_path))
    assert {item["verdict"] for dim in mod.DIMS for item in result["verdicts"][dim]} <= {
        "达", "不达", "不可判"}


def test_main_prints_both_bucket_tables_and_the_live_account(tmp_path, capsys):
    rc = mod.main(argv_for(write_pair(tmp_path)))
    out = capsys.readouterr().out
    assert rc == mod.EXIT_OK
    for needle in ("分桶表（category）", "分桶表（tier）", "守恒：category Σn",
                   "甲案扣除集合现读", "退步逐题点名", "进步逐题点名", "与在册报告对账"):
        assert needle in out
    assert "Σn＝" + str(TOTAL) in out

def twin(paths, tmp_path, dst="w13twin", slot="a"):
    """把某一窗的四本账原样复制成一个新标签（正控用：两窗逐字节相同）。"""
    import shutil
    updated = dict(paths)
    for name, suffix in (("answers", "-answers.jsonl"), ("sidecar", "-sidecar.jsonl"),
                         ("report", "-report.json"), ("window", ".window.json")):
        target = Path(tmp_path) / (dst + suffix)
        shutil.copyfile(str(Path(paths[name + "_" + slot])), str(target))
        updated[name + "_b"] = str(target)
    return updated


def digest(paths):
    return {key: hashlib.sha256(Path(value).read_bytes()).hexdigest()
            for key, value in paths.items()
            if key != "expect_total" and Path(str(value)).is_file()}


def test_counter_evidence_a_mutating_one_answer_moves_that_bucket(tmp_path):
    """刀a：把某一桶的 correct_n 手动改一枚 ⇒ 件必须报下降（证本件不是硬编码的表）。"""
    clean = mod.read_pair(**write_pair(tmp_path / "clean"))
    label_b = clean["labels"]["b"]
    baseline = {item["name"]: (item["n"], item[label_b]["correct_n"])
                for item in clean["buckets"][mod.DIM_CATEGORY]}
    paths = write_pair(tmp_path / "mutated",
                       answers=edited("w14", "report-01", "本期收入增长，成本不变。"))
    moved = mod.read_pair(**paths)
    reporting = bucket(moved, mod.DIM_CATEGORY, "报告生成")
    assert reporting["n"] == 1
    assert reporting[moved["labels"]["b"]]["correct_n"] == 0
    assert reporting["delta_correct_n"] == -1 and reporting["delta_score"] == -1.0
    assert reporting["direction"] == "down" and reporting["verdict"] == "不达"
    down = flip(moved, "report-01")
    assert down["direction"] == "down" and down["class"] == mod.CLASS_WORDING
    assert down["code"] == mod.CODE_WORD_CHUNK_SAME
    for item in moved["buckets"][mod.DIM_CATEGORY]:
        if item["name"] != "报告生成":
            assert (item["n"], item[label_b]["correct_n"]) == baseline[item["name"]]
    assert baseline["报告生成"][1] == 1


def test_counter_evidence_b_a_short_window_is_refused_not_renormalised(tmp_path):
    """刀b：指一份少一枚的 answers ⇒ REFUSE（rc=3），不许把分母悄悄改成 6。"""
    paths = write_pair(tmp_path, reports=False, drop_ids=("report-01",))
    assert len(mod.read_jsonl(paths["answers_a"], "test")) == TOTAL - 1
    with pytest.raises(mod.RefuseError):
        mod.read_pair(**paths)
    assert mod.main(argv_for(paths)) == mod.EXIT_REFUSE


def test_counter_evidence_c_self_comparison_reports_zero_drops(tmp_path, capsys):
    """刀c（正控）：拿同一窗跟自己比 ⇒ 所有桶 0 下降；这条路径不许被"读后端没换"挡死。"""
    paths = twin(write_pair(tmp_path), tmp_path)
    result = mod.read_pair(**paths)
    assert result["pairing"]["mode"] == "self-control"
    assert result["headline"]["flips_n"] == 0 and result["headline"]["down_n"] == 0
    assert {item["direction"] for dim in mod.DIMS for item in result["buckets"][dim]} == {"flat"}
    assert {item["verdict"] for dim in mod.DIMS for item in result["verdicts"][dim]} == {"达"}
    assert mod.main(argv_for(paths)) == mod.EXIT_OK


def test_counter_evidence_d_a_tampered_report_breaks_the_witness(tmp_path):
    """刀d：在册报告被改一枚数 ⇒ 本件必须当场对账不上（rc=2），不许跟着假数走。"""
    paths = write_pair(tmp_path)
    report = json.loads(Path(paths["report_b"]).read_text(encoding="utf-8"))
    report["answer_correctness"] = round(report["answer_correctness"] + 0.1, 4)
    Path(paths["report_b"]).write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    assert mod.main(argv_for(paths)) == mod.EXIT_RECONCILE
    with pytest.raises(mod.ReconcileError):
        mod.read_pair(**paths)


def test_counter_evidence_e_blinding_the_in_book_ruler_moves_every_bucket(tmp_path, monkeypatch):
    """刀e：摘用在册尺（把 _is_correct 换成恒真）⇒ 每一桶的数都必须跟着动，证本件没带第二把尺。"""
    paths = write_pair(tmp_path, reports=False)
    before = mod.read_pair(**paths)
    monkeypatch.setattr(quality_eval, "_is_correct", lambda row, result: True)
    after = mod.read_pair(**paths)
    for item in after["buckets"][mod.DIM_CATEGORY]:
        assert item[after["labels"]["a"]]["correct_n"] == item["n"]
    assert after["headline"]["flips_n"] == 0
    assert sum(item["n"] for item in before["buckets"][mod.DIM_TIER]) == TOTAL


def test_counter_evidence_f_without_parity_no_flip_is_attributable_to_the_leg(tmp_path):
    """刀f：不交 parity ⇒ 检索腿一类必须归零，其余三类不许跟着塌。"""
    paths = write_pair(tmp_path)
    paths["parity"] = str(Path(tmp_path) / "absent-parity.json")
    result = mod.read_pair(**paths)
    assert result["inputs"]["parity"]["state"] == mod.NOT_PROVIDED
    assert result["headline"]["class_totals"][mod.CLASS_LEG] == 0
    assert flip(result, "doc-01")["code"] == mod.CODE_UNMEASURED_NO_PARITY
    assert flip(result, "metric-03")["code"] == mod.CODE_UNMEASURED_NO_PARITY
    assert flip(result, "doc-02")["class"] == mod.CLASS_WORDING
    assert flip(result, "metric-02")["class"] == mod.CLASS_DENOM


def test_counter_evidence_g_tampered_leg_readout_reclassifies_the_flip(tmp_path):
    """刀g：把 parity 里"本腿独有"那几枚抹掉 ⇒ 同一道题必须从检索腿掉回量具取不到。"""
    parity_map = {key: dict(value) for key, value in PARITY_ROWS.items()}
    parity_map["doc-01"] = {"chroma": ["差旅细则.txt_2", "员工手册.txt_1"],
                            "pg": ["差旅细则.txt_2", "员工手册.txt_1"]}
    result = mod.read_pair(**write_pair(tmp_path, parity_map=parity_map))
    moved = flip(result, "doc-01")
    assert moved["class"] == mod.CLASS_UNMEASURED
    assert moved["code"] == mod.CODE_UNMEASURED_OUTSIDE
    assert result["headline"]["class_totals"][mod.CLASS_LEG] == 1     # 只剩 metric-03 那一枚


def test_counter_evidence_h_a_same_backend_pair_is_not_a_contrast(tmp_path, capsys):
    """刀h：两窗读后端相同 ⇒ "唯一变量"破了，判据不许用（rc=2 并点名读后端没换过）。"""
    paths = write_pair(tmp_path, backends={"w13": "", "w14": ""})
    assert mod.main(argv_for(paths)) == mod.EXIT_RECONCILE
    assert "读后端没换过" in capsys.readouterr().out


def test_counter_evidence_i_a_contradicting_backend_claim_is_rejected(tmp_path):
    """刀i：纸面声明的读后端与窗记现读矛盾 ⇒ 以窗记为准并 rc=2，不许拿声明覆盖读数。"""
    paths = write_pair(tmp_path)
    assert mod.main(argv_for(paths) + ["--backend-a", "pgvector"]) == mod.EXIT_RECONCILE


def test_counter_evidence_j_an_unregistered_backend_name_is_rejected(tmp_path):
    """刀j：窗记里冒出不在册的读后端名 ⇒ 没法对到具体的腿上，判据当场拒（rc=2）。"""
    paths = write_pair(tmp_path, backends={"w13": "weaviate", "w14": "pgvector"})
    assert mod.main(argv_for(paths)) == mod.EXIT_RECONCILE


def test_counter_evidence_k_the_instrument_never_writes_to_its_inputs(tmp_path, capsys):
    """刀k：跑完 table 与 json 两趟，输入八本账逐字节 sha256 一枚都不许动。"""
    paths = write_pair(tmp_path)
    before = digest(paths)
    assert mod.main(argv_for(paths)) == mod.EXIT_OK
    out_file = Path(tmp_path) / "readout.json"
    assert mod.main(argv_for(paths) + ["--format", "json", "--out", str(out_file)]) == mod.EXIT_OK
    assert out_file.is_file()
    assert digest(paths) == before


def test_counter_evidence_n_usage_errors_leave_with_refuse_not_reconcile():
    """刀n：用法错（少了 --answers-b）必须走"拒绝出数"那枚码，不许占用"对账不上"的 2。"""
    with pytest.raises(SystemExit) as caught:
        mod.main(["--answers-a", "nowhere-answers.jsonl", "--format", "table"])
    assert caught.value.code == mod.EXIT_REFUSE
    assert mod.EXIT_REFUSE != mod.EXIT_RECONCILE


def test_counter_evidence_l_the_pins_are_offline():
    """刀l：本钉不读任何临时真机目录（那批件是有期限的，常驻判据不许挂在它身上）。"""
    source = Path(__file__).resolve().read_text(encoding="utf-8")
    for token in ("eval" + "run", "App" + "Data", "Local" + "Temp", "Temp" + "Path"):
        assert token not in source, token


def test_counter_evidence_m_there_is_no_downgrade_marker_in_this_grille():
    """刀m：本单两件（量具与钉）零降级记号：不分层出门、不静默跳过、不标记必败。

    🔴 记号名一律用拼接长出来：本件若把这些字面直接写出来，自己就成了自己的反证。
    """
    sources = [(Path(__file__).resolve(), "钉"),
               (REPO_ROOT / "scripts" / "r580_per_class_attribution.py", "量具")]
    markers = ["pytest.mark." + "skip", "pytest." + "skip(", "pytest.mark." + "xfail",
               "pytest.mark." + "only", "pytest.mark." + "skipif"]
    for path, name in sources:
        source = path.read_text(encoding="utf-8")
        for marker in markers:
            assert marker not in source, name + " 里出现了降级记号 " + marker

