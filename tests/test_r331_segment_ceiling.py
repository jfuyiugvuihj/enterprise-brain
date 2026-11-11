"""R331 · `tables.parts()` 的余量必须按 `_assemble()` 实发的那枚锚预留（判据原文见派工词）。

缺陷形状（R305 施工时现取上报、总控裁定立案）：`parts()` 拿**不带段号**的 `anchor()` 算余量，
`_assemble()` 印出来的却是**带段号**的 `anchor(i, total)`，于是 "（i/j段）" 那一截从没被预留过。
真件 `data/报销明细表.csv` 实测最长段 450 > 本模块自己写在 docstring 里的上界 448 —— 检索今天
没炸（450 仍 < 上游 500，也 < R300 量出的 499 丢锚线），但那笔账是假的。同一件事在
`_header_only()` 里早就按"最坏段号宽度"（`anchor(99, 99)`）预留了，本单照**同一口径**补
`parts()` 这一路：不发明第二套预留法，不改锚的写法，不放宽任何一枚既有钉。

本文件钉的是**不变量**，不是某一枚实测数（实测数记在 tests/test_r305_spreadsheets.py）：

1 每一枚实发段——含段号、含表题、含表头与分隔行——长度 ≤ 它自己声明的上界，对**所有**段成立；
2 装不下就多切一段：数据行逐字、按源顺序、各出现一次，锚一枚不许少、段首必须是它那枚锚；
3 段号进到三位数（>99 段的大表，5000 行的真 CSV 就够）时预留跟着变宽，上界仍然是事实；
4 表题只印在第一段，因此也在预留里；退化成字段式的超宽行同样不许把段撑破。

读数：`SEGMENT_CHAR_BUDGET` = 448（与上游那把尺同值，同源现取，本文件不抄第二份常量）；
真件修后 38 段 / 最长 442。全程离线：不连库、不起服务、不打模型；真件只读，宽表在内存里直造。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from app.rag import spreadsheets, tables
from app.rag.tables import ANCHOR_JOIN, BLOCK_SEPARATOR, SEGMENT_CHAR_BUDGET, TableBlock

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_SOURCE = REPO_ROOT / "app" / "rag" / "tables.py"
SPLITTER_SOURCE = REPO_ROOT / "app" / "rag" / "retriever.py"
CORPUS_CSV = REPO_ROOT / "data" / "报销明细表.csv"

#: 真件那枚块的段数：修余量之前 37，之后 38——多切的那一段是**装不下的那一行**，
#: 一行不许多、一枚锚也不许少（判据③）。账钉在 tests/test_r305_spreadsheets.py。
CORPUS_SEGMENTS_BEFORE = 37
CORPUS_SEGMENTS_AFTER = 38


def r331_block(rows, header=("科目", "金额", "备注"), captions=(), filename="r331_block.csv", ordinal="1"):
    """一枚直造的表块：本单验的是装箱口径，不该被解析器牵着走。"""
    return TableBlock(
        filename=filename,
        ordinal=ordinal,
        header=tuple(header),
        rows=tuple(rows),
        source="csv",
        captions=tuple(captions),
    )


def r331_segments(block: TableBlock) -> list[str]:
    """这块表实发出去的段（与 `_assemble()` 的印法一字不差）。"""
    return block.to_markdown().split(BLOCK_SEPARATOR)


def r331_hold_the_ceiling(segments: list[str], block: TableBlock) -> list[str]:
    """本文件的判据本体：**每一枚**实发段都不许超过声明上界，且段首就是它那枚锚。"""
    assert segments, "装箱结果为空：一行都没发出去"
    total = len(segments)
    for index, segment in enumerate(segments, 1):
        first = segment.split("\n")[0]
        assert first == block.anchor(index, total), f"第{index}/{total}段首行不是它该带的锚：{first!r}"
        assert len(segment) <= SEGMENT_CHAR_BUDGET, (
            f"实发段 {len(segment)} 字 > 声明上界 {SEGMENT_CHAR_BUDGET} 字（第{index}/{total}段 {first!r}）"
            "：余量没按 `_assemble()` 实发的那枚锚预留，docstring 的尺就是假账"
        )
    return segments


def r331_data_lines(block: TableBlock, segments: list[str]) -> list[str]:
    """把实发段里"锚 + 可选表题 + 表头 + 分隔行"之外的那些行按序收回来。"""
    emitted: list[str] = []
    for segment in segments:
        lines = segment.split("\n")[1:]
        if block.captions:
            assert lines[0] in (block.caption_line, block.header_line), "表题只许出现在第一段"
            if lines[0] == block.caption_line:
                lines = lines[1:]
        assert lines[:2] == [block.header_line, block.separator_line], f"段的骨架变了：{lines[:3]}"
        emitted.extend(lines[2:])
    return emitted


def r331_splitter():
    """仓库里唯一那枚分块器，字面量从 app/rag/retriever.py 现取（R206 习惯，不抄第二份尺）。"""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    source = SPLITTER_SOURCE.read_text(encoding="utf-8")
    size = int(re.search(r"chunk_size=(\d+)", source).group(1))
    overlap = int(re.search(r"chunk_overlap=(\d+)", source).group(1))
    separators = ast.literal_eval(re.search(r"separators=(\[[^\]]*\])", source).group(1))
    return RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap, separators=separators)


# ---------------------------------------------------------------- 那把刀：预留的是哪一枚锚


def test_parts_reserves_the_anchor_that_actually_prints() -> None:
    """源码级钉：`parts()` 的余量里必须是带段号的锚，不许再出现 `len(self.anchor())`。"""
    source = MODULE_SOURCE.read_text(encoding="utf-8")
    match = re.search(r"^    def parts\(.*?(?=^    def |\Z)", source, re.S | re.M)
    assert match, "parts() 取不到函数体——是它的名字变了，不是它干净"
    body = match.group(0)

    assert "len(self.anchor(widest, widest))" in body, "余量必须按实发的带段号锚预留（与 _header_only() 同口径）"
    assert "len(self.anchor())" not in body, "摘回不带段号的 anchor() 就是本单破账的那把刀"
    assert "len(self.caption_line)" in body, "第一段实发还带表题，预留里不许把它漏了"

    head_only = re.search(r"^    def _header_only\(.*?(?=^    def |^@|\Z)", source, re.S | re.M)
    assert head_only, "_header_only() 取不到函数体——先例没了，口径就没得对照了"
    assert "self.anchor(99, 99)" in head_only.group(0), (
        "本单照的是 _header_only() 那枚'按最坏段号宽度预留'的先例，同一口径只许有一种"
    )


def test_the_part_number_is_wider_than_the_anchor_the_ceiling_used_to_reserve() -> None:
    """把缺陷本身钉住：段号那一截确实比不带段号的锚宽，所以旧账必然是假的。"""
    block = spreadsheets.load_spreadsheet(CORPUS_CSV).blocks[0]

    assert len(block.anchor()) == 14, block.anchor()
    assert len(block.anchor(CORPUS_SEGMENTS_AFTER, CORPUS_SEGMENTS_AFTER)) > len(block.anchor())
    assert block.anchor(CORPUS_SEGMENTS_AFTER, CORPUS_SEGMENTS_AFTER) == (
        f"报销明细表.csv{ANCHOR_JOIN}表1（{CORPUS_SEGMENTS_AFTER}/{CORPUS_SEGMENTS_AFTER}段）"
    ), "锚的写法（形状与字面）本单一字未动"


def test_the_writing_of_the_anchor_is_unchanged() -> None:
    """判据④反证位：预留改了，锚的输出形状一个字都不许跟着改。"""
    block = r331_block([("差旅", "100", "")], filename="r331_shape.csv")

    assert block.anchor() == f"r331_shape.csv{ANCHOR_JOIN}表1"
    assert block.anchor(7, 12) == f"r331_shape.csv{ANCHOR_JOIN}表1（7/12段）"
    assert block.anchor(1, 1) == block.anchor(), "单段表不许印出（1/1段）"


# ---------------------------------------------------------------- 真件：上界对每一段成立


def test_every_segment_of_the_real_table_holds_its_own_ceiling() -> None:
    """判据①②：真件每一段（不是只有最长那枚）都 ≤ 它自己声明的上界，行与锚一枚不多不少。"""
    found = spreadsheets.load_spreadsheet(CORPUS_CSV)
    block = found.blocks[0]
    segments = r331_hold_the_ceiling(found.text.split(BLOCK_SEPARATOR), block)

    assert len(segments) == CORPUS_SEGMENTS_AFTER, "修余量必然多切一段：装不下就多切，不许丢行"
    assert len(segments) > CORPUS_SEGMENTS_BEFORE, "37 -> 38 是这一修的账，回到 37 就说明余量被放宽了"
    assert r331_data_lines(block, segments) == list(block.row_lines), "数据行必须逐字、按源顺序、各出现一次"
    assert len(block.parts()) == len(segments)


def test_the_real_file_still_survives_the_real_splitter_with_an_anchor() -> None:
    """判据③：上界被守住之后，真件过一遍上游那把尺仍然是块块带头锚、行不断。"""
    found = spreadsheets.load_spreadsheet(CORPUS_CSV)
    chunks = [chunk for chunk in r331_splitter().split_text(found.text) if chunk.strip()]

    assert chunks
    for chunk in chunks:
        assert len(chunk) <= tables.CHUNK_SIZE_CHARS, f"分块超尺：{len(chunk)}"
        assert (ANCHOR_JOIN + "表") in chunk.split("\n")[0], f"这一块没有以锚开头：{chunk.splitlines()[0]!r}"
        for line in chunk.split("\n"):
            if line.startswith("|") and not line.startswith("|-"):
                assert line.endswith(" |"), f"表格行被从中间切断了：{line!r}"


# ---------------------------------------------------------------- 段号进三位数、表题、超宽行


def test_a_three_digit_part_number_still_fits_under_the_ceiling() -> None:
    """大表（>99 段，段号三位数）：最坏段号宽度跟着变宽，上界仍然是事实而不是 99 段的特权。"""
    rows = [(f"科目{index}", str(index), "备注" * 8) for index in range(1200)]
    block = r331_block(rows)
    segments = r331_segments(block)

    assert len(segments) > 99, "这枚 fixture 没造出三位数段号，等于没验这一格"
    r331_hold_the_ceiling(segments, block)
    assert r331_data_lines(block, segments) == list(block.row_lines)
    assert segments[99].split("\n")[0].endswith("（100/%d段）" % len(segments))


def test_a_big_table_with_an_over_wide_row_still_holds_its_ceiling() -> None:
    """>99 段 + 一枚超宽格同时上：段号进三位数、退化续行又比 cap 长一两枚字，这时候才见牙。

    实测（本机现取，就是下面这枚 fixture）：预留恒按 `anchor(99, 99)` 时 123 段里漏出 10 枚
    超界段（449 / 450 > 448）；跟着实发的最坏段号宽度加宽预留之后是 132 段、最长 448，一枚不漏
    —— 多切的那 9 段正是"装不下就多切、不许丢行"的账。
    """
    rows = [("科目%d" % index, str(index), "备注" * 8) for index in range(1200)]
    rows.append(("差旅", "0", "很长的经营说明" * 600))
    block = r331_block(rows)
    segments = r331_segments(block)

    assert len(segments) > 99, "这枚 fixture 没造出三位数段号，等于没验这一格"
    field_lines = [line for segment in segments for line in segment.split("\n") if line.startswith("- 备注")]
    assert len(field_lines) > 9, "超宽格没有退成字段式，等于没验退化续行那一格"
    r331_hold_the_ceiling(segments, block)
    rebuilt = "".join(line.split(": ", 1)[1] for line in field_lines)
    assert rebuilt == "很长的经营说明" * 600, "字段式可以难看，不可以丢字"


def test_more_rows_buy_more_segments_and_never_a_wider_one() -> None:
    """判据③：行数涨上去只许多切段，不许把某一段撑破——段数单调不减、上界段段成立。"""
    counts = []
    for rows_in in range(40, 640, 40):
        block = r331_block([("科目%d" % index, str(index), "说明" * 6) for index in range(rows_in)])
        segments = r331_hold_the_ceiling(r331_segments(block), block)
        assert r331_data_lines(block, segments) == list(block.row_lines)
        counts.append(len(segments))

    assert counts == sorted(counts) and counts[0] < counts[-1], counts


def test_a_caption_on_the_first_segment_is_reserved_too() -> None:
    """表题只印在第一段，但它同样占那把尺：预留没它，第一段就是破口。"""
    captions = ("全年分部门费用汇总及同比说明" * 3, "口径：含税")
    block = r331_block([("科目%d" % index, str(index), "说明" * 6) for index in range(300)], captions=captions)
    segments = r331_segments(block)

    assert len(segments) > 1, "这枚 fixture 没造出多段，等于没验表题那一格"
    assert segments[0].split("\n")[1] == block.caption_line
    assert block.caption_line.startswith("> ")
    r331_hold_the_ceiling(segments, block)
    assert r331_data_lines(block, segments) == list(block.row_lines), "表题只许一次，数据行不许因此少一行"


def test_a_row_wider_than_the_ceiling_degrades_instead_of_overflowing() -> None:
    """超宽行退成字段式：续行可以比自己的 cap 长一两枚字，那 4 枚余量就是给它留的，段不许破。"""
    long_cell = "很长的经营说明文字" * 60
    block = r331_block([("差旅", "1", long_cell), ("办公", "2", long_cell)], header=("科目", "金额", "说明"))
    segments = r331_segments(block)

    lines = [line for segment in segments for line in segment.split("\n")]
    assert any(line.startswith("- 说明") for line in lines), "超宽行没有退成字段式"
    assert any(segment.split("\n")[3:] and segment.split("\n")[3].startswith("- ") for segment in segments)
    r331_hold_the_ceiling(segments, block)
    rebuilt = "".join(line.split(": ", 1)[1] for line in lines if line.startswith("- 说明"))
    assert rebuilt == long_cell * 2, "字段式可以难看，不可以丢字，也不可以把两行并成一行"
