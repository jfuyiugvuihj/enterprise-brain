# -*- coding: utf-8 -*-
"""R640 · 账尺派生化的常驻牙：四格判定必须从事实派生，新档不许写死。

这单治的病：`scripts/audit_plan_ticket_ledger.py` 把 R143／R144／R39 三行的判定写死成
「ZERO＝零提交」，把 R51 的欠账理由句写死成「未量」。现取的账面事实是：R143 有结案裁定句
且量具的货色都在仓内（该读成 CLOSED）；R144 在计划书表格与跟进单 §21 判据表里都没有行
（该单列成 FOREIGN，而不是编进零提交分子）；R39 是业主裁定不建（NOTBUILT）；
R51 那一格 10-04 已由取证纸量到并判负（理由句必须跟着纸面改判）。

本件只判「派生有没有落地」，一字不改账面：所有断言都对着同一套现取事实——
祖先链上的提交、仓内路径、计划书表格行、跟进单 §21 判据表、docs/perf 与 docs/testing 的取证纸。
反证刀与正控在 tests/test_r640_counter_evidence_teeth.py。

跑法（必须用仓内 venv 的解释器，anaconda 那枚在 conftest 当场缺 chromadb）：
    .\\.venv\\Scripts\\python.exe -m pytest -p no:randomly -q tests/test_r640_ledger_tiers_are_derived.py
"""
from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RULER = REPO / "scripts" / "audit_plan_ticket_ledger.py"
IN_SCOPE = 43
STDLIB = {"argparse", "io", "re", "subprocess", "sys", "time", "pathlib"}


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, str(RULER))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ruler():
    return _load("r640_ruler_live")


@pytest.fixture(scope="module")
def reading(ruler):
    """一笔现取读数：git 门面复用（归集要逐枚 diff-tree），判定与理由句全走派生层。"""
    git = ruler.Git(ruler.REPO)
    quoter = ruler.Quoter(ruler.REPO)
    ids = [row["id"] for row in ruler.LEDGER]
    deriver = ruler.Deriver(git, quoter, ids)
    rows = ruler.build_rows(git, quoter, deriver)
    return {"ruler": ruler, "git": git, "quoter": quoter, "deriver": deriver,
            "rows": rows, "by_id": {row["id"]: row for row in rows},
            "failures": ruler.self_checks(rows)}


def tiers(reading):
    counts = dict((verdict, 0) for verdict in reading["ruler"].VERDICTS)
    for row in reading["rows"]:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    return counts


# ---------------------------------------------------------------------------
# 账面读数：新档落地、ZERO 归零、逐条自证那条一字不许放宽
# ---------------------------------------------------------------------------

def test_the_book_still_self_proves_every_in_scope_number(reading):
    assert reading["failures"] == [], "在册台账自检必须全过：" + "；".join(reading["failures"])
    assert len(reading["rows"]) == IN_SCOPE, "在册号数被改动了——派生化不许顺手缩范围"


def test_zero_is_empty_while_the_tier_still_exists(reading):
    ruler = reading["ruler"]
    counts = tiers(reading)
    assert counts["ZERO"] == 0, "还记着零提交假账：" + repr(
        [row["id"] for row in reading["rows"] if row["verdict"] == "ZERO"])
    assert "ZERO" in ruler.VERDICTS, "ZERO 这一档本身还得留着（真有零提交的号要往这儿放）"
    for tier in ("CLOSED", "FOREIGN", "NOTBUILT"):
        assert tier in ruler.VERDICTS, tier + " 必须是册内的正式档，不是脚注"


def test_the_four_cells_moved_out_of_the_zero_numerator(reading):
    got = {tid: reading["by_id"][tid]["verdict"] for tid in ("R39", "R143", "R144")}
    assert got == {"R39": "NOTBUILT", "R143": "CLOSED", "R144": "FOREIGN"}, got


# ---------------------------------------------------------------------------
# 逐格点名：判定用了哪条事实、凭据是不是仓内的
# ---------------------------------------------------------------------------

def test_r143_reads_closed_from_a_ruling_plus_repo_artifacts(reading):
    row = reading["by_id"]["R143"]
    facts = row["derived_facts"]
    assert row["verdict"] == "CLOSED"
    assert facts["instrument"].startswith("R") and facts["instrument"] != "R143"
    assert facts["instrument"] in facts["ruling"]["quote"], "结案句必须自己点名量具，不许由脚本另塞一枚号"
    assert "结案" in facts["ruling"]["quote"]
    assert facts["ruling"]["file"].endswith("backend-followup-requests.md")
    assert reading["git"].is_ancestor(facts["commit"]), "结案笔不在 HEAD 祖先链上＝没并树"
    assert facts["papers"] and all(path.startswith(("docs/perf/", "docs/testing/")) for path in facts["papers"])
    for path in list(facts["products"]) + list(facts["papers"]):
        assert (REPO / path).exists(), "结案凭据必须在仓内，got " + path
    assert facts["products"], "CLOSED 要量具的产物码真在树上，纯 docs 不算"


