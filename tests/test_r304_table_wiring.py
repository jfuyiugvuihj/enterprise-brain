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
⑦ 零新增依赖、tables.py 一个字节都不许改 -> test_no_new_dependency_*、test_the_tables_module_is_still_*
   （R352 甲案：这一格从「手抄一枚 hex」改成「派生自记名锚点提交」，另加四条腿 ->
   test_no_commit_after_the_anchor_*、test_the_anchor_*、test_the_ruler_measures_the_git_blob_layer_*；
   牙：不挪锚点的新提交红、锚点挪到不含该改动的提交红、checkout 层与 blob 层混比红）。

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
import subprocess
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

# ---------------------------------------------------------------- 判据⑦ 的账（R352 甲案：派生 + 记名锚点）
#
# 旧账长这样（R304 原钉）：
#     TABLES_SHA256 = "7acaa33c0568e8eec13c992823a55dbf134d3f7f870ecacc6c73ff011b4266dd"
#     digest = hashlib.sha256((REPO_ROOT / "app" / "rag" / "tables.py").read_bytes()).hexdigest()
# 那是一枚**手抄的十六进制**。R331（提交 58111c9：表格装箱预算按实发预留）合法改了
# app/rag/tables.py，改的人没重录，账就烂在这枚钉上 —— 钉红的是别人的合法改动，门跟着红
# （主树实测 1 failed / 20 passed）。手抄指纹的毛病从来不是"抄错了"，是"抄完那一瞬之后
# 没有任何人欠你一次重抄"。
#
# 甲案的改法：期望值不再手抄，而是**现算** `git show <锚点提交>:app/rag/tables.py` 的摘要。
# 锚点的语义写在名字旁边：**最后一次有意改动 tables.py 的那枚提交**。谁再改它，就把这枚具名
# 常量往前挪到自己那枚提交上 —— 重录从"改一串别人看不懂的数字"变成"指名道姓说清是谁改的"，
# 可审；而不挪锚点的改动照样当场红（两条腿：盘上一枚、树里一枚）。
#
# 🔴 比的是哪一层（本机实测，别猜）：本仓 core.autocrlf=true 且没有 .gitattributes ⇒
#   工作树 = CRLF：app/rag/tables.py 实测 40601 bytes / 968 枚 CRLF / 0 枚孤立 CR；
#   git blob = LF：同一枚内容在树里实测 39633 bytes / 0 枚 CR。
#   两层摘要实测不同：blob 层 27e697d90ba0b300…，checkout 层 e13a2878654c302b…
#   ⇒ 裸比字节必假红。本件一律按 **git blob 层（LF）** 比：盘上那份先换算回 blob 层再取摘要。
#   顺带把旧账的来源钉死（这就是为什么换层不是多此一举）：7acaa33c… 正是 R300 那枚 blob 被
#   checkout 成 CRLF 之后的摘要，sha256(git show 72a9bdc:app/rag/tables.py → CRLF) 实测等于它
#   —— 旧钉记的是 checkout 层，换到 blob 层之后 Linux / autocrlf=input / 容器里 checkout
#   成 LF 的机器读出的是同一个数。
TABLES_BLOB_PATH = "app/rag/tables.py"

#: 锚点提交 = 最后一次**有意**改动 tables.py 那枚文件（R331：表格装箱预算按实发预留）。
TABLES_ANCHOR_SHA = "58111c9"
#: 漂移对照锚（判据③）：R300 初次进树那枚，**不含** R331 的改动。用来证明锚点是被读的。
TABLES_PRE_ANCHOR_SHA = "72a9bdc"
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


def r304_git_blob(rev, rel=TABLES_BLOB_PATH):
    """取 **git blob 层**的字节：`git show <rev>:<rel>`，按仓根定位，与工作树行尾无关。"""
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "show", "%s:%s" % (rev, rel)],
        capture_output=True, cwd=str(REPO_ROOT),
    )
    assert out.returncode == 0, (
        "git show %s:%s 读不到（判据⑦ 的期望值是从提交里派生的，这枚件要读 git 历史）：%s"
        % (rev, rel, (out.stdout + out.stderr).decode("utf-8", "replace")[-200:])
    )
    return out.stdout


def r304_blob_layer(raw):
    """把 checkout 落盘的字节换算回 blob 层：CRLF -> LF，并且拒绝"第三种行尾"混进来。"""
    lf = raw.replace(b"\r\n", b"\n")
    assert b"\r" not in lf, "工作树里有孤立的 CR（既不是 CRLF 也不是 LF）：这层换算的前提没了"
    return lf


def r304_tables_digest_at(rev):
    """锚点/HEAD/对照提交那一枚 tables.py 的 blob 层摘要（现算，不抄）。"""
    return hashlib.sha256(r304_git_blob(rev)).hexdigest()


def r304_tables_digest_on_disk():
    """盘上那份的 blob 层摘要 —— 判据⑦ 比的两个数都出自这一层。"""
    return hashlib.sha256(r304_blob_layer((REPO_ROOT / TABLES_BLOB_PATH).read_bytes())).hexdigest()


def r304_git(*args):
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace", cwd=str(REPO_ROOT),
    )
    assert out.returncode == 0, "git %s 失败：%s" % (" ".join(args), (out.stdout + out.stderr)[-200:])
    return out.stdout


