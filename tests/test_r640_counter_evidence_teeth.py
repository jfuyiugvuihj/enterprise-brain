# -*- coding: utf-8 -*-
"""R640 的反证刀：把「派生」这件事逐枚摘一次，每一枚都必须红，且每把都先跑正控。

机械沿用 R545（样板＝主树并树笔里的影子端三态）：影子只在 tmp_path 里——源文从盘上读进字符串、
归一 LF、改、写出去、compile＋exec 成另一枚模块；仓内那枚尺子一个字节都不动，docs/handoff 也不动。
影子的 git 门面仍指真仓（祖先链是事实，不许伪造），只有「文件视图」被 OverlayQuoter 换过：
被改的正文不进跨刀共享的行缓存，其余照旧真仓只读。

十把刀（逐枚点名 victim 与咬它的牙）：
  K1  喂假 sha（`--fault R143=CLOSED@deadbeef`）→ C2/C6/C17 红并点名 R143
  K1b 喂真但不在祖先链的 sha（off-trunk 现取）→ C3 红并点名 R143
  K2  摘掉跟进单 §21 那句「R39 不建，沿用 R17」→ R39 变回它自己的判定（ZERO）并红（C12）
  K2b 摘掉计划书那行的删除线（裁定句留着）→ 同一格缺另一条腿，照样红（C12）
  K3  把派生判定改回硬编码（CLOSED／FOREIGN／ZERO 三种写法）→ C11 或 C13 红
  K4  把 R51 的理由句改回写死的「未量」→ 与在册取证纸打架，C14 红
  K5  把结案量具的取证纸「从盘上拿走」→ 结案派生断腿，R143 红（C12）
  K6  改纸面判语：翻成量不到→理由句跟着纸走且仍自证；翻成 PASS→C15 红（读的是内容不是标题）
  K7  新写一枚只在正文里转述 G-R51-1 的纸→ 不许认领这一格，量具的判语一个字都不许被顶掉
  K8  新写一枚在标题里认领 G-R51-1 的纸→ 同一格两枚纸说话，C12 当场红并点名两枚纸
  K9  一枚纸认领了某格却没写带极性的判语→ 即使该格理由句是写死的，C18 也得红（不许沉默）

摘刀、加豁免、`pytest.skip` 一律不许：每把都先用同一套机械跑正控（不带 edits/overrides），
正控不绿就不准算咬中。全程离线：零容器、零连库、零模型、产品码零字节落盘。

跑法（必须用仓内 venv 的解释器）：
    .\\.venv\\Scripts\\python.exe -m pytest -p no:randomly -q tests/test_r640_counter_evidence_teeth.py
"""
from __future__ import annotations

import importlib.util
import itertools
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RULER_REL = "scripts/audit_plan_ticket_ledger.py"
PLAN_REL = "docs/handoff/2026-09-17-perf-architecture-plan.md"
FOLLOWUP_REL = "docs/handoff/2026-09-15-backend-followup-requests.md"
CODE_RE = re.compile(r"(?:🔴 )?(C\d+)")
NAMES = itertools.count()
# 影子里凭空添的取证纸（只活在影子层，仓内与盘上都不落）
QUOTE_ONLY_REL = "docs/testing/r999-quote-only.md"
SECOND_CLAIM_REL = "docs/testing/r999-second-claim.md"
SILENT_CLAIM_REL = "docs/testing/r998-silent-claim.md"

# ---- 刀口（逐枚原文锚点；锚点漂了本件当场停手）--------------------------------
CUT_R39_RULING = ("每单的**判据与禁改边界**以本节为准。**R39 不建，沿用 R17**（裁定=甲）。",
                  "每单的**判据与禁改边界**以本节为准。（这一句被反证刀摘掉，不留裁定痕迹。）")
CUT_R39_STRIKE = ("| ~~R39~~ | **不建**，沿用 R17（裁定 5 = 甲） | — | — |",
                  "| R39 | 不建，沿用 R17（裁定 5 = 甲） | — | — |")
