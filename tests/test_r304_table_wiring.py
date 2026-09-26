"""R304 · 把 R300 的表格模块接进 app/rag/loader.py 的上传路径。

判据原文在派工单 R304，本文件逐条对应：
① 带表文件经 loader.load_document 交回的正文里有表格段 -> test_the_wired_pdf_exit_*、
   test_a_word_table_arrives_*、test_the_loader_string_is_the_string_*；
② 表不算「有正文」，也不算 no_text_content -> test_a_table_only_document_*（两枚）；
③ 每个 load_* 出口照旧过同一把尺 -> test_the_new_exits_pass_the_same_ruler（R130 那枚
   test_every_loader_exit_calls_the_same_ruler 由本单原样跑绿，不在这里复刻）；
④ 与 R298 的逐页来源账不打架 -> test_the_page_source_ledger_survives_*、
   test_a_scanned_page_and_a_bordered_table_*、test_the_scanned_table_boundary_*；
⑤ 预算触顶不许静默 -> test_a_bounded_walk_reports_*、test_the_docx_ceiling_*、
   test_every_truncation_kind_*；
⑦ 零新增依赖、tables.py 一个字节都不许改 -> test_no_new_dependency_*、
   test_the_tables_module_is_still_*。

fixture 全部由本文件现造（PDF 是手写最小合法字节串，DOCX 由 python-docx 生成），仓库里不
因此多出任何二进制；扫描页那一枚复用 tests/fixtures/r298_scanned_pages.pdf（只读）。
全程离线：不连库、不起服务、不打模型（OCR 引擎由调用方注入桩件）。
"""
from __future__ import annotations

import contextlib
import hashlib
import inspect
import io
import logging
import re
from pathlib import Path

import pytest

from app.documents import index_policy
from app.rag import loader, tables
from app.rag.tables import ANCHOR_JOIN, BLOCK_SEPARATOR

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
CORPUS_PDF = REPO_ROOT / "documents" / "refactor_guide.pdf"
TABLELESS_PDF = REPO_ROOT / "documents" / "AI-Agent学习路线图.pdf"
SCANNED_PDF = FIXTURES / "r298_scanned_pages.pdf"

#: 流水线本体，测试自己包一层上限时用这一枚（monkeypatch 叠 monkeypatch 会套住上一枚）。
R304_EXTRACT_DOCUMENT = tables.extract_document

#: R300 交工时的字节指纹（判据⑦：本单一律不许碰它）。
TABLES_SHA256 = "7acaa33c0568e8eec13c992823a55dbf134d3f7f870ecacc6c73ff011b4266dd"
NUL = chr(0)
PAGE_HEIGHT = 792.0
ROW_HEIGHT = 22.0
COLUMN_WIDTH = 100.0


# ------------------------------------------------------------------ 造件（与 R300 同一手法）


@contextlib.contextmanager
def _quiet_parser_warnings():
    pypdf_logger = logging.getLogger("pypdf")
    previous = pypdf_logger.level
    pypdf_logger.setLevel(logging.ERROR)
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            yield
    finally:
        pypdf_logger.setLevel(previous)


def r304_write_pdf(pages: list[str], path: Path) -> Path:
    """手写一份语法 plainly 合法的 PDF：一页一段内容流，不压缩。

    reportlab 不是本项目依赖（判据⑦：零新增依赖），所以字节是自己拼的。/Catalog 必须在，
    否则 pypdf 读不出来（pdfminer 能忍，两把尺都要能用才行）。
    """
    counter = {"next": 1}

    def new() -> int:
        value = counter["next"]
        counter["next"] += 1
        return value

    objs: dict[int, bytes] = {}
    font = new()
    catalog = new()
    pages_id = new()
    page_ids = [new() for _ in pages]
    stream_ids = [new() for _ in pages]
    objs[font] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    objs[catalog] = ("<< /Type /Catalog /Pages %d 0 R >>" % pages_id).encode("ascii")
    objs[pages_id] = ("<< /Type /Pages /Kids [%s] /Count %d >>" % (
        " ".join("%d 0 R" % pid for pid in page_ids), len(pages))).encode("ascii")
    for index, page_id in enumerate(page_ids):
        objs[page_id] = (
            "<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] /Resources << /Font << %s >> >>"
            " /Contents %d 0 R >>" % (pages_id, "/F1 %d 0 R" % font, stream_ids[index])
        ).encode("ascii")
    for index, stream_id in enumerate(stream_ids):
        payload = pages[index].encode("ascii")
        objs[stream_id] = (
            "<< /Length %d >>\nstream\n" % len(payload)
        ).encode("ascii") + payload + b"endstream"

    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for number in sorted(objs):
        offsets[number] = len(out)
        out += b"%d 0 obj\n" % number + objs[number] + b"\nendobj\n"
    start = len(out)
    xref = b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for number in range(1, len(objs) + 1):
        xref += b"%010d 00000 n \n" % offsets[number]
    out += xref + b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objs) + 1, catalog, start,
    )
    path.write_bytes(bytes(out))
    return path