def test_the_closure_credential_is_attached_and_checked_like_any_other_artifact(reading):
    row = reading["by_id"]["R143"]
    derived = [art for art in row["artifacts_resolved"] if art.get("derived")]
    assert len(derived) == 1, "结案凭据那一笔必须挂进台账，才能一起吃 C2/C3/C4/C5"
    assert derived[0]["owner"] == row["derived_facts"]["instrument"]
    assert derived[0]["ancestor"] is True and derived[0]["mention"] is True
    assert derived[0]["expect"] in derived[0]["files"]
    assert not [note for note in reading["failures"] if "R143" in note]


def test_r144_is_called_out_as_a_foreign_number_not_a_zero_commit(reading):
    row = reading["by_id"]["R144"]
    deriver = reading["deriver"]
    assert row["verdict"] == "FOREIGN"
    assert deriver.plan_rows.get("R144") is None, "计划书里读到了它的行就不是外来号"
    assert deriver.s21_rows.get("R144") is None, "跟进单 §21 判据表里有它的行就不是外来号"
    assert deriver.owned.get("R144") is None, "主干上归集到它的产物就不是外来号"
    assert row["artifacts_resolved"] == []
    assert "外来号现取" in row["why"]


def test_r39_is_adjudicated_not_built_and_never_counted_as_open_work(reading):
    row = reading["by_id"]["R39"]
    facts = row["derived_facts"]
    assert row["verdict"] == "NOTBUILT"
    assert "~~R39~~" in facts["plan"]["quote"], "计划书那行必须是删除线形才算裁定"
    assert "不建" in facts["ruling"]["quote"] and "沿用" in facts["ruling"]["quote"]
    assert facts["ruling"]["file"].endswith("backend-followup-requests.md")
    assert "NOTBUILT" in reading["ruler"].CLEARED_TIERS, "裁定不建的号不许进「未清」名单"


def test_r51_keeps_partial_but_hands_the_reason_line_to_the_paper(reading):
    ruler = reading["ruler"]
    row = reading["by_id"]["R51"]
    assert row["verdict"] == "PARTIAL", "R51 的状态本来就记着 PARTIAL，本单改的是理由句不是档位"
    assert row["why_declared"] == ruler.DERIVED
    paper = row["gap_reasons"][0][1]
    assert paper["polarity"] == "MEASURED"
    assert paper["phrase"] in (REPO / paper["paper"]).read_text(encoding="utf-8"), "判语必须逐字来自纸面"
    assert "FAIL" in paper["phrase"]
    assert paper["commit"] == reading["git"].first_add(paper["paper"])
    assert reading["git"].is_ancestor(paper["commit"])
    assert ruler.short(paper["commit"]) in row["why"] and paper["paper"] in row["why"]
    assert paper["counts"], "取证纸里点了未过线枚数，理由句就得带上这个数"
    assert row["why"].startswith(paper["phrase"])


def test_only_one_paper_claims_the_r51_gap(reading):
    hits = reading["deriver"].papers["R51-1"]
    assert hits and len({rel for rel, _, _ in hits}) == 1, "同一格欠账被两枚纸认领＝得先定谁说话"


def test_one_gap_one_voice_and_prose_is_not_a_claim(reading):
    """认领只发生在标题行；正文里提到同一格只记为转述。

    账尺自己的取证纸会把欠账号写进正文（本纸就是），量具那张纸也会在自己正文里再提一次——
    如果「提到就算认领」，任何一枚新写的纸都能顶掉量具的判语，那是另一族假账。
    """
    ruler, deriver = reading["ruler"], reading["deriver"]
    claimers = {}
    for key, hits in deriver.papers.items():
        voices = {rel for rel, _, _ in hits}
        assert len(voices) == 1, "G-%s 被 %d 枚纸在标题里认领：%s" % (key, len(voices), "、".join(sorted(voices)))
        claimers[key] = voices
        for rel, where, line in hits:
            assert ruler.CLAIM_HEAD_RE.match(line), "非标题行成了认领：%s 第 %d 行" % (rel, where + 1)
    assert deriver.quotings, "盘面上一处正文转述都没有＝这条口径压根没被测到"
    quoting = {rel for _, rel in deriver.quotings}
    claiming = {rel for voices in claimers.values() for rel in voices}
    assert quoting - claiming, "转述的纸与认领的纸完全重合＝「转述不认领」这条没真的分开"
    for row in reading["rows"]:
        if row["gap_reasons"]:
            paper = row["gap_reasons"][0][1]
            assert not paper.get("problem"), "G-%s 的判语读不出唯一：%s" % (row["gap_reasons"][0][0], paper["problem"])


