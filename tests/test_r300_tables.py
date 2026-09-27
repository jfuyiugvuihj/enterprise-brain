"""R300 · PDF / Word 表格抽取（判据原文见跟进单 §102 第四节，派工词逐字抄录）。

本文件同时是"实测行为"的记录处：合并单元格、跨页表、无框表、溢出单元格这四类形状，
下面钉的都是 pdfplumber 0.11.10 与 python-docx 1.2.0 **实际交回来的东西**，不是推测。
所有 fixture 由本文件里的代码现造（PDF 是手写最小合法字节串，DOCX 由 python-docx 生成），
仓库里不因此多出任何二进制或带字数的位图。

判据对应：① 锚 -> test_pdf_anchor_*、test_anchor_*；② 合并与跨页 -> test_pdf_colspan_* …
test_pdf_two_tables_*；③ 通道口径 -> test_budget_constants_match_*、
test_every_table_row_survives_the_real_splitter_*；④ 性能 -> test_measured_cost_*；
⑤ 反证三把 -> test_table_only_document_*（退回 paragraph-only 即红）、
test_anchor_is_the_first_line_*（锚丢即红）、test_pdf_text_does_not_repeat_*（同表吐两次即红）；
⑥ 表不等于正文 -> test_table_only_document_has_text_and_no_prose。

反证的牙不是嘴上说的：收尾时把 app/rag/tables.py 临时改坏七次，每次都跑完整本用例、跑完即
还原，并核对源文件与**记名锚点提交现算的 git blob** 一致（字节不变；锚点与派生尺子见本文件
末尾「现场 B」一节，与 tests/test_r304_table_wiring.py 同源，不另造第二本账）。这一格从前抄着
一串十六进制（7acaa33c…）：那是 58111c9（R331 动过 tables.py）之前那一份的 **checkout 层（CRLF）**
摘要，自 58111c9 起就不是今天的文件内容，而它写在散文里不是断言，所以永远不会红，只会骗下一位
照抄的人——期望值因此改成现算，🔴 不许就地重录一枚今天的 hex。
下面 (a)-(g) 是当时那 39 枚用例的反证读数（历史账，枚数以当时为准）：
  (a) docx 解析交回空集           -> 11 红    (b) pdf 解析交回空集          -> 19 红
  (c) docx 入口退回只发正文       ->  2 红    (d) pdf 入口退回只发正文       ->  4 红
  (e) 来源锚摘掉                 -> 10 红    (f) 正文不扣表框(同表吐两次)   ->  4 红
  (g) 每枚表重复吐一次            -> 15 红
(c)(d) 这两把是本轮补出来的：只测流水线时，入口被退回 paragraph-only 只有 1/3 枚会红，
于是补 test_the_two_wired_functions_carry_every_row_once，把波次二真要接的那两枚函数钉死。
全程离线：不连库、不起服务、不打模型（LOCAL_MODEL_NAME 由跑测试的外层钉成禁用值）。
"""
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

import pytest

from app.rag import loader, tables
from app.rag.tables import (
    ANCHOR_JOIN,
    BLOCK_SEPARATOR,
    CHUNK_OVERLAP_CHARS,
    CHUNK_SIZE_CHARS,
    SEGMENT_CHAR_BUDGET,
)