def r304_draw_text(x: float, y: float, value: str) -> str:
    return "BT /F1 10 Tf %.1f %.1f Td (%s) Tj ET\n" % (x, y, value)


def r304_draw_table(x0: float, y0: float, cells: list[list[str]]) -> str:
    rows = len(cells)
    cols = max(len(row) for row in cells)
    xs = [x0 + index * COLUMN_WIDTH for index in range(cols + 1)]
    ys = [y0 - index * ROW_HEIGHT for index in range(rows + 1)]
    ops = []
    for index, y in enumerate(ys):
        for band in range(cols):
            ops.append("%.1f %.1f m %.1f %.1f l S\n" % (xs[band], y, xs[band + 1], y))
    for index, x in enumerate(xs):
        for band in range(rows):
            ops.append("%.1f %.1f m %.1f %.1f l S\n" % (x, ys[band], x, ys[band + 1]))
    for row_index, row in enumerate(cells):
        for column_index, value in enumerate(row):
            if value:
                ops.append(r304_draw_text(xs[column_index] + 4, ys[row_index] - 15, value))
    return "".join(ops)


def r304_write_docx(path: Path, blocks: list) -> Path:
    """blocks 是 ("p", text) / ("t", rows) 两种；python-docx 现生成。"""
    from docx import Document

    document = Document()
    for kind, *rest in blocks:
        if kind == "p":
            document.add_paragraph(rest[0])
            continue
        rows = rest[0]
        table = document.add_table(rows=len(rows), cols=len(rows[0]))
        table.style = "Table Grid"
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                table.cell(row_index, column_index).text = value
    document.save(str(path))
    return path


def r304_paragraph_join(path: Path) -> str:
    """load_docx 今天那一串段落，逐字重做一份，作为「没丢东西」的对照。"""
    from docx import Document

    document = Document(str(path))
    return "\n".join(p.text for p in document.paragraphs if p.text.strip())


def r304_legacy_pdf_text(path: Path) -> str:
    """R298+R304 之前的 load_pdf：pypdf 逐页 strip，两段之间一个空行。"""
    from pypdf import PdfReader

    parts: list[str] = []
    with _quiet_parser_warnings():
        for page in PdfReader(str(path)).pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                parts.append(page_text.strip())
    return "\n\n".join(parts).strip()


class StubEngine:
    """假 OCR 引擎：与 RapidOCR 同形（callable(像素) -> (行列表, 耗时)）。"""

    def __init__(self, *rows) -> None:
        self.rows = list(rows)
        self.calls = 0

    def __call__(self, array):  # noqa: ANN001
        row = self.rows[min(self.calls, len(self.rows) - 1)] if self.rows else None
        self.calls += 1
        if row is None:
            return (None, [0.0])
        box = [[0.0, 0.0], [100.0, 0.0], [100.0, 20.0], [0.0, 20.0]]
        return ([[box, row, 0.98]], [0.0])


class LogRecorder:
    """把 loader 模块里的 logger 换成记账桩：判据⑤ 要的是「留了话」，不靠 caplog 配置。"""

    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.infos: list[str] = []

    def warning(self, message, *args, **kwargs) -> None:
        self.warnings.append(str(message))

    def info(self, message, *args, **kwargs) -> None:
        self.infos.append(str(message))

    def debug(self, message, *args, **kwargs) -> None:
        return None

    @property
    def text(self) -> str:
        return " | ".join([*self.warnings, *self.infos])


