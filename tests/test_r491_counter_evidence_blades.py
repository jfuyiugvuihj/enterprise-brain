# -*- coding: utf-8 -*-
"""R491 · 判据⑤：三把反证刀，各自摘掉一档判定，必须读红。

刀全落在**内存里的源码影子副本**上（`compile` + `exec`），盘上那把尺子一个字都不改。
每把刀先把锚点数一遍：锚点不唯一或找不到 ⇒ 当场判定这把刀空转（本席今天最恨的一种假绿）。

  K1 摘掉 (a) 的 MISSING 判定 → 「盘上无库里无」读成 OK → #90 那族假账全放行；
  K2 摘掉 (b) 的越界判定     → 999999 行也读成 IN_RANGE → 行号档变摆设；
  K3 把 (c) 六档塌成「被提及就算 HAS_COMMIT」→ MENTION_ONLY 那一格消失 → #88 与 R498 两族一起蒙混过关。
     （R498 之后 K3 的锚点从三档版 ticket_status 迁到六档版；落地形状那几把刀另立
      tests/test_r498_blades_split_mention_from_landing.py，本件只管这三把。）

每把刀跑同一套探针（探针 = 判据①②里那些真实读数），红几枚逐把报数；
对照 = 真件跑同一套，必须一枚都不红。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "dispatch_preflight.py"
SOURCE = SCRIPT.read_text(encoding="utf-8")

#: NEVER_FILED 探针池（与 tests/test_r491_ticket_ledger_keeps_three_tiers.py 同料，两边各自选各的）。
PROBE_POOL = ("R902", "R903", "R980", "R981", "R990", "R991")

FAKE = "tests/test_r387_teeth.py"
FAKE2 = "tests/test_r400_derived.py"
REAL = "tests/test_r387_label_ruler_teeth.py"
CHAT = "app/api/v1/chat.py"
GHOST = "%TEMP%\\evalrun\\r428-driver.md"

#: 三刀各自的一句源码改动，锚点必须在真件里唯一。
BLADES = {
    "K1_drop_missing_verdict": (
        '        return MISSING, "盘上无 · 库里无"',
        '        return OK, "摘掉了 MISSING 判定"',
    ),
    "K2_drop_range_verdict": (
        'if rng[1] > counts["text"]:',
        "if False:",
    ),
    "K3_collapse_three_tiers": (
        "        if landed:\n            shapes =",
        "        landed = landed or mentioned\n        if landed:\n            shapes =",
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
    return load(mutated, "r491_blade_" + name)


# ---------------------------------------------------------------------------
# 探针：每枚都是一条真实读数，红了就说明那档判定失效
# ---------------------------------------------------------------------------

def probe_missing_names_read_red(ctx):
    report = ctx["ruler"].check("新钉 {0} 与 {1} 两枚。".format(FAKE, FAKE2))
    statuses = sorted(row["status"] for row in report["names"])
    assert statuses == [ctx["MISSING"], ctx["MISSING"]], statuses
    assert report["red"] == 2


def probe_real_names_read_clean(ctx):
    report = ctx["ruler"].check("真名 {0} 一枚。".format(REAL))
    assert [row for row in report["names"] if row["status"] == ctx["MISSING"]] == []
    assert report["red"] == 0


def probe_line_bounds_read_both_ways(ctx):
    report = ctx["ruler"].check("锚点 {0}:999999 与 {0}:1005。".format(CHAT))
    got = {row["raw"]: row["status"] for row in report["lines"]}
    assert got[CHAT + ":999999"] == ctx["OUT_OF_RANGE"], "越界行号读成了：" + str(got)
    assert got[CHAT + ":1005"] == ctx["IN_RANGE"]
    assert report["red"] == 1


def probe_three_tiers_do_not_collapse(ctx):
    report = ctx["ruler"].check("已并树 R478，正文提过 R475，账面号 R476，从没立过 {0}。".format(
        ctx["probe"]))
    statuses = [row["status"] for row in report["numbers"]]
    assert statuses == [ctx["HAS_COMMIT"], ctx["MENTION_ONLY"], ctx["PAPER_ONLY"],
                        ctx["NEVER_FILED"]], statuses


def probe_unfiled_number_reads_red(ctx):
    report = ctx["ruler"].check("给 {0} 派一枚活。".format(ctx["probe"]))
    assert report["numbers"][0]["status"] == ctx["NEVER_FILED"]
    assert report["red"] == 1 and report["exit_code"] == 1


def clean_probe(ruler):
    """从没立过的探针号现选：提交记录与 docs/** 两路都读不到才算干净。"""
    index = ruler.paper_index()
    for one in PROBE_POOL:
        if ruler.records(one) == [] and one not in index:
            return one
    raise AssertionError("探针池 {0} 全被抄脏，换一批不落账的号".format(PROBE_POOL))


def probe_external_path_is_reported_but_not_fatal(ctx):
    report = ctx["ruler"].check("驱动件在 {0}。".format(GHOST))
    assert report["names"][0]["status"] == ctx["NOT_IN_REPO"]
    assert report["red"] == 0


PROBES = (
    probe_missing_names_read_red,
    probe_real_names_read_clean,
    probe_line_bounds_read_both_ways,
    probe_three_tiers_do_not_collapse,
    probe_unfiled_number_reads_red,
    probe_external_path_is_reported_but_not_fatal,
)


def context(namespace):
    """一个命名空间配一枚 Ruler：同一把刀下的探针共用读数，不重复跑 git。"""
    ruler = namespace["Ruler"](REPO_ROOT)
    return {
        "ruler": ruler,
        "probe": clean_probe(ruler),
        "MISSING": namespace["MISSING"],
        "OUT_OF_RANGE": namespace["OUT_OF_RANGE"],
        "IN_RANGE": namespace["IN_RANGE"],
        "HAS_COMMIT": namespace["HAS_COMMIT"],
        "MENTION_ONLY": namespace["MENTION_ONLY"],
        "PAPER_ONLY": namespace["PAPER_ONLY"],
        "NEVER_FILED": namespace["NEVER_FILED"],
        "NOT_IN_REPO": namespace["NOT_IN_REPO"],
    }


def run_probes(namespace):
    ctx = context(namespace)
    failed = set()
    for probe in PROBES:
        try:
            probe(ctx)
        except AssertionError:
            failed.add(probe.__name__)
    return failed


@pytest.fixture(scope="module")
def r491():
    spec = importlib.util.spec_from_file_location("dispatch_preflight_r491_blades", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_blade_anchors_are_unique_in_the_shipped_ruler():
    for name, (anchor, _) in BLADES.items():
        assert SOURCE.count(anchor) == 1, name + " 的锚点在真件里不是唯一一处"


def test_the_shipped_ruler_passes_every_probe(r491):
    assert run_probes(vars(r491)) == set(), "对照就该零红：尺子自己先跑通"


@pytest.mark.parametrize("blade,expected_red", [
    ("K1_drop_missing_verdict", {"probe_missing_names_read_red"}),
    ("K2_drop_range_verdict", {"probe_line_bounds_read_both_ways"}),
    ("K3_collapse_three_tiers", {"probe_three_tiers_do_not_collapse"}),
])
def test_each_blade_goes_red_exactly_where_it_is_cut(blade, expected_red):
    failed = run_probes(crippled(blade))
    assert failed == expected_red, "{0} 应只咬红 {1}，实读 {2}".format(blade, expected_red, failed)
    assert len(failed) >= 1, "这把刀没让任何探针红 = 空转"


def test_a_crippled_ruler_still_produces_a_full_ledger():
    """摘掉判定不等于尺子崩了：三档之外仍要出账，才说明红是判出来的、不是炸出来的。"""
    namespace = crippled("K1_drop_missing_verdict")
    report = namespace["Ruler"](REPO_ROOT).check("喂 {0} 与 R478 R901。".format(FAKE))
    assert len(report["numbers"]) == 2 and report["names"]
    assert "RESULT=" in namespace["render"](report)
