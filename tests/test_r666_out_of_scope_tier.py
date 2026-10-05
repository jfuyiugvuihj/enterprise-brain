# -*- coding: utf-8 -*-
"""R666 · OUT 档的常驻牙：移出不是判达，出处断头必须红并点名那一号。

治的病：判据「V1 计划书代码单清零」按读法乙挂着 16 号未清，其中 5 格不是没做完，而是判据本身
不成立——R29 实测判负（一分没省）、R43 要换推理引擎、R48 本机地板 11.0 s 物理不可达、R52 属交付
阶段、R50 已由丙案裁定。继续挂 PARTIAL 就是逼后人永远欠一笔还不掉的账。

加一档 OUT 把它们移出，但移出必须留下可核的凭据，三样缺一枚就当场红：
  ① 仓内真实存在的出处文档＋该文档里的判语关键词（C19）；
  ② 为什么不可达的证据数字或裁定句，「暂时不做」这种形容词过不去（C20）；
  ③ 逐字点名被移出的那一格，不许整号一笔抹掉（C21）。
OUT 不进读法甲／读法乙的未清分子，也绝不进「完成」那一列；报表里必须单列一段并逐格写「不算完成」。

刀口（每把都先跑正控，摘刀／加豁免／skip 一律不许）：
  N1 出处文档不在仓内      → C19 红并点名 R29
  N2 判语关键词漂移        → C19 红并点名 R48
  N3 锚点漂移（读不到）    → C19 红并点名 R52
  N4 证据只剩形容词        → C20 红并点名 R29
  N5 出处里锚点命中两枚    → C19 红并点名 R29
  N6 出处文档从盘上拿走    → C19 红并点名 R29 R43 R48 R52（R50 的出处另在 docs/deployment）
  N7 CLI 给没出处的号标 OUT → 非零退出并点名 R25
  N8 判定词拼错（OUTT／"OUT "／out）→ C1 照咬，七档不是「随便什么词都行」
  N9 出处指向代码文件（拿脚本自注当裁定）→ C19 红并点名 R43「不是仓内文书」
  N10 出处文书的落盘提交不在祖先链上 → C19 红并点名 R29「还没进主干」
  N11 出处只是本地便签（读不到落盘提交）→ C19 红并点名 5 号「本地便签不在册」
  N12 零产物的号判 OUT（没干过却想挪出半径）→ C22 红并点名 R29

跑法（必须用仓内 venv 的解释器，anaconda 那枚在 conftest 当场缺 chromadb）：
    .\\.venv\\Scripts\\python.exe -m pytest -p no:randomly -q tests/test_r666_out_of_scope_tier.py
"""
from __future__ import annotations

import copy
import importlib.util
import itertools
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RULER_REL = "scripts/audit_plan_ticket_ledger.py"
RULER = REPO / RULER_REL
ROADMAP = "docs/version-roadmap-and-requirements-2026-10-05.md"
OFFPEAK = "docs/deployment/offpeak-rebuild-execution-shape-2026-10-05.md"
PLAN = "docs/handoff/2026-09-17-perf-architecture-plan.md"   # 业主 09-24 门的归属裁定原文（总控 10-05 改判：OUT 出处不许指向总控自己写的版本文档＝双真源）
MOVED_SOURCES = (ROADMAP, OFFPEAK, PLAN)
MOVED = ("R29", "R43", "R48", "R50", "R52")
STILL_OPEN = ("R25", "R26", "R28", "R31", "R35", "R38", "R44", "R47", "R51")
DISCLAIMER = "不算完成"
CODE_RE = re.compile(r"(?:🔴 )?(C\d+)")
NAMES = itertools.count()

CUT_FAKE_FILE = ('out=OOS(PLAN, "BCDE 有些是不是属于后面版本的你可以放后面来", "移出 V1 门槛",',
                 'out=OOS("docs/testing/r666-paper-that-does-not-exist.md", '
                 '"BCDE 有些是不是属于后面版本的你可以放后面来", "移出 V1 门槛（这句被搬走）",')
CUT_DRIFTED_KEYWORD = ('out=OOS(PLAN, "R48 的判据① 随 B 一并移出 V1 门槛", "移出 V1 门槛",',
                       'out=OOS(PLAN, "R48 的判据① 随 B 一并移出 V1 门槛", "这句在出处里不存在",')