@pytest.fixture()
def loader_logs(monkeypatch) -> LogRecorder:
    recorder = LogRecorder()
    monkeypatch.setattr(loader, "logger", recorder)
    return recorder


# ------------------------------------------------------------------ 锚与行的读法


def anchor_lines(text: str, filename: str) -> list[str]:
    """段首的来源锚：以文件名开头、带分隔符、点名第几枚表。"""
    return [
        line
        for line in text.splitlines()
        if line.startswith(filename) and ANCHOR_JOIN in line and re.search(r"表\d+", line)
    ]


def rendered_lines(document) -> tuple[list[str], list[str]]:
    """(每一段都会重印的结构线, 只出现一次的数据行)。"""
    frame: list[str] = []
    data: list[str] = []
    for block in document.tables.blocks:
        frame.extend([block.anchor(), block.header_line, block.separator_line])
        data.extend(line for line in block.row_lines if line.strip())
    return frame, data


# ------------------------------------------------------------------ ① 端到端：表格段真的在正文里


def test_the_wired_pdf_exit_carries_every_table_once(capsys):
    """判据①：客户上传真语料里那枚带表的 PDF，load_document 交回的正文必须有表格段。"""
    assert CORPUS_PDF.is_file(), f"缺少真语料：{CORPUS_PDF}"

    with _quiet_parser_warnings():
        body = loader.load_document(str(CORPUS_PDF))
    document = tables.extract_document(CORPUS_PDF)
    table_text = document.tables.text
    frame, data = rendered_lines(document)

    anchors = anchor_lines(body, CORPUS_PDF.name)
    assert anchors, "正文里没有表格段：接线没有生效"
    assert len(set(anchors)) == len(anchors), "来源锚有重复"
    for line in anchors:
        assert body.count(line) == 1, f"来源锚重复了：{line!r}"
    assert len(data) == 48, f"数据行数与今天的实测账（48）不符：{len(data)}"

    # 每一表行恰好一次：正文里的次数必须与「只有表格段」时的次数逐字相等
    for line in data:
        assert body.count(line) == table_text.count(line), (
            f"这一行在正文里出现 {body.count(line)} 次、在表格段里 {table_text.count(line)} 次"
        )
    unique_rows = [line for line in data if table_text.count(line) == 1]
    assert len(unique_rows) >= 30, f"可核对的唯一表行太少：{len(unique_rows)}"
    for line in unique_rows:
        assert body.count(line) == 1

    # 表已扣出正文：段落里不许再留着表框里的任何一条渲染线
    prose_lines = [line.strip() for line in document.prose.splitlines() if line.strip()]
    assert prose_lines, "对照用：pdfplumber 那份散文不该是空的"
    leftovers = [line for line in prose_lines if line in frame or line in data]
    assert leftovers == [], f"表框里的线又回到正文里了（去重失效）：{leftovers[:3]}"

    with capsys.disabled():
        print(
            "\nR304 现取 %s: 正文 %d 字 / %d 行；表格锚 %d 行；表 %d 枚 / %d 行 / %d 字；"
            "散文 %d 字；页走 %s/%s 页"
            % (
                CORPUS_PDF.name,
                len(body),
                len(body.splitlines()),
                len(anchors),
                document.tables.table_count,
                document.tables.row_count,
                document.tables.char_count,
                len(document.prose),
                document.tables.pages_scanned,
                document.tables.pages,
            )
        )


def test_the_bordered_table_does_not_arrive_twice(tmp_path):
    """判据①：表框里的内容必须从正文里扣掉 —— 同一枚表既以裸文本又以表格段回来就是红。"""
    path = r304_write_pdf(
        [
            r304_draw_text(60, 770, "Prose alpha line.")
            + r304_draw_table(60, 700, [["Region", "Q1", "Q2"], ["East", "11", "12"]])
        ],
        tmp_path / "r304_once.pdf",
    )

    with _quiet_parser_warnings():
        body = loader.load_pdf(str(path))
        pypdf_version = r304_legacy_pdf_text(path)

    assert "East 11 12" in pypdf_version, "对照：pypdf 那一版本来就带着表框里的字"
    assert "Region Q1 Q2" not in body, "表又以裸文本回到正文里了：扣表框那一半失效"
    assert "East 11 12" not in body, "表又以裸文本回到正文里了：扣表框那一半失效"
    assert body.count("| Region | Q1 | Q2 |") == 1
    assert body.count("| East | 11 | 12 |") == 1
    assert "Prose alpha line." in body, "正文那一半被表格腿吞了"