# ---------------------------------------------------------------------------
# 反「写死」的静态牙：新档不许当字面量，派生结论不许在源码里预写
# ---------------------------------------------------------------------------

def _ticket_calls():
    tree = ast.parse(RULER.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "T":
            out.append(node)
    return out


def test_new_tiers_are_never_authored_as_literal_verdicts():
    offenders = []
    for call in _ticket_calls():
        verdict = call.args[1]
        if isinstance(verdict, ast.Constant) and verdict.value in ("CLOSED", "FOREIGN", "NOTBUILT"):
            offenders.append((call.args[0].value, verdict.value))
    assert offenders == [], "新档判定被写死了（本格只许挂 DERIVED 哨兵）：" + repr(offenders)


def test_the_derived_opt_ins_match_the_facts_exactly():
    tree = ast.parse(RULER.read_text(encoding="utf-8"))
    opted = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "T":
            if isinstance(node.args[1], ast.Name) and node.args[1].id == "DERIVED":
                opted.append(node.args[0].value)
    git = ruler_module().Git(RULER.parents[1])
    quoter = ruler_module().Quoter(RULER.parents[1])
    deriver = ruler_module().Deriver(git, quoter, [row["id"] for row in ruler_module().LEDGER])
    should = [row["id"] for row in ruler_module().LEDGER
              if (deriver.decide(row)[0] or "") in ("CLOSED", "FOREIGN", "NOTBUILT")]
    assert sorted(opted) == sorted(should), "标了派生的号必须正好是事实能派出新档的号：" + repr((opted, should))


def test_the_ruler_source_preloads_no_conclusions():
    source = RULER.read_text(encoding="utf-8")
    for rehearsed in ("R626", "4da0bad", "d00b791", "105／105", "105/105/106"):
        assert rehearsed not in source, "派生结论被预写进源码了：" + rehearsed
    for call in _ticket_calls():
        for arg in ast.walk(call):
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                assert "未量" not in arg.value, "台账里还藏着写死的「未量」理由句"


def test_derivation_reads_nothing_outside_the_repo():
    tree = ast.parse(RULER.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= STDLIB, "账尺只许 stdlib，不得 import 产品模块：" + repr(sorted(imported - STDLIB))
    assert not any(isinstance(node, ast.Attribute) and node.attr in ("environ", "expanduser")
                   for node in ast.walk(tree)), "派生不许读环境变量或用户目录（%TEMP% 里的工件不算凭据）"


def ruler_module():
    global _CACHED
    try:
        return _CACHED
    except NameError:
        _CACHED = _load("r640_ruler_static")
        return _CACHED


# ---------------------------------------------------------------------------
# 输出契约：CLI 读数、同一 HEAD 逐字节稳定
# ---------------------------------------------------------------------------

def _cli(*extra):
    proc = subprocess.run([sys.executable, str(RULER)] + list(extra), capture_output=True, cwd=str(REPO))
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def test_the_cli_prints_six_tiers_and_still_passes():
    code, text = _cli()
    assert code == 0, text[-800:]
    assert "在册 43 号：LANDED=23 · PARTIAL=17 · CLOSED=1 · ZERO=0 · FOREIGN=1 · NOTBUILT=1" in text
    assert "RESULT=PASS（0 条违规，在册 43 号逐条自证）" in text
    assert "不计入欠账的档：R39 R143 R144" in text
    assert "🔴 账面滞后：本尺派生为 CLOSED" in text, "计划书那行还写「待派」——尺只能报滞后，改表归人"


def test_same_head_twice_is_byte_identical(reading):
    ruler, git = reading["ruler"], reading["git"]
    ids = [row["id"] for row in ruler.LEDGER]
    first, second = [], []
    for sink in (first, second):
        deriver = ruler.Deriver(git, ruler.Quoter(ruler.REPO), ids)
        rows = ruler.build_rows(git, ruler.Quoter(ruler.REPO), deriver)
        out = ruler.render_head(git, rows, {}, deriver)
        ruler.render_tail(git, rows, out)
        sink.append("\n".join(out))
    assert first[0] == second[0], "同一 HEAD 两次读数不一致＝报表不可信"