CUT_DRIFTED_ANCHOR = ('out=OOS(PLAN, "**B 行与 E 行整行移出 V1 门槛**", "移出 V1 门槛",',
                      'out=OOS(PLAN, "**B 行与 E 行整行移出 V1 门槛（这半句是编的）", "移出 V1 门槛",')
CUT_ADJECTIVE_ONLY = ('              "真机 A/B 实测 30.6 s → ≤22 s 判负：改动落地后一分没省，并树的只有「不迁腿」这个负结果＋契约钉；"\n'
                      '              "这一格在 V1 硬件口径上不会变绿，判语「整行移出 V1 门槛」（业主 09-24 原话「BCDE 有些是不是属于后面版本的你可以放后面来」）")),',
                      '              "暂时不做")),')
CUT_SOURCE_IS_CODE = ('out=OOS(PLAN, "门的归属裁定（第四十四班", "移出 V1 门槛",',
                      'out=OOS("scripts/audit_plan_ticket_ledger.py", '
                      '"| R43 | ② E3 档实测 `cached_tokens > 0` | 已裁定移出", "已裁定移出",')


def _text(rel):
    return (REPO / rel).read_bytes().decode("utf-8").replace("\r\n", "\n")


def _apply(text, edits):
    out = text
    for old, new in edits:
        if out.count(old) != 1:
            raise AssertionError("刀口没落在唯一一处：%r（命中 %d 枚）" % (old[:60], out.count(old)))
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
    module.REPO = REPO  # 影子的仓根指回真仓：祖先链与仓内文档都是事实，不许伪造
    return module


def _load(name):
    spec = importlib.util.spec_from_file_location(name, str(RULER))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ruler():
    return _load("r666_ruler_live")


@pytest.fixture(scope="module")
def reading(ruler):
    git = ruler.Git(ruler.REPO)
    quoter = ruler.Quoter(ruler.REPO)
    deriver = ruler.Deriver(git, quoter, [row["id"] for row in ruler.LEDGER])
    rows = ruler.build_rows(git, quoter, deriver)
    return {"ruler": ruler, "git": git, "deriver": deriver, "rows": rows,
            "by_id": {row["id"]: row for row in rows}, "failures": ruler.self_checks(rows)}


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    sandbox = tmp_path_factory.mktemp("r666-shadow")
    return {"module": _exec("r666_live", _text(RULER_REL), sandbox),
            "git": None, "lines": {}, "sandbox": sandbox}


def overlay_class(module):
    class OverlayQuoter(module.Quoter):
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
        missing = frozenset()

        def exists(self, rel):
            return False if rel in self.missing else module.Deriver.exists(self, rel)

    return DenyDeriver


class GitMask:
    """只遮 git 名下几枚读数，其余照旧问真仓——「出处得先并树」那条腿就靠它喂假。"""

    def __init__(self, real, **masks):
        self._real = real
        self._masks = masks

    def __getattr__(self, name):
        mask = self._masks.get(name)
        return getattr(self._real, name) if mask is None else mask


def judge(live, tmp, ruler_edits=(), overrides=(), missing=(), git_masks=None):
    if live.get("git") is None:
        live["git"] = live["module"].Git(REPO)
    used = GitMask(live["git"], **git_masks) if git_masks else live["git"]
    if ruler_edits:
        module = _exec("r666_shadow_%d" % next(NAMES), _apply(_text(RULER_REL), ruler_edits), tmp)
    else:
        module = live["module"]
    quoter = overlay_class(module)(REPO, dict(overrides), live["lines"])
    deriver = denier_class(module)
    deriver.missing = frozenset(missing)
    built = deriver(used, quoter, [row["id"] for row in module.LEDGER])
    rows = module.build_rows(used, quoter, built)
    return module, rows, module.self_checks(rows)


def control(live, tmp):
    _, rows, failures = judge(live, tmp)
    assert failures == [], "正控必须先绿，否则后面的红没有意义：" + "；".join(failures)
    return {row["id"]: row for row in rows}


def codes(failures):
    return [CODE_RE.match(note).group(1) for note in failures if CODE_RE.match(note)]


def bites(failures, victim, code):
    picked = [note for note in failures if victim in note]
    assert picked, "没有一枚牙咬到 %s：%s" % (victim, "；".join(failures) or "全绿")
    assert code in codes(picked), "%s 的红不是 %s 咬的：%s" % (victim, code, "；".join(picked))
    return picked