# 现场 B（R364）：本文件 docstring 那句「跑完即还原，核对源文件 sha256」的期望值改成派生。
# 尺子与锚点**都用 R304/R352 那一把**（同一条锚、同一套 blob 层换算），不在本文件另造第二本账；
# 名字带 r304_ 前缀的都不是 test_* ⇒ 导进来不会被 pytest 当成本文件的用例再跑一遍。
from test_r304_table_wiring import (  # noqa: E402
    TABLES_ANCHOR_SHA,
    TABLES_BLOB_PATH,
    r304_git,
    r304_git_blob,
    r304_tables_digest_at,
    r304_tables_digest_on_disk,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SPLITTER_SOURCE = REPO_ROOT / "app" / "rag" / "retriever.py"
EVIDENCE_SOURCE = REPO_ROOT / "app" / "agents" / "evidence.py"
MODULE_SOURCE = REPO_ROOT / "app" / "rag" / "tables.py"
CORPUS_PDF = REPO_ROOT / "documents" / "refactor_guide.pdf"

#: 真语料实测（判据④），改一个就是改账，必须连耗时一起重测。
CORPUS_PAGES = 28
CORPUS_TABLES = 9
CORPUS_ROWS = 48

#: 与 app/rag/retriever.py:892 逐字同一串分隔符；上面那枚断言负责盯着它。
SEQUENCE = ["\n\n", "\n", "。", "；", "　", " ", ""]

PAGE_HEIGHT = 792.0
COLUMN_WIDTH = 100.0
ROW_HEIGHT = 22.0


# ------------------------------------------------------------------ 造 PDF（手写最小字节串）


def r300_write_pdf(pages: list[str], path: Path, *, cjk: bool = False) -> Path:
    """Write a syntactically plain PDF: one content stream per page, no compression.

    Written by hand on purpose -- reportlab is not a project dependency and uv add is out of
    bounds. pdfminer tolerates a missing /Catalog, pypdf does not, so the catalog is here and
    the fixture is readable by both parsers.
    """
    counter = {"next": 1}

    def new() -> int:
        value = counter["next"]
        counter["next"] += 1
        return value

    objs: dict[int, bytes] = {}
    font = new()
    cid_font = new() if cjk else 0  # id 0 does not exist in the table, so it never gets written
    catalog = new()
    pages_id = new()
    page_ids = [new() for _ in pages]
    stream_ids = [new() for _ in pages]
    objs[font] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    if cjk:
        # A standard CJK font with a predefined CMap: no embedding, and pdfminer maps the
        # UCS-2 codes straight back to the Chinese text, so a fixture can hold 真实中文表格。
        objs[cid_font] = (
            b"<< /Type /Font /Subtype /Type0 /BaseFont /STSong-Light /Encoding /UniGB-UCS2-H "
            b"/DescendantFonts [ << /Type /Font /Subtype /CIDFontType0 /BaseFont /STSong-Light "
            b"/CIDSystemInfo << /Registry (Adobe) /Ordering (GB1) /Supplement 2 >> >> ] >>"
        )
    refs = "/F1 %d 0 R" % font + (" /F2 %d 0 R" % cid_font if cjk else "")
    objs[catalog] = ("<< /Type /Catalog /Pages %d 0 R >>" % pages_id).encode()
    kids = " ".join("%d 0 R" % value for value in page_ids)
    objs[pages_id] = ("<< /Type /Pages /Kids [ %s ] /Count %d >>" % (kids, len(pages))).encode()
    for index, (page_id, stream_id) in enumerate(zip(page_ids, stream_ids)):
        objs[page_id] = (
            "<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 %d] "
            "/Resources << /Font << %s >> >> /Contents %d 0 R >>"
            % (pages_id, int(PAGE_HEIGHT), refs, stream_id)
        ).encode()
        data = pages[index].encode("latin-1", "replace")
        objs[stream_id] = b"<< /Length %d >>\nstream\n" % len(data) + data + b"\nendstream"
    top = max(objs)
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    for number in range(1, top + 1):
        offsets[number] = len(out)
        out += b"%d 0 obj\n" % number + objs[number] + b"\nendobj\n"
    start = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (top + 1)
    for number in range(1, top + 1):
        out += b"%010d 00000 n \n" % offsets[number]
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (top + 1, catalog, start)
    path.write_bytes(bytes(out))
    return path


def r300_draw_text(x: float, y: float, value: str, *, font: str = "F1") -> str:
    if font == "F2":
        return "BT /F2 10 Tf %.1f %.1f Td <%s> Tj ET\n" % (x, y, value.encode("utf-16-be").hex().upper())
    return "BT /F1 10 Tf %.1f %.1f Td (%s) Tj ET\n" % (x, y, value)


def r300_draw_table(
    x0: float,
    y0: float,
    cells: list[list[str]],
    *,
    open_v: tuple[tuple[int, int], ...] = (),
    open_h: tuple[tuple[int, int], ...] = (),
    font: str = "F1",
    column_width: float = COLUMN_WIDTH,
) -> str:
    """Stroke a bordered grid, optionally opening a segment out to fake a merged cell.

    open_v=(0, 2) drops the internal vertical boundary between columns 1 and 2 of row band 0
    (a colspan); open_h=(1, 0) drops the horizontal boundary under row 0 of column band 0 (a
    rowspan). That is how a word processor draws a merge: fewer lines, not a special object.
    """
    rows = len(cells)
    cols = max(len(row) for row in cells)
    xs = [x0 + index * column_width for index in range(cols + 1)]
    ys = [y0 - index * ROW_HEIGHT for index in range(rows + 1)]
    ops = []
    for index, y in enumerate(ys):
        for band in range(cols):
            if index in (0, rows) or (index, band) not in open_h:
                ops.append("%.1f %.1f m %.1f %.1f l S\n" % (xs[band], y, xs[band + 1], y))
    for index, x in enumerate(xs):
        for band in range(rows):
            if index in (0, cols) or (band, index) not in open_v:
                ops.append("%.1f %.1f m %.1f %.1f l S\n" % (x, ys[band], x, ys[band + 1]))
    for row_index, row in enumerate(cells):
        for column_index, value in enumerate(row):
            if value:
                ops.append(r300_draw_text(xs[column_index] + 4, ys[row_index] - 15, value, font=font))
    return "".join(ops)


# ------------------------------------------------------------------ 造 DOCX（python-docx 现生成）


def r300_write_docx(path: Path, blocks: list) -> Path:
    """Blocks are ("p", text) / ("t", rows, merges) tuples; merges are (row, col, row, col)."""
    from docx import Document

    document = Document()
    for kind, *rest in blocks:
        if kind == "p":
            document.add_paragraph(rest[0])
            continue
        rows, merges = rest
        table = document.add_table(rows=len(rows), cols=len(rows[0]))
        table.style = "Table Grid"
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                table.cell(row_index, column_index).text = value
        for (first_row, first_col, last_row, last_col) in merges:
            table.cell(first_row, first_col).merge(table.cell(last_row, last_col))
    document.save(str(path))
    return path


def r300_prose_of(path: Path) -> str:
    """The exact expression load_docx uses today, so the no-duplication claim is about it."""
    from docx import Document

    document = Document(str(path))
    return "\n".join(p.text for p in document.paragraphs if p.text.strip())


def r300_splitter():
    """The project's one and only chunker, rebuilt from the literals in app/rag/retriever.py.

    Read out of the source rather than retyped (the R206 habit): a test that carries its own
    copy of the ruler stays green after somebody widens it, which is the exact accident this
    ticket must not have. SEQUENCE below is the pinned expectation.
    """
    import ast

    from langchain_text_splitters import RecursiveCharacterTextSplitter

    source = SPLITTER_SOURCE.read_text(encoding="utf-8")
    size = int(re.search(r"chunk_size=(\d+)", source).group(1))
    overlap = int(re.search(r"chunk_overlap=(\d+)", source).group(1))
    separators = ast.literal_eval(re.search(r"separators=(\[[^\]]*\])", source).group(1))
    assert separators == SEQUENCE, f"上游分隔符序列变了，这把尺得重测：{separators}"
    return RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap, separators=separators)


def r300_anchors(text: str) -> list[str]:
    return [line for line in text.split("\n") if ANCHOR_JOIN in line and "表" in line]


# ------------------------------------------------------------------ ① 结构化 markdown + 来源锚


def test_pdf_anchor_names_file_page_and_table_ordinal(tmp_path):
    """判据①: 一条锚至少说清"哪个文件、第几页、本页第几枚表"。"""
    one = r300_draw_table(60, 700, [["Region", "Q1"], ["East", "11"]])
    two = r300_draw_table(60, 500, [["Item", "Cost"], ["Server", "800"]])
    path = r300_write_pdf([one + two], tmp_path / "r300_two.pdf")

    found = tables.extract_pdf_tables(path)

    assert [block.anchor() for block in found.blocks] == [
        f"r300_two.pdf{ANCHOR_JOIN}第1页{ANCHOR_JOIN}表1",
        f"r300_two.pdf{ANCHOR_JOIN}第1页{ANCHOR_JOIN}表2",
    ]
    assert found.blocks[1].ordinal == "2" and found.blocks[1].page == 1


def test_markdown_shape_is_a_header_a_separator_and_one_line_per_row(tmp_path):
    """判据①: 吐的是 markdown 表，不是把单元格摊平成一句话。"""
    path = r300_write_pdf(
        [r300_draw_table(60, 700, [["大区", "营收"], ["华东", "1200"], ["华南", "900"]], font="F2")],
        tmp_path / "r300_plain.pdf",
        cjk=True,
    )

    text = tables.extract_pdf_text(path)

    assert text.split("\n") == [
        f"r300_plain.pdf{ANCHOR_JOIN}第1页{ANCHOR_JOIN}表1",
        "| 大区 | 营收 |",
        "|---|---|",
        "| 华东 | 1200 |",
        "| 华南 | 900 |",
    ]


def test_cjk_table_survives_the_round_trip(tmp_path):
    """中文业务表是本项目的主场景，锚和单元格都得逐字回来。"""
    path = r300_write_pdf(
        [r300_draw_table(60, 700, [["季度营收", "大区"], ["2026Q1", "华东"]], font="F2")],
        tmp_path / "r300_cjk.pdf",
        cjk=True,
    )

    block = tables.extract_pdf_tables(path).blocks[0]

    assert (block.header, block.rows) == (("季度营收", "大区"), (("2026Q1", "华东"),))


