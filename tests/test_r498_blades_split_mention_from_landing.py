# -*- coding: utf-8 -*-
"""R498 · 反证刀：把「提及」与「并树」分家的每一枚牙单独摘掉，必须读红。

R491 那三把刀（tests/test_r491_counter_evidence_blades.py）管的是 A/B/C 三档塌没塌；
本件管 R498 新长的七枚牙，每把只摘一枚，红了哪一枚探针要能对答：

  B1 subject_shape 退回「首行里有这枚号就行」→ 正文「另立 R495」被当成 R495 的并树；
  B2 摘掉「实改清单非空」→ 空提交也算并树；
  B3 摘掉「实改仍在 git ls-files 在册」→ 并完又被撤掉的也算并树；
  B4 摘掉「实改与正文点名的写域有交集」→ 首行挂本号、货是别人的，也算并树；
  B5 摘掉「在不在本树 HEAD 祖先链上」→ 躺在别的 ref 上的落地冒充本树的货；
  B6 把「盘上有 · 库里没 · 也没被 ignore」整档降成 IGNORED → 为降噪放宽 #82 那一族；
  B7 message_names_token 退回子串命中 → R26 一口吃掉 R260–R269 那一族。

刀全落在内存里的源码影子副本（compile + exec），盘上那把尺子一个字都不改；
探针料是撒进内存的影子账 + pytest tmp_path 里的一棵影子 git 树，真仓工作区零写入。
对照 = 真件跑同一套探针，必须一枚都不红。
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "dispatch_preflight.py"
SOURCE = SCRIPT.read_text(encoding="utf-8")

#: 首行是 R484 的落地、正文才「另立 R495」——派工词今天那三枚就是这个形状。
LAND_R495 = "并树 R495（施工 Example/01a0e000，树 be-r495@abc1234）：新钉 tests/test_r495_owner.py 一枚。"
MENTION_R495 = ("并树 R484（施工 Example/01a0e000，树 be-r484@abc1234）：会话读腿对账；"
                "另立 R495 把这层承重变显式契约。")
FAMILY_R260 = "并树 R260（施工 Example/01a0e000，树 be-r260@abc1234）：收口 tests/test_r260_anchor.py。"

PRODUCT = "tests/test_r495_owner.py"
OTHER = "scripts/unrelated_tool.py"

#: 七把刀，锚点在真件里各唯一（有钉咬）；每把只咬下面指定的那一枚探针。
BLADES = {
    "B1_shape_is_presence_not_position": (
        '        return SHAPE_LANDING if match.group("tok") == token else None',
        "        return SHAPE_LANDING if token in subject else None",
    ),
    "B2_empty_diff_counts_as_landing": (
        "        if not files:\n            return EMPTY",
        "        if False:\n            return EMPTY",
    ),
    "B3_offledger_products_count_as_landing": (
        "        if not in_ledger:\n            return OFFLEDGER",
        "        if False:\n            return OFFLEDGER",
    ),
    "B4_write_domain_intersection_dropped": (
        "        return UNMATCHED, (",
        "        return LANDED, (",
    ),
    "B5_any_ref_counts_as_this_trees_landing": (
            '            elif not self.on_trunk(rec["sha"]):',
            "            elif False:",
    ),
    "B6_untracked_demoted_to_ignored": (
        '            return UNTRACKED, "盘上有，库里没（#82 那一族）"',
        '            return IGNORED, "盘上有库里没，一律不判红（把整档放宽了）"',
    ),
    "B7_number_boundary_collapsed": (
        "    return token in NUMBER_RE.findall(message)",
        "    return token in message",
    ),
}


def load(source, name):
    namespace = {"__file__": str(SCRIPT), "__name__": name}
    exec(compile(source, str(SCRIPT), "exec"), namespace)
    return namespace


def crippled(name):
    anchor, replacement = BLADES[name]
    assert SOURCE.count(anchor) == 1, "注入点变了或不止一处，这把刀会空转：" + name
    mutated = SOURCE.replace(anchor, replacement)
    assert mutated != SOURCE, "刀没切进去：" + name
    return load(mutated, "r498_blade_" + name)


# ---------------------------------------------------------------------------
# 探针料：影子账（内存）+ 影子树（tmp_path 里的一棵真 git 仓）
# ---------------------------------------------------------------------------

def rec(sha, subject, files=(), parents=("d" * 40,), message=""):
    return {"sha": sha, "parents": list(parents), "subject": subject,
            "message": subject + chr(10) + message, "files": list(files)}


def ledger(namespace, sandbox, records_by_token, tracked, on_trunk=True, paper=None):
    """把 git 层换成影子账；档位判据（形状/实改/在册/写域/祖先链/号界）全照跑。"""
    ruler = namespace["Ruler"](sandbox)
    ruler._tracked = set(tracked)
    ruler._head = "0" * 40
    ruler.records = lambda token: list(records_by_token.get(token, []))
    ruler.paper_index = lambda: dict(paper or {})
    ruler.on_trunk = lambda sha: on_trunk
    return ruler


def tier(ruler, namespace, token):
    status, landed, mentioned, paper, note = ruler.ticket_status(token)
    return status, note


def row_of(ruler, token):
    return ruler.check("核 {0} 一枚。".format(token))["numbers"][0]


def probe_a_prose_mention_is_not_a_landing(ctx):
    """正文「另立 R495」对 R484 是凭据、对 R495 只是提及：两枚读数必须相反。"""
    records = {"R495": [rec("a1" * 20, MENTION_R495, [OTHER])],
               "R484": [rec("a1" * 20, MENTION_R495, [OTHER])]}
    ruler = ledger(ctx["ns"], ctx["sandbox"], records, [OTHER])
    got = [tier(ruler, ctx["ns"], one)[0] for one in ("R484", "R495")]
    assert got == [ctx["HAS_COMMIT"], ctx["MENTION_ONLY"]], got


def probe_an_empty_landing_claim_names_the_empty_diff(ctx):
    records = {"R495": [rec("b2" * 20, LAND_R495, [])]}
    ruler = ledger(ctx["ns"], ctx["sandbox"], records, [PRODUCT])
    status, note = tier(ruler, ctx["ns"], "R495")
    assert status == ctx["MENTION_ONLY"], status
    assert "实改清单为空" in note, note


def probe_landing_whose_products_left_the_ledger_is_refused(ctx):
    records = {"R495": [rec("c3" * 20, LAND_R495, [PRODUCT])]}
    ruler = ledger(ctx["ns"], ctx["sandbox"], records, [])
    status, note = tier(ruler, ctx["ns"], "R495")
    assert status == ctx["MENTION_ONLY"], status
    assert "不在 git ls-files 在册" in note, note


def probe_write_domain_mismatch_is_a_named_conflict(ctx):
    records = {"R495": [rec("d4" * 20, LAND_R495, [OTHER])]}
    ruler = ledger(ctx["ns"], ctx["sandbox"], records, [OTHER])
    status, note = tier(ruler, ctx["ns"], "R495")
    assert status == ctx["LANDING_CONFLICT"], status + " · " + note
    assert "对不上" in note and "d4d4d4d" in note, note
    assert status not in ctx["RED_STATUSES"], "冲突既不许记已并树，也不许判死"


def probe_landing_off_this_trunk_is_not_landed(ctx):
    records = {"R495": [rec("e5" * 20, LAND_R495, [PRODUCT])]}
    ruler = ledger(ctx["ns"], ctx["sandbox"], records, [PRODUCT], on_trunk=False)
    status, note = tier(ruler, ctx["ns"], "R495")
    assert status == ctx["LANDING_OFF_TRUNK"], status + " · " + note
    assert "祖先链" in note and "e5e5e5e" in note, note
    assert row_of(ruler, "R495")["commits"] == 0, "脱链的货不许记进并树凭据枚数"


def probe_a_plain_untracked_product_is_still_dead(ctx):
    """B6 那一刀的靶子：盘上有 · 库里没 · 也没被 ignore，仍须 UNTRACKED 判红。"""
    ruler = ctx["ns"]["Ruler"](ctx["sandbox"])
    ruler._tracked = set()
    ruler._head = "0" * 40
    report = ruler.check("挂名件 scripts/hanging.py 一枚。")
    got = [row["status"] for row in report["names"]]
    assert got == [ctx["UNTRACKED"]], got
    assert report["red"] == 1 and report["exit_code"] == 1, "真假账被降噪放宽了"


def probe_an_ignored_product_stays_quiet(ctx):
    """见证：第四档在每一把刀下都该安静（本单加的档，不是本单摘的牙）。"""
    ruler = ctx["ns"]["Ruler"](ctx["sandbox"])
    ruler._tracked = set()
    ruler._head = "0" * 40
    report = ruler.check("编译产物 tests/__pycache__/deadbeef.cpython-311.pyc 一枚。")
    got = [row["status"] for row in report["names"]]
    assert got == [ctx["IGNORED"]], got
    assert report["red"] == 0, "正当引用被喊成假账"


def probe_a_sibling_number_is_not_attributed_to_its_parent(ctx):
    records = {"R26": [rec("f6" * 20, FAMILY_R260, [PRODUCT])]}
    ruler = ledger(ctx["ns"], ctx["sandbox"], records, [PRODUCT],
               paper={"R26": ["docs/handoff/note.md"]})
    status, note = tier(ruler, ctx["ns"], "R26")
    assert status == ctx["PAPER_ONLY"], status + " · " + note
    assert row_of(ruler, "R26")["mentions"] == 0, "R260 的提交被记到 R26 名下了"


PROBES = (
    probe_a_prose_mention_is_not_a_landing,
    probe_an_empty_landing_claim_names_the_empty_diff,
    probe_landing_whose_products_left_the_ledger_is_refused,
    probe_write_domain_mismatch_is_a_named_conflict,
    probe_landing_off_this_trunk_is_not_landed,
    probe_a_plain_untracked_product_is_still_dead,
    probe_an_ignored_product_stays_quiet,
    probe_a_sibling_number_is_not_attributed_to_its_parent,
)

#: 探针在 PROBES 里的名字，逐枚与刀对答；红几枚逐把报数。
EXPECTED = {
    "B1_shape_is_presence_not_position": {"probe_a_prose_mention_is_not_a_landing"},
    "B2_empty_diff_counts_as_landing": {"probe_an_empty_landing_claim_names_the_empty_diff"},
    "B3_offledger_products_count_as_landing": {"probe_landing_whose_products_left_the_ledger_is_refused"},
    "B4_write_domain_intersection_dropped": {"probe_write_domain_mismatch_is_a_named_conflict"},
    "B5_any_ref_counts_as_this_trees_landing": {"probe_landing_off_this_trunk_is_not_landed"},
    "B6_untracked_demoted_to_ignored": {"probe_a_plain_untracked_product_is_still_dead"},
    "B7_number_boundary_collapsed": {"probe_a_sibling_number_is_not_attributed_to_its_parent"},
}


def context(namespace, sandbox):
    return {
        "ns": namespace,
        "sandbox": sandbox,
        "HAS_COMMIT": namespace["HAS_COMMIT"],
        "LANDING_OFF_TRUNK": namespace["LANDING_OFF_TRUNK"],
        "LANDING_CONFLICT": namespace["LANDING_CONFLICT"],
        "MENTION_ONLY": namespace["MENTION_ONLY"],
        "PAPER_ONLY": namespace["PAPER_ONLY"],
        "UNTRACKED": namespace["UNTRACKED"],
        "IGNORED": namespace["IGNORED"],
        "RED_STATUSES": namespace["RED_STATUSES"],
    }


def run_probes(namespace, sandbox):
    ctx = context(namespace, sandbox)
    failed = set()
    for probe in PROBES:
        try:
            probe(ctx)
        except AssertionError:
            failed.add(probe.__name__)
    return failed


@pytest.fixture(scope="module")
def r498():
    spec = importlib.util.spec_from_file_location("dispatch_preflight_r498_blades", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def sandbox(r498, tmp_path_factory):
    """一棵影子 git 仓：三行 ignore + 一枚被 ignore 的产物 + 一枚裸的未跟踪件。"""
    root = tmp_path_factory.mktemp("r498_blade_sandbox")
    for args in (("init", "-q"),):
        run = subprocess.run(("git", "-C", str(root)) + args, capture_output=True)
        assert run.returncode == 0, run.stderr.decode("utf-8", "replace")
    (root / ".gitignore").write_bytes(b"__pycache__/" + bytes((10,)))
    for rel, payload in (("tests/__pycache__/deadbeef.cpython-311.pyc", b"x"),
                         ("scripts/hanging.py", b"x"),
                         ("scripts/unrelated_tool.py", b"x"),
                         ("tests/test_r495_owner.py", b"x")):
        path = root / Path(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    return root


def test_blade_anchors_are_unique_in_the_shipped_ruler():
    for name, (anchor, _) in BLADES.items():
        assert SOURCE.count(anchor) == 1, name + " 的锚点在真件里不是唯一一处"


def test_the_shipped_ruler_passes_every_probe(r498, sandbox):
    assert run_probes(vars(r498), sandbox) == set(), "对照就该零红：尺子自己先跑通"


@pytest.mark.parametrize("blade", sorted(EXPECTED))
def test_each_blade_goes_red_exactly_where_it_is_cut(blade, r498, sandbox):
    failed = run_probes(crippled(blade), sandbox)
    assert failed == EXPECTED[blade], "{0} 应只咬红 {1}，实读 {2}".format(
        blade, sorted(EXPECTED[blade]), sorted(failed))


def test_no_blade_is_a_no_op():
    """每一把刀都真改了字节：改完的源码与原文不等，且档位常量都还在。"""
    for name in sorted(EXPECTED):
        namespace = crippled(name)
        for word in ("HAS_COMMIT", "MENTION_ONLY", "PAPER_ONLY", "LANDING_OFF_TRUNK",
                     "LANDING_CONFLICT", "UNTRACKED", "IGNORED", "NEVER_FILED"):
            assert isinstance(namespace[word], str), name + " 摘刀后档位名没了 " + word


def test_the_blade_table_covers_every_new_tooth(r498):
    """七把刀对答七枚牙：B1/B4/B5/B7 管 C 档，B2/B3 管落地凭据的两枚实改牙，B6 管第四档放宽。"""
    assert len(EXPECTED) == 7
    assert set(EXPECTED) == set(BLADES)
    bitten = {one for names in EXPECTED.values() for one in names}
    assert len(bitten) == 7, "两把刀咬同一枚探针＝其中一把是空转"
    assert bitten == {one.__name__ for one in PROBES} - {"probe_an_ignored_product_stays_quiet"}