def test_the_loader_string_is_the_string_the_module_was_pinned_to(tmp_path):
    """判据①：接线用的两枚入口函数与流水线串逐字相等（R300 钉的就是它们）。"""
    path = r304_write_pdf(
        [
            r304_draw_text(60, 770, "Prose before the grid.")
            + r304_draw_table(60, 700, [["Region", "Q1"], ["East", "11"]])
        ],
        tmp_path / "r304_entry.pdf",
    )
    docx = r304_write_docx(
        tmp_path / "r304_entry.docx",
        [("p", "表前说明。"), ("t", [["科目", "金额"], ["差旅", "12"]])],
    )

    with _quiet_parser_warnings():
        assert loader.load_pdf(str(path)) == tables.extract_pdf_text(path)
    assert loader.load_docx(str(docx)) == tables.extract_docx_text(docx, r304_paragraph_join(docx))


def test_a_word_table_arrives_through_load_document(tmp_path):
    """判据①：仓里没有真 .docx，所以现造一份带段带表的，走 load_document 全链路。"""
    path = r304_write_docx(
        tmp_path / "r304_report.docx",
        [
            ("p", "分部门费用明细如下。"),
            ("t", [["科目", "金额"], ["差旅", "1200"], ["招待", "900"]]),
            ("p", "表后的补充说明。"),
        ],
    )

    body = loader.load_document(str(path))
    prose = r304_paragraph_join(path)

    assert prose in body, "段落那一半被接线弄丢了"
    anchors = anchor_lines(body, path.name)
    assert len(anchors) == 1, f"该有一段表格、一枚锚：{anchors}"
    assert body.splitlines()[body.splitlines().index(anchors[0]) + 1] == "| 科目 | 金额 |"
    for row in ("| 差旅 | 1200 |", "| 招待 | 900 |"):
        assert body.count(row) == 1, f"{row!r} 出现 {body.count(row)} 次"
    assert body.startswith(prose), "表格段插到了正文前面"
    assert body == prose + BLOCK_SEPARATOR + tables.extract_document(path, prose=prose).table_text, (
        "正文与表格段的拼接口径变了"
    )


def test_a_tableless_pdf_is_handed_back_byte_for_byte_as_today():
    """存量账（判据①的另一半）：0 表的 PDF 逐字退回今天的 load_pdf，索引不重算 hash。"""
    assert TABLELESS_PDF.is_file()

    with _quiet_parser_warnings():
        body = loader.load_pdf(str(TABLELESS_PDF))
        legacy = loader.sanitize_text(r304_legacy_pdf_text(TABLELESS_PDF))
        exit_ = loader.extract_pdf_with_tables(str(TABLELESS_PDF))

    assert body == legacy
    assert hashlib.sha256(body.encode("utf-8")).digest() == hashlib.sha256(legacy.encode("utf-8")).digest()
    assert (exit_.tables.tables, exit_.tables.attached, exit_.tables.degraded) == (0, False, "")


# ------------------------------------------------------------------ ② 表不算「有正文」


def test_a_table_only_document_has_text_and_no_prose(tmp_path):
    """判据②：只有表的文档，正文非空、首行是锚，而 has_prose 必须是 False。"""
    pdf = r304_write_pdf(
        [r304_draw_table(60, 700, [["Region", "Revenue"], ["East", "1200"]])], tmp_path / "r304_only.pdf"
    )
    docx = r304_write_docx(tmp_path / "r304_only.docx", [("t", [["科目", "金额"], ["差旅", "12"]])])

    with _quiet_parser_warnings():
        exits = (("pdf", loader.extract_pdf_with_tables(str(pdf))),)
    exits += (("docx", loader.extract_docx_with_tables(str(docx))),)

    for (name, exit_), path in zip(exits, (pdf, docx)):
        assert exit_.text.strip(), f"{name}: 只有表的文档抽出了空串"
        assert exit_.tables.has_prose is False, f"{name}: 表被算成了有正文"
        assert exit_.has_prose is False, f"{name}: 两份账口径不一致"
        assert exit_.tables.attached is True, f"{name}: 表格通道没接上"
        assert exit_.text.splitlines()[0].startswith(path.name), f"{name}: 锚不是表格段的首行"