def test_docx_anchor_has_no_page_but_a_locator_a_reader_can_use(tmp_path):
    """判据①: docx 没有页号可给，就用文档序号 + 前一段正文定位。"""
    path = r300_write_docx(
        tmp_path / "r300_ctx.docx",
        [
            ("p", "第三章节：分部门费用。"),
            ("t", [["科目", "金额"], ["差旅", "12"]], []),
        ],
    )

    block = tables.extract_docx_tables(path).blocks[0]

    assert block.page is None and block.page_label == ""
    assert block.anchor() == f"r300_ctx.docx{ANCHOR_JOIN}表1{ANCHOR_JOIN}前文「第三章节：分部门费用。」"


def r300_cross_pages():
    """A table that runs out of the page: 32 data rows on page one, 2 more on page two.

    Row height is 22 and the band starts at y=748, so the last row of page one lands at y=24
    -- still inside the box. Draw one row more and it falls off the foot: pdfplumber never
    sees its text, the row comes back empty, and the fixture measures something else. Measured
    at 34 data rows: the 34th disappears, which is how this trap was found.
    """
    head = ["Region", "Q1", "Q2"]
    page_one = [head] + [["R%d" % index, str(index), str(index * 2)] for index in range(1, 33)]
    page_two = [head] + [["R33", "33", "66"], ["R34", "34", "68"]]
    return page_one, page_two


def test_anchor_is_the_first_line_of_every_segment(tmp_path):
    """判据①/⑤: 下游引用条只带 filename+chunk_index，锚必须是块内第一行才点得回原文。"""
    page_one, page_two = r300_cross_pages()
    path = r300_write_pdf(
        [r300_draw_table(60, 748, page_one), r300_draw_table(60, 748, page_two)],
        tmp_path / "r300_parts.pdf",
    )

    found = tables.extract_pdf_tables(path)
    text = found.text

    assert found.table_count == 1, "跨页拼成一枚表，段数由预算决定，不由页数决定"
    segments = text.split(BLOCK_SEPARATOR)
    assert len(segments) > 1, "这张表超预算，必须分段"
    for index, segment in enumerate(segments, 1):
        expected = f"r300_parts.pdf{ANCHOR_JOIN}第1-2页{ANCHOR_JOIN}表1（{index}/{len(segments)}段）"
        assert segment.startswith(expected), segment.splitlines()[0]
        assert segment.split("\n")[3].startswith("|"), "锚之后紧跟表头与分隔行"


def test_anchor_fits_inside_the_excerpt_the_citation_bar_keeps(EVIDENCE_LIMIT):
    """判据①: 引用条只截正文前 N 字（app/agents/evidence.py 的 _EXCERPT_LIMIT），锚必须活下来。"""
    limit = int(EVIDENCE_LIMIT)
    long_name = "r300_一个比较长的中文文件名用来压测锚长度.pdf"
    block = tables.TableBlock(
        filename=long_name,
        ordinal="12",
        header=("大区", "营收", "同比"),
        rows=(("华东", "1200", "+12%"),),
        source="pdf",
        page=34,
        end_page=36,
        spans=7,
    )

    anchor = block.anchor()

    assert anchor.startswith(long_name) and "第34-36页" in anchor and "合并单元格7处" in anchor
    assert len(anchor) + len(block.header_line) + 2 <= limit, "摘录窗口必须装得下锚和表头"


# ------------------------------------------------------------------ ② 合并单元格与跨页表：实测行为


def test_pdf_colspan_measured_behaviour(tmp_path):
    """实测：合并文字的表落在最左那一格，被盖住的位置 pdfplumber 交回 None，本模块按左侧值补齐。

    第四格是"真空格"（交回的是空串，不是 None），所以它不补 —— 这条区分是解析器给的，
    不是本模块猜的。表头那行因此长成 "Q1 H2 | Q1 H2 |  "，两格同值即一个跨列。
    """
    cells = [["Region", "Q1", "H2", ""], ["East", "11", "12", "13"]]
    path = r300_write_pdf([r300_draw_table(60, 700, cells, open_v=((0, 2),))], tmp_path / "r300_cs.pdf")

    block = tables.extract_pdf_tables(path).blocks[0]

    assert block.spans == 1
    assert block.header == ("Region", "Q1 H2", "Q1 H2", "")
    assert block.rows == (("East", "11", "12", "13"),)
    assert block.anchor().endswith(f"表1{ANCHOR_JOIN}合并单元格1处")
    assert block.row_lines[0] == "| East | 11 | 12 | 13 |"


def test_pdf_rowspan_measured_behaviour(tmp_path):
    """实测：竖合并把两格文字用换行粘在第一格（Region + East -> "Region East"），下一行同列交回 None。

    本模块把换行折成空格（否则 markdown 行会被自己撕开），并把 None 位置按上一行同列补齐。
    第三行第一格是解析器交回的真空格，保持空 —— 它是"这格没内容"，不是"被上面盖住"。
    """
    cells = [["Region", "Q1", "Q2"], ["East", "", "12"], ["", "13", "14"]]
    path = r300_write_pdf([r300_draw_table(60, 700, cells, open_h=((1, 0),))], tmp_path / "r300_rs.pdf")

    block = tables.extract_pdf_tables(path).blocks[0]

    assert block.spans == 1
    assert block.header == ("Region East", "Q1", "Q2")
    assert block.rows == (("Region East", "", "12"), ("", "13", "14"))
    assert all("\n" not in cell for row in (block.header,) + block.rows for cell in row)


def test_docx_merge_measured_behaviour(tmp_path):
    """实测：python-docx 反过来 —— 横竖合并都把同一格的文字重复交回每个被覆盖的位置。

    所以同一个值在同一行里出现两次（横合并）或相邻两行同列各一次（竖合并）。本模块沿用
    "每个位置都带盖住它的值"这一条口径，与 PDF 侧对齐，并把合并处数写进锚。
    """
    horizontal = r300_write_docx(
        tmp_path / "r300_h.docx",
        [("t", [["大区", "营收", "同比"], ["华南", "900", "-3%"]], [(1, 1, 1, 2)])],
    )
    vertical = r300_write_docx(
        tmp_path / "r300_v.docx",
        [("t", [["Region", "Q1"], ["East", "11"]], [(0, 0, 1, 0)])],
    )

    left = tables.extract_docx_tables(horizontal).blocks[0]
    right = tables.extract_docx_tables(vertical).blocks[0]

    assert left.spans == 1 and left.rows == (("华南", "900 -3%", "900 -3%"),)
    assert right.spans == 1 and right.header == ("Region East", "Q1")
    assert right.rows == (("Region East", "11"),)