def cli(*extra):
    proc = subprocess.run([sys.executable, str(RULER)] + list(extra), capture_output=True, cwd=str(REPO))
    return proc.returncode, proc.stdout.decode("utf-8", "replace")

# ---------------------------------------------------------------------------
# 账面读数：5 进 9 留（R27③／R37③ 两格已由 R686 结算成 LANDED），OUT 在册但不是派生档，老三档口径一字未动
# ---------------------------------------------------------------------------

def test_out_is_the_seventh_tier_and_the_old_tiers_stay_in_order(ruler):
    assert ruler.VERDICTS == ("LANDED", "PARTIAL", "CLOSED", "ZERO", "FOREIGN", "NOTBUILT", "OUT")
    assert ruler.VERDICTS[:3] == ("LANDED", "PARTIAL", "CLOSED"), "老三档的位序与口径不许动"
    assert "OUT" in ruler.CLEARED_TIERS, "OUT 不许留在「未清」分子里"
    assert "OUT" not in ruler.DERIVABLE_TIERS, "OUT 不许派生：移出是人执笔的裁定"
    assert ruler.OUT_DISCLAIMER == DISCLAIMER


def test_exactly_the_five_named_cells_moved_and_nine_stay_partial(reading):
    assert reading["failures"] == [], "在册台账自检必须全过：" + "；".join(reading["failures"])
    tiers = {row["id"]: row["verdict"] for row in reading["rows"]}
    moved = tuple(sorted(tid for tid, verdict in tiers.items() if verdict == "OUT"))
    assert moved == tuple(sorted(MOVED)), "改判 OUT 的必须正好是工单点名的 5 号：" + repr(moved)
    partials = tuple(sorted(tid for tid, verdict in tiers.items() if verdict == "PARTIAL"))
    assert partials == tuple(sorted(STILL_OPEN)), "其余 9 号必须仍为 PARTIAL：" + repr(partials)
    assert len(reading["rows"]) == 43, "在册号数不许被本单改动"


def test_the_nine_partials_still_name_their_debt_verbatim(reading):
    for tid in STILL_OPEN:
        row = reading["by_id"][tid]
        assert row["verdict"] == "PARTIAL", tid + " 不该被本单碰"
        quotes = [gap["quote"] for gap in row["gaps_resolved"]]
        assert quotes and all(quote.strip() for quote in quotes), tid + " 的欠账必须逐字点名"


def test_moved_cells_still_carry_their_products_and_name_their_cell(reading):
    """移出 ≠ 没干过：产物提交仍得在树上，被移出的那一格仍得逐字点名，只是不再按欠账计。"""
    for tid in MOVED:
        row = reading["by_id"][tid]
        assert row["artifacts_resolved"], tid + " 移出不许抹掉它在树上的产物"
        assert all(art["ancestor"] for art in row["artifacts_resolved"]), tid + " 的产物提交不在祖先链上"
        assert row["gaps_resolved"], tid + " 必须逐字点名被移出的那一格（C21）"


def test_every_out_source_is_a_real_repo_doc_with_the_verdict_on_that_line(reading):
    for tid in MOVED:
        source = reading["by_id"][tid]["out_resolved"]
        assert source and not source.get("problem"), tid + " 的出处落不实地：" + repr(source)
        assert source["problems"] == [], tid + " 的证据空心：" + repr(source["problems"])
        assert source["file"] in MOVED_SOURCES, tid + " 的出处得是在册的仓内裁定文书（计划书／专门裁定纸），不许是总控自己写的版本文档"
        assert (REPO / source["file"]).exists(), tid + " 的出处不在仓内"
        line = _text(source["file"]).split("\n")[source["line"] - 1]
        assert source["keyword"] in line, tid + " 的判语关键词没落在那一行上"


def test_out_cells_leave_both_reading_numerators(reading):
    counts = dict((verdict, 0) for verdict in reading["ruler"].VERDICTS)
    for row in reading["rows"]:
        counts[row["verdict"]] += 1
    assert counts["OUT"] == 5 and counts["PARTIAL"] == 9 and counts["ZERO"] == 0
    landed = {row["id"] for row in reading["rows"] if row["verdict"] == "LANDED"}
    assert counts["LANDED"] == 26, "LANDED 只许是 R666 那笔的 24 号＋R686 结算的 2 号"
    assert {"R27", "R37"} <= landed, "R686 结算的两格必须真在 LANDED 里"
    assert not set(MOVED) & landed, "移出不是判达：OUT 那 5 号一枚都不许混进 LANDED"


