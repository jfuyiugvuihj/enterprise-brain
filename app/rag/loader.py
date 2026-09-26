"""
Unified document loader for PDF / DOCX / DOC / TXT / Markdown.

R130: every loader below ends in :func:`sanitize_text`, because pypdf really does hand
back a NUL character (measured in documents/AI-Agent学习路线图.pdf) and a PostgreSQL
text column cannot hold one.

R298: PDF 不再只有文本层这一条腿。逐页判定"这页是扫描页"（判据①），扫描页交给
本地 OCR 通道（app/rag/ocr.py，判据②），有文本层的页一个字都不再 OCR（判据④）。OCR
出来的文字与 pypdf 交回的文字过的是**同一个** :func:`sanitize_text`（判据⑤）—— PG 那一腿
对 NUL 的拒绝与它从哪条通道来无关。
"""
import os
from dataclasses import dataclass, replace
from pathlib import Path

from pypdf import PdfReader

from app.common.logger import logger
from app.rag import ocr as ocr_channel

#: U+0000 -- the one character a PostgreSQL ``text`` column refuses, and therefore the
#: one character this module drops. psycopg only complains about it from inside
#: ``executemany``, by which point the batch has no document name left to report, so
#: the drop belongs here, at the edge where a third-party parser stops being our problem.
#: The mirror in app/rag/pg_store.py keeps its own gate for anything arriving by another
#: route: two layers, each doing its own job.
NUL_CHARACTER = "\x00"


def sanitize_text(text: str) -> str:
    """Drop NUL characters and nothing else.

    Deliberately surgical (R130 判据①): whitespace, blank lines, emoji, letter case and
    every other control character belong to the document, so they leave unchanged. A text
    without NUL comes back byte-identical, which is what keeps the already-indexed corpus
    (R130 判据④: 985 chunks, none of them dirty) untouched by this ticket.
    """
    if NUL_CHARACTER not in text:
        return text
    return text.replace(NUL_CHARACTER, "")


# ==================== 扫描页判定（判据①） ====================

#: 一页"文本层实质字符"（去掉全部空白后计数）少于这么多，**且**该页存在图像对象，才判为
#: 扫描页。两个条件缺一不可：只看字符数会把空白页/纯矢量图页猜成扫描页，只看图像会把
#: "正文 + 一张插图"的数字页整个重跑一遍 OCR（判据④）。
#:
#: 这个数是量出来的，不是拍的。2026-09-26 在本树 documents/ 现取（pypdf 逐页抽文本、去空白
#: 计数，脚本在仓库外，未改任何生产数据）：
#:   - ``documents/AI-Agent学习路线图.pdf`` 8 页 = 754/957/939/829/937/973/832/942；
#:   - ``documents/refactor_guide.pdf`` 28 页，最小 79、中位 641、最大 1,342；
#:   - 两本合计 36 页，**空文本层 0 页** ⇒ 真·数字 PDF 的实测下沿是 79 个字符。
#: 扫描页一侧：纯图件实测 0 字符（``tests/fixtures/r298_scanned_pages.pdf``），带垃圾隐形
#: 文本层的扫描件通常只剩页码或水印一行（1-20 字符）。48 卡在"一行中文正文"以下、实测下沿
#: 79 以上，两侧都留了余量；客户机要收紧/放宽走 PDF_SCANNED_PAGE_TEXT_CHARS。
SCANNED_PAGE_TEXT_CHARS = 48

#: 运维覆盖入口（与 app/documents/index_policy.py 的 DOCUMENT_INDEX_MIN_CHARS 同风格：
#: **调用期**读环境变量，不在 import 期固化，避开 conftest R70 那一段坑）。
SCANNED_PAGE_TEXT_CHARS_ENV = "PDF_SCANNED_PAGE_TEXT_CHARS"

#: 判据④：来源要逐页记，不许整件二选一。五个态各自可核对。
PAGE_SOURCE_TEXT_LAYER = "text-layer"
PAGE_SOURCE_OCR = "ocr"
PAGE_SOURCE_OCR_EMPTY = "ocr-empty"
PAGE_SOURCE_OCR_DEGRADED = "ocr-degraded"
PAGE_SOURCE_BLANK = "blank"

#: 跟进 ``page_has_image_object``：位图常包在 Form XObject 里，往下一层查，再多不查。
FORM_XOBJECT_DEPTH_LIMIT = 1

#: 判据⑥"降级句"的前缀。测试按它钉"出降级句而非空文本"。
DEGRADATION_NOTE_PREFIX = "扫描页 OCR 降级"