CUT_R143_CLOSED = ('    T("R143", DERIVED, [], [],', '    T("R143", "CLOSED", [], [],')
CUT_R143_ZERO = ('    T("R143", DERIVED, [], [],', '    T("R143", "ZERO", [], [],')
CUT_R144_FOREIGN = ('    T("R144", DERIVED, [], [],', '    T("R144", "FOREIGN", [], [],')
CUT_R51_WHY = ('      [S21(51, "②")], DERIVED),',
               '      [S21(51, "②")], "② 加总误差 <1% 未量；rewrite/reflect 两格插桩后置"),')
CUT_PAPER_UNMEASURED = ("G-R51-1 的判语从「量不到（RC=3）」改为「量到了，三窗全 FAIL（RC=1）」",
                        "G-R51-1 的判语从「量到了，三窗全 FAIL（RC=1）」改为「量不到（RC=3）」")
CUT_PAPER_PASS = ("G-R51-1 的判语从「量不到（RC=3）」改为「量到了，三窗全 FAIL（RC=1）」",
                  "G-R51-1 的判语从「量不到（RC=3）」改为「量到了，三窗全 PASS（RC=0）」")


def _text(rel):
    return (REPO / rel).read_bytes().decode("utf-8").replace("\r\n", "\n")


def _apply(text, edits):
    out = text
    for old, new in edits:
        if out.count(old) != 1:
            raise AssertionError("刀口没落在唯一一处：%r（命中 %d 枚）" % (old[:48], out.count(old)))
        out = out.replace(old, new, 1)
    return out


WRITES = []


