# -*- coding: utf-8 -*-
"""R491 · 判据③：号账逐档各有实例，且不许塌档。R498 把档位从三档扩到六档并换掉烧掉的探针。

病根（09-29 事故 #88）：账面把从没立过的号（R475/R476 那族）当成有提交的单派了工；
另一半病根（R498）：把「提交信息里提到这个号」当成「这个号的货并了树」——反向的同一种假账。
`scripts/dispatch_preflight.py` 的 (c) 档吃两路证据：
  证据一 = `git log --all -F --grep=<号> --name-only`（逐枚按号边界复核，防 R26 蒙中 R260–R269；
            并树还须过三腿：首行落地形状 / 实改非空且在 `git ls-files` 在册 / 与正文点名写域有交集）；
  证据二 = docs/** 里的账面提及（在册 + 未忽略的工作区件，同 `rg -l <号> docs` 口径）。
分档：有并树凭据 ⇒ HAS_COMMIT；声称并树却不在本树祖先链 ⇒ LANDING_OFF_TRUNK；
      声称并树而写域对不上 ⇒ LANDING_CONFLICT；父号零并树而子号有 ⇒ SUBNUMBER_LANDED；
      只被提及 ⇒ MENTION_ONLY；零提交但有账面 ⇒ PAPER_ONLY；两路皆零 ⇒ NEVER_FILED（判死）。

本件吃的是活账：R478 在树上（HAS_COMMIT 实例），R476/R486 是 #88 那族账面号（至少一枚必须仍读
PAPER_ONLY），R475 是「正文提过、货没并树」的活实例（R491 落地信息里点了它的名），
NEVER_FILED 从一枚都不挂在账面里的探针池现选。读数一份共享（模块级 fixture），不重跑 git。

🔴 NEVER_FILED 的探针号只许活在测试件里：被 docs/** 提到就翻 PAPER_ONLY，被任何一枚提交信息提到
   就翻 MENTION_ONLY。R491 那一班就栽在这一格——它的并树提交正文里写了「R475 PAPER_ONLY/
   R900 NEVER_FILED」，把 R900 自己烧了（本席 09-29 现读：R900 mentions=1 首笔 7126614）。
   所以探针改成**从池里现选**，并另有一枚 tripwire 指名是谁把哪枚号抄走的。
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
PHANTOM = ("R475", "R476", "R486")  # #88 那族账面号 ⇒ 一枚都不许读成已并树
MENTIONED = "R475"                  # 正文提过、货没并树 ⇒ MENTION_ONLY 的活实例
#: NEVER_FILED 探针池：六枚都不该被任何提交信息与 docs/** 提到；被烧了就换下一枚。
UNFILED_POOL = ("R902", "R903", "R980", "R981", "R990", "R991")
PROBE_FLOOR = 4                     # 池里至少四枚仍两路皆零，否则这格的证据层就是坏的


def ledger_text(probes):
    return "把 {0} 的并树账与 {1} 三枚账面号、以及 {2} 两枚没立过的号一起核一遍。".format(
        LANDED, " ".join(PHANTOM), " ".join(probes))


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
def probes(ruler):
    """两路皆零的探针现选（提交记录与 docs 都读不到才算干净）。"""
    index = ruler.paper_index()
    clean = [one for one in UNFILED_POOL if ruler.records(one) == [] and one not in index]
    assert len(clean) >= PROBE_FLOOR, (
        "探针池只剩 {0} 枚干净号（< {1}）：池子被抄脏了，换一批不落账的号".format(
            clean, PROBE_FLOOR))
    return tuple(clean[:2])


@pytest.fixture(scope="module")
def ledger(ruler, probes):
    return ruler.check(ledger_text(probes), label="ledger")


def row_for(report, token):
    hits = [item for item in report["numbers"] if item["token"] == token]
    assert len(hits) == 1, token + " 在该读几枚？引用切重了"
    return hits[0]


# ---------------------------------------------------------------------------
# 三档各有实例，且互不相同
# ---------------------------------------------------------------------------

def test_all_three_tiers_show_up_in_one_reading(r491, ledger, probes):
    statuses = [row_for(ledger, token)["status"]
                for token in (LANDED,) + PHANTOM + probes]
    assert r491.HAS_COMMIT in statuses and r491.PAPER_ONLY in statuses and r491.NEVER_FILED in statuses
    assert len(set(statuses)) >= 3, "三档塌成一档或两档，这档检查就是摆设"
    #: R498 加的档也必须在同一笔读数里现形，且不许有任何一档塌进 HAS_COMMIT。
    assert row_for(ledger, MENTIONED)["status"] in (r491.MENTION_ONLY, r491.PAPER_ONLY)
    assert [one for one in (LANDED,) + PHANTOM + probes
            if row_for(ledger, one)["status"] == r491.HAS_COMMIT] == [LANDED]


def test_a_mention_is_never_read_as_a_landing(r491, ruler):
    """R475 只在别人的并树正文里被提过：这一枚必须读成提及，且读数要说出口是哪一枚提交。"""
    report = ruler.check("{0} 这号被 R491 的并树信息提过。".format(MENTIONED), label="mention")
    row = row_for(report, MENTIONED)
    assert row["status"] == r491.MENTION_ONLY, (
        "{0} 读成了 {1}：本枚吃的是「正文提及而未并树」的活账，它一旦真并树就得换新料".format(
            MENTIONED, row["status"]))
    assert row["commits"] == 0 and row["mentions"] > 0 and row["first"]
    assert "并树 0 枚" in row["note"], "MENTION_ONLY 的读数必须把「并树零枚」说出口：" + row["note"]


def test_the_six_tiers_are_six_different_words(r491):
    """六档各是一个字面不同的读数，两两不许同名（塌档的第一道牙）。"""
    tiers = (r491.HAS_COMMIT, r491.LANDING_OFF_TRUNK, r491.LANDING_CONFLICT,
             r491.SUBNUMBER_LANDED, r491.MENTION_ONLY, r491.PAPER_ONLY, r491.NEVER_FILED)
    assert len(set(tiers)) == len(tiers)
    assert sum(1 for one in tiers if one in r491.RED_STATUSES) == 1, "号账这一档仍只许咬 NEVER_FILED"


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


def test_the_unfiled_numbers_read_red(r491, ledger, probes):
    for token in probes:
        row = row_for(ledger, token)
        assert row["status"] == r491.NEVER_FILED
        assert (row["commits"], row["docs"]) == (0, 0)
    assert row_for(ledger, probes[0])["red"] is True


def test_only_never_filed_numbers_are_judged_dead(r491, ledger, probes):
    reds = [item["token"] for item in ledger["numbers"] if item["red"]]
    assert reds == list(probes), "号账这一档只许咬 NEVER_FILED，不许顺手把账面号也判死"
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


def test_never_filed_tokens_have_zero_commit_evidence(ruler, probes):
    for token in probes:
        assert ruler.records(token) == [], token + " 名下已经有提交了？档位得重排"
        assert ruler.landing_hits(token)[0] == [], token + " 名下读出并树凭据了？"


def test_the_never_filed_probes_are_not_burned_by_documentation(ruler):
    """tripwire：探针号一旦被 docs/** 抄走就点名是谁。"""
    index = ruler.paper_index()
    burned = [(one, index[one]) for one in UNFILED_POOL if one in index]
    assert len(burned) <= 2, "探针池被账面抄脏：" + repr(burned)


def test_the_landing_commit_of_a_sibling_ticket_does_not_burn_a_probe(ruler):
    """R491 那一班的并树正文把 R900 写进去、于是 R900 再也不是 NEVER_FILED：这一族要有牙。

    点名要求：任何一枚**首行是落地形状**的提交，正文里都不许出现探针池的号——
    出现即红，并把「哪一枚提交、烧了哪枚号」说出口（R491 的落地信息今天仍带着 R900，
    所以本枚只查落地形状提交新烧的号，旧账由上面两枚兜住）。
    """
    burned = []
    for token in UNFILED_POOL:
        landed, offtrunk, mentioned, refused = ruler.landing_hits(token)
        if landed or offtrunk:
            burned.append((token, landed[0]["sha"] if landed else offtrunk[0]["sha"]))
    assert burned == [], "探针号被人当成已并树立起来了，换号再来：" + repr(burned)
