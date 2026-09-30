# -*- coding: utf-8 -*-
"""R547 派生钉（二）：纸面上每一枚坐标与每一行末行都必须是**现读派生**的，手抄即红。

这枚钉盯的是本单最容易漂的三样东西：

  ① 业主四条裁定的行号——由 `owner_rulings()` 按锚现读派生，纸面那四枚 `:NNN` 必须逐枚等值；
     锚若漂到不唯一，派生当场停（"改错一格"就是这一形）。
  ② 纸面上那些"实测末行"——必须与量具**此刻**打印的行逐字节相同（live／shapes／reread 三道各若干行），
     抄错一个字、把一个 rc 写成另一个 rc，都算手改读数。
  ③ 三态与口径——生产臂四件在纸面与计划书里都记「未验」；凡提到格③ 那一格的行必须自己带着
     否定词（不／没／假／未验／欠），一枚"格③ 已翻绿"都进不了这本账；
     「只证行为、不证客户隔离」那句业主原话逐字在位；252 与 72 两本账各归各源、不许互相顶。

  ④ 计划书侧那三枚 `:NNN`（(d) 记账口径／§9.3 那行改判据／§13.四 第 ② 格）——同样按锚现读，
     派生入口 `plan_citations()`；计划书自己漂一格，本纸那两枚硬坐标当场脱钩。
     09-30 实测：本单在 §9.3 那一节插了一行，`(d)` 那枚就从 `:499` 推到 `:500`、第 ② 格从 `:528` 推到 `:543`。

🔴 全程只读盘上字节与进程内派生，零写口、不连库、不起服务、不打模型。
   摘守卫的门与同族一致：`R547_GAUGE_TOOL` 指到改过的量具副本（配 `R547_REPO_ROOT` 仍指真树）。
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, "读不到量具：" + str(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


TOOL_PATH = Path(os.getenv("R547_GAUGE_TOOL") or (REPO / "scripts" / "r547_scope_verdict_gauge.py"))
GAUGE = _load(TOOL_PATH, "r547_scope_verdict_gauge_for_pins")
LIB, DRIVER = GAUGE.load_instruments()

PAPER_REL = "docs/testing/r547-scope-verdict-2026-09-30.md"
OWNER = GAUGE.OWNER_LABEL = "docs/handoff/2026-09-17-human-gates.md"

#: 凡提到格③ 的行，必须自带这些否定形状之一，否则就是在宣布绿。
NEGATORS = ("不", "没", "假", "未验", "欠", "量不到")


def paper_lines():
    return GAUGE.read_rows(PAPER_REL)


def paper_text():
    return "\n".join(paper_lines())


def gauge_lines(argv, monkeypatch=None):
    """在进程内跑一道，把 stdout 逐行取回来——纸面引用的末行必须与它逐字节相同。"""
    import io
    from contextlib import redirect_stdout

    if monkeypatch is not None:
        for name in (GAUGE.PRODUCTION_DSN_ENV, GAUGE.SANDBOX_DSN_ENV):
            monkeypatch.delenv(name, raising=False)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        rc = GAUGE.main(argv)
    return rc, [line for line in buffer.getvalue().splitlines() if line.startswith("[R547]")]


# ------------------------------------------------------------------ ① 裁定坐标

def test_the_four_ruling_coordinates_on_paper_are_derived():
    derived = GAUGE.owner_rulings()
    cited = re.findall(r"`" + re.escape(OWNER) + r":(\d+)`", paper_text())
    for key, anchor, what in GAUGE.RULING_ANCHORS:
        rows = [line for line in GAUGE.read_rows(OWNER) if anchor in line]
        assert len(rows) == 1, (key, what, len(rows))
        assert str(derived[key]["line"]) in cited, (key, derived[key]["line"], cited)


def test_the_paper_quotes_the_owner_verbatim_where_it_matters():
    text = paper_text()
    assert "只证行为、不证客户隔离" in text
    assert "拿它翻绿格③ 是假话" in text, "A3 那句原话必须整句在位，不许转述成 softer 的说法"
    assert "不在真库做，改沙盒" in text
    assert "交付阶段按客户真实密级做" in text
    assert "密级档位 = 3" in text


def test_a_single_wrong_coordinate_reddens_this_book():
    """把派生行号改一格就应当脱钩——本件用现读值反证这一点（不是豁免，是形状证明）。"""
    derived = GAUGE.owner_rulings()
    cited = {int(value) for value in
             re.findall(r"`" + re.escape(OWNER) + r":(\d+)`", paper_text())}
    truth = {item["line"] for item in derived.values()}
    assert cited == truth, (sorted(cited), sorted(truth))
    for number in truth:
        assert number + 1 not in cited or number + 1 in truth


# ------------------------------------------------------------------ ② 末行逐字节

def test_the_production_live_last_lines_on_paper_are_byte_identical(capsys, monkeypatch):
    rc, lines = gauge_lines(["--mode", "live", "--arm", "both"], monkeypatch)
    assert rc == LIB.EXIT_PRECONDITION, lines
    text = paper_text()
    for line in lines:
        assert line in text, line
    assert any("点名=" + GAUGE.ENV_DSN_UNSET in line for line in lines), lines


def test_the_shapes_last_lines_on_paper_are_byte_identical():
    rc, lines = gauge_lines(["--mode", "shapes"])
    assert rc == LIB.EXIT_OK, lines
    text = paper_text()
    for line in lines:
        assert line in text, line
        assert GAUGE.FIXTURE_MARK in line or "夹具" in line or "[R547][末行]" in line, line
    assert sum(1 for line in lines if "rc=0" in line) == 1, "三形各自都不许交 rc=0"


def test_the_reread_last_line_on_paper_is_byte_identical_and_keeps_the_252():
    rc, lines = gauge_lines(["--mode", "reread"])
    assert rc == LIB.EXIT_OK, lines
    line = next(item for item in lines if item.startswith("[R547][末行] mode=reread"))
    assert line in paper_text(), line
    payload = GAUGE.run_reread(GAUGE.READOUT_REL, LIB, DRIVER)
    assert payload["arms"][LIB.ARM_SANDBOX]["no_predicate_outside"] == payload["ruling_synth_count"] == 252
    assert payload["arms"][LIB.ARM_SANDBOX]["synth_rows"] == 72
    assert payload["arms"][LIB.ARM_PRODUCTION]["status"] == LIB.STATUS_NOT_MEASURED


# ------------------------------------------------------------------ ③ 三态与口径

def test_every_cell3_line_in_the_paper_negates_green():
    offenders = [line for line in paper_lines()
                 if "格③" in line and not any(mark in line for mark in NEGATORS)]
    assert offenders == [], offenders


def test_the_plan_still_records_abc_as_unverified():
    section = GAUGE.read_rows(GAUGE.PLAN_REL)
    start = next(no for no, line in enumerate(section, 1) if line.startswith("## 13."))
    body = "\n".join(section[start - 1:])
    assert "(a)(b)(c) 继续记「未验」" in body, "§13 改口必须保留那三件的未验记录"
    assert "任一不满足即记" in body and "，不得记通过" in body
    assert "已裁" in body and "不在真库做，改沙盒" in body, "欠什么要按已裁口径改写"
    assert "格③ 通过" not in body and "格③ 已翻绿" not in body


def test_the_ninth_section_gate_row_still_says_unverified():
    rows = GAUGE.read_rows(GAUGE.PLAN_REL)
    hits = [line for line in rows if "09-30 改口（R547" in line]
    assert len(hits) == 2, len(hits)          # §9.3 第 3 格与 §13 四第③格各一枚
    for line in hits:
        assert "未验" in line, line[:60]
        assert "不证客户隔离" in line or "不关门" in line or "不前进一格" in line, line[:60]


def test_the_paper_names_why_the_production_arm_is_unmeasurable_not_empty():
    text = paper_text()
    assert "postgresql-x64-16" in text, "野 PG 那一行现取证据要在位"
    assert "未发布宿主端口" in text, "容器端口那一行现取证据要在位"
    assert "量不到不等于" in text, "必须把量不到不等于干净这句说出口"
    assert "库里没有数据" in text, "要明写这两行都不许读成库里没有数据"


def test_the_sandbox_arm_cannot_be_used_to_close_the_gate_anywhere_in_the_paper():
    for line in paper_lines():
        if "沙盒" in line and ("PASS" in line or "有牙" in line or "252" in line):
            assert any(mark in line for mark in ("不关门", "不证客户隔离", "只证行为", "不许", "两本账", "未验", "不构成")), line[:80]


def test_the_criterion_table_rows_a_b_c_stay_marked_not_verified():
    """§13.一 那本表的 (a)(b)(c) 三行今天仍不许挂 ✅：只有 (d) 那行带着"空集意义上成立"的历史标记。"""
    rows = GAUGE.read_rows(GAUGE.PLAN_REL)
    start = next(no for no, line in enumerate(rows, 1) if line.startswith("## 13."))
    body = rows[start - 1:]
    for key in ("(a)", "(b)", "(c)"):
        hits = [line for line in body if line.startswith("| " + key + " |")]
        assert len(hits) == 1, (key, len(hits))
        assert chr(0x2705) not in hits[0], (key, hits[0][:80])
        assert ("❌" in hits[0]) or ("未验" in hits[0]), (key, hits[0][:80])


def test_no_line_in_the_plan_declares_the_gate_closeable():
    """想在 §13 里写一句"因此通过／可以关门"，必须同一行自带否定形状，否则就是翻绿。"""
    rows = GAUGE.read_rows(GAUGE.PLAN_REL)
    start = next(no for no, line in enumerate(rows, 1) if line.startswith("## 13."))
    green_words = ("因此通过", "可以关门", "已翻绿", "格③ 通过", "格③已通过")
    offenders = []
    for no, line in enumerate(rows[start - 1:], start):
        if any(word in line for word in green_words) and not any(mark in line for mark in NEGATORS):
            offenders.append((no, line[:80]))
    assert offenders == [], offenders


def test_the_floors_and_their_line_are_derived_not_written_into_the_paper():
    floors = GAUGE.plan_floors()
    line = GAUGE.read_rows(GAUGE.PLAN_REL)[floors["line"] - 1]
    assert "不同部门 ≥2" in line and "不同密级 ≥2" in line
    assert str(floors["line"]) in paper_text(), "纸面那枚 floors 落点行号要与现读同值"


# ------------------------------------------------------------------ ④ 计划书侧坐标

def test_the_plan_side_coordinates_on_paper_are_derived():
    """纸面那三枚计划书侧 `:NNN` 必须与按锚现读同值，且锚就落在那一行上。"""
    cites = GAUGE.plan_citations()
    text = paper_text()
    rows = GAUGE.read_rows(GAUGE.PLAN_REL)
    for key, item in cites.items():
        assert "`:" + str(item["line"]) + "`" in text, (key, item["line"], item["what"])
        hit = rows[item["line"] - 1]
        assert item["anchor"] in hit, (key, item["line"], hit[:70])


def test_the_plan_side_coordinate_set_on_the_paper_is_all_derived():
    """手抄一枚旧坐标即红：纸面每一枚 `:NNN` 裸坐标都必须来自派生集（业主侧∪计划书侧），
    而计划书侧那三枚必须一枚不缺——计划书自己漂一格，本纸这枚钉就点出漂掉的那枚。"""
    plan = {str(item["line"]) for item in GAUGE.plan_citations().values()}
    gates = {str(item["line"]) for item in GAUGE.owner_rulings().values()}
    cited = set(re.findall(r"`:(\d{2,4})`", paper_text()))
    assert cited - plan - gates == set(), sorted(cited - plan - gates)
    assert plan <= cited, (sorted(cited), sorted(plan))
    # 门槛那一枚（plan_floors）刻意不在这张集合里：它只出现在量具自己打印的读数行内，
    # 由 test_the_floors_and_their_line_are_derived_not_written_into_the_paper 单独盯。


def test_a_drifted_plan_coordinate_reddens_this_book():
    """形状证明：每一枚派生坐标的上下邻行都不握着那把锚——漂一格就点不到原句。"""
    cites = GAUGE.plan_citations()
    rows = GAUGE.read_rows(GAUGE.PLAN_REL)
    for key, item in cites.items():
        no = item["line"]
        for neighbour in (no - 1, no + 1):
            if 1 <= neighbour <= len(rows):
                assert item["anchor"] not in rows[neighbour - 1], (key, neighbour, no)