def _exec(name, source, where):
    where.mkdir(parents=True, exist_ok=True)
    path = where / (name + ".py")
    WRITES.append(path)
    path.write_bytes(source.replace("\n", "\r\n").encode("utf-8"))
    spec = importlib.util.spec_from_file_location(name, str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    module.REPO = REPO  # 影子模块的仓根一律指回真仓，否则红得没有道理
    return module


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    """未改动的尺子＋一枚复用 git 门面（祖先链与归集缓存在这里，逐刀不重跑 git）。"""
    sandbox = tmp_path_factory.mktemp("r640-shadow")
    module = _exec("r640_teeth_live", _text(RULER_REL), sandbox)
    return {"module": module, "git": module.Git(REPO), "lines": {}, "sandbox": sandbox}


def overlay_class(module):
    class OverlayQuoter(module.Quoter):
        """文件视图：overrides 里的正文替换盘上读数，其余照旧读真仓。"""

        def __init__(self, root, overrides, shared):
            module.Quoter.__init__(self, root)
            self._lines = shared
            self.overrides = dict(overrides)

        def file_lines(self, rel):
            if rel in self.overrides:
                return [line.rstrip("\r") for line in self.overrides[rel].split("\n")]
            return module.Quoter.file_lines(self, rel)

    return OverlayQuoter


def denier_class(module):
    class DenyDeriver(module.Deriver):
        """把某枚仓内产物「假装不在盘上」——只在影子里判存在，真仓一个文件都不碰。"""

        missing = frozenset()
        extra_papers = ()

        def exists(self, rel):
            return False if rel in self.missing else module.Deriver.exists(self, rel)

        def evidence_paths(self):
            """影子里添一枚取证纸不必往仓里写文件：清单换掉，正文走 OverlayQuoter 的覆盖视图。"""
            return list(module.Deriver.evidence_paths(self)) + list(self.extra_papers)

    return DenyDeriver


def judge(live, tmp, ruler_edits=(), overrides=(), missing=(), extra_papers=()):
    if ruler_edits:
        module = _exec("r640_teeth_shadow_%d" % next(NAMES),
                       _apply(_text(RULER_REL), ruler_edits), tmp)
    else:
        module = live["module"]
    view = dict(overrides)
    view.update(extra_papers)
    quoter = overlay_class(module)(REPO, view, live["lines"])
    deriver = denier_class(module)
    deriver.missing = frozenset(missing)
    deriver.extra_papers = tuple(sorted(extra_papers))
    built = deriver(live["git"], quoter, [row["id"] for row in module.LEDGER])
    rows = module.build_rows(live["git"], quoter, built)
    return module, rows, module.self_checks(rows), built


def control(live, tmp):
    _, rows, failures, _ = judge(live, tmp)
    assert failures == [], "正控必须先绿，否则后面的红没有意义：" + "；".join(failures)
    return {row["id"]: row for row in rows}


def row_of(rows, tid):
    return [row for row in rows if row["id"] == tid][0]


def codes(failures):
    return [CODE_RE.match(note).group(1) for note in failures if CODE_RE.match(note)]


def bites(failures, victim, code):
    picked = [note for note in failures if victim in note]
    assert picked, "没有一枚牙咬到 %s：%s" % (victim, "；".join(failures) or "全绿")
    assert code in codes(picked), "%s 的红不是 %s 咬的：%s" % (victim, code, "；".join(picked))
    return picked


CLI_RUNS = {}


def cli(*extra):
    """CLI 读数按参数记忆：同一枚注入只跑一次子进程（跑一次量具要十几秒，不该逐枚重付）。"""
    if extra not in CLI_RUNS:
        proc = subprocess.run([sys.executable, str(REPO / RULER_REL)] + list(extra),
                              capture_output=True, cwd=str(REPO))
        CLI_RUNS[extra] = (proc.returncode, proc.stdout.decode("utf-8", "replace"))
    return CLI_RUNS[extra]


# ---------------------------------------------------------------------------
# K1／K1b：假 sha 与 off-trunk sha
# ---------------------------------------------------------------------------

def test_k1_feeding_a_fake_sha_reddens_and_names_the_ticket():
    code, text = cli()
    assert code == 0 and "RESULT=PASS" in text, "正控：不注入故障时这本账必须自证"
    code, text = cli("--fault", "R143=CLOSED@deadbeef")
    assert code == 1, "喂假 sha 还 PASS＝这把刀是摆设"
    assert "RESULT=FAIL" in text and "R143" in text
    picked = [line for line in text.splitlines() if line.startswith("🔴") and "R143" in line]
    assert picked and any("不存在" in line for line in picked), picked


def test_k1b_an_off_trunk_sha_is_refused_by_the_ancestor_chain():
    pool = subprocess.run(["git", "-C", str(REPO), "rev-list", "--all", "--not", "HEAD"],
                          capture_output=True).stdout.decode().split()
    assert pool, "本仓一枚 off-trunk 提交都没有＝这把刀没料，留一枚在飞的分支再来"
    code, text = cli("--fault", "R143=CLOSED@" + pool[0])
    assert code == 1 and "R143" in text
    assert any("不在 HEAD 祖先链上" in line for line in text.splitlines() if "R143" in line), text[-400:]


# ---------------------------------------------------------------------------
# K2／K2b：裁定句与删除线只能成对，缺一条腿就红
# ---------------------------------------------------------------------------

def test_k2_removing_the_r39_ruling_reverts_it_to_its_own_judgment_and_reddens(live, tmp_path):
    control(live, tmp_path)
    follow = _apply(_text(FOLLOWUP_REL), (CUT_R39_RULING,))
    _, rows, failures, _ = judge(live, tmp_path, overrides={FOLLOWUP_REL: follow})
    assert row_of(rows, "R39")["verdict"] == "ZERO", "摘了裁定就该变回它自己的判定"
    picked = bites(failures, "R39", "C12")
    assert "删除线" in " ".join(picked), picked


def test_k2b_unstriking_the_plan_row_reddens_the_other_leg(live, tmp_path):
    control(live, tmp_path)
    plan = _apply(_text(PLAN_REL), (CUT_R39_STRIKE,))
    _, _, failures, _ = judge(live, tmp_path, overrides={PLAN_REL: plan})
    picked = bites(failures, "R39", "C12")
    assert "裁定句" in " ".join(picked), picked


# ---------------------------------------------------------------------------
# K3：判定改回硬编码就得被咬（新档写死＝C11，写死成 ZERO 与事实打架＝C13）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cut,code", [
    (CUT_R143_CLOSED, "C11"),
    (CUT_R144_FOREIGN, "C11"),
    (CUT_R143_ZERO, "C13"),
])
def test_k3_rehardcoding_a_verdict_is_refused(live, tmp_path, cut, code):
    control(live, tmp_path)
    victim = cut[0].split('"')[1]
    _, rows, failures, _ = judge(live, tmp_path, ruler_edits=(cut,))
    picked = bites(failures, victim, code)
    assert row_of(rows, victim)["verdict"] == cut[1].split('"')[3], "影子台账没接住这枚硬编码"
    assert picked