def test_a_table_only_document_is_not_read_as_no_text_content(tmp_path):
    """判据②：这种文档在 R49 闸门里不许被判成 no_text_content，也不许 parse_status=failed。"""
    pdf = r304_write_pdf(
        [r304_draw_table(60, 700, [["Region", "Revenue"], ["East", "1200"]])], tmp_path / "r304_gate.pdf"
    )
    docx = r304_write_docx(tmp_path / "r304_gate.docx", [("t", [["科目", "金额"], ["差旅", "12"]])])

    for path in (pdf, docx):
        with _quiet_parser_warnings():
            body = loader.load_document(str(path))
        eligibility = index_policy.evaluate_index_eligibility(body, size_bytes=path.stat().st_size)

        assert eligibility.reason != index_policy.REASON_NO_TEXT, (
            f"{path.name}: 只有表的文档被判成没有正文 —— {eligibility.metrics}"
        )
        assert eligibility.eligible is True, f"{path.name}: 被排除的码是 {eligibility.reason}"
        assert eligibility.metrics["content_chars"] > index_policy.min_content_chars()


def test_a_scan_only_pdf_is_still_no_text_content():
    """判据②的边界：没有表也没有文字的扫描页，闸门结论不许被接线放宽（R298 钉过这条）。"""
    assert SCANNED_PDF.is_file()

    with _quiet_parser_warnings():
        body = loader.load_pdf(str(SCANNED_PDF), enable_ocr=False)
    eligibility = index_policy.evaluate_index_eligibility(body, size_bytes=SCANNED_PDF.stat().st_size)

    assert body == ""
    assert eligibility.eligible is False
    assert eligibility.reason == index_policy.REASON_NO_TEXT


# ------------------------------------------------------------------ ③ 同一把尺


def test_the_new_exits_call_the_same_ruler():
    """判据③：接线的每一枚出口都过 :func:`sanitize_text`，不许为新通道开特例。"""
    missing = [
        name
        for name in (
            "load_pdf",
            "load_docx",
            "extract_pdf_with_tables",
            "extract_docx_with_tables",
            "_docx_paragraph_prose",
        )
        if "sanitize_text(" not in inspect.getsource(getattr(loader, name))
    ]

    assert missing == [], f"这些出口没过同一把尺：{missing}"


def test_a_dirty_table_string_leaves_the_wired_exit_clean(monkeypatch):
    """判据③：表格那一腿交回来的串里带 NUL，出口也必须洗掉 —— 尺不在接线这里被绕过。"""
    dirty_prose = "段落" + NUL + "继续"
    dirty_rows = (("表头" + NUL, "乙"), ("1", "2"))

    def fake_document_tables(path, **limits):
        name = Path(path).name
        source = "docx" if name.endswith(".docx") else "pdf"
        block = tables.TableBlock(
            filename=name, ordinal="1", header=dirty_rows[0], rows=dirty_rows[1:], source=source, page=1
        )
        return tables.DocumentTables(
            filename=name,
            source=source,
            prose=dirty_prose,
            tables=tables.TableSet(filename=name, source=source, blocks=(block,)),
        )

    monkeypatch.setattr(loader.table_channel, "extract_document", fake_document_tables)
    report = loader.PdfExtractionReport(
        file_path="demo.pdf",
        page_count=1,
        pages=(),
        text=dirty_prose,
        ocr_dpi=200,
        ocr_engine="stub",
        ocr_attempted=False,
        ocr_available=True,
    )
    monkeypatch.setattr(loader, "extract_pdf", lambda *args, **kwargs: report)
    monkeypatch.setattr(loader, "_docx_paragraph_prose", lambda path: dirty_prose)

    for body in (loader.load_pdf("demo.pdf"), loader.load_document("demo.pdf"), loader.load_docx("demo.docx")):
        assert NUL not in body, "带 NUL 的表格串从出口漏出去了"
        assert "段落继续" in body
        assert "| 1 | 2 |" in body


# ------------------------------------------------------------------ ④ 与 R298 的逐页来源账