def test_a_full_width_span_becomes_a_caption_instead_of_n_copies(tmp_path):
    """整行只有一格（横幅表题）时，吐 N 份同样的值不如吐一行标题；表头取下一行。"""
    cells = [["Merged title across all columns", "", ""], ["Region", "Q1", "Q2"], ["East", "11", "12"]]
    path = r300_write_pdf(
        [r300_draw_table(60, 700, cells, open_v=((0, 1), (0, 2)))],
        tmp_path / "r300_banner.pdf",
    )

    block = tables.extract_pdf_tables(path).blocks[0]

    assert block.captions == ("Merged title across all columns",)
    assert block.header == ("Region", "Q1", "Q2")
    assert block.to_markdown().split("\n")[1] == "> Merged title across all columns"


def test_pdf_table_split_by_pagination_is_stitched_into_one_block(tmp_path):
    """跨页表实测：第 1 页最后一格贴到页脚、第 2 页开头贴到页首、列数相同 -> 一枚表一个锚。

    第 2 页 Word 会重画一遍表头，拼接时那行重复表头被丢掉（它已经在锚上面了），
    所以行数 = 两页数据行相加，一行不多一行不少。
    """
    page_one, page_two = r300_cross_pages()
    path = r300_write_pdf(
        [r300_draw_table(60, 748, page_one), r300_draw_table(60, 748, page_two)],
        tmp_path / "r300_cross.pdf",
    )

    found = tables.extract_pdf_tables(path)

    assert found.table_count == 1
    block = found.blocks[0]
    assert (block.page, block.end_page) == (1, 2)
    assert block.row_count == 34, "32 行来自第 1 页，2 行来自第 2 页，重复表头不计入"
    assert block.rows[0] == ("R1", "1", "2") and block.rows[-1] == ("R34", "34", "68")
    assert block.header == ("Region", "Q1", "Q2")
    assert found.duplicates() == []
    assert found.text.count("| R33 | 33 | 66 |") == 1


def test_pdf_two_tables_on_consecutive_pages_stay_two_blocks(tmp_path):
    """反方向的实测：第二页那张表从页面中间开始，就不许拼成一张 —— 宁可不猜。"""
    page_one, _ = r300_cross_pages()
    page_two = [["Note", "X", "Y"], ["n1", "1", "2"]]
    path = r300_write_pdf(
        [r300_draw_table(60, 748, page_one), r300_draw_table(60, 400, page_two)],
        tmp_path / "r300_two_pages.pdf",
    )

    found = tables.extract_pdf_tables(path)

    assert [block.anchor().split(ANCHOR_JOIN)[-1] for block in found.blocks] == ["表1", "表2"]
    assert [(block.page, block.end_page) for block in found.blocks] == [(1, 1), (2, 2)]


def test_merge_continuations_can_be_switched_off(tmp_path):
    """拼接是策略不是事实：关掉之后回到解析器交回的枚数，锚各指各的页。"""
    page_one, page_two = r300_cross_pages()
    path = r300_write_pdf(
        [r300_draw_table(60, 748, page_one), r300_draw_table(60, 748, page_two)],
        tmp_path / "r300_off.pdf",
    )

    split = tables.extract_pdf_tables(path, merge_continuations=False)
    stitched = tables.extract_pdf_tables(path)

    assert split.table_count == 2
    assert [(block.page, block.end_page) for block in split.blocks] == [(1, 1), (2, 2)]
    assert split.row_count == stitched.row_count, "拼不拼接只该动锚，不该动行"
    assert split.blocks[1].rows == (("R33", "33", "66"), ("R34", "34", "68"))
    assert split.blocks[1].anchor().endswith("表2")


def test_borderless_pdf_table_is_not_found_measured(tmp_path):
    """实测边界：没有框线的"表"pdfplumber 一枚都找不到（默认 lines 策略），本模块不猜。"""
    ops = "".join(
        r300_draw_text(60 + column * 100, 700 - row * 20, value)
        for row, line in enumerate([["Region", "Q1"], ["East", "11"]])
        for column, value in enumerate(line)
    )
    path = r300_write_pdf([ops], tmp_path / "r300_borderless.pdf")

    found = tables.extract_pdf_tables(path)

    assert found.table_count == 0
    assert found.truncated == ""
    assert loader.load_pdf(str(path)).splitlines()[-1] == "East 11", "正文那半照旧在，没被吞掉"


def test_a_cell_that_overflows_its_column_is_split_measured(tmp_path):
    """实测边界：文字越过本列边线时，pdfplumber 按列把它切开塞进相邻列。

    这不是本模块能修的事实（它拿到的已经是切完的格子），但正文那一半仍然带着整句，
    所以信息没有离开索引 —— 这里钉的就是这两件事同时成立。
    """
    long = "variance analysis narrative"
    cells = [["Region", "Note", "Q1"], ["East", long + " " + long, "11"]]
    path = r300_write_pdf([r300_draw_table(60, 700, cells)], tmp_path / "r300_over.pdf")

    found = tables.extract_pdf_tables(path)
    text = tables.extract_pdf_text(path)

    assert found.table_count == 1
    assert found.blocks[0].rows == (
        ("East", "variance analysis narr", "a1t1ive variance analysis"),
    ), "实测：越过列边线的文字被按列切碎，还与相邻列的字符互相穿插"
    assert all(len(cell) < len(long) for cell in found.blocks[0].rows[0]), "长格被按列界切短了"
    assert tables.pdf_prose_without_tables(path) == "narrative"
    assert long not in text, "整句回不来 —— 这是解析器的事实，本模块不许假装修好了它"
    assert text.count("variance analysis narr") == 1, "切碎之后也只吐一次，不去重的接线会吐两次"


# ------------------------------------------------------------------ ③ 通道口径：走既有分块，不另起一套


@pytest.fixture(scope="module")
def EVIDENCE_LIMIT() -> str:
    """引用条的摘录窗口，现取自 app/agents/evidence.py，不抄第二份。"""
    source = EVIDENCE_SOURCE.read_text(encoding="utf-8")
    return re.search(r"_EXCERPT_LIMIT = (\d+)", source).group(1)


def test_budget_constants_match_the_only_splitter_in_the_repo():
    """判据③: 装箱预算是上游那把尺，本模块只许对齐它 —— 上游改了这里不跟着改就红。"""
    source = SPLITTER_SOURCE.read_text(encoding="utf-8")
    sizes = [int(value) for value in re.findall(r"chunk_size=(\d+)", source)]
    overlaps = [int(value) for value in re.findall(r"chunk_overlap=(\d+)", source)]

    assert sizes and set(sizes) == {CHUNK_SIZE_CHARS}, f"分块 chunk_size={sizes} 与本模块 {CHUNK_SIZE_CHARS} 不同尺"
    assert overlaps and set(overlaps) == {CHUNK_OVERLAP_CHARS}
    assert SEGMENT_CHAR_BUDGET == CHUNK_SIZE_CHARS - CHUNK_OVERLAP_CHARS - len(BLOCK_SEPARATOR)
    assert SEGMENT_CHAR_BUDGET == 448