# ---------------------------------------------------------------------------
# K4：R51 理由句翻回写死的「未量」
# ---------------------------------------------------------------------------

def test_k4_a_stale_hardcoded_reason_contradicts_the_paper(live, tmp_path):
    by_id = control(live, tmp_path)
    assert "取证纸现取" in by_id["R51"]["why"], "正控里 R51 的理由句就该是纸面派生的"
    _, _, failures, _ = judge(live, tmp_path, ruler_edits=(CUT_R51_WHY,))
    picked = bites(failures, "R51", "C14")
    assert "未量" in " ".join(picked) and "取证纸" in " ".join(picked), picked


# ---------------------------------------------------------------------------
# K5：结案量具的取证纸不在盘上＝结案没有仓内凭据
# ---------------------------------------------------------------------------

def test_k5_hiding_the_closure_paper_breaks_the_closed_tier(live, tmp_path):
    by_id = control(live, tmp_path)
    papers = by_id["R143"]["derived_facts"]["papers"]
    assert papers, "结案凭据里读不到仓内取证纸＝这本账本来就是假的"
    _, rows, failures, _ = judge(live, tmp_path, missing=papers)
    assert row_of(rows, "R143")["verdict"] != "CLOSED"
    picked = bites(failures, "R143", "C12")
    assert "取证纸" in " ".join(picked) or "祖先" in " ".join(picked), picked


# ---------------------------------------------------------------------------
# K6：理由句跟的是纸面内容——翻成「量不到」就跟着改口，翻成 PASS 就当场红
# ---------------------------------------------------------------------------

def test_k6a_the_reason_follows_the_paper_not_the_ticket_title(live, tmp_path):
    by_id = control(live, tmp_path)
    paper_rel = by_id["R51"]["gap_reasons"][0][1]["paper"]
    flipped = _apply(_text(paper_rel), (CUT_PAPER_UNMEASURED,))
    module, rows, failures, _ = judge(live, tmp_path, overrides={paper_rel: flipped})
    assert failures == [], "纸面改口成「量不到」是合法订正，不该红：" + "；".join(failures)
    facts = row_of(rows, "R51")["gap_reasons"][0][1]
    assert facts["polarity"] == "UNMEASURED" and "量不到" in facts["phrase"]
    assert "量不到" in row_of(rows, "R51")["why"], "理由句没跟着纸面走＝它根本不是派生的"
    assert "FAIL" not in row_of(rows, "R51")["why"]


def test_k6b_a_paper_that_judged_the_gap_passed_reddens_the_open_debt(live, tmp_path):
    by_id = control(live, tmp_path)
    paper_rel = by_id["R51"]["gap_reasons"][0][1]["paper"]
    flipped = _apply(_text(paper_rel), (CUT_PAPER_PASS,))
    _, _, failures, _ = judge(live, tmp_path, overrides={paper_rel: flipped})
    picked = bites(failures, "R51", "C15")
    assert "PASS" in " ".join(picked), picked