def test_the_page_source_ledger_survives_the_wiring():
    """判据④：带表文件的 page source 记账仍逐页成立，表格那一腿不改写 OCR 的账。"""
    with _quiet_parser_warnings():
        plain = loader.extract_pdf(str(CORPUS_PDF))
        exit_ = loader.extract_pdf_with_tables(str(CORPUS_PDF))

    assert exit_.pdf is not None, "接线之后逐页账没了"
    assert [page.page_number for page in exit_.pdf.pages] == list(range(1, plain.page_count + 1))
    assert exit_.pdf.source_counts == plain.source_counts
    assert exit_.pdf.text == plain.text, "R298 那条正文被接线改写了"
    for wired, before in zip(exit_.pdf.pages, plain.pages):
        assert (wired.page_number, wired.source, wired.text, wired.is_scanned) == (
            before.page_number,
            before.source,
            before.text,
            before.is_scanned,
        )
    assert all(page.source == loader.PAGE_SOURCE_TEXT_LAYER for page in exit_.pdf.pages)
    assert exit_.tables.tables == 9


def r304_merge_pages(paths_pages: list[tuple[Path, int]], path: Path) -> Path:
    """把给定文件的指定页拼成一份新 PDF（pypdf 现拼，不落二进制进仓）。"""
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for source, index in paths_pages:
        with _quiet_parser_warnings():
            writer.add_page(PdfReader(str(source)).pages[index])
    with path.open("wb") as handle:
        writer.write(handle)
    return path


def test_a_scanned_page_and_a_bordered_table_share_one_document(tmp_path):
    """判据④：扫描页（靠 OCR 才有字）与带框表同处一件，两半都要在、都只一次。"""
    table_pdf = r304_write_pdf(
        [
            r304_draw_text(60, 770, "Narration above the grid.")
            + r304_draw_table(60, 700, [["Region", "Q1"], ["East", "11"]])
        ],
        tmp_path / "r304_tables_only.pdf",
    )
    merged = r304_merge_pages([(SCANNED_PDF, 0), (table_pdf, 0)], tmp_path / "r304_mixed.pdf")
    engine = StubEngine("扫描页上的那一行字")

    with _quiet_parser_warnings():
        exit_ = loader.extract_pdf_with_tables(str(merged), engine=engine)
    body = exit_.text

    assert exit_.pdf.pages[0].source == loader.PAGE_SOURCE_OCR, "第 1 页的逐页账被接线改口径了"
    assert exit_.pdf.pages[1].source == loader.PAGE_SOURCE_TEXT_LAYER
    assert body.count("扫描页上的那一行字") == 1, "OCR 回来的正文被表格腿弄丢或吐了两次"
    assert body.count("| East | 11 |") == 1
    assert anchor_lines(body, merged.name), "带表的那一页没有表格段"
    assert exit_.tables.tables == 1
    assert exit_.tables.has_prose is True


def test_the_scanned_table_boundary_is_written_down():
    """判据④：这条边界必须写在 docstring 里，不许让后来人以为扫描件里的表格也支持。"""
    docstring = inspect.getdoc(loader.extract_pdf_with_tables) or ""

    assert "扫描件里的表格" in docstring, "边界说明被删了"
    assert "不支持" in docstring
    assert "pdfplumber" in docstring or "框线" in docstring


# ------------------------------------------------------------------ ⑤ 预算触顶不许静默


def r304_three_page_pdf(tmp_path: Path) -> Path:
    return r304_write_pdf(
        [
            r304_draw_text(60, 770, "Page one narration line.")
            + r304_draw_table(60, 700, [["Region", "Q1"], ["East", "11"]]),
            r304_draw_text(60, 770, "Page two narration line.")
            + r304_draw_table(60, 700, [["Item", "Qty"], ["Disk", "7"]]),
            r304_draw_text(60, 770, "Page three unique narration line."),
        ],
        tmp_path / "r304_three.pdf",
    )


def r304_forced_limit(monkeypatch, **limits):
    """让 loader 那一趟表格走按给定上限收口（上限本身是 R300 的常量，不在这里改）。"""
    real = R304_EXTRACT_DOCUMENT

    def _bounded(path, **call_limits):
        merged = dict(call_limits)
        merged.update(limits)
        return real(path, **merged)

    monkeypatch.setattr(loader.table_channel, "extract_document", _bounded)