def test_the_tables_module_is_still_the_bytes_the_anchor_shipped():
    """判据⑦：盘上这份 tables.py 必须逐字节等于**记名锚点提交**交出的那一份（blob 层）。

    与旧钉同强度、不同出身：旧钉拿 read_bytes() 比一串手抄 hex，这枚拿"换算回 blob 层的盘上
    字节"比"从锚点提交现算的字节"。R331 之后 tables.py 又被人改了一枚而不挪锚点 ⇒ 当场红。
    """
    expected = r304_tables_digest_at(TABLES_ANCHOR_SHA)
    actual = r304_tables_digest_on_disk()
    assert actual == expected, (
        "app/rag/tables.py 与锚点提交 %s 不等（盘上 blob 层 %s != 锚点 %s）。两条路二选一："
        "① 这次改动是有意的 ⇒ 把 TABLES_ANCHOR_SHA 往前挪到你那枚提交（顺手在上面的注释里写清"
        "是谁改的、为什么）；② 这次改动不是本单授权的 ⇒ 先 git status --porcelain 取证再还原。"
        "🔴 不许就地重录一枚今天的 hex：那只是把这枚钉的寿命续到下一次改动。"
        % (TABLES_ANCHOR_SHA, actual[:16], expected[:16])
    )


def test_no_commit_after_the_anchor_has_touched_the_tables_module():
    """第二条腿盯**树里**：HEAD 那枚 blob 也必须还是锚点那份。

    两枚腿各堵一种形状：上面那枚堵"工作树被改了没还原"（R339 那一族事故：摘刀留在盘上），
    这一枚堵"提交了改动却不挪锚点"——后者在有人 checkout 回干净工作树时仍要红。
    """
    head = r304_tables_digest_at("HEAD")
    anchor = r304_tables_digest_at(TABLES_ANCHOR_SHA)
    assert head == anchor, (
        "HEAD 里的 app/rag/tables.py（%s）已经不是锚点提交 %s 那一份（%s）了：动它的提交没被记名。"
        "把 TABLES_ANCHOR_SHA 改成那枚提交，别改判据。" % (head[:16], TABLES_ANCHOR_SHA, anchor[:16])
    )


def test_the_anchor_is_read_not_decorated():
    """判据③：派生不许变成同义反复 —— 锚点换成不含该改动的提交，必须读出另一个数。

    TABLES_PRE_ANCHOR_SHA（72a9bdc，R300 初次进树）交的 tables.py **不含** R331 的装箱预留。
    今天有人图省事把锚点写成它，第一枚钉当场红；这枚钉把那件事预先演一遍：它自己绿就说明
    "两枚提交读出来是两个数、而盘上那份等于锚点那枚"——锚点在被读，不是装饰。
    """
    pre = r304_tables_digest_at(TABLES_PRE_ANCHOR_SHA)
    anchor = r304_tables_digest_at(TABLES_ANCHOR_SHA)
    assert pre != anchor, (
        "锚点与对照提交读出同一个数（%s）：派生腿根本没读那枚提交 ⇒ 判据⑦ 已经变成同义反复" % pre[:16]
    )
    assert anchor == r304_tables_digest_on_disk(), "锚点读出的数与盘上那份不等：第一枚钉的理由在这儿也得成立"


def test_the_anchor_commit_really_is_the_one_that_changed_the_file():
    """锚点不许是一枚"内容碰巧相同"的提交：它得真在树上、真改过这枚文件。"""
    ancestor = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "merge-base", "--is-ancestor", TABLES_ANCHOR_SHA, "HEAD"],
        capture_output=True, cwd=str(REPO_ROOT),
    )
    assert ancestor.returncode == 0, "锚点 %s 不在 HEAD 的祖先链上：这枚提交没进树" % TABLES_ANCHOR_SHA
    listed = {line.strip().replace("\\", "/") for line in
              r304_git("show", "--pretty=format:", "--name-only", TABLES_ANCHOR_SHA).splitlines() if line.strip()}
    assert TABLES_BLOB_PATH in listed, (
        "锚点 %s 的提交清单里没有 %s：它不是那枚「有意改动」，指名指错了人" % (TABLES_ANCHOR_SHA, TABLES_BLOB_PATH)
    )
    assert r304_tables_digest_at(TABLES_ANCHOR_SHA) != r304_tables_digest_at(TABLES_ANCHOR_SHA + "^"), (
        "锚点交出的 tables.py 与它的父提交相同：这枚提交没动过它，不配当「最后一次有意改动」"
    )


def test_the_ruler_measures_the_git_blob_layer_not_the_checkout():
    """钉死"比的是哪一层"：blob 层恒 LF；本机 checkout 层是 CRLF ⇒ 两层摘要必然不同。

    本仓 core.autocrlf=true 且没有 .gitattributes（实测 git config 读出 true，仓库根没有
    .gitattributes）。哪天有人给这枚件加"直接 read_bytes() 跟 git show 比"的写法，这枚先红：
    它量的是不同层。反之，若这台机器 checkout 成了 LF（autocrlf=input），枚内那条 if 自动不
    触发 —— 判据不依赖某台机器的行尾，只依赖"比的是 blob 层"这一条。
    """
    raw = (REPO_ROOT / TABLES_BLOB_PATH).read_bytes()
    blob = r304_git_blob(TABLES_ANCHOR_SHA)
    assert b"\r" not in blob, "锚点那枚 blob 里出现了 CR：git blob 层应当恒 LF，本件的层口径变了"
    assert r304_blob_layer(raw) == blob, "盘上那份换算到 blob 层以后与锚点不同：见第一枚钉的处置说明"
    if b"\r\n" in raw:
        assert hashlib.sha256(raw).hexdigest() != hashlib.sha256(blob).hexdigest(), (
            "工作树明明有 CRLF，checkout 层与 blob 层却读出同一个数：这枚层口径钉量不到东西了"
        )


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