def test_tables_module_invents_no_second_chunker():
    """判据③: 本模块不许自带分块器，也不许新引 Chroma（向量库定案见 AGENTS.md）。"""
    source = MODULE_SOURCE.read_text(encoding="utf-8")

    assert "RecursiveCharacterTextSplitter" not in source
    assert "split_text(" not in source
    assert "TextSplitter" not in source
    assert "langchain" not in source
    assert "chroma" not in source.lower()


def test_tables_module_does_not_import_the_loader_at_import_time():
    """接线契约要求 loader 反过来 import 本模块，顶层再 import 回去就是一个环。"""
    source = MODULE_SOURCE.read_text(encoding="utf-8")
    head = source.split("def _finish(")[0]

    assert "from app.rag.loader import" not in head
    assert "from app.rag.loader import" in source.split("def _finish(")[1], "净化闸门仍然只能是 R130 那一枚"


#: 锚行的形状："文件名 · 第N页 · 表M"，或 docx 的"文件名 · 表M · 前文「…」"。
ANCHOR_MARK = ANCHOR_JOIN + "表"


@pytest.mark.parametrize("case", ["corpus", "stitched", "docx", "merged", "nested"])
def test_every_table_row_survives_the_real_splitter_exactly_once(case, tmp_path):
    """判据③/⑤: 拿真分块器切一遍表格那一半，四条同时成立才算走了既有通道。

    1 每一块都不超上游那把 500 字的尺；
    2 每一块第一行就是锚（段被切开、锚掉在后半截上，正是本单要防的形状）；
    3 每一块里的表格行都是完整一行，没有从中间断掉的；
    4 每一段一枚锚；段的骨架是"锚 / 可选表题 / 表头 / 分隔行 / 数据行"，
      收回来的数据行与源表逐字同序同数 —— 表头才按段数重复，数据行一条不许多。
    """
    document = _r300_document(case, tmp_path)
    rendered = document.table_text
    blocks = document.tables.blocks
    assert rendered and blocks

    segments = rendered.split(BLOCK_SEPARATOR)
    for segment in segments:
        assert len(segment) <= SEGMENT_CHAR_BUDGET, f"段超预算:{len(segment)}"
    assert len(r300_anchors(rendered)) == len(segments), "一枚段一枚锚，锚既不缺席也不野涨"

    chunks = r300_splitter().split_text(rendered)

    assert chunks
    for chunk in chunks:
        assert len(chunk) <= CHUNK_SIZE_CHARS, f"分块超尺：{len(chunk)}"
        lines = chunk.split("\n")
        assert ANCHOR_MARK in lines[0], f"这一块没有以锚开头：{lines[0]!r}"
        for line in lines:
            if line.startswith("|") and not line.startswith("|-"):
                assert line.endswith(" |"), f"表格行被从中间切断了：{line!r}"

    # 4) 段的骨架只能是：锚 / 可选表题 / 表头 / 分隔行 / 数据行；把数据行逐条收回来比对。
    emitted: list[str] = []
    for segment in segments:
        lines = segment.split("\n")
        body = lines[1:]
        if body and body[0].startswith("> "):
            body = body[1:]
        pipes = [line for line in body if line.startswith("|")]
        if pipes:
            assert pipes[0].startswith("| ") and pipes[1].startswith("|-"), f"段首不是表头与分隔行：{pipes[:2]}"
            assert sum(1 for line in pipes if line.startswith("|-")) == 1, "一枚表一枚分隔行"
            emitted += pipes[2:]
        else:
            assert all(line.startswith("- ") for line in body if line.strip()), "无表头的段只能由字段式行组成"

    source_rows = [line for block in blocks for line in block.row_lines if line.startswith("| ")]
    if case != "nested":
        assert source_rows
    assert emitted == source_rows, "数据行必须逐字、按源顺序、各出现一次"
    for line in set(source_rows):
        assert rendered.count(line) == 1 or line == blocks[0].header_line, line


def test_the_498_margin_is_measured_not_decorative():
    """预算为什么留 52 字余量：同一把真尺下，498 字的段每块都有锚，501 字就开始丢锚。"""
    splitter = r300_splitter()

    def anchored_ratio(size: int) -> tuple[float, int]:
        segments = [("A%d-ANCHOR" % index + "\n| c |").ljust(size, "x") for index in range(6)]
        assert {len(segment) for segment in segments} == {size}
        chunks = [chunk for chunk in splitter.split_text(BLOCK_SEPARATOR.join(segments)) if chunk.strip()]
        return sum(1 for chunk in chunks if "ANCHOR" in chunk) / len(chunks), len(chunks)

    whole, _ = anchored_ratio(498)
    kept, pieces = anchored_ratio(501)
    assert whole == 1.0, "498 字的段本应一块一锚"
    assert kept < 1.0, "抬到尺子上限还不丢锚，这条钉子就失效了（%d 块，仅 %d 块带锚）" % (pieces, round(kept * pieces))


def test_a_row_wider_than_the_budget_degrades_to_named_fields(tmp_path):
    """一条放不下的行退成"一列一行"，每行仍然自报列名，且拼回去与原文逐字相等。"""
    long = "很长的经营说明文字" * 60
    path = r300_write_docx(tmp_path / "r300_wide.docx", [("t", [["科目", "说明"], ["差旅", long]], [])])

    document = tables.extract_document(path, prose="说明正文")
    text = document.table_text

    lines = [line for line in text.split("\n") if line.startswith("- ")]
    assert lines, "超宽行没有退成字段式"
    assert all(len(line) <= SEGMENT_CHAR_BUDGET for line in lines)
    assert all(": " in line for line in lines), "每行都得带列名，不许出现找不到家的裸文字"
    rebuilt = "".join(line.split(": ", 1)[1] for line in lines if line.startswith("- 说明"))
    assert rebuilt == long, "字段式可以难看，不可以丢字"


# ------------------------------------------------------------------ ④ 现取实测的性能账


def test_measured_cost_on_the_versioned_corpus(capsys):
    """判据④: 每文件表格数、页数、耗时都是现取的，上限由它定，不是拍的。"""
    started = time.perf_counter()
    found = tables.extract_pdf_tables(CORPUS_PDF)
    wall = time.perf_counter() - started

    assert (found.pages, found.table_count, found.row_count) == (CORPUS_PAGES, CORPUS_TABLES, CORPUS_ROWS)
    assert found.truncated == ""
    assert found.pages_scanned == CORPUS_PAGES
    assert wall < 20.0, f"28 页表格扫描实测 {wall:.2f} s，超出预期量级就先重估上限"
    with capsys.disabled():
        print(
            "\nR300 实测 %s: pages=%d tables=%d rows=%d table_chars=%d segments=%d 表扫描 %.3fs 全程 %.3fs"
            % (
                found.filename,
                found.pages,
                found.table_count,
                found.row_count,
                found.char_count,
                sum(len(block.parts()) for block in found.blocks),
                found.elapsed_s,
                wall,
            )
        )