def test_a_bounded_page_walk_says_so_through_the_loader_exit(tmp_path, monkeypatch, loader_logs):
    """判据⑤：页数收口时，触顶这件事必须从 loader 的出口看得见，而且正文一个字都不许多丢。"""
    path = r304_three_page_pdf(tmp_path)
    r304_forced_limit(monkeypatch, max_pages=1)

    with _quiet_parser_warnings():
        exit_ = loader.extract_pdf_with_tables(str(path))

    assert exit_.tables.tables >= 1
    assert exit_.tables.truncated.startswith("pages:"), exit_.tables.truncated
    notice = exit_.tables.truncated_notice
    assert "页数上限" in notice and "第 2-3 页" in notice, notice
    assert any(loader.TABLE_TRUNCATION_LOG_PREFIX in line for line in loader_logs.warnings), loader_logs.warnings
    assert "Page three unique narration line." in exit_.text, "触顶把未走到的页的正文一起丢了"
    assert "Page two narration line." in exit_.text
    assert exit_.text.count("| East | 11 |") == 1


def test_a_bounded_char_walk_and_a_bounded_word_document_say_so(tmp_path, monkeypatch, loader_logs):
    """判据⑤：字数收口（PDF）与枚数收口（DOCX）同样是看得见的截断。"""
    path = r304_three_page_pdf(tmp_path)
    r304_forced_limit(monkeypatch, max_chars=40)
    with _quiet_parser_warnings():
        pdf_exit = loader.extract_pdf_with_tables(str(path))
    assert pdf_exit.tables.truncated.startswith("chars:"), pdf_exit.tables.truncated
    assert "表格字数上限" in pdf_exit.tables.truncated_notice
    assert any(loader.TABLE_TRUNCATION_LOG_PREFIX in line for line in loader_logs.warnings)

    docx = r304_write_docx(
        tmp_path / "r304_many.docx",
        [
            ("p", "三枚表的说明。"),
            ("t", [["科目", "金额"], ["差旅", "1"]]),
            ("t", [["科目", "金额"], ["招待", "2"]]),
            ("t", [["科目", "金额"], ["办公", "3"]]),
        ],
    )
    r304_forced_limit(monkeypatch, max_tables=2)
    docx_exit = loader.extract_docx_with_tables(str(docx))

    assert docx_exit.tables.tables == 2
    assert docx_exit.tables.truncated.startswith("tables:"), docx_exit.tables.truncated
    assert "表格枚数上限" in docx_exit.tables.truncated_notice
    assert "三枚表的说明。" in docx_exit.text
    assert "| 差旅 | 1 |" in docx_exit.text and "| 办公 | 3 |" not in docx_exit.text
    assert any(loader.TABLE_TRUNCATION_LOG_PREFIX in line for line in loader_logs.warnings[-1:])


def test_a_timed_out_walk_keeps_every_word_of_prose(tmp_path, monkeypatch, loader_logs):
    """判据⑤：时间预算收口（一枚表都没走到）时，正文必须仍是完整的今天的正文。"""
    path = r304_three_page_pdf(tmp_path)
    # 0.0 是刀口：同一台机器上跑出过 time:1of3 与完全不触顶两种结果。负预算把
    # 「时间这一档收口」变成确定事件，本条测的是 loader 的可见性，不是计时器本身。
    r304_forced_limit(monkeypatch, time_budget_s=-1.0)

    with _quiet_parser_warnings():
        exit_ = loader.extract_pdf_with_tables(str(path))

    assert exit_.tables.truncated.startswith("time:"), exit_.tables.truncated
    notice = exit_.tables.truncated_notice
    # 走到第几页才超时是计时器的事，这一枚测试不钉它（R300 也只钉前缀）
    assert "时间预算" in notice and re.search(r"第 \d+-3 页", notice), notice
    assert any(loader.TABLE_TRUNCATION_LOG_PREFIX in line for line in loader_logs.warnings)
    for line in ("Page one narration line.", "Page two narration line.", "Page three unique narration line."):
        assert exit_.text.count(line) == 1, line
    assert exit_.tables.tables <= 2
    if exit_.tables.tables == 0:
        assert exit_.tables.attached is False, "一枚表都没接到，这条不许装成接上了"


