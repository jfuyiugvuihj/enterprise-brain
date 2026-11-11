# -*- coding: utf-8 -*-
"""R638 反证刀 —— 证明那枚棘轮钉是活牙：改了必红、没改必绿，全部在 tmp_path 影子根里跑。

姿势（在册规矩，AGENTS.md 与事故 #96／#107 同族）：
  · 影子根＝``tmp_path/shadow/docs``，正文从主树真 .md 复制来——枚数与主树同源，改的只是影子；
  · 基线＝同一把尺对影子根**改动前**现取派生，不抄第二份数字；
  · 刀＝只在影子根里追加／删掉／改写几行字节，主树盘上一个字都不动（末了有牙复核这一条）；
  · 正控＝动手之前先跑一遍同一判据，读数必须是零枚。红来自那一枚改动，不来自影子机制本身。

🔴 本件不许把「此刻工作树脏不脏」当判据：全程只看尺的读数与影子根的字节。
🔴 零 import 产品码：坐标解析走尺内部的 AST 腿；行号与符号区间一律现取派生，不抄字面量。

返工判据 R638-R 对号：刀十＝任意 .md 上方插一行必须不红；刀十一＝整行搬到相邻行身份不变；
刀十二＝行照被 splice 改写而坐标没多没少 → 只落 ``shifted`` 点名不红；刀二＝删掉一行含坐标的正文
必须报 ``shrank`` 并点名那一枚，且一枚都不许进 ``grew``。刀九末复核主树 digest 动手前后逐枚相等。
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "r638_doc_pointer_ruler.py"
REAL_DOCS = REPO / "docs"

#: 一手造坐标的把手：源文里绝不出现 ``.py:数字`` 形状，否则本件自己就成了在册坐标。
PY = ".py"
SEP = ":"


def _ruler():
    name = "r638_doc_pointer_ruler"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ruler = _ruler()


def coordinate(file_part: str, start: int, end: int | None = None) -> str:
    """现场拼一枚坐标：文件串 ＋ 冒号 ＋ 行号（可带区间）。"""
    tail = str(start) if end is None else "%d-%d" % (start, end)
    return "%s%s%s%s" % (file_part, PY, SEP, tail)


def shadow_copy(tmp_path: Path, docs: list[str]) -> Path:
    """把主树那几枚 .md 逐字节复制进影子根（``tmp_path/shadow/docs``），返回影子的 docs 根。"""
    root = tmp_path / "shadow" / "docs"
    for rel in docs:
        source = REAL_DOCS / rel.removeprefix("docs/")
        target = root / rel.removeprefix("docs/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    return root


def write_shadow(shadow_docs: Path, rel: str, text: str) -> Path:
    path = shadow_docs / rel.removeprefix("docs/")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def analyze(shadow_docs: Path) -> dict:
    """尺对影子根跑一遍；被引 .py 仍走真树名册（只读），所以判定与主树同判。"""
    return ruler.analyze(shadow_docs, REPO)


def baseline_of(shadow_docs: Path) -> dict:
    return ruler.build_baseline(analyze(shadow_docs))


def doc_text(path: Path) -> str:
    text, _meta = ruler.decode_text(path.read_bytes())
    return text


# ==================== 刀一：往纸上添一枚坐标——棘轮必须红 ====================


def test_appending_a_coordinate_turns_the_ratchet_red(tmp_path) -> None:
    """正控先零枚；影子根里追加一行「chat 点 py 冒号 99」那一形之后，棘轮必须点名这一枚。"""
    shadow = shadow_copy(tmp_path, ["docs/api/contract-v1.md"])
    stored = baseline_of(shadow)
    before = ruler.ratchet_diff(stored, baseline_of(shadow))
    assert before["grew"] == [] and before["offenders"] == [], "正控：没动手就该零枚"

    target = shadow / "api" / "contract-v1.md"
    target.write_bytes(target.read_bytes() + ("\n见 %s 那一格。\n" % coordinate("chat", 99)).encode("utf-8"))
    diff = ruler.ratchet_diff(stored, baseline_of(shadow))
    assert diff["grew"], "追加了一枚坐标而棘轮不咬：这枚钉是死牙"
    added = [key for entry in diff["grew"] for key in entry["added"]]
    assert len(added) == 1 and added[0].endswith(coordinate("chat", 99)), added
    assert diff["forged"] == []


# ==================== 刀二：删掉一行含坐标的正文——必须报 shrank 并点名 ====================


def test_deleting_a_line_that_bears_a_coordinate_reports_shrank(tmp_path) -> None:
    """R638-R② 那一形：整行删掉。grew 必须空、shrank 必须逐枚点名那一枚，方向不许装反。"""
    rel = "docs/api/contract-v1.md"
    shadow = shadow_copy(tmp_path, [rel])
    stored = baseline_of(shadow)
    doc = shadow / "api" / "contract-v1.md"
    found, _meta = ruler.scan_doc(rel, doc)
    assert found, "正控：影子根里一枚坐标都没扫到，本刀量不到"
    target = found[0]
    victims = [occ.identity for occ in found if occ.doc_line == target.doc_line]

    text, _meta = ruler.decode_text(doc.read_bytes())
    lines = ruler.doc_lines(text)
    del lines[target.doc_line - 1]
    doc.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    diff = ruler.ratchet_diff(stored, baseline_of(shadow))
    assert diff["grew"] == [], "枚数下降被报成 grew：方向又装反了"
    assert diff["forged"] == [], diff["forged"]
    assert diff["offenders"] == [], "少了一枚反而判红：棘轮方向装反了"
    assert [row["doc"] for row in diff["shrank"]] == [rel], diff["shrank"]
    cell = diff["shrank"][0]
    assert cell["before"] - cell["after"] == len(victims), cell
    assert len(cell["removed"]) == len(victims), cell
    for key in victims:
        cited = key.split("::", 2)[2]
        assert any(cited in name for name in cell["removed"]), (cell, key)


# ==================== 刀三：基线里的数字被手抄——必须红 ====================


def test_a_hand_literalized_count_in_the_baseline_dies(tmp_path) -> None:
    """正控：尺自己落的基线自证零违规。刀：把一枚 count 改成手抄字面量，当场红。"""
    shadow = shadow_copy(tmp_path, ["docs/handoff/2026-09-25-plan-ticket-closure.md"])
    baseline = baseline_of(shadow)
    assert ruler.validate_baseline(baseline) == []

    doctored = json.loads(json.dumps(baseline))
    victim = sorted(doctored["files"])[0]
    doctored["files"][victim]["count"] = doctored["files"][victim]["count"] + 1
    offenders = ruler.validate_baseline(doctored)
    assert offenders and victim in " ".join(offenders), offenders
    assert ruler.ratchet_diff(doctored, baseline)["forged"], "手抄的数没被对出来"


def test_a_shortened_identity_list_dies_even_with_a_matching_count(tmp_path) -> None:
    """更阴的一形：清单里删一枚、count 跟着改成自洽——正文没动，尺的现读立刻把它对出来。"""
    shadow = shadow_copy(tmp_path, ["docs/handoff/2026-09-25-plan-ticket-closure.md"])
    baseline = baseline_of(shadow)
    doctored = json.loads(json.dumps(baseline))
    victim = sorted(doctored["files"])[0]
    dropped = sorted(doctored["files"][victim]["pointers"])[0]
    doctored["files"][victim]["pointers"] = [
        key for key in doctored["files"][victim]["pointers"] if key != dropped
    ]
    doctored["files"][victim]["count"] = len(doctored["files"][victim]["pointers"])
    doctored["total_pointers"] = sum(row["count"] for row in doctored["files"].values())
    assert ruler.validate_baseline(doctored) == [], "自洽的手抄件过得了自证这一格（预期如此）"

    diff = ruler.ratchet_diff(doctored, baseline)
    assert diff["forged"], "digest 未动而清单与现读不等：这一格必须咬"
    assert any(row["doc"] == victim for row in diff["forged"]), diff["forged"]


# ==================== 刀四：形状被改窄——区间与裸基名必须还在射程里 ====================


def test_the_shape_bites_ranges_bare_names_and_rejects_lookalikes(tmp_path) -> None:
    """三枚真形一枚假形：区间／裸基名／全路径都数得到，光有文件名不算坐标。"""
    shadow = shadow_copy(tmp_path, ["docs/api/contract-v1.md"])
    lines = [
        coordinate("app/api/v1/chat", 120, 135),
        coordinate("chat", 99),
        coordinate("scripts/r631_stage_sum_delta", 12),
        "app/api/v1/chat" + PY + " 这个文件",
    ]
    path = write_shadow(shadow, "docs/knife-shape.md", "\n".join(lines) + "\n")
    found, meta = ruler.scan_doc("docs/knife-shape.md", path)
    assert meta["pointers"] == 3, [occ.raw for occ in found]
    assert meta["ranges"] == 1
    assert {occ.file_part for occ in found} == {
        "app/api/v1/chat.py", "chat.py", "scripts/r631_stage_sum_delta.py"
    }


# ==================== 刀五：符号声称——真错的红、真对的不红 ====================


@pytest.fixture(scope="module")
def a_live_symbol() -> dict:
    """现取一枚真符号与其区间：本件的行号与路径一律现取派生，不抄任何字面量。"""
    index = ruler.PyIndex(REPO)
    rel = "app/common/stage_timing.py"
    table = index.table(rel)
    assert table.parsed, "被引文件 AST 解析不了：本刀的前提变了"
    for entry in table.entries:
        if entry["kind"] in ("def", "class") and "." not in entry["chain"]:
            return {"rel": rel, "stem": rel[:-len(PY)],
                    "symbol": entry["chain"], "lo": entry["lo"], "hi": entry["hi"]}
    raise AssertionError("取不到一枚可锚的模块级具名符号：本刀的前提变了")


def coordinate_target_line(info: dict, offset: int) -> int:
    return info["lo"] + offset


def test_a_wrong_symbol_claim_dies_and_a_right_one_passes(tmp_path, a_live_symbol) -> None:
    """同一枚文件同一枚符号，一枚指着它真在的行、一枚指着它不在的行：只有后者该红。"""
    info = a_live_symbol
    shadow = shadow_copy(tmp_path, ["docs/api/contract-v1.md"])
    write_shadow(shadow, "docs/knife-claim.md", "\n".join([
        "符号 %s 此刻在 %s。" % ("`%s`" % info["symbol"], coordinate(info["stem"], info["lo"])),
        "符号 %s 此刻在 %s。" % ("`%s`" % info["symbol"], coordinate(info["stem"], info["hi"] + 40)),
    ]) + "\n")
    rows = analyze(shadow)["rows"]
    judged = {row["cited"]: row for row in rows if row["doc"] == "docs/knife-claim.md"}
    right = judged[coordinate(info["stem"], info["lo"])]
    wrong = judged[coordinate(info["stem"], info["hi"] + 40)]
    assert right["verdict"] == "claim_matches" and right["hard"] is False, right
    assert wrong["verdict"] == "symbol_mismatch" and wrong["hard"] is True, wrong
    assert wrong["owner_now"], "判红却不交现读所属：这枚清单没法抽查"


# ==================== 刀六：文件在不在——缺文件红、依赖不红 ====================


def a_dependency_coordinate() -> str:
    """现取一枚落在依赖里的路径串（``.venv`` 的 site-packages）：不是本仓的行号账。"""
    if not ruler.PyIndex(REPO)._site:
        pytest.skip("现跑的解释器里没有可点名的 site-packages：这一格量不到，不假红")
    for base in ruler.PyIndex(REPO)._site:
        for path in sorted(base.rglob("*.py")):
            rel = path.relative_to(base).as_posix()
            if "/" in rel and len(rel) < 60:
                return coordinate(rel[:-3], 10)
    raise AssertionError("依赖里没有可点名的 .py：本刀的前提变了")


def test_a_missing_file_dies_and_a_dependency_citation_does_not(tmp_path) -> None:
    """两形并列：仓里查无此文件＝硬判红；点名的是依赖里的文件＝如实单列，不算漂移。"""
    shadow = shadow_copy(tmp_path, ["docs/api/contract-v1.md"])
    ghost = coordinate("app/api/v1/r638_knife_ghost_module", 7)
    dep = a_dependency_coordinate()
    write_shadow(shadow, "docs/knife-file.md", "见 %s 与 %s。\n" % (ghost, dep))
    rows = {row["cited"]: row for row in analyze(shadow)["rows"] if row["doc"] == "docs/knife-file.md"}
    assert rows[ghost]["verdict"] == "file_missing" and rows[ghost]["hard"] is True
    assert rows[dep]["verdict"] == "external_dependency" and rows[dep]["hard"] is False
    assert rows[dep]["resolution"] == "external"


# ==================== 刀七：空行与注释——一指的红、注释不裁 ====================


@pytest.fixture(scope="module")
def blank_and_comment_lines() -> dict:
    """现取一枚仓内 .py 里的一行空行与一行注释：本刀不抄任何行号。"""
    index = ruler.PyIndex(REPO)
    for rel in index.files:
        lines = index.lines(rel)
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                blank = number
                comment = next((i for i, row in enumerate(lines, start=1)
                                if row.strip().startswith("#") and len(row.strip()) > 12), None)
                if comment:
                    return {"rel": rel, "stem": rel[:-len(PY)],
                            "blank": blank, "comment": comment}
                break
    raise AssertionError("仓里取不到一枚空行＋一枚注释：本刀的前提变了")


def test_an_empty_target_line_dies_and_a_comment_line_is_not_judged(tmp_path, blank_and_comment_lines) -> None:
    """指着空气＝红（那一枚一个字都没有，没有裁量余地）；指着注释＝不裁（可能在指注释写的那件事）。"""
    info = blank_and_comment_lines
    shadow = shadow_copy(tmp_path, ["docs/api/contract-v1.md"])
    blank = coordinate(info["stem"], info["blank"])
    comment = coordinate(info["stem"], info["comment"])
    write_shadow(shadow, "docs/knife-blank.md", "%s ；%s 。\n" % (blank, comment))
    rows = {row["cited"]: row for row in analyze(shadow)["rows"] if row["doc"] == "docs/knife-blank.md"}
    assert rows[blank]["verdict"] == "empty_target_line" and rows[blank]["hard"] is True
    assert rows[comment]["verdict"] == "comment_target_line" and rows[comment]["hard"] is False

# ==================== 刀八：批量切法——账本／契约／取证行一枚都不许落进批 ====================


def test_ledgers_contract_and_forensic_lines_never_enter_a_batch(tmp_path) -> None:
    """四类并列进影子根，只许第四类落批：账本与契约整枚排除，取证行逐枚排除。"""
    shadow = shadow_copy(tmp_path, ["docs/api/contract-v1.md"])
    rows = {
        "docs/handoff/knife-ledger.md": "跟进单抄了 %s。\n" % coordinate("app/api/v1/chat", 10),
        "docs/api/contract-v1.md": "契约正文抄了 %s。\n" % coordinate("app/agents/nodes", 20),
        "docs/testing/knife-forensic.md": "事故 #7 取证原文：%s 当时读着是对的。\n"
        % coordinate("app/rag/retriever", 30),
        "docs/perf/knife-plain.md": "这里抄了一枚 %s。\n" % coordinate("app/tools/export", 40),
    }
    for rel, text in rows.items():
        write_shadow(shadow, rel, text)
    plan = ruler.batch_plan(analyze(shadow))

    batched = {doc for batch in plan["batches"] for doc in batch["docs"]}
    assert batched == {"docs/perf/knife-plain.md"}, batched
    excluded_docs = set(plan["excluded"]["ledger_append_only"]["docs"]) | set(
        plan["excluded"]["contract_append_only"]["docs"]
    )
    assert "docs/handoff/knife-ledger.md" in excluded_docs, plan["excluded"]
    assert "docs/api/contract-v1.md" in excluded_docs, plan["excluded"]
    assert plan["excluded"]["ledger_append_only"]["reason"], "排除必须带理由，不能只给名单"
    assert plan["excluded"]["contract_append_only"]["reason"]

    forensic = [row["where"].split(":")[0] for row in plan["forensic_lines"]]
    assert forensic == ["docs/testing/knife-forensic.md"], plan["forensic_lines"]
    assert plan["totals"]["convertible_pool"] == 1, plan["totals"]
    assert plan["totals"]["excluded"] == 2, plan["totals"]
    assert plan["totals"]["convertible_pool"] + plan["totals"]["excluded"] \
        + plan["totals"]["forensic_lines"] == 4, plan["totals"]


# ==================== 刀九：刀只落在影子上，主树一个字都不动 ====================


def main_tree_digests(docs: list[str]) -> dict:
    """主树那几枚 .md 的正文 digest：动手前后各取一次，逐枚相等才算没漏。"""
    readings = {}
    for rel in docs:
        path = REAL_DOCS / rel.removeprefix("docs/")
        text, _meta = ruler.decode_text(path.read_bytes())
        readings[rel] = ruler.content_digest(text)
    return readings


def test_the_knives_never_touched_the_main_tree(tmp_path) -> None:
    """同一枚刀在影子里必须咬红，而主树逐枚 digest 恒定——本单的写域就是零 .md 正文。"""
    watched = ["docs/api/contract-v1.md", "docs/handoff/2026-09-15-orchestration-board.md"]
    before = main_tree_digests(watched)

    shadow = shadow_copy(tmp_path, watched)
    stored = baseline_of(shadow)
    assert ruler.ratchet_diff(stored, baseline_of(shadow))["offenders"] == [], "正控：没动手就该零枚"

    victim = shadow / "handoff" / "2026-09-15-orchestration-board.md"
    victim.write_bytes(victim.read_bytes()
                       + ("\n见 " + coordinate("chat", 99) + "。\n").encode("utf-8"))
    diff = ruler.ratchet_diff(stored, baseline_of(shadow))
    assert [row["doc"] for row in diff["grew"]] == [
        "docs/handoff/2026-09-15-orchestration-board.md"], diff

    assert main_tree_digests(watched) == before, "影子刀把主树文档改了：写域被越过了"
    assert not (REPO / "docs" / "handoff" / "knife-ledger.md").exists()


# ==================== 刀十：账面上方插一行——棘轮必须不红（R638-R① 硬牙） ====================


def test_splicing_a_line_above_the_coordinates_stays_green(tmp_path) -> None:
    """在最上方插一行不带坐标的正文：逐枚身份不变、六格全空；插完再追加一枚，牙还得咬。"""
    rel = "docs/api/contract-v1.md"
    shadow = shadow_copy(tmp_path, [rel])
    stored = baseline_of(shadow)
    assert ruler.ratchet_diff(stored, baseline_of(shadow))["offenders"] == [], "正控：没动手就该零枚"

    doc = shadow / "api" / "contract-v1.md"
    doc.write_bytes(("总控记一笔：这一格只是账面追加，不带任何坐标。\n" + doc_text(doc)).encode("utf-8"))
    live = baseline_of(shadow)
    diff = ruler.ratchet_diff(stored, live)
    for cell in ("grew", "shrank", "shifted", "forged", "new_docs", "offenders"):
        assert diff[cell] == [], (cell, diff[cell][:1])
    for doc_rel, entry in live["files"].items():
        assert entry["pointers"] == stored["files"][doc_rel]["pointers"], doc_rel

    doc.write_bytes(doc.read_bytes() + ("\n见 " + coordinate("chat", 77) + "。\n").encode("utf-8"))
    grew = ruler.ratchet_diff(stored, baseline_of(shadow))["grew"]
    assert grew and grew[0]["added"] and grew[0]["added"][0].endswith(coordinate("chat", 77)), grew


# ==================== 刀十一：整行搬到相邻行——身份逐枚不变 ====================


def test_moving_a_bearing_line_to_its_neighbour_keeps_every_identity(tmp_path) -> None:
    """内容一字未动、只是行位挪一格：身份逐字符不变，棘轮零枚（行位口径的旧版在这一格必红）。"""
    rel = "docs/handoff/2026-09-25-plan-ticket-closure.md"
    shadow = shadow_copy(tmp_path, [rel])
    stored = baseline_of(shadow)
    doc = shadow / "handoff" / "2026-09-25-plan-ticket-closure.md"
    found, _meta = ruler.scan_doc(rel, doc)
    text, _meta = ruler.decode_text(doc.read_bytes())
    lines = ruler.doc_lines(text)
    slot = next((occ.doc_line - 1 for occ in found
                 if occ.doc_line < len(lines) and not ruler.COORD.search(lines[occ.doc_line])), None)
    assert slot is not None, "搬行的落点取不到：本刀的前提变了"
    moved = lines[slot]
    lines[slot], lines[slot + 1] = lines[slot + 1], lines[slot]
    doc.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    live = baseline_of(shadow)
    assert live["files"][rel]["pointers"] == stored["files"][rel]["pointers"], rel
    assert ruler.ratchet_diff(stored, live)["offenders"] == []
    assert ruler.line_digest(moved) == ruler.line_digest("  " + moved.strip() + "   "), "空白折叠那一格失效"


# ==================== 刀十二：行照被 splice 改写而坐标没多没少——落 shifted 不红 ====================


def test_a_reworded_line_that_keeps_its_coordinate_is_shifted_not_grew(tmp_path) -> None:
    """账面把一行的句子改了、坐标照抄：枚数不变，只许落 shifted 点名，不许红。"""
    rel = "docs/api/contract-v1.md"
    shadow = shadow_copy(tmp_path, [rel])
    stored = baseline_of(shadow)
    doc = shadow / "api" / "contract-v1.md"
    found, _meta = ruler.scan_doc(rel, doc)
    only = next(occ for occ in found
                if len([other for other in found if other.doc_line == occ.doc_line]) == 1)
    text, _meta = ruler.decode_text(doc.read_bytes())
    lines = ruler.doc_lines(text)
    old_line = lines[only.doc_line - 1]
    lines[only.doc_line - 1] = "（本班订正一句假话）" + old_line
    doc.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    diff = ruler.ratchet_diff(stored, baseline_of(shadow))
    assert diff["grew"] == [] and diff["forged"] == [] and diff["offenders"] == [], diff
    assert [row["doc"] for row in diff["shifted"]] == [rel], diff["shifted"]
    cell = diff["shifted"][0]
    assert cell["before"] == cell["after"] == stored["files"][rel]["count"], cell
    assert len(cell["added"]) == 1 and len(cell["removed"]) == 1, cell
    assert ruler.line_digest(old_line) != ruler.line_digest("（本班订正一句假话）" + old_line)


# ==================== 本件自己先过一遍尺 ====================


def test_these_teeth_copy_no_coordinate() -> None:
    """钉与刀自己的源文里一枚 ``.py:数字`` 都不许有（造坐标一律走 coordinate 把手）。"""
    for source in (Path(__file__).resolve(), SCRIPT, REPO / "tests" / "test_r638_pointer_ratchet.py"):
        assert ruler.COORD.findall(source.read_text(encoding="utf-8")) == [], source


def test_the_teeth_leave_nothing_behind(tmp_path) -> None:
    """影子根只活在 tmp_path：跑完刀，tmp_path 之外不该多出任何文件。"""
    shadow = shadow_copy(tmp_path, ["docs/api/contract-v1.md"])
    before = sorted(p.name for p in tmp_path.rglob("*") if p.is_file())
    write_shadow(shadow, "docs/knife-temp.md", "见 %s。\n" % coordinate("chat", 1))
    after = sorted(p.name for p in tmp_path.rglob("*") if p.is_file())
    assert len(after) == len(before) + 1, (before, after)
    assert str(tmp_path) in str(shadow)
