# -*- coding: utf-8 -*-
"""R491 · 判据③：号账三档各有实例，且不许塌成一档。

病根（09-29 事故 #88）：账面把从没立过的号（R475/R476 那族）当成有提交的单派了工。
`scripts/dispatch_preflight.py` 的 (c) 档吃两路证据：
  证据一 = `git log --all -F --grep=<号>`（并按号边界复核，防 R47 蒙中 R478）；
  证据二 = docs/** 里的账面提及（在册 + 未忽略的工作区件，同 `rg -l <号> docs` 口径）。
分档：有提交 ⇒ HAS_COMMIT；零提交但有账面 ⇒ PAPER_ONLY；两路皆零 ⇒ NEVER_FILED（判死）。

本件吃的是活账：R478 在树上（HAS_COMMIT 实例），R475/R476/R486 是 #88 那族账面号
（至少一枚必须仍读 PAPER_ONLY），R888/R999 两路皆零（NEVER_FILED 实例）。
读数一份共享（模块级 fixture），免得每枚测试都去重跑一遍 git。

🔴 NEVER_FILED 的探针号只许活在测试件里：一旦被 docs/** 提到，它就翻成 PAPER_ONLY（本单初稿抄进
   说明文档后，这枚钉当场红过一次），所以下面另有一枚 tripwire 指名是谁把它抄走的。
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "dispatch_preflight.py"

LANDED = "R478"                     # 已并树 ⇒ HAS_COMMIT 的活实例
PHANTOM = ("R475", "R476", "R486")  # #88 那族账面号 ⇒ PAPER_ONLY 的活实例
UNFILED = ("R900", "R901")          # 两路皆零 ⇒ NEVER_FILED 的探针号

LEDGER_TEXT = "把 {0} 的并树账与 {1} 三枚账面号、以及 {2} 两枚没立过的号一起核一遍。".format(
    LANDED, " ".join(PHANTOM), " ".join(UNFILED))


@pytest.fixture(scope="module")
def r491():
    spec = importlib.util.spec_from_file_location("dispatch_preflight_r491_ledger", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ruler(r491):
    return r491.Ruler(REPO_ROOT)


@pytest.fixture(scope="module")
def ledger(ruler):
    return ruler.check(LEDGER_TEXT, label="ledger")


def row_for(report, token):
    hits = [item for item in report["numbers"] if item["token"] == token]
    assert len(hits) == 1, token + " 在该读几枚？引用切重了"
    return hits[0]


# ---------------------------------------------------------------------------
# 三档各有实例，且互不相同
# ---------------------------------------------------------------------------

def test_all_three_tiers_show_up_in_one_reading(r491, ledger):
    statuses = [row_for(ledger, token)["status"] for token in (LANDED,) + PHANTOM + UNFILED]
    assert r491.HAS_COMMIT in statuses and r491.PAPER_ONLY in statuses and r491.NEVER_FILED in statuses
    assert len(set(statuses)) == 3, "三档塌成一档或两档，这档检查就是摆设"


def test_the_landed_ticket_names_a_real_commit(r491, ledger):
    row = row_for(ledger, LANDED)
    assert row["status"] == r491.HAS_COMMIT
    assert row["commits"] > 0 and re.fullmatch(r"[0-9a-f]{7}", row["first"]), "HAS_COMMIT 得能报出首笔 sha"


def test_the_phantom_family_still_reads_paper_only(r491, ledger):
    paper = [t["token"] for t in ledger["numbers"] if t["status"] == r491.PAPER_ONLY]
    assert set(paper) & set(PHANTOM), (
        "R475/R476/R486 一枚都没读成 PAPER_ONLY：账面样本变了，本件要按 #88 的新账换号"
    )
    for token in set(paper) & set(PHANTOM):
        row = row_for(ledger, token)
        assert row["commits"] == 0 and row["docs"] > 0, token + " 的 PAPER_ONLY 必须真是「零提交 + 有账面」"


def test_the_unfiled_numbers_read_red(r491, ledger):
    for token in UNFILED:
        row = row_for(ledger, token)
        assert row["status"] == r491.NEVER_FILED
        assert (row["commits"], row["docs"]) == (0, 0)
    assert row_for(ledger, UNFILED[0])["red"] is True


def test_only_never_filed_numbers_are_judged_dead(r491, ledger):
    reds = [item["token"] for item in ledger["numbers"] if item["red"]]
    assert reds == list(UNFILED), "号账这一档只许咬 NEVER_FILED，不许顺手把账面号也判死"
    assert ledger["exit_code"] == 1


def test_a_reading_about_landed_tickets_only_stays_clean(r491, ruler):
    report = ruler.check("只提 {0} 与 R231 两枚已并树的号。".format(LANDED))
    assert {item["status"] for item in report["numbers"]} == {r491.HAS_COMMIT}
    assert report["red"] == 0 and report["exit_code"] == 0


# ---------------------------------------------------------------------------
# 证据口径：号边界与 docs 窗口
# ---------------------------------------------------------------------------

def test_the_number_tokens_do_not_bleed_into_each_other(r491):
    assert r491.extract_numbers("R47 R478 R4785 R205a R4900") == ["R47", "R478", "R205a"]


def test_a_lowercase_ticket_inside_a_filename_is_not_a_number(r491):
    assert r491.extract_numbers("tests/test_r387_label_ruler_teeth.py") == []
    assert r491.extract_numbers("%TEMP%\\evalrun\\r428-driver.md") == []


@pytest.mark.parametrize("message,token,expected", [
    ("R478 并树", "R478", True),
    ("看板 §4DV：R478/R481/R483 三枚", "R481", True),
    ("R4785 这号不存在", "R478", False),
    ("r478 小写不算", "R478", False),
    ("priorR478 粘着字母", "R478", False),
    ("R47 单独一枚", "R47", True),
])
def test_the_commit_evidence_is_rechecked_at_the_number_boundary(r491, message, token, expected):
    assert r491.message_names_token(message, token) is expected


def test_the_paper_evidence_window_is_docs_only(r491, ruler):
    index = ruler.paper_index()
    assert index, "docs/** 里一枚号都读不到？这台尺子的账面窗口空转了"
    for token, files in index.items():
        assert files, token + " 不该挂着零枚出处"
        for rel in files:
            assert rel.startswith("docs/"), "账面证据只许来自 docs/**，got " + rel


def test_never_filed_tokens_have_zero_commit_evidence(ruler):
    for token in UNFILED:
        assert ruler.commit_hits(token) == [], token + " 已经有提交了？三档得重排"


def test_the_never_filed_probes_are_not_burned_by_documentation(ruler):
    index = ruler.paper_index()
    for token in UNFILED:
        assert token not in index, (
            "{0} 已被 docs/** 提起（{1}）：探针号只许写在测试件里，换号再来".format(
                token, ", ".join(index.get(token, []))))