# ---------------------------------------------------------------------------
# K7／K8／K9：谁在说话——认领看标题，转述不算，同一格不许两枚纸抢
# ---------------------------------------------------------------------------

QUOTE_ONLY_PAPER = """# R999 —— 一枚只在正文里转述别人的纸

本纸不测任何格，只是引用：G-R51-1 那一格早前有人说过「量不到（RC=3）」。
"""

SECOND_CLAIM_PAPER = """# R999 —— G-R51-1 这一格从今天起归本纸说话

正文：本纸重跑一遍，结论照抄。
"""

SILENT_CLAIM_PAPER = """# R998 —— G-R25-1 取证纸

正文只写过程：起了两遍，取了数，没写带极性的判语。
"""


def test_k7_a_prose_quotation_does_not_claim_the_gap(live, tmp_path):
    by_id = control(live, tmp_path)
    truth = by_id["R51"]["gap_reasons"][0][1]
    module, rows, failures, built = judge(
        live, tmp_path, extra_papers={QUOTE_ONLY_REL: QUOTE_ONLY_PAPER})
    assert failures == [], "一枚只转述的纸不该动这本账：" + "；".join(failures)
    facts = row_of(rows, "R51")["gap_reasons"][0][1]
    assert facts["paper"] == truth["paper"], "转述顶掉了量具那张纸——认领口径又塌回「提到就算」"
    assert facts["phrase"] == truth["phrase"] and facts["polarity"] == "MEASURED"
    assert {rel for rel, _, _ in built.papers["R51-1"]} == {truth["paper"]}, "认领集里混进了转述的纸"
    assert ("R51-1", QUOTE_ONLY_REL) in built.quotings, "转述没被数进报表头＝口径收窄之后悄悄漏了没人知道"
    assert module.CLAIM_HEAD_RE.match(QUOTE_ONLY_PAPER.split("\n")[2]) is None


def test_k8_two_papers_claiming_one_gap_reddens(live, tmp_path):
    by_id = control(live, tmp_path)
    truth = by_id["R51"]["gap_reasons"][0][1]["paper"]
    _, _, failures, _ = judge(live, tmp_path, extra_papers={SECOND_CLAIM_REL: SECOND_CLAIM_PAPER})
    picked = bites(failures, "R51", "C12")
    joined = "；".join(picked)
    assert "认领" in joined and truth in joined and SECOND_CLAIM_REL in joined, picked


def test_k9_a_claim_without_a_verdict_is_never_silent(live, tmp_path):
    by_id = control(live, tmp_path)
    assert by_id["R25"]["gap_reasons"] == [], "正控前提：R25 这格今天没有纸认领，理由句是写死的"
    _, _, failures, _ = judge(live, tmp_path, extra_papers={SILENT_CLAIM_REL: SILENT_CLAIM_PAPER})
    picked = bites(failures, "R25", "C18")
    assert "判语" in " ".join(picked) and SILENT_CLAIM_REL in " ".join(picked), picked


# ---------------------------------------------------------------------------
# 常驻闸：影子不落仓内，且真仓的读数在每把刀之后仍然自证
# ---------------------------------------------------------------------------

def test_the_knives_never_write_into_the_repo(live):
    tree = __import__("ast").parse(_text(RULER_REL))
    names = set()
    for node in tree.body:
        if isinstance(node, (__import__("ast").Import,)):
            names.update(alias.name.split(".")[0] for alias in node.names)
    assert "shutil" not in names and "os" not in names and "tempfile" not in names, \
        "账尺只读：源码顶层不许出现能写盘或摸用户目录的件"
    code, text = cli()
    assert code == 0 and "RESULT=PASS（0 条违规，在册 43 号逐条自证）" in text, \
        "逐把刀跑完，真仓这本账仍得原样自证：" + text[-400:]
    assert not [path for path in WRITES if REPO in path.resolve().parents], \
        "影子写回了仓内：" + "、".join(str(path) for path in WRITES if REPO in path.resolve().parents)