def test_ceilings_truncate_out_loud():
    """三道上限都必须能真的收口，并在 stats 里留下是哪一个收的。"""
    page_bounded = tables.extract_pdf_tables(CORPUS_PDF, max_pages=3)
    char_bounded = tables.extract_pdf_tables(CORPUS_PDF, max_chars=400)
    time_bounded = tables.extract_pdf_tables(CORPUS_PDF, time_budget_s=0.0)

    assert page_bounded.truncated.startswith("pages:") and page_bounded.pages_scanned == 3
    assert char_bounded.truncated.startswith("chars:") and 0 < char_bounded.table_count < CORPUS_TABLES
    assert time_bounded.truncated.startswith("time:")
    assert "truncated" in page_bounded.stats()


def test_a_word_document_stops_at_its_own_ceiling(tmp_path):
    """.docx 没有页可数，它的上限是表的枚数与字数，收口时同样要留字据。"""
    blocks = []
    for index in range(4):
        blocks.append(("p", f"第{index}节。"))
        blocks.append(("t", [["科目", "金额"], ["差旅", str(index)]], []))
    path = r300_write_docx(tmp_path / "r300_many.docx", blocks)

    bounded = tables.extract_docx_tables(path, max_tables=2)

    assert bounded.table_count == 2
    assert bounded.truncated.startswith("tables:")
    assert bounded.stats()["truncated"] == bounded.truncated
    assert tables.extract_docx_tables(path).truncated == ""


def test_the_page_ceiling_is_ahead_of_the_measured_corpus():
    """上限必须比已知最坏的存量文件宽松，否则它天天在切真数据。"""
    from app.rag.tables import MAX_TABLE_CHARS, MAX_TABLE_PAGES

    found = tables.extract_pdf_tables(CORPUS_PDF)

    assert MAX_TABLE_PAGES > found.pages
    assert MAX_TABLE_CHARS > found.char_count


# ------------------------------------------------------------------ ⑤⑥ 反证与"表不等于正文"


def test_table_only_document_has_text_and_no_prose(tmp_path):
    """判据⑥: 只有表格的文档，抽取结果不能是空串；但表不能算成"有正文"的凭据。"""
    pdf = r300_write_pdf(
        [r300_draw_table(60, 700, [["大区", "营收"], ["华东", "1200"]])], tmp_path / "r300_only.pdf"
    )
    docx = r300_write_docx(tmp_path / "r300_only.docx", [("t", [["科目", "金额"], ["差旅", "12"]], [])])

    for path in (pdf, docx):
        document = tables.extract_document(path)

        assert document.text.strip(), f"{path.name}: 只有表格的文档抽出了空串"
        assert document.has_prose is False, f"{path.name}: 表被当成了正文"
        assert document.prose.strip() == ""
        assert document.table_count == 1
        assert document.text.splitlines()[0].startswith(path.name)


def test_load_docx_no_longer_drops_word_tables(tmp_path):
    """R300 当年记的是病灶快照（paragraph-only）；R304 接上表格腿之后这一条必须反过来。

    改口由总控落笔（随 R304 并树）。这枚件的使命从来不是「表被丢掉」那句话，而是
    「表不许静默消失」，所以快照过期不等于放宽——断言反而更硬：走真入口 loader.load_docx，
    单元格里的字必须在、必须是以来源锚开头的表格段、而且只能出现一次。
    """
    path = r300_write_docx(tmp_path / "r300_dropped.docx", [("t", [["大区", "营收"], ["华东", "1200"]], [])])

    text = loader.load_docx(str(path))

    assert "华东" in text, "Word 表格又被静默丢掉了"
    assert "| 大区 | 营收 |" in text, "回来的不是表格段，是没有锚的裸文本"
    assert text.splitlines()[0].startswith(path.name), "表格段首行没有来源锚"
    assert text.count("华东") == 1, "同一张表吐了两次"


def test_pdf_text_does_not_repeat_the_table(tmp_path):
    """判据⑤: 同一张表吐两次就是红 —— pypdf 的正文里本来就有这些字，接线必须用扣掉表框那一半。"""
    prose = r300_draw_text(60, 770, "Prose alpha line.")
    cells = [["Region", "Q1", "Q2"], ["East", "11", "12"]]
    path = r300_write_pdf([prose + r300_draw_table(60, 700, cells)], tmp_path / "r300_dup.pdf")

    text = tables.extract_pdf_text(path)

    assert "Region Q1 Q2" not in text, "表又以裸文本回到正文里了：去重那一半失效"
    assert text.count("| Region | Q1 | Q2 |") == 1
    assert "Prose alpha line." in text
    # 对照组必须不经 load_pdf：接线之后 pdf_prose_via_loader 交回的就是接线版本身，
    # 拿它当「今天 pypdf 那一版」是假对照。这里直接调 pypdf，量的仍是那份未接线的正文。
    from pypdf import PdfReader

    legacy = "\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages)
    assert legacy.count("East 11 12") == 1, "对照失效：pypdf 那一版本来就带着表行"


def test_docx_prose_and_tables_do_not_overlap(tmp_path):
    """判据⑤: docx 侧结构上就不可能重 —— 段落通道从来不含单元格，拼起来正好是一次。"""
    path = r300_write_docx(
        tmp_path / "r300_part.docx",
        [("p", "表前的说明。"), ("t", [["大区", "营收"], ["华东", "1200"]], []), ("p", "表后的说明。")],
    )
    prose = r300_prose_of(path)

    document = tables.extract_document(path, prose=prose)

    assert prose == "表前的说明。\n表后的说明。"
    grid = [document.tables.blocks[0].header, *document.tables.blocks[0].rows]
    assert all(cell not in prose for row in grid for cell in row)
    assert document.text == prose + BLOCK_SEPARATOR + document.table_text


def test_duplicate_detector_is_not_decorative(tmp_path):
    """判据⑤: "同表重复"这把反证得自己会红 —— 喂两枚同指纹的表，duplicates() 必须点名第二枚。"""
    block = tables.TableBlock(
        filename="r300_dup.pdf", ordinal="1", header=("A", "B"), rows=(("1", "2"),), source="pdf", page=1
    )
    clean = tables.TableSet(filename="r300_dup.pdf", source="pdf", blocks=(block,))
    doubled = tables.TableSet(filename="r300_dup.pdf", source="pdf", blocks=(block, block))

    assert clean.duplicates() == []
    assert doubled.duplicates() == [block.anchor()]
    assert tables.extract_pdf_tables(CORPUS_PDF).duplicates() == []


