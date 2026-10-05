# -*- coding: utf-8 -*-
"""R686 · 把 R27③／R37③ 两格已量到的「达」结算进账尺，并留一枚反证牙。

治的病：账尺读法乙挂着 11 号未清，其中两格其实早已量到达——
R27③ 端到端 −≥35 s：基线 160.552 s → 问答类 p95 50.1 s（降 110.4 s ≥ 35 s），量具
`scripts/r595_latency_readout.py`，run22 与 run23 两窗互证，读数代次 9556513；
R37③ 队列失败有终态与原因码：量具 R585（并树代次 1f0f0f2）把 {reason, retryable} 排在写状态键
之前进账，在册牙三件亲跑 99 passed／0 failed／37.39 s。账不结算，业主看到的就是「还差 11」这句假话。

本件只判四件事，缺一即红（全程离线：零容器、零连库、零模型、产品码零字节改动）：
  T1 两格真在 LANDED，且自检仍全过（在册 43 号逐条自证，一枚不减）；
  T2 理由句必须带量具名＋读数＋代次 sha，「等 A 门／未重量」这类形容词不许留在账上；
  T3 计数从 LANDED=24／PARTIAL=11／未清 11 变成 LANDED=26／PARTIAL=9／未清 9；
  T4 摘牙即退回：C15（取证纸已判达不许仍挂欠账）与 C8（PARTIAL 必须逐字点名欠账）原样在尺上，
     并且真咬——把 R27 改回 PARTIAL 却不点名欠账，账尺必须非零退出并点名那一号。

「达」的依据在仓内可查：`docs/testing/v1-cell-closeout-2026-10-05.md` 的 R27③／R37③ 两节
（本件只读它，不许反过来改它）。R37 那条点名例外（`deploy/queue_worker.py::_process_reserved`
收尾传 str(e)）另立 R675：既不算进本格欠账，也不许拿它挡判达。

跑法（必须用仓内 venv 的解释器，anaconda 那枚在 conftest 当场缺 chromadb）：
    .\\.venv\\Scripts\\python.exe -m pytest -p no:randomly -q tests/test_r686_two_measured_cells_land.py
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RULER = REPO / "scripts" / "audit_plan_ticket_ledger.py"
CLOSEOUT_REL = "docs/testing/v1-cell-closeout-2026-10-05.md"
COUNTS_LINE = ("在册 43 号：LANDED=26 · PARTIAL=9 · CLOSED=1 · ZERO=0 · FOREIGN=1 · "
               "NOTBUILT=1 · OUT=5")
STALE_COUNTS_LINE = ("在册 43 号：LANDED=24 · PARTIAL=11 · CLOSED=1 · ZERO=0 · FOREIGN=1 · "
                     "NOTBUILT=1 · OUT=5")
OPEN_LINE = "读法乙（判据全达才算清）：未清 9 号（PARTIAL 9 ＋ ZERO 0）"
STALE_OPEN_LINE = "读法乙（判据全达才算清）：未清 11 号（PARTIAL 11 ＋ ZERO 0）"
SETTLED = ("R27", "R37")
VAGUE = ("等 A 门", "未重量", "待重量", "再量看看")
SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b")
MARKS = {
    "R27": ("scripts/r595_latency_readout.py", "160.552", "50.1", "110.4", "35 s", "9556513",
            "run22", "run23", "端到端"),
    "R37": ("R585", "1f0f0f2", "fail_or_retry", "99 passed", "0 failed", "37.39", "R675",
            "原因码"),
}

def _cli(*extra):
    proc = subprocess.run([sys.executable, str(RULER)] + list(extra), capture_output=True,
                          cwd=str(REPO))
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


@pytest.fixture(scope="module")
def clean_cli():
    """正控：不带故障注入的现取读数——正控不绿，任何一把刀都不准算咬中。"""
    return _cli()


@pytest.fixture(scope="module")
def ruler():
    spec = importlib.util.spec_from_file_location("r686_ruler", str(RULER))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["r686_ruler"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def reading(ruler):
    """一笔现取读数：git 门面复用，判定与理由句全部走派生层。"""
    git = ruler.Git(ruler.REPO)
    quoter = ruler.Quoter(ruler.REPO)
    deriver = ruler.Deriver(git, quoter, [row["id"] for row in ruler.LEDGER])
    rows = ruler.build_rows(git, quoter, deriver)
    return {"ruler": ruler, "git": git, "rows": rows,
            "by_id": {row["id"]: row for row in rows}, "failures": ruler.self_checks(rows)}


# ---------------------------------------------------------------------------
# T1 两格真结算：档位、欠账清空、自检一枚不减
# ---------------------------------------------------------------------------

def test_both_cells_land_while_the_book_still_self_proves(reading):
    assert reading["failures"] == [], "在册台账自检必须全过：" + "；".join(reading["failures"])
    landed = {row["id"] for row in reading["rows"] if row["verdict"] == "LANDED"}
    assert set(SETTLED) <= landed, "两格没进 LANDED：" + repr(
        {tid: reading["by_id"][tid]["verdict"] for tid in SETTLED})
    for tid in SETTLED:
        row = reading["by_id"][tid]
        assert row["gaps"] == [], tid + " 判 LANDED 却还挂着点名欠账的出处"
        assert row["gaps_resolved"] == [], tid + " 的欠账名单没清空"
        products = [art for art in row["artifacts_resolved"] if art["product"]]
        assert products, tid + " 判 LANDED 必须有在树产物（C6 同源，不许空手翻绿）"
        for art in products:
            assert reading["git"].is_ancestor(art["full"]), "%s 的产物 `%s` 不在 HEAD 祖先链上" % (
                tid, art["sha"])


def test_the_other_in_scope_numbers_are_untouched(reading):
    """其余 41 号一字不许动：五格 OUT、另九格 PARTIAL 与派生那一腿都得原样。"""
    tiers = {row["id"]: row["verdict"] for row in reading["rows"]}
    assert sorted(tid for tid, tier in tiers.items() if tier == "OUT") == [
        "R29", "R43", "R48", "R50", "R52"], tiers
    assert sorted(tid for tid, tier in tiers.items() if tier == "PARTIAL") == [
        "R25", "R26", "R28", "R31", "R35", "R38", "R44", "R47", "R51"], tiers
    assert tiers["R39"] == "NOTBUILT" and tiers["R143"] == "CLOSED" and tiers["R144"] == "FOREIGN"
    assert len(reading["rows"]) == 43, "在册号数不许被本单改动"

# ---------------------------------------------------------------------------
# T2 理由句：量具名＋读数＋代次 sha，形容词不许顶替
# ---------------------------------------------------------------------------

def test_each_landed_reason_carries_instrument_reading_and_generation(reading):
    for tid in SETTLED:
        why = reading["by_id"][tid]["why"]
        for piece in MARKS[tid]:
            assert piece in why, "%s 的理由句缺「%s」：理由句必须带量具名＋读数＋代次" % (tid, piece)
        assert SHA_RE.search(why), tid + " 的理由句没有代次 sha（不许用形容词结算）"
        for word in VAGUE:
            assert word not in why, "%s 的理由句还挂着形容词「%s」＝没结算成量" % (tid, word)


# ---------------------------------------------------------------------------
# T3 计数：改前 LANDED=24／PARTIAL=11／未清 11，改后 26／9／9
# ---------------------------------------------------------------------------

def test_the_cli_counts_move_as_the_ticket_demands(clean_cli):
    code, text = clean_cli
    assert code == 0, "账尺整跑必须 RESULT=PASS（0 条违规）：" + text[-500:]
    assert "RESULT=PASS（0 条违规，在册 43 号逐条自证）" in text
    assert COUNTS_LINE in text, "七档计数没改到 26／9：" + text[text.index("## 7. 计数"):][:400]
    assert OPEN_LINE in text, "读法乙未清没从 11 变 9"
    assert STALE_COUNTS_LINE not in text and STALE_OPEN_LINE not in text, "旧计数原文还留在报表上"
    for tid in SETTLED:
        assert "- %s（PARTIAL）差：" % tid not in text, tid + " 仍挂在欠账名单里"


# ---------------------------------------------------------------------------
# T4 反证牙：改回 PARTIAL 却不点名欠账 ⇒ 非零退出并点名那一号；两把常驻牙不许摘
# ---------------------------------------------------------------------------

def test_de_settling_a_row_without_naming_the_debt_reddens_and_names_it(clean_cli):
    code, text = _cli("--fault", "R27=PARTIAL@ce0b041")
    assert code != 0, "反证没咬住：把 R27 改回 PARTIAL 且不点名欠账，账尺必须非零退出"
    assert "R27" in text, "账尺非零退出却没点名那一号"
    assert "C8 R27" in text, "咬住这一号的必须是 C8（PARTIAL 必须逐字点名欠账）：" + text[-500:]


def test_the_reusable_counter_evidence_teeth_still_have_their_edges():
    """摘牙＝退回：C15 与 C8 两把常驻牙必须原样长在尺子上（正证跑在 T3／T4 那两枚用例里）。"""
    source = RULER.read_bytes().decode("utf-8")
    assert '"C15 %s：取证纸已把 G-%s 判达' in source, "C15「取证纸已判达不许仍挂欠账」被摘掉了"
    assert '"C8 %s：判 PARTIAL 却没点名欠哪条判据' in source, "C8「PARTIAL 必须逐字点名欠账」被摘掉了"
    for tid, shas in (("R27", ("ce0b041", "6a4f02b")), ("R37", ("45b9720", "0c08209"))):
        for sha in shas:
            assert sha in source, "%s 的在册产物提交 `%s` 被从台账里抹掉了" % (tid, sha)


def test_the_closeout_paper_is_untouched_and_carries_the_same_readings():
    """依据必须在仓内可查：结案纸只读，且读数与代次必须对得上尺子。"""
    paper = (REPO / CLOSEOUT_REL).read_bytes().decode("utf-8")
    for piece in ("160.552", "50.1", "9556513", "1f0f0f2", "99 passed", "37.39", "R675"):
        assert piece in paper, "结案纸读不到这枚读数／代次：" + piece
    assert paper.count("达**（本班可结案") + paper.count("达**（过期账订正") >= 2, \
        "结案纸里那两行必须逐枚点名「达」，尺子不许凭空翻绿"