# ---------------------------------------------------------------------------
# 输出契约：单列成一段、带「不算完成」、老三档口径原样、CLEARED 与报表同进退
# ---------------------------------------------------------------------------

def test_the_cli_singles_out_the_moved_cells_with_the_disclaimer(ruler):
    code, text = cli()
    assert code == 0, text[-800:]
    assert ("## 9. 移出的 5 格（OUT·" + DISCLAIMER + "）") in text, "OUT 进了 CLEARED_TIERS 却不单列＝假账"
    assert "读法乙（判据全达才算清）：未清 9 号（PARTIAL 9 ＋ ZERO 0）" in text
    assert "读法甲（产物在树即算清）：未清 0 号" in text
    for tid in MOVED:
        assert ("- %s ｜OUT ｜移出格：G-" % tid) in text, tid + " 没被单列"
    assert text.count("这一格" + DISCLAIMER) == 5, "逐格都得写「不算完成」，不许只在段头说一句"
    assert "≠ 判达" in text
    assert "不计入欠账的档：R39 R143 R144" in text, "派生那一腿的口径不许被本单动过"
    assert "OUT" in ruler.CLEARED_TIERS and DISCLAIMER in text


def test_the_old_three_tiers_wording_survives_the_upgrade():
    code, text = cli()
    assert code == 0, text[-800:]
    assert "LANDED＝产物在树且无点名欠账；PARTIAL＝产物在树但点名欠判据；" in text
    assert "ZERO＝HEAD 祖先链上全史零产物" in text
    assert "七档口径：" in text and "判定词只许七档" in text
    assert "六档" not in text, "六档的说法还留在账面上＝这档压根没升上去"


# ---------------------------------------------------------------------------
# N8：C1 改口成七档之后仍然咬得住判定词
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bogus", ["PARTIA", "PARDIAL", "LANDED ", "OUTT", "out", "OUTG", "DONE"])
def test_c1_still_bites_any_verdict_word_outside_the_seven(reading, bogus):
    row = copy.deepcopy(reading["by_id"]["R25"])
    row["verdict"] = bogus
    picked = [note for note in reading["ruler"].self_checks([row]) if note.startswith("C1 ")]
    assert picked, "判定词拼错还放过＝C1 被摘成了摆设：" + repr(bogus)
    assert "R25" in picked[0] and bogus in picked[0] and "七档" in picked[0], picked


def test_c1_does_not_bite_the_seventh_tier_itself(reading):
    row = copy.deepcopy(reading["by_id"]["R43"])
    row["verdict"] = "OUT"
    assert not [note for note in reading["ruler"].self_checks([row]) if note.startswith("C1 ")]


def test_c19_bites_an_out_row_authored_without_a_source(reading):
    row = copy.deepcopy(reading["by_id"]["R25"])
    row["verdict"] = "OUT"
    row["out_resolved"] = None
    picked = [note for note in reading["ruler"].self_checks([row]) if note.startswith("C19")]
    assert picked and "R25" in picked[0], picked


# ---------------------------------------------------------------------------
# N1～N6：出处断头／判语漂移／锚点漂移／形容词／锚点重复／文档从盘上拿走
# N7：CLI 给没出处的号标 OUT
# ---------------------------------------------------------------------------

def test_n1_a_fake_source_document_reddens_and_names_the_ticket(live, tmp_path):
    control(live, tmp_path)
    _, _, failures = judge(live, tmp_path, ruler_edits=(CUT_FAKE_FILE,))
    picked = bites(failures, "R29", "C19")
    assert "不在仓内" in " ".join(picked), picked


def test_n2_a_keyword_that_is_not_on_the_cited_line_reddens(live, tmp_path):
    control(live, tmp_path)
    _, _, failures = judge(live, tmp_path, ruler_edits=(CUT_DRIFTED_KEYWORD,))
    picked = bites(failures, "R48", "C19")
    assert "判语关键词" in " ".join(picked), picked


def test_n3_a_drifted_anchor_reddens(live, tmp_path):
    control(live, tmp_path)
    _, _, failures = judge(live, tmp_path, ruler_edits=(CUT_DRIFTED_ANCHOR,))
    picked = bites(failures, "R52", "C19")
    assert "锚点" in " ".join(picked), picked