def test_the_two_wired_functions_carry_every_row_once(tmp_path):
    """判据⑤: 波次二接的就是 extract_pdf_text / extract_docx_text 这两枚函数。

    入口若被退回"只发正文"，光靠流水线断言只有 1~3 枚会红，所以这里单独把入口钉住：
    入口串必须与流水线串逐字相等、必须带来源锚、每一表行必须出现且仅出现一次。
    """
    pdf = r300_write_pdf(
        [
            r300_draw_text(60, 770, "Prose beta line.")
            + r300_draw_table(60, 700, [["Region", "Q1"], ["East", "11"]])
        ],
        tmp_path / "r300_entry.pdf",
    )
    docx = r300_write_docx(
        tmp_path / "r300_entry.docx",
        [("p", "入表前说明。"), ("t", [["大区", "营收"], ["华东", "1200"]], [])],
    )

    cases = [
        (
            pdf,
            tables.extract_pdf_text(pdf),
            tables.extract_document(pdf).text,
            ["| Region | Q1 |", "| East | 11 |"],
            "Prose beta line.",
        ),
        (
            docx,
            tables.extract_docx_text(docx, r300_prose_of(docx)),
            tables.extract_document(docx, prose=r300_prose_of(docx)).text,
            ["| 大区 | 营收 |", "| 华东 | 1200 |"],
            "入表前说明。",
        ),
    ]
    for path, entry, pipeline, rows, prose in cases:
        assert entry == pipeline, f"{path.name}: 接线用的函数与流水线不是同一串"
        assert prose in entry, f"{path.name}: 入口把正文那一半弄丢了"
        assert r300_anchors(entry), f"{path.name}: 入口交回的串里没有来源锚"
        for row in rows:
            assert entry.count(row) == 1, f"{path.name}: {row!r} 出现 {entry.count(row)} 次"

def test_cells_leave_no_nul_character():
    """R130 那道闸门对本模块的输出同样成立：PG text 列容不下的字符不能进渲染结果。"""
    block = tables.TableBlock(
        filename="r300_nul.pdf",
        ordinal="1",
        header=("A" + chr(0), "B"),
        rows=(("1", chr(0) + "2"),),
        source="pdf",
        page=1,
    )

    text = tables.render_tables([block])

    assert chr(0) not in text
    assert text == tables._finish(text)


def test_a_table_nested_inside_a_cell_is_not_dropped(tmp_path):
    """实测边界：doc.tables 只列顶层，单元格里的子表两版 API 都不会交回来 —— 不递归就是丢数据。"""
    from docx import Document

    path = tmp_path / "r300_nested.docx"
    document = Document()
    outer = document.add_table(rows=1, cols=2)
    outer.style = "Table Grid"
    outer.cell(0, 0).text = "outer-a"
    outer.cell(0, 1).text = "outer-b"
    inner = outer.cell(0, 1).add_table(rows=1, cols=2)
    inner.style = "Table Grid"
    inner.cell(0, 0).text = "NESTED-1"
    inner.cell(0, 1).text = "NESTED-2"
    document.save(str(path))

    found = tables.extract_docx_tables(path)

    assert [block.ordinal for block in found.blocks] == ["1", "1.1"]
    assert found.blocks[1].header == ("NESTED-1", "NESTED-2")
    assert "NESTED-1" in found.text
    assert found.text.count("outer-b") == 1, "父格文字与子表各算一次，不互相覆盖"


def test_unsupported_format_is_refused(tmp_path):
    """分派口径与 load_document 一致：不支持的扩展名要出声，不要交回空表当成"没有表"。"""
    path = tmp_path / "r300_notes.txt"
    path.write_text("纯文本没有表格可言", encoding="utf-8")

    with pytest.raises(ValueError) as refused:
        tables.extract_tables(path)

    assert "不支持该格式" in str(refused.value)


def test_a_pdf_without_tables_keeps_todays_text_byte_for_byte():
    """存量账：0 表的 PDF 走 pypdf 那一版，接线之后老索引不会因为本模块重算 hash。"""
    corpus = REPO_ROOT / "documents" / "AI-Agent学习路线图.pdf"

    found = tables.extract_pdf_tables(corpus)
    document = tables.extract_document(corpus)

    assert found.table_count == 0
    assert document.text == loader.load_pdf(str(corpus))


# ------------------------------------------------------------------ 用例间的公共料


def _r300_document(case: str, tmp_path: Path):
    """四种形状各来一份：真语料、跨页拼接、Word（含合并与前文）、纯竖合并。"""
    if case == "corpus":
        return tables.extract_document(CORPUS_PDF)
    if case == "stitched":
        page_one, page_two = r300_cross_pages()
        path = r300_write_pdf(
            [r300_draw_table(60, 748, page_one), r300_draw_table(60, 748, page_two)],
            tmp_path / "r300_stitched.pdf",
        )
        return tables.extract_document(path)
    if case == "nested":
        # A nested table with one row has no data rows at all, so it takes the header-only
        # branch of to_markdown -- which still has to respect the ruler.
        from docx import Document

        path = tmp_path / "r300_nested_channel.docx"
        document = Document()
        outer = document.add_table(rows=1, cols=2)
        outer.style = "Table Grid"
        outer.cell(0, 0).text = "outer-a"
        outer.cell(0, 1).text = "outer-b"
        inner = outer.cell(0, 1).add_table(rows=1, cols=24)
        inner.style = "Table Grid"
        for column in range(24):
            inner.cell(0, column).text = "列名%s" % ("很长的表头文字" * 3) + str(column)
        document.save(str(path))
        return tables.extract_document(path, prose="")
    if case == "docx":
        path = r300_write_docx(
            tmp_path / "r300_split.docx",
            [
                ("p", "分部门费用明细如下。"),
                ("t", [["科目", "金额", "同比"], ["差旅", "120", "+3%"], ["招待", "90", "-3%"]], [(2, 1, 2, 2)]),
            ],
        )
        return tables.extract_document(path, prose=r300_prose_of(path))
    cells = [["Region", "Q1", "Q2"], ["East", "", "12"], ["", "13", "14"]]
    path = r300_write_pdf([r300_draw_table(60, 700, cells, open_h=((1, 0),))], tmp_path / "r300_merged.pdf")
    return tables.extract_document(path)


# ============================================== 现场 B（R364）：手抄指纹换成派生（docstring 那句话的债）
#
# 本文件 docstring 承诺「反证跑完即还原，并核对源文件字节不变」。那句话从前抄着一串 sha256，
# 而它不是断言 —— 58111c9（R331）合法改过 app/rag/tables.py 之后，它继续绿着讲假话。下面四枚钉
# 把这句承诺变成真断言：期望值从**记名锚点提交**（TABLES_ANCHOR_SHA，与 R304/R352 同一条锚）现算，
# 比较一律落在 **git blob 层（LF）**，盘上那份先归一。
#
# 三枚自校钉一枚都不许省，因为它们各堵一种"派生被写过期"的形状：锚点不在树上（读一枚愿望）、
# 锚点没改过这枚文件（指名指错人）、锚点交出的字节与父提交相同（派生退化成同义反复）。
# 第四枚（最后一枚）用一枚**真冒充者**当场演一遍：内容逐字节相同而没动过这枚文件的提交，三枚钉
# 必须把它拒了 —— 它自己绿，才说明前三枚在量东西。