def test_every_truncation_kind_has_a_sentence():
    """判据⑤的口径钉子：四道上限各有一句话，没触顶时是空串。"""
    cases = {
        "pages:9of28": "页数上限",
        "time:9of28": "时间预算",
        "chars:3of9": "表格字数上限",
        "tables:200": "表格枚数上限",
    }
    for code, label in cases.items():
        report = loader.TableExtractionReport(source="pdf", truncated=code)
        assert label in report.truncated_notice, code
    assert loader.TableExtractionReport(source="pdf").truncated_notice == ""
    bounded = loader.TableExtractionReport(source="pdf", page_count=28, pages_scanned=9, truncated="pages:9of28")
    assert "第 10-28 页" in bounded.truncated_notice


# ------------------------------------------------------------------ 退化与递归账


def test_a_broken_table_channel_returns_todays_text_and_names_itself(tmp_path, loader_logs):
    """表格通道塌了只朝一个方向退化：回到今天的正文，并在账里写明原因，不许冒充「没有表」。"""
    with _quiet_parser_warnings():
        with pytest.raises(FileNotFoundError):
            loader.extract_pdf_with_tables("no-such-file.pdf")
    assert loader_logs.warnings == [], "解析本来就没成功，不该由表格通道冒出一句降级"

    good = r304_write_pdf(
        [r304_draw_text(60, 770, "Narration only line.")], tmp_path / "r304_plain.pdf"
    )
    with _quiet_parser_warnings():
        before = loader.extract_pdf_with_tables(str(good))
        import pdfplumber

        def _boom(*args, **kwargs):
            raise RuntimeError("表格解析器炸了")

        original = pdfplumber.open
        pdfplumber.open = _boom
        try:
            after = loader.extract_pdf_with_tables(str(good))
        finally:
            pdfplumber.open = original

    assert after.text == before.text, "退化那一腿改了正文"
    assert after.tables.degraded and "RuntimeError" in after.tables.degraded
    assert any(loader.TABLE_CHANNEL_LOG_PREFIX in line for line in loader_logs.warnings), loader_logs.warnings
    assert after.tables.tables == 0


def test_the_wiring_asks_the_loader_for_its_prose_exactly_once(tmp_path):
    """递归账：0 表时 tables 回调 load_pdf 一次（一层，不回头）；有表时一次都不回调。"""
    calls: list[str] = []
    real = tables.pdf_prose_via_loader

    def _counting(path):
        calls.append(str(path))
        return real(path)

    tables.pdf_prose_via_loader = _counting
    try:
        tableless = r304_write_pdf([r304_draw_text(60, 770, "Only prose here.")], tmp_path / "r304_none.pdf")
        with _quiet_parser_warnings():
            loader.load_pdf(str(tableless))
        assert calls == [str(tableless)], f"0 表的回调次数不对：{calls}"

        calls.clear()
        bearing = r304_write_pdf(
            [r304_draw_table(60, 700, [["Region", "Q1"], ["East", "11"]])], tmp_path / "r304_one.pdf"
        )
        with _quiet_parser_warnings():
            loader.load_pdf(str(bearing))
        assert calls == [], f"有表的文档不该回调今天的正文：{calls}"
    finally:
        tables.pdf_prose_via_loader = real


# ------------------------------------------------------------------ ⑦ 纪律


def test_the_tables_module_is_still_the_bytes_r300_shipped():
    """判据⑦：app/rag/tables.py 一个字节都不许改。"""
    digest = hashlib.sha256((REPO_ROOT / "app" / "rag" / "tables.py").read_bytes()).hexdigest()

    assert digest == TABLES_SHA256, f"tables.py 被改过：{digest}"


def test_the_wiring_adds_no_dependency():
    """判据⑦：接线只许用仓里已有的东西，pdfplumber 继续只从 tables.py 进来。"""
    import ast

    tree = ast.parse((REPO_ROOT / "app" / "rag" / "loader.py").read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])

    allowed = {"app", "contextlib", "dataclasses", "docx", "olefile", "os", "pathlib", "pypdf", "threading"}
    assert roots == allowed, roots
    source = (REPO_ROOT / "app" / "rag" / "loader.py").read_text(encoding="utf-8")
    for token in ("import pdfplumber", "import camelot", "import img2table", "from pdf2image"):
        assert token not in source, f"接线把 {token} 直接引进 loader 了"