def test_n4_an_adjective_only_excuse_reddens(live, tmp_path):
    control(live, tmp_path)
    _, _, failures = judge(live, tmp_path, ruler_edits=(CUT_ADJECTIVE_ONLY,))
    picked = bites(failures, "R29", "C20")
    joined = " ".join(picked)
    assert "暂时不做" in joined and "形容词" in joined, picked


def test_n5_a_duplicated_anchor_line_reddens(live, tmp_path):
    by_id = control(live, tmp_path)
    source = by_id["R29"]["out_resolved"]
    line = _text(source["file"]).split("\n")[source["line"] - 1]
    doubled = _text(source["file"]) + "\n" + line + "\n"
    _, _, failures = judge(live, tmp_path, overrides={source["file"]: doubled})
    picked = bites(failures, "R29", "C19")
    assert "命中 2 处" in " ".join(picked), picked


def test_n6_hiding_the_source_doc_from_disk_breaks_the_tier(live, tmp_path):
    control(live, tmp_path)
    _, _, failures = judge(live, tmp_path, missing=(PLAN,))
    for tid in ("R29", "R43", "R48", "R52"):
        picked = bites(failures, tid, "C19")
        assert "不在仓内" in " ".join(picked), picked
    assert not [note for note in failures if "R50" in note], "R50 的出处在 docs/deployment，不该跟着倒"


def test_n7_the_cli_refuses_an_out_verdict_without_a_source():
    code, text = cli()
    assert code == 0 and "RESULT=PASS" in text, "正控：不注入故障时这本账必须自证"
    code, text = cli("--fault", "R25=OUT@ad85821")
    assert code == 1, "给没出处的号标 OUT 还 PASS＝这把刀是摆设"
    picked = [line for line in text.splitlines() if line.startswith("🔴") and "R25" in line]
    assert any("C19" in line for line in picked), picked
    assert any("C21" in line for line in picked), picked
    assert "RESULT=FAIL" in text


def test_n9_a_code_file_cannot_play_a_ruling_source(live, tmp_path):
    control(live, tmp_path)
    _, _, failures = judge(live, tmp_path, ruler_edits=(CUT_SOURCE_IS_CODE,))
    picked = bites(failures, "R43", "C19")
    joined = " ".join(picked)
    assert "不是仓内文书" in joined, picked
    assert "README.md" in joined, "红里得把「只认哪些路径」说清楚：" + joined


def test_n10_a_ruling_doc_that_is_not_on_the_trunk_breaks_the_tier(live, tmp_path):
    control(live, tmp_path)
    _, _, failures = judge(live, tmp_path, git_masks={"is_ancestor": lambda sha: False})
    picked = bites(failures, "R29", "C19")
    assert "不在 HEAD 祖先链上" in " ".join(picked), picked


def test_n11_a_local_note_without_a_landing_commit_breaks_the_tier(live, tmp_path):
    control(live, tmp_path)
    _, _, failures = judge(live, tmp_path, git_masks={"first_add": lambda rel: None})
    for tid in MOVED:
        picked = bites(failures, tid, "C19")
        assert "本地便签不在册" in " ".join(picked), tid + "：" + "；".join(picked)


def test_n12_an_out_row_with_zero_products_is_bitten_by_c22(reading):
    stripped = copy.deepcopy(reading["by_id"]["R29"])
    stripped["artifacts_resolved"] = []
    picked = [note for note in reading["ruler"].self_checks([stripped]) if note.startswith("C22")]
    assert picked and "R29" in picked[0], "零产物还想挪出半径却没被咬＝C22 是摆设：" + repr(picked)
    assert "产物" in picked[0], picked
    untouched = [note for note in reading["ruler"].self_checks([copy.deepcopy(reading["by_id"]["R29"])])
                 if note.startswith("C22")]
    assert not untouched, "正控：R29 名下有在树产物时 C22 不许咬——" + "；".join(untouched)


def test_the_knives_never_write_into_the_repo():
    assert not [path for path in WRITES if REPO in path.resolve().parents], \
        "影子写回了仓内：" + "、".join(str(path) for path in WRITES if REPO in path.resolve().parents)
    code, text = cli()
    assert code == 0 and "RESULT=PASS（0 条违规，在册 43 号逐条自证）" in text, text[-400:]