#: 派生钉量的那枚文件，用正相对仓根的名字写（与 docstring 里那句「源文件」同一枚，见最后一枚钉）。
TABLES_REL = "app/rag/tables.py"

#: 找冒充者时沿 HEAD 祖先链往上扫的枚数（今天的树里第一枚 HEAD 就够；留余量是给合并提交）。
IMPOSTOR_SCAN_LIMIT = 40


def _commit_touches_tables(rev):
    """这枚提交的改动清单里有没有 TABLES_REL（`--name-only`，与工作树行尾无关）。"""
    listed = {
        line.strip().replace("\\", "/")
        for line in r304_git("show", "--pretty=format:", "--name-only", rev).splitlines()
        if line.strip()
    }
    return TABLES_REL in listed


def _anchor_disqualified_reasons(rev):
    """三枚自校钉，交回**不合格理由**名单（空名单 = 三枚全过）。

    做成名单而不是三条 assert：冒充者那枚反证钉要能指名道姓说清是哪一枚咬住了它，
    否则"红了"和"因为对的原因红了"还是两回事。
    """
    reasons = []
    ancestor = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "merge-base", "--is-ancestor", rev, "HEAD"],
        capture_output=True,
        cwd=str(REPO_ROOT),
    )
    if ancestor.returncode != 0:
        reasons.append("%s 不在 HEAD 的祖先链上：这枚提交没进树，读它等于读一枚愿望" % rev[:7])
    if not _commit_touches_tables(rev):
        reasons.append("%s 的提交清单里没有 %s：它不是那枚「有意改动」，指名指错了人" % (rev[:7], TABLES_REL))
    if r304_tables_digest_at(rev) == r304_tables_digest_at(rev + "^"):
        reasons.append("%s 交出的 %s 与它的父提交相同：这枚提交没动过它，不配当锚点" % (rev[:7], TABLES_REL))
    return reasons


def _identical_impostor_rev():
    """现算一枚冒充者：在祖先链上、与锚点**逐字节相同**、但自己没改过这枚文件的提交。"""
    anchor = r304_tables_digest_at(TABLES_ANCHOR_SHA)
    revs = r304_git("rev-list", "--max-count=%d" % IMPOSTOR_SCAN_LIMIT, "HEAD").split()
    for rev in revs:
        if r304_tables_digest_at(rev) == anchor and not _commit_touches_tables(rev):
            return rev
    raise AssertionError(
        "沿 HEAD 往上 %d 枚里找不到一枚「与锚点 %s 同字节而没动过 %s」的提交："
        "要么锚点已经落后于树（先去看 test_the_tables_module_is_still_the_bytes_the_anchor_shipped），"
        "要么扫描余量要给大一点 —— 这枚反证钉不许改成恒真。" % (IMPOSTOR_SCAN_LIMIT, TABLES_ANCHOR_SHA, TABLES_REL)
    )


def test_the_restored_bytes_are_the_ones_the_named_anchor_shipped():
    """docstring 那句「跑完即还原」的正腿：盘上那份归一到 blob 层以后，等于锚点提交现算的那份。"""
    assert re.fullmatch(r"[0-9a-f]{7,40}", TABLES_ANCHOR_SHA), "锚点得是一枚提交名，不是一串指纹：%r" % TABLES_ANCHOR_SHA
    anchor_blob = r304_git_blob(TABLES_ANCHOR_SHA)
    assert b"\r" not in anchor_blob, "git blob 层应当恒 LF：层口径变了，下面这枚比较不再有意义"
    assert r304_tables_digest_on_disk() == r304_tables_digest_at(TABLES_ANCHOR_SHA), (
        "app/rag/tables.py 与锚点提交 %s 不等（都按 blob 层现算）。两条路二选一："
        "① 改动是有意的 ⇒ 把 TABLES_ANCHOR_SHA 往前挪到你那枚提交并写清是谁改的；"
        "② 改动未经授权 ⇒ 先取证再还原。🔴 不许在本文件重录一枚今天的 hex，那只是把 R364 治过的雷再埋一遍。"
        % TABLES_ANCHOR_SHA
    )


def test_the_anchor_of_the_restoration_claim_passes_its_three_self_check_nails():
    """三枚自校钉落在真锚点上：一枚都不许省，也不许有事后拿 `>=` 糊过去。"""
    reasons = _anchor_disqualified_reasons(TABLES_ANCHOR_SHA)
    assert not reasons, "锚点 %s 不自校：%s" % (TABLES_ANCHOR_SHA, " / ".join(reasons))


def test_a_commit_with_identical_bytes_does_not_qualify_as_the_anchor():
    """反证钉（常驻）：拿"内容恰好相同"的另一枚提交冒充锚点，三枚自校钉必须当场拒了它。

    这一枚自己绿，才证明上面那枚不是同义反复 —— 派生最省事的糊法是随便指一枚同字节的提交，
    字节比对照样绿，而锚点已经不再读任何东西。
    """
    impostor = _identical_impostor_rev()
    assert r304_tables_digest_at(impostor) == r304_tables_digest_at(TABLES_ANCHOR_SHA), (
        "%s 与锚点不同字节：它不是「内容恰好相同的冒充者」，这枚反证的前提没了" % impostor[:7]
    )
    reasons = _anchor_disqualified_reasons(impostor)
    assert reasons, "冒充者 %s 三枚自校钉全过：那三枚钉量不到任何东西了" % impostor[:7]
    assert " %s " % TABLES_REL in " ".join(reasons) or any(TABLES_REL in reason for reason in reasons), (
        "拒它的理由没落在「这枚提交没改过这枚文件」上，红得不是地方：%s" % reasons
    )


def test_the_derived_nail_measures_the_file_the_prose_names():
    """派生钉量的文件 == docstring 里那句「源文件」== 本件一直在测的那枚模块 == R304 量的那枚。

    防的是"钉与账对不上"：两枚件共用一条锚，就得共用同一枚靶子，否则锚点推进时只有一枚件会红。
    """
    assert MODULE_SOURCE == REPO_ROOT / TABLES_REL, (
        "MODULE_SOURCE（%s）与派生钉量的 %s 不是同一枚文件" % (MODULE_SOURCE, TABLES_REL)
    )
    assert TABLES_REL == TABLES_BLOB_PATH, "两枚件量的不是同一枚文件：r300=%s / r304=%s" % (TABLES_REL, TABLES_BLOB_PATH)
    assert (REPO_ROOT / TABLES_REL).exists(), TABLES_REL