def scanned_page_text_char_threshold() -> int:
    """扫描页判定的字符阈值（环境变量优先，非法值退回常量并 WARNING）。"""
    raw = (os.getenv(SCANNED_PAGE_TEXT_CHARS_ENV) or "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            logger.warning(f"[PDF] 忽略 {SCANNED_PAGE_TEXT_CHARS_ENV}={raw!r}（不是整数）")
    return SCANNED_PAGE_TEXT_CHARS


def _resolve_pdf_object(value):
    """IndirectObject -> 真身；已经是真身就原样返回。"""
    getter = getattr(value, "get_object", None)
    return getter() if callable(getter) else value


def _lookup_pdf_key(node, key: str):
    """读一个字典键，读不到返回 ``None``。

    这一层同时挡住"页对象根本是个鸭子"的情况：``tests/test_document_upload_resilience.py``
    的 FakePage 只有 ``extract_text``，没有 ``get``，走的就是这条返回 ``None`` 的分支。
    """
    getter = getattr(node, "get", None)
    if not callable(getter) or node is None:
        return None
    try:
        return _resolve_pdf_object(getter(key))
    except Exception as exc:  # noqa: BLE001 - 探测失败不是解析失败
        logger.debug(f"[PDF] 读 {key} 失败，按未判定处理：{type(exc).__name__}: {exc}")
        return None


def _mapping_items(node) -> list:
    getter = getattr(node, "items", None)
    if not callable(getter):
        return []
    try:
        return list(getter())
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[PDF] 展开 XObject 失败：{type(exc).__name__}: {exc}")
        return []


def page_has_image_object(page) -> bool:
    """这页的资源树里有没有位图对象（``/Subtype /Image``）。

    只认位图，不认"Form 里画了什么"：判据① 要的是"这一页是一张图"。位图常被扫描驱动包在
    Form XObject 里，所以往下一层查（``FORM_XOBJECT_DEPTH_LIMIT``），再多不查——深度无上限
    的递归会给一张构造怪异的 PDF 把上传线程拖住。

    探测不出结果时返回 ``False``，方向是刻意选的：漏一页 OCR 只是回到今天的结局，而猜一页
    "有图"再把它的文本层重跑一遍 OCR，就是判据④ 点名的双份正文。
    """
    stack: list[tuple[object, int]] = [(page, 0)]
    while stack:
        node, depth = stack.pop()
        resources = _lookup_pdf_key(node, "/Resources")
        xobjects = _lookup_pdf_key(resources, "/XObject")
        for _name, raw_entry in _mapping_items(xobjects):
            entry = _resolve_pdf_object(raw_entry)
            subtype = str(_lookup_pdf_key(entry, "/Subtype") or "")
            if subtype == "/Image":
                return True
            if subtype == "/Form" and depth < FORM_XOBJECT_DEPTH_LIMIT:
                stack.append((entry, depth + 1))
    return False


def _text_layer_char_count(text: str) -> int:
    """文本层"实质字符"数：全部空白不计，其余一个字算一个（与阈值同一口径）。"""
    return len("".join(text.split()))


@dataclass(frozen=True)
class PdfPageExtraction:
    """一页的提取账（判据①④）：判了什么、用了哪条通道、为什么。"""

    page_number: int  # 1-based，人读的页码
    source: str  # PAGE_SOURCE_* 之一
    text: str  # 进入正文的文本（可能为空）
    text_layer_chars: int  # 判据① 左半边：该页文本层实质字符数
    has_image_object: bool  # 判据① 右半边：该页有没有位图对象
    is_scanned: bool
    note: str = ""  # 降级原因 / "图里没字"，正常页为空
    ocr_elapsed_ms: float = 0.0
    raster_size: tuple[int, int] = (0, 0)


@dataclass(frozen=True)
class PdfExtractionReport:
    """一份 PDF 的提取总账。``load_document`` 只要 ``text``，这一份是给排查用的。"""

    file_path: str
    page_count: int
    pages: tuple[PdfPageExtraction, ...]
    text: str
    ocr_dpi: int
    ocr_engine: str
    ocr_attempted: bool
    #: 本轮 OCR 通道是否可用。``False`` 时降级句走"引擎不可用"那一档措辞，
    #: 与"引擎在、只是这一页没跑成（超上限 / 栅格化炸）"区分开。
    ocr_available: bool = True

    @property
    def scanned_page_numbers(self) -> tuple[int, ...]:
        return tuple(page.page_number for page in self.pages if page.is_scanned)

    @property
    def scanned_pages(self) -> int:
        return len(self.scanned_page_numbers)

    @property
    def source_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for page in self.pages:
            counts[page.source] = counts.get(page.source, 0) + 1
        return counts

    @property
    def degradation_notes(self) -> tuple[str, ...]:
        return tuple(
            f"第{page.page_number}页：{page.note}" for page in self.pages if page.source == PAGE_SOURCE_OCR_DEGRADED
        )

    @property
    def degradation_sentence(self) -> str:
        """一句能直接给客户看的降级说明；没有降级时空串（判据②⑥）。"""
        notes = self.degradation_notes
        if not notes:
            return ""
        head = DEGRADATION_NOTE_PREFIX if self.ocr_available else ocr_channel.ENGINE_UNAVAILABLE_NOTE
        return f"{head}：{'；'.join(notes)}"

    def summary(self) -> str:
        """判据① 要求的口径：扫描页数 / 总页数，外加每页来源。"""
        sources = " ".join(f"{name}={count}" for name, count in sorted(self.source_counts.items()))
        return (
            f"pages={self.page_count} scanned={self.scanned_pages}/{self.page_count} "
            f"scanned_pages={list(self.scanned_page_numbers)} dpi={self.ocr_dpi} [{sources}]"
        )


def extract_pdf(
    file_path: str,
    *,
    dpi: int | None = None,
    enable_ocr: bool = True,
    engine=None,
    include_degradation_note: bool = False,
) -> PdfExtractionReport:
    """逐页抽取一份 PDF：文本层照旧，扫描页走本地 OCR 通道（R298）。

    两条通道的分工按页定，不按件定（判据④）：有文本层的页**一个字都不再 OCR**，双份正文
    等于双份墓碑 + 双份近重复命中 —— R269 刚实测过近重复把 Chroma ``ef_search=100`` 的候选
    预算吃光（240 探针 miss 23），检索面不为这种重复买单。

    ``include_degradation_note`` 默认 ``False``：降级说明进 ``report.degradation_sentence``
    与 WARNING 日志，**不默认进正文**，因为那句"本页未能识别文字"会被切块、被 embedding、
    被检索命中，正是要避免的那类墓碑。要它进正文的调用方自己承担后果（测试钉住了两态）。
    """
    reader = PdfReader(file_path)
    pages = list(reader.pages)
    threshold = scanned_page_text_char_threshold()

    probed: list[tuple[int, str, int, bool, bool]] = []
    for index, page in enumerate(pages, start=1):
        layer_text = (page.extract_text() or "").strip()
        chars = _text_layer_char_count(layer_text)
        has_image = page_has_image_object(page)
        probed.append((index, layer_text, chars, has_image, chars < threshold and has_image))

    scanned_numbers = [number for number, _t, _c, _h, is_scanned in probed if is_scanned]
    ocr_by_page: dict[int, ocr_channel.OcrPageOutcome] = {}
    ocr_dpi = ocr_channel.resolve_dpi(dpi)
    ocr_available = True
    if scanned_numbers and enable_ocr:
        run = ocr_channel.ocr_pages(file_path, scanned_numbers, dpi=ocr_dpi, engine=engine)
        ocr_dpi = run.dpi
        ocr_available = run.available
        ocr_by_page = {outcome.page_number: outcome for outcome in run.outcomes}

    records: list[PdfPageExtraction] = []
    parts: list[str] = []
    for number, layer_text, chars, has_image, is_scanned in probed:
        note = ""
        elapsed = 0.0
        raster: tuple[int, int] = (0, 0)
        if not is_scanned:
            source = PAGE_SOURCE_TEXT_LAYER if layer_text else PAGE_SOURCE_BLANK
            body = layer_text
            if not layer_text and not has_image:
                note = "该页既无文本层也无图像对象"
        else:
            outcome = ocr_by_page.get(number)
            if outcome is None:
                source = PAGE_SOURCE_OCR_DEGRADED
                body = layer_text
                note = "扫描页未送 OCR（本次调用关闭了 OCR 通道）"
            elif outcome.ok and outcome.status == ocr_channel.STATUS_RECOGNIZED:
                # 判据⑤：OCR 通道出来的文字过同一个 sanitize_text（R130 那一刀）。
                # 整件在收尾还会再过一次，这里是"谁产出谁负责"，不是重复劳动。
                body = sanitize_text(outcome.text).strip()
                elapsed = outcome.elapsed_ms
                raster = outcome.raster_size
                # 净化后一个字都不剩（整页只有一枚 NUL 这种形状）不能算"OCR 出来了"：
                # 不变量是 source=ocr ⇒ 这一页真的往正文里放了字。
                source = PAGE_SOURCE_OCR if body else PAGE_SOURCE_OCR_EMPTY
                if not body:
                    note = "OCR 文字经 sanitize_text 后为空"
                else:
                    note = ""
            elif outcome.ok:
                source = PAGE_SOURCE_OCR_EMPTY
                body = layer_text
                note = "图像页 OCR 未检出文字"
                elapsed = outcome.elapsed_ms
                raster = outcome.raster_size
            else:
                source = PAGE_SOURCE_OCR_DEGRADED
                body = layer_text
                note = outcome.reason or outcome.status
                elapsed = outcome.elapsed_ms
                raster = outcome.raster_size
        if body:
            parts.append(body)
        records.append(
            PdfPageExtraction(
                page_number=number,
                source=source,
                text=body,
                text_layer_chars=chars,
                has_image_object=has_image,
                is_scanned=is_scanned,
                note=note,
                ocr_elapsed_ms=elapsed,
                raster_size=raster,
            )
        )

    text = sanitize_text("\n\n".join(parts).strip())
    report = PdfExtractionReport(
        file_path=file_path,
        page_count=len(pages),
        pages=tuple(records),
        text=text,
        ocr_dpi=ocr_dpi,
        ocr_engine=ocr_channel.OCR_ENGINE_MODULE,
        ocr_attempted=bool(scanned_numbers) and enable_ocr,
        ocr_available=ocr_available,
    )
    if include_degradation_note:
        sentence = report.degradation_sentence
        if sentence:
            report = replace(report, text=sanitize_text("\n\n".join(item for item in (text, sentence) if item)))
    logger.info(f"Extracted PDF: {file_path} | {report.summary()}")
    for line in report.degradation_notes:
        logger.warning(f"[PDF] OCR 降级: {file_path} {line}")
    return report


def load_pdf(
    file_path: str,
    *,
    dpi: int | None = None,
    enable_ocr: bool = True,
    engine=None,
    include_degradation_note: bool = False,
) -> str:
    """抽取 PDF 正文：本地 pypdf 文本层 + 本地 OCR 扫描页（判据②：不联网、不上云）。

    出口再过一次 :func:`sanitize_text` —— R130 的不变量是"每一个 load_* 出口都过同一把
    尺"（``tests/test_r130_text_unencodable_is_named_refusal.py`` 按源码钉这条），尺在
    ``extract_pdf`` 里已经落过两次（OCR 通道一次、整件收尾一次），这里是第三个出口口径，
    对不含 NUL 的文本是恒等，不多改一个字符。
    """
    report = extract_pdf(
        file_path,
        dpi=dpi,
        enable_ocr=enable_ocr,
        engine=engine,
        include_degradation_note=include_degradation_note,
    )
    return sanitize_text(report.text)


def load_docx(file_path: str) -> str:
    """Extract plain text from .docx."""
    from docx import Document

    doc = Document(file_path)
    return sanitize_text("\n".join(p.text for p in doc.paragraphs if p.text.strip()))


def load_doc(file_path: str) -> str:
    """Best-effort extraction for old .doc files."""
    import olefile

    ole = olefile.OleFileIO(file_path)
    if ole.exists("WordDocument"):
        stream = ole.openstream("WordDocument")
        raw = stream.read()
        text = "".join(chr(b) for b in raw if 31 < b < 127 or b in (10, 13))
        lines = [line.strip() for line in text.split("\n") if len(line.strip()) > 2]
        ole.close()
        return sanitize_text("\n".join(lines))
    ole.close()
    return ""


def load_txt(file_path: str) -> str:
    """Read TXT with automatic encoding detection."""
    for encoding in ["utf-8", "gbk", "gb2312"]:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                return sanitize_text(f.read())
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Unable to detect text encoding: {file_path}")


def load_md(file_path: str) -> str:
    """Read Markdown as plain source text, reusing TXT encoding detection."""
    return sanitize_text(load_txt(file_path))


def load_document(file_path: str) -> str:
    """Auto-detect file type and return plain text."""
    ext = Path(file_path).suffix.lower()
    logger.info(f"Loading document: {file_path} ({ext})")

    if ext == ".pdf":
        return sanitize_text(load_pdf(file_path))
    if ext == ".docx":
        return sanitize_text(load_docx(file_path))
    if ext == ".doc":
        return sanitize_text(load_doc(file_path))
    if ext == ".txt":
        return sanitize_text(load_txt(file_path))
    if ext == ".md":
        return sanitize_text(load_md(file_path))
    raise ValueError(f"Unsupported file format: {ext}")
