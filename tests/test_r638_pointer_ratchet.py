# -*- coding: utf-8 -*-
"""R638 常驻钉 —— 纸面坐标的棘轮：只许减少，不许变多；基线由尺现取派生。

这单的定位（派工词 R638）：先止血。今天最贵的不是「有一堆漂了的行号」，是**没有一把尺挡得住
新的一枚继续长进纸里**。所以本件钉的是「枚数只许降」这一条，正文批量转换属后面几枚单。

判据对号：
  ① 本件的枚数与总控那把宽尺**同一形状**：另拿派工词原文那枚正则独立再数一遍 docs 全集，
     两把必须同值——这条不靠注释维持，也不许任何一处把枚数抄成常量。
  ② 尺的硬判红每一枚都带现读凭据（被引文件／该行所属符号／该行现读），逐枚可抽查。
  ③ 基线是**派生**的：盘上那件基线每一格 count 都等于逐枚身份清单的长度；正文 digest 未变时，
     尺的现读必须与那份清单逐枚相等。谁把数字抄进基线，这两格当场红。
   棘轮主判据（R638-R①②）：身份是 ``doc::整行文本哈希::被引坐标串``，**与行位无关**；
      任何一枚 .md 的枚数变多＝红，变少＝不红而逐枚点名少了谁，枚数不变而身份变了（账面 splice
      改了句子）＝不红而点名，盘上新落的 .md＝不红而点名（别的单的正文不由本单定罪）。
      更新基线只有一条路：``scripts/r638_doc_pointer_ruler.py --write-baseline``。
   🔴 红只由 ``grew``＋``forged`` 决定：拿行位当身份会「每写一次账面全仓变红」，那是假案不是止血。

🔴 本件不许把「此刻工作树脏不脏」当判据（同族病今天第三次，事故 #107）：全程只读盘上文本与
   尺的读数，不调 git、不比 dirty、不看任何人的施工态。
🔴 零 import 产品码：坐标解析走尺内部的 AST 腿——``app/api/v1/chat.py`` 一 import 就发 Postgres
   探针并把被跟踪的 ``chroma_db/chroma.sqlite3`` 写脏（今天两枚执行层都踩过）。
🔴 影子刀在 ``tests/test_r638_counter_evidence_teeth.py``，全部落 tmp_path；本件一枚盘上 .md 都不改。
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
BASELINE_ARTIFACT = REPO / "docs" / "testing" / "r638-pointer-baseline.json"


def _load_ruler():
    """按路径装载本单的尺（先注册进 sys.modules：dataclass 要拿得到自己的模块）。"""
    name = "r638_doc_pointer_ruler"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ruler = _load_ruler()


@pytest.fixture(scope="module")
def analysis():
    """整把尺跑一次（现读全部 docs）；本件其余用例复用同一枚读数，不各数各的。"""
    return ruler.analyze(REPO / "docs", REPO)


@pytest.fixture(scope="module")
def live_baseline(analysis):
    return ruler.build_baseline(analysis)


@pytest.fixture(scope="module")
def stored_baseline():
    assert BASELINE_ARTIFACT.is_file(), "盘上没有基线件：这枚棘轮还没配账，尺无从对"
    return json.loads(BASELINE_ARTIFACT.read_text(encoding="utf-8"))


# ==================== 判据① —— 与总控那把宽尺同一形状 ====================


def independent_ticket_count() -> tuple[int, int]:
    """拿派工词点名的那枚正则原文，独立再数一遍：不用尺的任何把手。"""
    pattern = re.compile(ruler.TICKET_SHAPE)
    total = 0
    docs = 0
    for path in sorted((REPO / "docs").rglob("*.md")):
        if any(part.startswith(".") for part in path.relative_to(REPO / "docs").parts[:-1]):
            continue
        text, _meta = ruler.decode_text(path.read_bytes())
        found = sum(len(pattern.findall(line)) for line in ruler.doc_lines(text))
        if found:
            docs += 1
        total += found
    return total, docs


def test_the_ruler_counts_what_the_ticket_regex_counts(analysis) -> None:
    """两把尺同形同值：形状原文相等，枚数与文件数逐枚对上（谁改形状，这一格先红）。"""
    assert ruler.TICKET_SHAPE == r"[A-Za-z0-9_./-]+\.py:[0-9]+(-[0-9]+)?"
    total, docs = independent_ticket_count()
    readings = analysis["readings"]
    assert readings["total_pointers"] == total, (readings["total_pointers"], total)
    assert readings["md_files_with_pointers"] == docs, (readings["md_files_with_pointers"], docs)


def test_the_shape_catches_ranges_and_bare_names(analysis) -> None:
    """形状不许被"改窄"蒙混：区间形与裸基名形都在这把尺的射程里，且现读真有这两族。"""
    verdicts = analysis["readings"]["verdict_counts"]
    rows = analysis["rows"]
    assert any(row["is_range"] for row in rows), "整把尺没量到一枚区间引用"
    assert any(row["resolution"] == "unique" for row in rows), "整把尺没量到一枚裸基名引用"
    assert verdicts["ambiguous_path"] > 0, "基名撞车那一档空了：解析腿大概被改窄了"


def test_the_ruler_is_not_a_dead_ruler(tmp_path) -> None:
    """死尺前置：把坐标拆开现场拼出来喂进影子根，它必须数到——否则上面的同值什么都量不出。"""
    forged = "app/api/v1/chat" + ".py" + ":" + "9" + "9"
    ranged = forged + "-" + "1" + "2"
    shadow = tmp_path / "docs"
    shadow.mkdir()
    (shadow / "forged.md").write_text("见 %s 与 %s\n" % (forged, ranged), encoding="utf-8", newline="\n")
    found, meta = ruler.scan_doc("docs/forged.md", shadow / "forged.md")
    assert [occ.raw for occ in found] == [forged, ranged]
    assert meta["pointers"] == 2 and meta["ranges"] == 1


# ==================== 判据③ —— 基线由尺派生，不是手抄 ====================


def test_the_stored_baseline_is_self_derived(stored_baseline) -> None:
    """每一格 count 都等于清单长度、digest 在场、总数与形状自洽——手抄一列数字当场红。"""
    assert ruler.validate_baseline(stored_baseline) == []


def test_the_stored_baseline_matches_the_rulers_own_reading(stored_baseline, live_baseline) -> None:
    """正文 digest 未变的每一枚 .md，尺的现读必须与基线那份清单逐枚相等。

    这一格钉的是「数是谁取的」：谁把基线里的身份串改了／删了而正文一个字没动，
    现读与清单就不等，当场红——它不许基线成为第二份真源。
    """
    diff = ruler.ratchet_diff(stored_baseline, live_baseline)
    assert diff["forged"] == [], diff["forged"]


# ==================== 棘轮主判据 —— 只许降 ====================


def test_no_markdown_file_grew_its_paper_coordinates(stored_baseline, live_baseline) -> None:
    """棘轮正门：在册那几枚 .md 一枚都不许多出坐标；红只由 grew＋forged 决定。"""
    diff = ruler.ratchet_diff(stored_baseline, live_baseline)
    assert diff["grew"] == [], "纸上多长了几枚手抄坐标：%s" % diff["grew"]
    assert diff["forged"] == [], "基线不是尺取的：%s" % diff["forged"]
    assert diff["offenders"] == []
    for cell in diff["new_docs"]:
        # 新落的 .md 只点名不定罪（R638-R 病因三）：但每枚都得报得出几枚、是哪几枚。
        assert cell["count"] == len(cell["added"]) or cell["count"] > 0, cell
        assert cell["added"], cell


def test_shrink_is_named_not_silently_forgiven(stored_baseline, live_baseline) -> None:
    """变少不算红，但必须点得出名：每一格少了谁，逐枚交回，不许一句「少了」蒙过。"""
    diff = ruler.ratchet_diff(stored_baseline, live_baseline)
    for entry in diff["shrank"]:
        assert entry["after"] < entry["before"], entry
        assert entry["removed"], entry
        assert len(entry["removed"]) == entry["before"] - entry["after"], entry
    assert not [entry for entry in diff["grew"] if entry["after"] < entry["before"]], \
        "枚数下降却进了 grew：方向装反（R638-R② 的第二条病因）"


def test_a_count_decrease_can_never_be_reported_as_growth() -> None:
    """纯函数级反证（不落盘、不碰影子）：同一枚 doc 少一枚，必须走 shrank 而非 grew。"""
    doc = "docs/handoff/synthetic.md"
    ident = doc + "::" + "0" * 16 + "::" + "chat" + ".py" + ":" + "1"
    ident2 = doc + "::" + "1" * 16 + "::" + "chat" + ".py" + ":" + "2"
    stored = {"shape": ruler.TICKET_SHAPE, "identity_scheme": ruler.IDENTITY_SCHEME,
              "total_pointers": 2, "files": {doc: {"digest": "a" * 16, "count": 2,
                                                   "pointers": sorted([ident, ident2])}}}
    live = {"files": {doc: {"digest": "b" * 16, "count": 1, "pointers": [ident]}}}
    diff = ruler.ratchet_diff(stored, live)
    assert diff["grew"] == [] and diff["offenders"] == [], diff
    assert [row["doc"] for row in diff["shrank"]] == [doc], diff["shrank"]
    assert diff["shrank"][0]["removed"] == [ident2], diff["shrank"]


# ==================== R638-R① —— 身份里不许有行位 ====================


def test_the_baseline_identity_carries_no_line_position(stored_baseline) -> None:
    """每一枚身份串都是「doc::行文本哈希::被引坐标」：第二段是 sha256 前 16 位，不是行号。

    这一格钉的是病因一本身——谁把身份改回带行位的口径，账面一 splice 就全仓变红，当场红。
    """
    scheme = stored_baseline.get("identity_scheme")
    assert scheme == ruler.IDENTITY_SCHEME, scheme
    named = 0
    for doc, entry in stored_baseline["files"].items():
        for key in entry["pointers"]:
            head, _, tail = key[len(doc) + 2:].partition("::")
            assert re.fullmatch(r"[0-9a-f]{16}", head), key
            assert tail.startswith(doc) is False and tail, key
            named += 1
    assert named == stored_baseline["total_pointers"], (named, stored_baseline["total_pointers"])
    assert named > 0, "基线一枚身份都没有：这格空过等于没钉"


def test_the_identity_of_a_line_survives_a_position_shift() -> None:
    """同一行文本搬到第 1 行与第 9 行，身份逐字符相等；上面插一行不改任何人的身份。"""
    line = "见 " + "chat" + ".py" + ":" + "99" + " 那一格。"
    pad = ["先垫一行。", "再垫一行。", "还是垫行。", "继续垫。", "还垫。", "垫。",
           "垫。", "垫。", "垫。"]
    docs = {"docs/testing/synth-a.md": [line], "docs/testing/synth-b.md": pad + [line]}
    ident = {}
    for rel, lines in docs.items():
        text = "\n".join(lines) + "\n"
        found = []
        for number, row in enumerate(ruler.doc_lines(text), start=1):
            for match in ruler.COORD.finditer(row):
                found.append(ruler.Occurrence(rel, number, match.start(), match.group(0),
                                              "chat" + ".py", 99, None, row))
        assert len(found) == 1, rel
        ident[rel] = found[0].identity
    assert [row.split("::")[1] for row in ident.values()] == \
        [ruler.line_digest(line)] * 2, ident
    assert ident["docs/testing/synth-a.md"].split("::", 2)[2] == \
        ident["docs/testing/synth-b.md"].split("::", 2)[2], ident


# ==================== 判据② —— 硬判红每一枚都带现读凭据 ====================


def test_every_stale_row_carries_its_own_evidence(analysis) -> None:
    """判红的每一枚都得说得出「现读是什么」：本席抽查 10 枚时逐枚按这一格复现。"""
    hard = [row for row in analysis["rows"] if row["hard"]]
    assert hard, "整把尺一枚都没判红：要么纸被洗干净了，要么尺死了"
    line_bound = ("line_out_of_range", "empty_target_line", "symbol_mismatch")
    for row in hard:
        assert row["where"].count(":") >= 1 and row["cited"] and row["doc_excerpt"], row
        assert row["verdict"] in ruler.HARD_VERDICTS, row
        assert row["anchor_note"], row
        if row["verdict"] == "symbol_mismatch":
            # 这一档裁的是「句子说 A 在这一行，现读这一行属 B」，两栏都得摆出来才谈得上抽查。
            assert row["target"] and row["owner_now"], row
            assert row["claims"] and row["claim_spans"], row
        elif row["verdict"] == "file_missing":
            assert row["target"] is None, row
        elif row["verdict"] == "file_moved":
            assert isinstance(row["target"], list) and row["target"], row
        if row["verdict"] in line_bound:
            assert row["line_now"] is not None, row


def test_unverifiable_rows_say_so_instead_of_passing_green(analysis) -> None:
    """量不到的档如实占一格（不判红也不装成已核对）：这一格是「别把没量过说过」的下限。"""
    verdicts = analysis["readings"]["verdict_counts"]
    assert verdicts.get("unverified_no_claim", 0) > 0
    assert set(verdicts) <= set(ruler.HARD_VERDICTS) | set(ruler.SOFT_VERDICTS) | {"claim_matches"}


# ==================== 本单自己不往纸上添坐标 ====================


def test_this_ticket_papers_no_coordinate_of_its_own() -> None:
    """止血单的取证纸自己一枚坐标都不许抄：docs/testing/r638-*.md 必须是零枚。

    机器件（基线 json）里那几千枚身份串不算——尺只扫 ``*.md``，这是刻意分工，不是漏扫。
    """
    papers = sorted((REPO / "docs" / "testing").glob("r638-*.md"))
    for path in papers:
        found, meta = ruler.scan_doc(path.relative_to(REPO).as_posix(), path)
        assert found == [], (str(path), meta["pointers"])
    assert papers, "本单的取证纸没落盘：docs/testing/r638-*.md 一枚都没有"


def test_the_ruler_itself_copies_no_coordinate() -> None:
    """钉与尺自己都不许抄坐标（R630/R635 同族口径）：源文里一枚 ``.py:数字`` 都不能有。"""
    for source in (Path(__file__).resolve(), SCRIPT):
        text = source.read_text(encoding="utf-8")
        assert ruler.COORD.findall(text) == [], source
